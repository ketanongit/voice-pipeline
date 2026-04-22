# 🎙️ Sarvam Voice Pipeline

A fully browser-based conversational voice bot built on **Sarvam AI's** Indian language stack — no phone number, no external telephony, no complex setup. Speak into your mic, get a spoken response back in under a second.

```
Mic → Sarvam STT (saarika:v2.5) → Groq LLM → Sarvam TTS (bulbul:v2) → Speaker
```

---

## What It Does

- 🎤 **Records** your voice directly in the browser
- 📝 **Transcribes** speech using Sarvam's `saarika:v2.5` model — supports Hindi, Tamil, Telugu, Bengali, Kannada, Malayalam, Marathi, Gujarati, Punjabi, and English
- 🧠 **Generates** a response via Groq (Llama 3.3 70B, Llama 3.1 8B, Mixtral, Gemma2)
- 🔊 **Speaks** the response back using Sarvam's `bulbul:v2` TTS with 44 Indian voice options
- 💬 **Maintains** full conversation history with per-turn latency tracking

---

## Stack

| Layer            | Model / Tool                             |
| ---------------- | ---------------------------------------- |
| STT              | Sarvam `saarika:v2.5`                    |
| LLM              | Groq (`llama-3.3-70b-versatile` default) |
| TTS              | Sarvam `bulbul:v2`                       |
| UI               | Streamlit                                |
| Audio processing | `soundfile` + `numpy`                    |

---

## Project Structure

```
demo-sarvam/
├── voice_pipeline.py   # Main app — full STT → LLM → TTS pipeline
├── template.md         # Bot persona, instructions & guardrails (edit this)
├── sarvam_tts.py       # Standalone TTS explorer (Streamlit)
├── sarvam_twilio.py    # Twilio voice webhook (optional, WIP)
├── .env                # API keys (never commit this)
└── README.md
```

---

## Setup

### 1. Clone / download the project

```bash
cd demo-sarvam
```

### 2. Install dependencies

```bash
pip install streamlit requests groq soundfile numpy python-dotenv
```

> **Windows note:** No system-level tools (ffmpeg etc.) required. Everything installs via pip.

### 3. Add your API keys

Create a `.env` file in the project root:

```env
SARVAM_API_KEY=your-sarvam-key-here
GROQ_API_KEY=gsk_your-groq-key-here
```

| Key              | Where to get it                                                    |
| ---------------- | ------------------------------------------------------------------ |
| `SARVAM_API_KEY` | [dashboard.sarvam.ai](https://dashboard.sarvam.ai)                 |
| `GROQ_API_KEY`   | [console.groq.com](https://console.groq.com) — free tier available |

### 4. Run

```bash
streamlit run voice_pipeline.py
```

Opens at `http://localhost:8501`

> Requires **Streamlit ≥ 1.33** for `st.audio_input()`. Upgrade with `pip install --upgrade streamlit`.

---

## Customizing the Bot

All persona, instructions, and guardrails live in **`template.md`** — no Python changes needed.

```
template.md
├── PERSONA        → Name, tone, language style
├── ROLE & SCOPE   → What the bot handles / doesn't handle
├── INSTRUCTIONS   → Step-by-step behavioral rules
├── GUARDRAILS     → Hard constraints and safety rules
└── SAMPLE OPENING → Example first turn (anchors tone)
```

Edit `template.md`, save, restart the app. The sidebar shows the loaded prompt and lets you tweak it live mid-session without restarting.

### Example: switching to a different persona

Open `template.md` and change:

- `Aria` → your bot's name
- `Nexus Insurance` → your company name
- The **SCOPE** section → your supported use cases
- The **SAMPLE OPENING** → your actual greeting

---

## Sidebar Controls

| Control            | What it does                                  |
| ------------------ | --------------------------------------------- |
| Sarvam API Key     | Your Sarvam subscription key                  |
| Groq API Key       | Your Groq API key                             |
| Language           | Input + output language for STT and TTS       |
| Speaker            | One of 44 Indian voice options for TTS        |
| Pace               | Speech speed — 0.5x (slow) to 2.0x (fast)     |
| Model              | Groq LLM model to use                         |
| System Prompt      | Editable live — pre-loaded from `template.md` |
| Clear conversation | Resets history and last audio                 |

---

## How the Audio Pipeline Works

`st.audio_input()` records in **WebM/Opus** on Chrome and **WAV** on some browsers. The app detects the format from magic bytes and converts to **16kHz mono PCM WAV** before sending to Sarvam STT — which is what the API expects.

TTS audio from Sarvam comes back as base64-encoded WAV and is decoded and played directly in the browser via `st.audio(..., autoplay=True)`.

---

## Supported Languages

| Language  | Code    |
| --------- | ------- |
| Hindi     | `hi-IN` |
| Bengali   | `bn-IN` |
| Tamil     | `ta-IN` |
| Telugu    | `te-IN` |
| Kannada   | `kn-IN` |
| Malayalam | `ml-IN` |
| Marathi   | `mr-IN` |
| Gujarati  | `gu-IN` |
| Punjabi   | `pa-IN` |
| English   | `en-IN` |
