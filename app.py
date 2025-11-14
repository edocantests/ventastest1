# app.py
import streamlit as st
import re
import json
from youtube_transcript_api import YouTubeTranscriptApi
from urllib.parse import urlparse, parse_qs
import google.generativeai as genai

st.set_page_config(page_title="YouTube → Teachings JSON (Gemini)", layout="centered")

st.title("Extraer enseñanzas de YouTube → JSON (Gemini)")
st.markdown("Pega enlaces de YouTube (uno por línea) y presiona **Procesar**.")

# Inputs
urls_text = st.text_area("Enlaces de YouTube (uno por línea)", height=150)

prompt_custom = st.text_area(
    "Prompt para Gemini",
    height=140,
    value=(
        "Eres un experto educativo. Lee esta transcripción de un video y extrae las "
        "enseñanzas o lecciones prácticas. Para cada enseñanza devuelve: id, resumen corto, "
        "explicación detallada, timestamps si aplican, citas relevantes, e 'importancia' (1-5). "
        "Responde SOLO en JSON válido siguiendo el schema."
    )
)

api_key = st.text_input("Tu Google API Key (de Google AI Studio)", type="password")

process = st.button("Procesar enlaces")


# ---------------------------
# Helper: extract video ID
# ---------------------------
def extract_video_id(url):
    try:
        parsed = urlparse(url.strip())
        if parsed.hostname in ["youtu.be"]:
            return parsed.path.lstrip("/")
        if "youtube" in parsed.hostname:
            qs = parse_qs(parsed.query)
            return qs.get("v", [None])[0]
    except:
        return None
    return None


# ---------------------------
# Helper: obtener transcripción
# ---------------------------
def fetch_transcript(video_id):
    try:
        data = YouTubeTranscriptApi.get_transcript(video_id, languages=["es", "en"])
        full_text = " ".join(seg["text"] for seg in data)
        return full_text, data
    except Exception as e:
        return None, str(e)


# ---------------------------
# Construir prompt final
# ---------------------------
def build_prompt_for_transcript(transcript, url):
    return (
        f"{prompt_custom}\n\n"
        f"URL: {url}\n\n"
        f"TRANSCRIPCIÓN:\n{transcript}\n\n"
        f"Devuelve JSON válido."
    )


# ---------------------------
# Llamada a Gemini
# ---------------------------
def call_gemini(api_key, prompt, model_name="gemini-1.5-flash"):
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(model_name)
    response = model.generate_content(prompt)
    return response.text


# ---------------------------
# Procesamiento principal
# ---------------------------
if process:
    if not urls_text.strip():
        st.error("Pega al menos un enlace.")
    elif not api_key:
        st.error("Debes pegar tu API key de Google.")
    else:
        urls = [u.strip() for u in urls_text.splitlines() if u.strip()]
        results = []
        st.info(f"Procesando {len(urls)} enlaces...")

        for i, url in enumerate(urls, start=1):
            st.write(f"({i}/{len(urls)}) {url}")

            vid = extract_video_id(url)
            if not vid:
                st.warning(f"No se pudo extraer el ID del video: {url}")
                continue

            transcript, meta = fetch_transcript(vid)
            if not transcript:
                st.warning(f"No pude obtener la transcripción del video {vid}. Error: {meta}")
                continue

            prompt = build_prompt_for_transcript(transcript, url)

            try:
                ai_out = call_gemini(api_key, prompt)

                try:
                    parsed = json.loads(ai_out)
                except Exception:
                    m = re.search(r"(\{.*\}|\[.*\])", ai_out, re.DOTALL)
                    if m:
                        parsed = json.loads(m.group(1))
                    else:
                        parsed = {"error_parsing": ai_out}

                results.append(
                    {
                        "video_id": vid,
                        "url": url,
                        "extracted": parsed,
                    }
                )

            except Exception as e:
                st.error(f"Error llamando a Gemini: {e}")

        final_json = {"results": results}

        st.json(final_json)
        st.download_button(
            "Descargar JSON",
            json.dumps(final_json, ensure_ascii=False, indent=2),
            file_name="teachings.json",
            mime="application/json",
        )
