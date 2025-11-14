# app.py
import streamlit as st
import re
import json
from youtube_transcript_api import YouTubeTranscriptApi
import openai
from urllib.parse import urlparse, parse_qs

st.set_page_config(page_title="YouTube -> Teachings JSON", layout="centered")

st.title("Extraer enseñanzas de YouTube → JSON")
st.markdown("Pega enlaces de YouTube (uno por línea), ajusta el prompt si quieres, y pulsa `Procesar`.")

# Input
urls_text = st.text_area("Enlaces de YouTube (uno por línea)", height=150)
prompt_custom = st.text_area("Prompt para el modelo (déjalo si quieres usar el predeterminado)", height=140, value=(
    "Eres un experto educativo. Lee esta transcripción de un video y extrae las *enseñanzas* "
    "o lecciones prácticas. Para cada enseñanza devuelve: id, resumen corto (español), "
    "explicación más larga, timestamps sugeridos (si hay), citas textuales relevantes (si las hay), "
    "y un campo 'importancia' del 1 al 5. Responde **solo** con JSON que cumpla el schema indicado."
))
model_choice = st.selectbox("Proveedor de LLM", ["openai (API key requerida)","(por defecto) openai"])
api_key = st.text_input("Tu API key (será guardada como secreto en Streamlit mientras la app corre)", type="password")

process = st.button("Procesar enlaces")

# Helper: get video id
def extract_video_id(url):
    # works for youtu.be and youtube.com/watch?v=
    try:
        parsed = urlparse(url.strip())
        if parsed.hostname in ["youtu.be"]:
            return parsed.path.lstrip('/')
        if 'youtube' in parsed.hostname:
            qs = parse_qs(parsed.query)
            return qs.get('v', [None])[0]
    except Exception:
        return None
    return None

# get transcript
def fetch_transcript(video_id):
    try:
        data = YouTubeTranscriptApi.get_transcript(video_id, languages=['es','en'])
        # data is list of {'text':..., 'start':..., 'duration':...}
        full_text = " ".join(seg['text'] for seg in data)
        return full_text, data
    except Exception as e:
        return None, str(e)

# Build schema for each video
def build_prompt_for_transcript(transcript, url):
    return f"{prompt_custom}\n\nURL: {url}\n\nTRANSCRIPCIÓN:\n{transcript}\n\nDevuelve JSON válido."

# Call OpenAI
def call_openai(api_key, prompt, model="gpt-4o-mini"):
    import openai as _openai
    _openai.api_key = api_key
    messages = [
        {"role":"system","content":"Eres un asistente que extrae enseñanzas y devuelve JSON estricto."},
        {"role":"user","content": prompt}
    ]
    resp = _openai.ChatCompletion.create(model=model, messages=messages, temperature=0.1, max_tokens=1500)
    text = resp['choices'][0]['message']['content']
    return text

if process:
    if not urls_text.strip():
        st.error("Pega al menos un enlace.")
    elif "openai" in model_choice and not api_key:
        st.error("Para usar OpenAI necesitas pegar tu API key.")
    else:
        urls = [u.strip() for u in urls_text.splitlines() if u.strip()]
        results = []
        st.info(f"Procesando {len(urls)} enlaces...")
        for i, url in enumerate(urls, start=1):
            st.write(f"({i}/{len(urls)}) {url}")
            vid = extract_video_id(url)
            if not vid:
                st.warning(f"No se pudo extraer ID del enlace: {url}")
                continue
            transcript, meta = fetch_transcript(vid)
            if not transcript:
                st.warning(f"No hay transcripción automática disponible para {vid}. Error: {meta}")
                # aquí podríamos añadir fallback (ej. servicio STT), pero lo dejamos para version 2
                continue
            prompt = build_prompt_for_transcript(transcript, url)
            try:
                ai_out = call_openai(api_key, prompt)
                # Intentamos parsear JSON que el modelo debería devolver
                try:
                    parsed = json.loads(ai_out)
                except Exception:
                    # Si el modelo devolvió texto extra, intentamos extraer el JSON
                    m = re.search(r"(\{.*\}|\[.*\])", ai_out, re.DOTALL)
                    if m:
                        parsed = json.loads(m.group(1))
                    else:
                        parsed = {"error_parsing": ai_out}
                results.append({
                    "video_id": vid,
                    "url": url,
                    "extracted": parsed
                })
            except Exception as e:
                st.error(f"Error llamando al LLM: {e}")
        # show and download
        final_json = {"generated_at": st.secrets.get("generated_at", ""), "results": results}
        st.json(final_json)
        st.download_button("Descargar JSON", json.dumps(final_json, ensure_ascii=False, indent=2), file_name="teachings.json", mime="application/json")
