<div align="center">

<img src="parker_icon.png" width="110" alt="Parker icon" />

# P · A · R · K · E · R

**Personal AI with Recursive Knowledge & Episodic Recall**

*A production-grade JARVIS-style AI assistant with persistent long-term memory, voice cloning, and multi-modal access — built from scratch.*

<br/>

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![LangGraph](https://img.shields.io/badge/LangGraph-0.2+-1C3C3C?style=flat-square&logo=langchain&logoColor=white)](https://langchain-ai.github.io/langgraph/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL_+_pgvector-4169E1?style=flat-square&logo=postgresql&logoColor=white)](https://github.com/pgvector/pgvector)
[![Groq](https://img.shields.io/badge/Groq_LLaMA_70B-F55036?style=flat-square)](https://groq.com)
[![Ollama](https://img.shields.io/badge/Ollama-Local_Embeddings-black?style=flat-square)](https://ollama.com)
[![Telegram](https://img.shields.io/badge/Telegram_Bot-26A5E4?style=flat-square&logo=telegram&logoColor=white)](https://telegram.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow?style=flat-square)](LICENSE)

<br/>

> *Most AI assistants forget you the moment the window closes.*
> *Parker compounds every conversation — forever.*

<br/>

[System Design](#system-design) · [Memory Architecture](#memory-architecture) · [Quickstart](#quickstart) · [Configuration](#configuration) · [Voice Setup](#voice-setup) · [Telegram](#telegram-bot) · [CLI Reference](#cli-reference)

---

</div>

## Overview

Parker is a **fully local-first, production-grade personal AI system** with persistent long-term memory, voice cloning, and concurrent multi-modal access. It is built on a custom four-layer memory architecture that compounds across sessions — transforming raw conversations into a hierarchical summary tree that spans chat turns, days, weeks, months, and years.

The system is designed around three core engineering goals:

- **Memory that scales** — no raw transcript storage; every interaction is distilled into structured, semantically indexed memory through an LLM extraction pipeline running entirely in the background
- **Latency that doesn't compound** — chat response time is never blocked by memory writes; all extraction runs on background threads drained at shutdown
- **Personality that holds** — JARVIS-style voice and behavior enforced at the prompt level with a hard banned-phrases list, not left to model default behavior

---

## System Design

### Runtime Graph

Parker uses a **LangGraph state machine** to orchestrate every conversation turn through four deterministic nodes:

```
START ──► trigger ──► retrieve ──► chat ──► remember ──► END
```

| Node | Responsibility | LLM | Blocking? |
|---|---|---|---|
| `trigger` | Classifies whether the message needs memory retrieval and/or storage. Regex override forces retrieval for memory queries. | `trigger_llm` (key 4) | ✅ Yes |
| `retrieve` | Assembles full memory context: profile, critical facts, relevant facts, active projects, and episodic summaries via semantic search. | — | ✅ Yes |
| `chat` | Generates the JARVIS-style response. Post-processes output to strip any AI disclaimers and repair memory-denial phrases. | `chat_llm` (key 1) | ✅ Yes |
| `remember` | Dispatches profile, facts, and project extraction as non-blocking background threads. Never delays the response. | keys 2–4 | ❌ No |

### Multi-Key Groq Architecture

Each LLM task is assigned a dedicated Groq API key to prevent rate-limit collisions across concurrent workloads:

```
GROQ_API_KEY_1  ──►  chat_llm          (serial, heaviest — full context every turn)
GROQ_API_KEY_2  ──►  rollup_llm        (startup/shutdown only — day/week/month/year)
                      projects_llm      (background — minimal time overlap with rollup)
GROQ_API_KEY_3  ──►  facts_llm         (background — post-turn extraction)
                      episodes_llm      (background — chat summary generation)
GROQ_API_KEY_4  ──►  trigger_llm       (serial, tiny — classification before every turn)
                      profile_llm       (background — identity extraction)
```

This design allows all background extraction tasks to run concurrently without interfering with the primary chat loop.

### Service Architecture

```
python main.py
    ├── auto-starts  →  ollama serve
    ├── auto-starts  →  Chatterbox TTS Server (localhost:8004)
    ├── connects     →  PostgreSQL + pgvector via Docker (localhost:5442)
    └── on exit      →  drains background job queue → saves rollups → closes DB
```

### Core File Map

```
parker/
├── main.py                    CLI runtime — session loop, service lifecycle
├── telegram_interface.py      Telegram bot — text + voice, all memory commands
│
├── graph.py                   LangGraph state machine — 4 nodes, JARVIS post-processing
├── retrieval.py               Memory context assembly — semantic + temporal routing
│
├── config.py                  Centralized env-var configuration with defaults
├── models.py                  Per-task LLM instances with multi-key Groq rotation
├── database.py                PostgresStore + PostgresSaver with retry logic
│
├── interface.py               Rich terminal UI — PARKER theme, panels, status bar
├── ears.py                    Whisper small + Silero VAD — push-to-speak, auto-stop
├── mouth.py                   Chatterbox TTS — voice clone streaming via mpv
│
├── memory/
│   ├── profile.py             Stable identity extraction (name, university, tools…)
│   ├── facts.py               Discrete facts with importance tiers + stale archival
│   ├── projects.py            Multi-session project state tracking + archive
│   ├── episodes.py            Chat summary writer + hierarchical episode retrieval
│   └── rollup/
│       ├── core.py            Rollup scheduler — detects crossed time boundaries
│       ├── summarizers.py     Day / week / month / year summary generation
│       └── bounds.py          ISO calendar boundary detection helpers
│
└── prompts/
    ├── chat.py                JARVIS system prompt — personality + memory directives
    ├── memory.py              Structured extraction prompts (profile, facts, projects)
    └── rollup.py              Rollup summarization prompts (chat → year)
```

---

## Memory Architecture

The single most technically significant aspect of Parker is its **four-layer persistent memory system**. Every layer is stored in PostgreSQL with pgvector embeddings, enabling semantic search across all historical context.

### Layer 1 — Profile

Stable identity facts extracted from conversation: name, university, branch, hardware, editor, preferences. Stored as a single merged JSON object. New values overwrite stale ones. Injected into every prompt.

### Layer 2 — Facts

Discrete facts with four importance tiers:

| Tier | Behavior |
|---|---|
| `critical` | Injected as hard constraints into every prompt. Never archived. |
| `high` | Surfaced by semantic search on relevant queries. Never archived. |
| `normal` | Archived after 365 days of inactivity. |
| `low` | Archived after 90 days of inactivity. |

Archived facts move to a separate namespace and remain searchable by semantic query. The extraction prompt includes existing facts so the LLM can distinguish `add`, `update`, and `skip` actions — preventing duplicates at the source.

### Layer 3 — Projects

Multi-session project state with full history:

- `name`, `status` (active / paused / completed / abandoned)
- `summary` — current state description, updated each session
- `stack` — tech stack, merged across sessions
- `open_threads` — unresolved decisions from this session
- `decisions_log` — dated decision history, never overwritten
- `linked_chats` — ISO timestamps of sessions that touched this project

Completed and abandoned projects auto-archive on startup. Active projects are injected in full; archived projects are retrieved by semantic query when relevant.

### Layer 4 — Episodes (Summary Tree)

The deepest layer. Raw transcripts are **never stored**. Every chat turn is distilled by the `episodes_llm` into a structured memory entry:

```json
{
  "summary": "Discussed pgvector schema design...",
  "key_topics": ["pgvector", "embeddings", "schema"],
  "projects_mentioned": ["Parker AI"],
  "decisions": ["Use mxbai-embed-large at 1024 dims"],
  "left_unfinished": ["Benchmarking alternative embedding models"]
}
```

These chat-level entries are rolled up into a **five-level summary tree**:

```
chat turn  ──►  day summary  ──►  week summary  ──►  month summary  ──►  year summary
```

Rollups are triggered by ISO calendar boundary crossing detected at session start. Retrieval drills top-down — year → month → week → day → chat — guided by semantic search at each level, with temporal shortcuts for queries like "yesterday" and "today" that bypass the semantic path entirely.

### Retrieval Strategy

For each turn, `build_context()` assembles:

1. Full profile (always)
2. Critical facts (always — hard constraints)
3. Top-8 semantically relevant facts (query + active project names)
4. Active projects in full + historically relevant archived projects
5. Relevant episodes — semantic search across the full summary tree, with temporal override for date-anchored queries
6. Archive recall — stale facts surfaced if semantically relevant

The assembled context is injected into the system prompt as organic knowledge. Parker never sees a retrieval mechanism — it sees its own memory.

---

## Quickstart

### Prerequisites

| Dependency | Purpose |
|---|---|
| Python 3.11+ | Runtime |
| [Docker Desktop](https://www.docker.com/products/docker-desktop/) | PostgreSQL + pgvector |
| [Ollama](https://ollama.com) | Local embeddings |
| [Groq API key(s)](https://console.groq.com) | LLM inference (free tier available) |
| [mpv](https://mpv.io) | TTS audio streaming |
| [Chatterbox TTS Server](https://github.com/mirbehnam/Chatterbox-TTS-Server-windows-easyInstallation) | Voice cloning |

### 1 — Clone and install

```bash
git clone https://github.com/your-username/parker.git
cd parker
pip install -r requirements.txt
```

### 2 — Pull Ollama models

```bash
ollama pull mxbai-embed-large   # 1024-dim embeddings
ollama pull qwen2.5:3b          # optional: local memory LLM fallback
```

### 3 — Start PostgreSQL

```bash
docker compose up -d
```

### 4 — Configure environment

```bash
cp .env.example .env
```

Edit `.env` with your keys:

```env
# ── Groq (use the same key for all if you have one account) ───────────────────
GROQ_API_KEY_1=gsk_...   # chat responses
GROQ_API_KEY_2=gsk_...   # rollup + projects
GROQ_API_KEY_3=gsk_...   # facts + episodes
GROQ_API_KEY_4=gsk_...   # trigger + profile

# ── Memory LLM ────────────────────────────────────────────────────────────────
MEMORY_LLM_PROVIDER=groq                  # groq (recommended) or ollama
MEMORY_LLM_MODEL=llama-3.3-70b-versatile

# ── Identity ──────────────────────────────────────────────────────────────────
USER_NAME=YourName

# ── Telegram (optional) ───────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_ALLOWED_USER=your_numeric_user_id
```

### 5 — Run

```bash
# Windows
run_parker.bat

# macOS / Linux
python main.py
```

Ollama and Chatterbox start automatically. Docker must be running.

---

## Configuration Reference

| Variable | Default | Description |
|---|---|---|
| `DB_URI` | `postgresql://postgres:postgres@localhost:5442/postgres` | PostgreSQL connection string |
| `GROQ_API_KEY_1..4` | — | Per-task Groq API keys |
| `CHAT_LLM_MODEL` | `llama-3.3-70b-versatile` | Chat response model |
| `CHAT_LLM_TEMPERATURE` | `0.7` | Chat generation temperature |
| `CHAT_LLM_MAX_TOKENS` | `1024` | Max tokens per response |
| `MEMORY_LLM_PROVIDER` | `ollama` | `groq` or `ollama` |
| `MEMORY_LLM_MODEL` | `qwen2.5:3b` | Memory extraction model |
| `EMBEDDING_MODEL` | `mxbai-embed-large` | Ollama embedding model |
| `EMBEDDING_DIMS` | `1024` | Vector dimensions for pgvector |
| `DEFAULT_USER_ID` | `u1` | User namespace key |
| `REMINDER_POLL_INTERVAL` | `30` | Scheduler poll interval (seconds) |
| `TELEGRAM_BOT_TOKEN` | — | Telegram bot token |
| `TELEGRAM_ALLOWED_USER` | — | Numeric Telegram user ID (security gate) |

### Memory LLM: Groq vs Ollama

```env
# Groq — recommended for accuracy
MEMORY_LLM_PROVIDER=groq
MEMORY_LLM_MODEL=llama-3.3-70b-versatile

# Ollama — fully local, no rate limits, slightly less accurate
MEMORY_LLM_PROVIDER=ollama
MEMORY_LLM_MODEL=qwen2.5:3b
```

---

## Voice Setup

Parker uses [Chatterbox TTS](https://github.com/mirbehnam/Chatterbox-TTS-Server-windows-easyInstallation) for voice cloning and [faster-whisper](https://github.com/SYSTRAN/faster-whisper) + [Silero VAD](https://github.com/snakers4/silero-vad) for speech input.

### Install Chatterbox (Windows)

```bash
git clone https://github.com/mirbehnam/Chatterbox-TTS-Server-windows-easyInstallation.git
cd Chatterbox-TTS-Server-windows-easyInstallation
.\setup.bat    # choose option 1 for NVIDIA GPU
```

### Install mpv

```bash
winget install shinchiro.mpv
# Add to PATH: C:\Program Files\MPV Player
```

### Clone a voice

Provide any clean 10–15 second audio clip — single speaker, no background music.

```python
from pydub import AudioSegment

audio = AudioSegment.from_wav("source.wav")
audio[2000:17000].export("reference.wav", format="wav")
```

```bash
copy reference.wav "Chatterbox-TTS-Server-windows-easyInstallation\reference_audio\reference.wav"
```

### Test TTS

```powershell
Invoke-WebRequest -Method POST `
  -Uri "http://localhost:8004/tts" `
  -ContentType "application/json" `
  -Body '{"text":"Good evening, sir.","language":"en","voice_mode":"clone","reference_audio_filename":"reference.wav"}' `
  -OutFile "test.wav"
```

---

## Telegram Bot

Access Parker from any device — mobile data, campus WiFi, anywhere — with full memory access.

### Setup

1. Open Telegram → `@BotFather` → `/newbot` → copy token
2. Open Telegram → `@userinfobot` → copy your numeric user ID
3. Add to `.env`: `TELEGRAM_BOT_TOKEN` and `TELEGRAM_ALLOWED_USER`
4. Run:

```bash
python telegram_interface.py
```

### Commands

| Command | Action |
|---|---|
| `/start` | Show available commands |
| `/profile` | Display identity profile |
| `/facts` | List stored facts by importance tier |
| `/projects` | List active projects with stack and status |
| Send text | Full Parker response with memory context |
| Send voice | Whisper transcription → Parker response |

---

## CLI Reference

### Input Modes

| Command | Action |
|---|---|
| `v` | Switch to voice input (Whisper + VAD) |
| `t` | Switch to text input |

### Memory Commands

| Command | Action |
|---|---|
| `/profile` | Display identity profile |
| `/facts` | List all facts, sorted by importance tier |
| `/projects` | List active projects |

### Session Commands

| Command | Action |
|---|---|
| `/clear` | Clear terminal screen |
| `exit` / `quit` / `bye` | Drain background jobs → save rollups → shutdown |
| `Ctrl+C` | Clean shutdown (same as exit) |

---

## Database Management

**Inspect episodic memory:**

```bash
python debug_db.py
```

**Full reset** — destroys all memory (destructive):

```bash
docker compose down -v
docker compose up -d
python main.py
```

---

## Engineering Notes

**Memory writes never block chat.** All extraction (profile, facts, projects, episode summary) runs in tracked background threads. `wait_for_background_jobs()` drains the queue on shutdown to prevent data loss.

**Namespace-level write locking.** Concurrent background threads writing to the same PostgreSQL namespace are serialized with per-namespace `threading.Lock` instances, preventing read-modify-write races.

**No raw transcript storage.** Episodes are summary-only. The extraction prompt produces structured JSON with topics, decisions, and open threads — not a verbatim copy of the conversation.

**JARVIS personality is enforced structurally.** A hard banned-phrases list at the prompt level plus a post-generation repair pass that detects and rewrites any response containing memory-denial language ensure the personality holds regardless of base model behavior.

**Single Groq key works.** If you only have one Groq account, set all four key variables to the same value. Rate limits will be hit faster under concurrent load, but the system degrades gracefully.

**Temporal episode retrieval bypasses semantic search.** Queries containing "yesterday" or "today" resolve directly to a date key and scan that day's chat entries by timestamp proximity — no embedding lookup needed, and no risk of semantic drift on time-anchored questions.

---

## Tech Stack

| Layer | Technology |
|---|---|
| LLM Inference | Groq (LLaMA 3.3 70B) |
| Orchestration | LangGraph |
| Vector Store | PostgreSQL + pgvector |
| Embeddings | Ollama (mxbai-embed-large, 1024-dim) |
| Speech-to-Text | faster-whisper (small, int8) + Silero VAD |
| Text-to-Speech | Chatterbox TTS (voice clone mode) |
| Terminal UI | Rich |
| Remote Access | python-telegram-bot |
| Containerization | Docker + docker compose |

---

## License

MIT — see [LICENSE](LICENSE).

---

<div align="center">

Built by **Pavan** · IIT Guwahati

</div>
