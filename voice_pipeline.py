"""
Complete Browser Voice Pipeline
─────────────────────────────────
Mic → Sarvam STT (saarika:v2.5) → OpenAI LLM → Sarvam TTS (bulbul:v2) → Speaker

Install:
  pip install streamlit requests openai soundfile numpy python-dotenv

Run:
  streamlit run voice_pipeline.py

Requires Streamlit >= 1.33  (for st.audio_input)
"""

import io, os, base64, json
from datetime import datetime

import numpy as np
import requests
import soundfile as sf
import streamlit as st
from dotenv import load_dotenv
from groq import Groq

load_dotenv()

# ── Load system prompt from template.md ──────────────────────────────────────
def load_template(path: str = "template.md") -> str:
    """Load bot persona/instructions from markdown file. Strip markdown for voice."""
    try:
        raw = open(path, encoding="utf-8").read()
        # Remove markdown headers, bullets, bold — keeps plain prose for LLM
        import re
        clean = re.sub(r"^#{1,3} .+$", "", raw, flags=re.MULTILINE)  # headers
        clean = re.sub(r"\*\*(.+?)\*\*", r"\1", clean)               # bold
        clean = re.sub(r"^[-*] ", "", clean, flags=re.MULTILINE)      # bullets
        clean = re.sub(r"\n{3,}", "\n\n", clean)                      # extra blank lines
        return clean.strip()
    except FileNotFoundError:
        return (
            "You are a helpful customer support agent. "
            "Keep responses concise and conversational — 2-3 sentences max. "
            "Respond in the same language the user speaks."
        )

DEFAULT_SYSTEM_PROMPT = load_template()

# ── Page setup ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Voice Pipeline · Sarvam AI",
    page_icon="🎙️",
    layout="wide",
)

