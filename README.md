<div align="center">

<img src="parker_icon.png" width="100" alt="Parker icon" />

# P.A.R.K.E.R.
### Personal AI with Persistent Memory — JARVIS Edition

[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![LangGraph](https://img.shields.io/badge/LangGraph-0.2+-1C3C3C?style=flat-square&logo=langchain&logoColor=white)](https://langchain-ai.github.io/langgraph/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL+pgvector-4169E1?style=flat-square&logo=postgresql&logoColor=white)](https://github.com/pgvector/pgvector)
[![Groq](https://img.shields.io/badge/Groq-Multi--Key-F55036?style=flat-square)](https://groq.com)
[![Chatterbox](https://img.shields.io/badge/Chatterbox-Voice_Clone-black?style=flat-square)](https://github.com/resemble-ai/chatterbox)
[![Telegram](https://img.shields.io/badge/Telegram-Bot-26A5E4?style=flat-square&logo=telegram)](https://telegram.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow?style=flat-square)](LICENSE)

**A JARVIS-style personal AI assistant with persistent memory, voice cloning, Telegram access, and multi-key Groq rotation.**

[Quickstart](#quickstart) · [Architecture](#architecture) · [Memory System](#memory-system) · [Voice Setup](#voice-setup) · [Telegram](#telegram) · [Configuration](#configuration) · [CLI Reference](#cli-reference)

</div>

---

## What Parker Is

Most AI assistants forget you the moment the window closes. Parker compounds every conversation — profile, facts, projects, and a full episodic summary tree from chat → day → week → month → year.

It speaks with a JARVIS personality: dry, precise, direct. No filler. No questions at the end of every response. It uses your memory as its own organic knowledge.

---

## What's New

### JARVIS Personality
Complete rewrite of `prompts/chat.py`. Parker now responds like JARVIS — concise, dry British wit, addresses you as "sir" naturally, never asks "How does that sound?", never says "Certainly!" or "Of course!". Banned phrases list enforced at prompt level.

### Multi-Key Groq Rotation
Each LLM task gets its own dedicated Groq API key to avoid rate limit conflicts:

| LLM | Key | Task |
|---|---|---|
| `chat_llm` | key1 (solo) | Chat responses — heaviest, serial |
| `rollup_llm` | key2 | Day/week/month/year rollups |
| `projects_llm` | key2 (shared) | Project extraction — background |
| `facts_llm` | key3 | Fact extraction — background |
| `episodes_llm` | key3 (shared) | Chat summary generation |
| `trigger_llm` | key4 | Trigger classification — serial |
| `profile_llm` | key4 (shared) | Profile extraction — background |

### Voice Cloning via Chatterbox
Parker speaks in a cloned voice. Provide any 10–15 second clean reference audio clip and Chatterbox replicates it. Default setup uses a cloned reference voice placed at `reference_audio/reference.wav` in the Chatterbox server directory.

### Auto-Start Services
`main.py` now automatically starts Ollama and the Chatterbox TTS server on launch, and stops them cleanly on exit. No manual service management needed.

### Telegram Bot
Access Parker from anywhere via Telegram — mobile data, hostel WiFi, college network. Supports text messages, voice messages (Whisper transcription), and all memory commands.

---

## Quickstart

### Prerequisites

- Python 3.11+
- [Docker Desktop](https://www.docker.com/products/docker-desktop/)
- [Ollama](https://ollama.com) installed
- [Groq API keys](https://console.groq.com) — up to 4 accounts recommended
- [mpv](https://mpv.io) installed and in PATH (for Chatterbox streaming)
- [Chatterbox TTS Server](https://github.com/mirbehnam/Chatterbox-TTS-Server-windows-easyInstallation) installed separately

### 1. Clone and install

```bash
git clone https://github.com/your-username/parker.git
cd parker
pip install -r requirements.txt
```

### 2. Pull Ollama models

```bash
ollama pull qwen2.5:3b
ollama pull mxbai-embed-large
```

### 3. Start PostgreSQL

```bash
docker compose up -d
```

### 4. Configure environment

```bash
cp .env.example .env
```

Edit `.env`:

```env
# Multi-key Groq setup (use same key for all if you only have one account)
GROQ_API_KEY_1=gsk_key1
GROQ_API_KEY_2=gsk_key2
GROQ_API_KEY_3=gsk_key3
GROQ_API_KEY_4=gsk_key4

# Memory LLM — switch to groq for better extraction accuracy
MEMORY_LLM_PROVIDER=groq
MEMORY_LLM_MODEL=llama-3.3-70b-versatile

# Telegram (optional)
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_ALLOWED_USER=your_telegram_user_id
```

### 5. Set up voice cloning

1. Find a clean 10–15 second audio clip (no background music)
2. Trim it:
```python
from pydub import AudioSegment
audio = AudioSegment.from_wav("source.wav")
audio[2000:17000].export("reference.wav", format="wav")
```
3. Copy to Chatterbox server: `reference_audio/reference.wav`

### 6. Run

```bash
# Windows
run_parker.bat

# or directly
python main.py
```

Ollama and Chatterbox start automatically. Docker must be running.

---

## Architecture

### Runtime flow

```
START → trigger → retrieve → chat → remember → END
```

| Node | What it does |
|---|---|
| `trigger` | `trigger_llm` classifies needs_retrieval + needs_storage. Regex override forces retrieval for memory queries. |
| `retrieve` | Assembles profile, facts, projects, episodic memories via semantic search. |
| `chat` | Groq LLaMA 70B generates response with JARVIS personality. Post-processes to strip AI disclaimers. |
| `remember` | Background threads: save_profile, save_facts, save_projects, write_chat_turn. Never blocks chat. |

### Dual-model design

| Role | Default | Why |
|---|---|---|
| Chat LLM | Groq LLaMA 3.3 70B (key1) | High-quality JARVIS responses |
| Memory LLMs | Groq LLaMA 3.3 70B (keys 2–4) | Accurate structured extraction |
| Embeddings | Ollama mxbai-embed-large | Local semantic search |

### Service architecture

```
python main.py
    ├── auto-starts: ollama serve
    ├── auto-starts: Chatterbox TTS Server (localhost:8004)
    ├── connects: PostgreSQL via Docker (localhost:5442)
    └── on exit: stops Chatterbox + Ollama cleanly
```

### Core file map

```
parker/
├── main.py                  CLI runtime — auto-starts services, session loop
├── telegram_interface.py    Telegram bot — text + voice messages
├── graph.py                 LangGraph state machine — 4 nodes
├── retrieval.py             Memory context assembly
├── database.py              PostgresStore + PostgresSaver
├── config.py                Centralized env-var configuration
├── models.py                Per-task LLM instances with key rotation
├── interface.py             Rich terminal UI
├── ears.py                  Whisper + Silero VAD — speech to text
├── mouth.py                 Chatterbox voice clone TTS
├── memory/
│   ├── profile.py           Identity extraction
│   ├── facts.py             Fact extraction + archival
│   ├── projects.py          Project state tracking
│   ├── episodes.py          Chat summary + episodic retrieval
│   └── rollup/              Day/week/month/year rollup scheduler
└── prompts/
    ├── chat.py              JARVIS personality + memory directives
    ├── memory.py            Extraction prompts
    └── rollup.py            Rollup summarization prompts
```

---

## Memory System

### Four layers

**Profile** — Stable identity. Name, university, branch, tools, preferences. Single dict, merge-on-update.

**Facts** — Discrete facts with importance tiers (`critical`, `high`, `normal`, `low`). Critical facts injected into every prompt as hard constraints. Stale facts auto-archived.

**Projects** — Multi-session project state. Name, status, stack, open threads, decisions log. Completed projects archived automatically.

**Episodes** — Summary tree:
```
chat turn → day → week → month → year
```
Retrieval drills top-down: year → month → week → day → chat. Temporal shortcuts for "yesterday"/"today" queries bypass semantic search.

---

## Voice Setup

Parker uses [Chatterbox TTS Server](https://github.com/mirbehnam/Chatterbox-TTS-Server-windows-easyInstallation) for voice output with voice cloning.

### Install Chatterbox (Windows)

```bash
git clone https://github.com/mirbehnam/Chatterbox-TTS-Server-windows-easyInstallation.git
cd Chatterbox-TTS-Server-windows-easyInstallation
.\setup.bat  # choose option 1 for NVIDIA GPU
```

### Install mpv (required for streaming)

```bash
winget install shinchiro.mpv
# then add to PATH: C:\Program Files\MPV Player
```

### Clone a voice

```bash
# Download reference audio
pip install yt-dlp
python -m yt_dlp -x --audio-format wav "YOUTUBE_URL"

# Trim to clean 10-15 second clip
python -c "
from pydub import AudioSegment
audio = AudioSegment.from_wav('source.wav')
audio[2000:17000].export('reference.wav', format='wav')
"

# Copy to Chatterbox
copy reference.wav "Chatterbox-TTS-Server-windows-easyInstallation\reference_audio\reference.wav"
```

### Test voice

```powershell
Invoke-WebRequest -Method POST -Uri "http://localhost:8004/tts" -ContentType "application/json" -Body '{"text": "Good evening sir.", "language": "en", "voice_mode": "clone", "reference_audio_filename": "reference.wav"}' -OutFile "test.wav"
```

---

## Telegram

Access Parker from your phone anywhere.

### Setup

1. Open Telegram → `@BotFather` → `/newbot` → copy token
2. Open Telegram → `@userinfobot` → copy your numeric user ID
3. Add to `.env`:
```env
TELEGRAM_BOT_TOKEN=your_token
TELEGRAM_ALLOWED_USER=your_numeric_id
```
4. Run:
```bash
python telegram_interface.py
```

### Commands

| Command | What it does |
|---|---|
| `/start` | Show available commands |
| `/profile` | Display memory profile |
| `/facts` | List stored facts by importance |
| `/projects` | List active projects |
| Send text | Parker responds |
| Send voice message | Whisper transcribes → Parker responds |

---

## Configuration

### Multi-key Groq

```env
GROQ_API_KEY_1=gsk_...   # chat responses
GROQ_API_KEY_2=gsk_...   # rollup + projects
GROQ_API_KEY_3=gsk_...   # facts + episodes
GROQ_API_KEY_4=gsk_...   # trigger + profile
```

If you have one account, set all to the same key. Parker still works — you'll just hit rate limits faster under heavy use.

### Memory LLM provider

```env
# Groq (recommended — better extraction accuracy)
MEMORY_LLM_PROVIDER=groq
MEMORY_LLM_MODEL=llama-3.3-70b-versatile

# Ollama (local, no rate limits, less accurate)
MEMORY_LLM_PROVIDER=ollama
MEMORY_LLM_MODEL=qwen2.5:3b
```

### Full configuration reference

| Variable | Default | Description |
|---|---|---|
| `DB_URI` | `postgresql://postgres:postgres@localhost:5442/postgres?sslmode=disable` | PostgreSQL connection |
| `GROQ_API_KEY_1..4` | — | Per-task Groq keys |
| `CHAT_LLM_MODEL` | `llama-3.3-70b-versatile` | Chat model |
| `MEMORY_LLM_PROVIDER` | `ollama` | `groq` or `ollama` |
| `MEMORY_LLM_MODEL` | `qwen2.5:3b` | Memory extraction model |
| `EMBEDDING_MODEL` | `mxbai-embed-large` | Ollama embedding model |
| `TELEGRAM_BOT_TOKEN` | — | Telegram bot token |
| `TELEGRAM_ALLOWED_USER` | — | Your Telegram user ID |
| `DEFAULT_USER_ID` | `u1` | User namespace |
| `REMINDER_POLL_INTERVAL` | `30` | Scheduler poll interval (seconds) |

---

## CLI Reference

### Commands

| Command | What it does |
|---|---|
| `v` | Switch to voice input mode |
| `t` | Switch to text input mode |
| `/profile` | Show memory profile |
| `/facts` | Show stored facts by importance tier |
| `/projects` | Show active projects |
| `/clear` | Clear screen |
| `exit` / `quit` / `bye` | Save state and shut down cleanly |
| `Ctrl+C` | Clean shutdown |

---

## Database Management

**Reset all memory** (destructive):

```bash
docker compose down -v
docker compose up -d
python main.py
```

**Inspect episodes:**

```bash
python debug_db.py
```

---

## Project Notes

- Each session gets a unique thread ID. Cross-session memory lives in PostgresStore namespaces, not the LangGraph checkpointer.
- Memory writes never block chat. All extraction runs in background threads. `wait_for_background_jobs()` drains them on shutdown.
- Episodes are summary-only. Raw transcripts are never stored.
- The JARVIS personality is enforced at prompt level with a banned-phrases list and strict length rules.
- Voice cloning quality depends on reference audio cleanliness — no background music, single speaker, 10–15 seconds minimum.

---

## License

MIT — see [LICENSE](LICENSE).