st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600&family=Sora:wght@300;400;600&display=swap');

  html, body, [class*="css"] { font-family: 'Sora', sans-serif; }
  .main { background: #080b12; }

  .pipeline-box {
    background: #0d1117; border: 1px solid #1e2736;
    border-radius: 12px; padding: 18px 22px; margin-bottom: 10px;
  }
  .pipeline-box.active  { border-color: #f97316; background: rgba(249,115,22,0.06); }
  .pipeline-box.done    { border-color: #22c55e; background: rgba(34,197,94,0.06); }
  .pipeline-box.error   { border-color: #ef4444; background: rgba(239,68,68,0.06); }

  .step-label {
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px; letter-spacing: 0.15em;
    text-transform: uppercase; color: #6b7280;
    margin-bottom: 4px;
  }
  .step-value { font-size: 15px; color: #e5e7eb; line-height: 1.6; }

  .bubble-user {
    background: #1e2736; border-radius: 16px 16px 4px 16px;
    padding: 12px 18px; margin: 8px 0; max-width: 80%;
    margin-left: auto; color: #e5e7eb; font-size: 14px;
  }
  .bubble-ai {
    background: rgba(249,115,22,0.12); border: 1px solid rgba(249,115,22,0.2);
    border-radius: 16px 16px 16px 4px;
    padding: 12px 18px; margin: 8px 0; max-width: 80%;
    color: #e5e7eb; font-size: 14px;
  }
  .meta { font-size: 11px; color: #4b5563; font-family: 'JetBrains Mono', monospace; margin-top: 4px; }

  div[data-testid="stAudioInput"] > div { border-color: #1e2736 !important; }
  div[data-testid="stAudioInput"] { background: #0d1117; border-radius: 12px; }
</style>
""", unsafe_allow_html=True)


# ── Session state ─────────────────────────────────────────────────────────────
if "history" not in st.session_state:
    st.session_state.history = []          # [{role, content, ts, latency_ms}]
if "last_audio" not in st.session_state:
    st.session_state.last_audio = None


# ── Sidebar — Config ──────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## ⚙️ Config")

    sarvam_key = st.text_input("Sarvam API Key", type="password",
                                value=os.getenv("SARVAM_API_KEY", ""),
                                placeholder="your-sarvam-key")
    openai_key = st.text_input("Groq API Key", type="password",
                                value=os.getenv("GROQ_API_KEY", ""),
                                placeholder="gsk_...")

    st.divider()
    st.markdown("**Voice**")

    LANGUAGES = {
        "Hindi (हिन्दी)":      "hi-IN",
        "Bengali (বাংলা)":     "bn-IN",
        "Tamil (தமிழ்)":       "ta-IN",
        "Telugu (తెలుగు)":     "te-IN",
        "Kannada (ಕನ್ನಡ)":    "kn-IN",
        "Malayalam (മലയാളം)": "ml-IN",
        "Marathi (मराठी)":     "mr-IN",
        "Gujarati (ગુજરાતી)":  "gu-IN",
        "Punjabi (ਪੰਜਾਬੀ)":   "pa-IN",
        "English":             "en-IN",
    }
    lang_label = st.selectbox("Language", list(LANGUAGES.keys()))
    lang_code  = LANGUAGES[lang_label]

    SPEAKERS = [
        "anushka","abhilash","manisha","vidya","arya","karun","hitesh","aditya",
        "ritu","priya","neha","rahul","pooja","rohan","simran","kavya","amit",
        "dev","ishita","shreya","ratan","varun","manan","sumit","roopa","kabir",
        "aayan","shubh","ashutosh","advait","anand","tanya","tarun","sunny",
        "mani","gokul","vijay","shruti","suhani","mohit","kavitha","rehan",
        "soham","rupali",
    ]
    speaker = st.selectbox("Speaker", SPEAKERS)
    pace    = st.slider("Pace", 0.5, 2.0, 1.0, 0.1)

    st.divider()
    st.markdown("**LLM**")

    llm_model = st.selectbox("Model", ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "mixtral-8x7b-32768", "gemma2-9b-it"])

    system_prompt = st.text_area(
        "System Prompt",
        value=DEFAULT_SYSTEM_PROMPT,
        height=120,
    )

    st.divider()
    if st.button("🗑️ Clear conversation", use_container_width=True):
        st.session_state.history  = []
        st.session_state.last_audio = None
        st.rerun()


# ── API helpers ───────────────────────────────────────────────────────────────

def detect_audio_format(audio_bytes: bytes) -> tuple[bytes, str, str]:
    """
    Detect audio format from magic bytes and convert to 16kHz mono WAV.
    st.audio_input() records WebM/Opus in Chrome, WAV in some browsers.
    Returns (converted_bytes, filename, mimetype).
    """
    # Detect format from magic bytes
    if audio_bytes[:4] == b'RIFF':
        fmt, fname, mime = "wav",  "audio.wav",  "audio/wav"
    elif audio_bytes[:4] == b'OggS':
        fmt, fname, mime = "ogg",  "audio.ogg",  "audio/ogg"
    elif audio_bytes[:4] in (b'\x1aE\xdf\xa3', b'\x1aE\xdf\xa3'):
        fmt, fname, mime = "webm", "audio.webm", "audio/webm"
    elif audio_bytes[:3] == b'ID3' or audio_bytes[:2] == b'\xff\xfb':
        fmt, fname, mime = "mp3",  "audio.mp3",  "audio/mpeg"
    else:
        # Unknown — send as-is and let Sarvam figure it out
        return audio_bytes, "audio.wav", "audio/wav"

    # Try converting to 16kHz mono WAV with soundfile
    try:
        data, sr = sf.read(io.BytesIO(audio_bytes), format=fmt if fmt != "webm" else None)
        if len(data.shape) > 1:
            data = data.mean(axis=1)
        if sr != 16000:
            new_len = int(len(data) * 16000 / sr)
            data = np.interp(np.linspace(0, len(data), new_len),
                             np.arange(len(data)), data)
        data = np.clip(data, -1.0, 1.0)
        data = (data * 32767).astype(np.int16)
        buf = io.BytesIO()
        sf.write(buf, data, 16000, format="WAV", subtype="PCM_16")
        return buf.getvalue(), "audio.wav", "audio/wav"
    except Exception:
        # Conversion failed — send raw with correct mime type
        return audio_bytes, fname, mime


def convert_tts_for_browser(raw_bytes: bytes) -> bytes:
    """Ensure TTS audio plays cleanly in browser."""
    try:
        data, sr = sf.read(io.BytesIO(raw_bytes))
        if len(data.shape) > 1:
            data = data.mean(axis=1)
        buf = io.BytesIO()
        sf.write(buf, data, sr, format="WAV", subtype="PCM_16")
        return buf.getvalue()
    except Exception:
        return raw_bytes


def sarvam_stt(audio_bytes: bytes, language_code: str) -> dict:
    """Returns {transcript, language_code, latency_ms}"""
    converted, fname, mime = detect_audio_format(audio_bytes)
    t0 = datetime.now()

    # Build form data — only include language_code if not auto-detect
    form_data = {"model": "saarika:v2.5"}
    if language_code and language_code != "auto":
        form_data["language_code"] = language_code

    resp = requests.post(
        "https://api.sarvam.ai/speech-to-text",
        headers={"api-subscription-key": sarvam_key},
        files={"file": (fname, converted, mime)},
        data=form_data,
        timeout=30,
    )

    if not resp.ok:
        raise Exception(f"{resp.status_code}: {resp.text}")

    latency = int((datetime.now() - t0).total_seconds() * 1000)
    data = resp.json()
    return {
        "transcript":    data.get("transcript", ""),
        "language_code": data.get("language_code", language_code),
        "latency_ms":    latency,
    }


def llm_respond(user_text: str, history: list, system: str, model: str) -> dict:
    """Returns {response, latency_ms}"""
    client   = Groq(api_key=openai_key)
    messages = [{"role": "system", "content": system}]
    for turn in history[-8:]:   # last 4 exchanges
        messages.append({"role": turn["role"], "content": turn["content"]})
    messages.append({"role": "user", "content": user_text})

    t0   = datetime.now()
    comp = client.chat.completions.create(model=model, messages=messages, max_tokens=300)
    latency = int((datetime.now() - t0).total_seconds() * 1000)
    return {
        "response":   comp.choices[0].message.content.strip(),
        "latency_ms": latency,
    }


def sarvam_tts(text: str, language_code: str, speaker: str, pace: float) -> dict:
    """Returns {audio_bytes, latency_ms}"""
    t0 = datetime.now()
    resp = requests.post(
        "https://api.sarvam.ai/text-to-speech",
        headers={
            "Content-Type": "application/json",
            "api-subscription-key": sarvam_key,
        },
        json={
            "inputs": [text],
            "target_language_code": language_code,
            "speaker": speaker,
            "model": "bulbul:v2",
            "pace": pace,
            "enable_preprocessing": True,
        },
        timeout=30,
    )
    resp.raise_for_status()
    latency     = int((datetime.now() - t0).total_seconds() * 1000)
    raw_bytes   = base64.b64decode(resp.json()["audios"][0])
    audio_bytes = convert_tts_for_browser(raw_bytes)
    return {"audio_bytes": audio_bytes, "latency_ms": latency}


# ── Main UI ───────────────────────────────────────────────────────────────────
st.markdown("## 🎙️ Voice Pipeline")
st.markdown(
    "<span style='color:#6b7280;font-size:13px;font-family:monospace'>"
    "Mic → Sarvam STT (saarika:v2.5) → OpenAI LLM → Sarvam TTS (bulbul:v2) → Speaker"
    "</span>",
    unsafe_allow_html=True,
)
st.divider()

col_record, col_pipeline = st.columns([1, 1], gap="large")

with col_record:
    st.markdown("#### Record")
    audio_input = st.audio_input("Click the mic to record, click again to stop")

    if audio_input is not None:
        if not sarvam_key:
            st.error("⚠️ Add your Sarvam API key in the sidebar.")
        elif not openai_key:
            st.error("⚠️ Add your Groq API key in the sidebar.")
        else:
            audio_bytes = audio_input.read()

            # ── Step 1: STT ──────────────────────────────────────────────────
            with col_pipeline:
                st.markdown("#### Pipeline")
                stt_box = st.empty()
                llm_box = st.empty()
                tts_box = st.empty()

            with col_pipeline:
                stt_box.markdown(
                    '<div class="pipeline-box active">'
                    '<div class="step-label">① STT — saarika:v2.5</div>'
                    '<div class="step-value">Transcribing…</div>'
                    '</div>', unsafe_allow_html=True)

                try:
                    stt_result = sarvam_stt(audio_bytes, lang_code)
                    transcript = stt_result["transcript"]

                    stt_box.markdown(
                        f'<div class="pipeline-box done">'
                        f'<div class="step-label">① STT — saarika:v2.5 &nbsp;✓ {stt_result["latency_ms"]}ms</div>'
                        f'<div class="step-value">"{transcript}"</div>'
                        f'</div>', unsafe_allow_html=True)

                except Exception as e:
                    stt_box.markdown(
                        f'<div class="pipeline-box error">'
                        f'<div class="step-label">① STT — Error</div>'
                        f'<div class="step-value">{e}</div>'
                        f'</div>', unsafe_allow_html=True)
                    st.stop()

                # ── Step 2: LLM ──────────────────────────────────────────────
                llm_box.markdown(
                    '<div class="pipeline-box active">'
                    '<div class="step-label">② LLM — ' + llm_model + '</div>'
                    '<div class="step-value">Thinking…</div>'
                    '</div>', unsafe_allow_html=True)

                try:
                    llm_result  = llm_respond(
                        transcript, st.session_state.history, system_prompt, llm_model
                    )
                    llm_response = llm_result["response"]

                    llm_box.markdown(
                        f'<div class="pipeline-box done">'
                        f'<div class="step-label">② LLM — {llm_model} &nbsp;✓ {llm_result["latency_ms"]}ms</div>'
                        f'<div class="step-value">"{llm_response}"</div>'
                        f'</div>', unsafe_allow_html=True)

                except Exception as e:
                    llm_box.markdown(
                        f'<div class="pipeline-box error">'
                        f'<div class="step-label">② LLM — Error</div>'
                        f'<div class="step-value">{e}</div>'
                        f'</div>', unsafe_allow_html=True)
                    st.stop()

                # ── Step 3: TTS ──────────────────────────────────────────────
                tts_box.markdown(
                    '<div class="pipeline-box active">'
                    '<div class="step-label">③ TTS — bulbul:v2</div>'
                    '<div class="step-value">Generating audio…</div>'
                    '</div>', unsafe_allow_html=True)

                try:
                    tts_result  = sarvam_tts(llm_response, lang_code, speaker, pace)
                    audio_out   = tts_result["audio_bytes"]

                    tts_box.markdown(
                        f'<div class="pipeline-box done">'
                        f'<div class="step-label">③ TTS — bulbul:v2 &nbsp;✓ {tts_result["latency_ms"]}ms</div>'
                        f'<div class="step-value">Audio ready · {len(audio_out)//1024} KB</div>'
                        f'</div>', unsafe_allow_html=True)

                    st.session_state.last_audio = audio_out

                except Exception as e:
                    tts_box.markdown(
                        f'<div class="pipeline-box error">'
                        f'<div class="step-label">③ TTS — Error</div>'
                        f'<div class="step-value">{e}</div>'
                        f'</div>', unsafe_allow_html=True)
                    st.stop()

                # ── Save to history ──────────────────────────────────────────
                ts = datetime.now().strftime("%H:%M:%S")
                st.session_state.history.append(
                    {"role": "user",      "content": transcript,   "ts": ts,
                     "latency_ms": stt_result["latency_ms"]})
                st.session_state.history.append(
                    {"role": "assistant", "content": llm_response, "ts": ts,
                     "latency_ms": llm_result["latency_ms"] + tts_result["latency_ms"]})

            # Auto-play response audio
            if st.session_state.last_audio:
                with col_record:
                    st.markdown("#### Response")
                    st.audio(st.session_state.last_audio, format="audio/wav", autoplay=True)

with col_pipeline:
    if audio_input is None:
        st.markdown("#### Pipeline")
        for label, icon in [
            ("① STT — saarika:v2.5", "🎤"),
            ("② LLM — " + llm_model, "🧠"),
            ("③ TTS — bulbul:v2", "🔊"),
        ]:
            st.markdown(
                f'<div class="pipeline-box">'
                f'<div class="step-label">{label}</div>'
                f'<div class="step-value" style="color:#374151">{icon} Waiting for audio…</div>'
                f'</div>', unsafe_allow_html=True)


# ── Conversation history ──────────────────────────────────────────────────────
if st.session_state.history:
    st.divider()
    st.markdown("#### Conversation")

    total_latency = sum(t.get("latency_ms", 0) for t in st.session_state.history
                        if t["role"] == "assistant")
    turns = len([t for t in st.session_state.history if t["role"] == "user"])
    st.markdown(
        f"<span class='meta'>{turns} turn{'s' if turns != 1 else ''} · "
        f"avg response {total_latency // max(turns,1)}ms end-to-end</span>",
        unsafe_allow_html=True
    )
    st.markdown("")

    for turn in reversed(st.session_state.history):
        if turn["role"] == "user":
            st.markdown(
                f'<div class="bubble-user">{turn["content"]}'
                f'<div class="meta">You · {turn["ts"]}</div></div>',
                unsafe_allow_html=True)
        else:
            st.markdown(
                f'<div class="bubble-ai">{turn["content"]}'
                f'<div class="meta">Maya · {turn["ts"]} · {turn.get("latency_ms",0)}ms</div></div>',
                unsafe_allow_html=True)