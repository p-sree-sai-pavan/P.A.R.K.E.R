<div align="center">

<img src="parker_icon.png" width="100" alt="Parker icon" />

# P.A.R.K.E.R.
### Personal AI with Persistent Memory

[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![LangGraph](https://img.shields.io/badge/LangGraph-0.2+-1C3C3C?style=flat-square&logo=langchain&logoColor=white)](https://langchain-ai.github.io/langgraph/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL+pgvector-4169E1?style=flat-square&logo=postgresql&logoColor=white)](https://github.com/pgvector/pgvector)
[![Groq](https://img.shields.io/badge/Groq-Chat_Model-F55036?style=flat-square)](https://groq.com)
[![Ollama](https://img.shields.io/badge/Ollama-Memory_Model-000000?style=flat-square)](https://ollama.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow?style=flat-square)](LICENSE)

**A CLI-first personal AI assistant that accumulates memory across every session — profile, facts, projects, and a full episodic summary tree from chat → day → week → month → year.**

[Quickstart](#quickstart) · [Architecture](#architecture) · [Memory System](#memory-system) · [Configuration](#configuration) · [CLI Reference](#cli-reference)

</div>

---

## Why Parker

Most AI assistants forget you the moment the window closes. Parker is built around the opposite assumption: every conversation should compound on the last one.

It maintains four persistent memory layers — a stable identity profile, discrete facts, active project state, and a time-indexed episodic summary tree. On each turn, relevant context from all layers is retrieved via semantic search and injected into the system prompt. After each turn, new information is extracted and written back. Memory grows continuously across sessions without ever needing to replay raw transcripts.

---

## Quickstart

### Prerequisites

- Python 3.11+
- [Docker Desktop](https://www.docker.com/products/docker-desktop/)
- [Ollama](https://ollama.com) installed and running
- [Groq API key](https://console.groq.com) (free tier works)

### 1. Clone and install

```bash
git clone https://github.com/your-username/parker.git
cd parker
pip install -r requirements.txt
```

### 2. Pull Ollama models

```bash
ollama pull qwen2.5:3b        # memory model — fast local extraction
ollama pull mxbai-embed-large # embedding model — semantic search
```

### 3. Start PostgreSQL

```bash
docker compose up -d
```

This starts `pgvector/pgvector:pg16` on port 5442. Data persists in a Docker volume by default.

### 4. Configure environment

```bash
cp .env.example .env
```

Open `.env` and set your Groq key:

```env
GROQ_API_KEY=gsk_your_key_here
```

All other defaults work out of the box. See [Configuration](#configuration) for the full reference.

### 5. Run

```bash
python main.py
```

On Windows:

```bash
run_parker.bat
```

---

## Architecture

### Runtime flow

```
START → trigger → retrieve → chat → remember → END
```

Every user message passes through four LangGraph nodes in sequence.

| Node | What it does |
|---|---|
| `trigger` | Asks the memory LLM whether the message needs retrieval and/or storage. Casual greetings skip both. |
| `retrieve` | Runs `build_context()` — assembles profile, facts, projects, and episodic memories via semantic search. |
| `chat` | Sends the assembled context + conversation history to the chat LLM and produces the reply. |
| `remember` | Fires background threads to extract and save new profile data, facts, and project updates. |

The trigger gate is the key performance optimization. A message like `"ok thanks"` costs one small LLM call and nothing else. A message like `"what were we working on yesterday"` triggers full retrieval from the episodic tree.

### Dual-model design

Parker uses two LLMs with different roles:

| Role | Default | Why |
|---|---|---|
| Chat LLM | Groq LLaMA 3.3 70B | High-quality, fast cloud inference for user-facing responses |
| Memory LLM | Ollama Qwen2.5:3b | Local, zero-latency extraction for background memory writes |

This means user responses are never blocked by memory writes. All extraction runs in background threads.

### Core file map

```
parker/
├── main.py               CLI runtime — session loop, startup/shutdown hooks
├── graph.py              LangGraph state machine and all four nodes
├── retrieval.py          Memory context assembly — all four layers + time
├── database.py           PostgresStore + PostgresSaver with retry logic
├── config.py             Centralized env-var configuration
├── models.py             LLM and embedding initialization
├── interface.py          Rich-based terminal UI components
├── ears.py               Whisper + Silero VAD — speech to text
├── mouth.py              pyttsx3 — text to speech (background thread)
├── memory/
│   ├── profile.py        Stable identity extraction and storage
│   ├── facts.py          Discrete fact extraction, importance ranking, archival
│   ├── projects.py       Project state tracking across sessions
│   ├── episodes.py       Chat summary generation, episodic retrieval
│   └── rollup/
│       ├── core.py       Rollup scheduler — detects crossed time boundaries
│       ├── summarizers.py Day / week / month / year summary generation
│       └── bounds.py     Time boundary detection helpers
└── prompts/
    ├── chat.py           System prompt and memory injection template
    ├── memory.py         Extraction prompts for profile, facts, projects
    └── rollup.py         Rollup summarization prompts
```

---

## Memory System

### Four layers

**Profile** — Stable identity facts that rarely change. Name, university, branch, tools, preferences. Extracted incrementally; new values overwrite old ones by key.

**Facts** — Discrete, self-contained facts with importance levels (`critical`, `high`, `normal`, `low`). Critical facts are always injected into every prompt as hard constraints. Normal and low facts are retrieved semantically. Stale facts are archived automatically based on age thresholds.

**Projects** — Multi-session project state. Tracks name, status, stack, open threads, and a running decisions log. Project entries are created on first mention and updated each session. Completed or abandoned projects move to an archive namespace.

**Episodes** — Summary-based conversational memory organized as a time hierarchy:

```
chat turn  →  day summary  →  week summary  →  month summary  →  year summary
```

Each level is generated by the memory LLM from the level below it. Retrieval searches top-down: year → month → week → day → chat. This keeps token costs flat regardless of how many sessions have accumulated.

### Retrieval strategy

On each turn that needs retrieval, `build_context()`:

1. Loads the full profile (always — it's small)
2. Loads all critical facts (always — they are hard constraints)
3. Runs semantic search over facts, matching against both the user message and active project names
4. Loads all active projects plus semantically relevant historical projects
5. Builds an expanded episode query from the current message and recent history
6. Drills the episode tree from year → chat, filtering each level by relevance to the level above
7. Injects current datetime for temporal grounding

The assembled context is formatted and injected into the system prompt before the chat LLM is called.

### Rollup scheduling

On session start, `rollup_if_needed()` checks the last session date. If time boundaries (day, week, month, year) have been crossed since the last run, it sequentially generates summaries for each closed period. This keeps the tree up to date even if Parker is not used every day.

On session end, `refresh_active_rollups()` regenerates the current open period summaries from the latest chat data.

---

## Configuration

All settings are loaded from `.env`. Copy `.env.example` to get started.

### Database

| Variable | Default | Description |
|---|---|---|
| `DB_URI` | `postgresql://postgres:postgres@localhost:5442/postgres?sslmode=disable` | PostgreSQL connection string |
| `DB_MAX_RETRIES` | `3` | Connection retry attempts |
| `DB_RETRY_DELAY` | `2.0` | Base delay between retries (seconds; multiplied by attempt number) |

### Chat LLM

| Variable | Default | Description |
|---|---|---|
| `CHAT_LLM_PROVIDER` | `groq` | `groq` or `ollama` |
| `CHAT_LLM_MODEL` | `llama-3.3-70b-versatile` | Model name for the provider |
| `CHAT_LLM_TEMPERATURE` | `0.7` | Response creativity |
| `CHAT_LLM_MAX_TOKENS` | `1024` | Max output tokens |
| `CHAT_LLM_TIMEOUT` | `60` | Request timeout (seconds) |

### Memory LLM

| Variable | Default | Description |
|---|---|---|
| `MEMORY_LLM_PROVIDER` | `ollama` | `ollama` or `groq` |
| `MEMORY_LLM_MODEL` | `qwen2.5:3b` | Model name for extraction tasks |
| `MEMORY_LLM_TEMPERATURE` | `0` | Zero — extraction must be deterministic |
| `MEMORY_LLM_CTX` | `2048` | Context window for the memory model |

### Embeddings

| Variable | Default | Description |
|---|---|---|
| `EMBEDDING_MODEL` | `mxbai-embed-large` | Ollama embedding model |
| `EMBEDDING_DIMS` | `1024` | Vector dimensions — must match the model |

### API keys

| Variable | Required | Description |
|---|---|---|
| `GROQ_API_KEY` | Yes (if using Groq) | Get from [console.groq.com](https://console.groq.com) |

### Session defaults

| Variable | Default | Description |
|---|---|---|
| `DEFAULT_USER_ID` | `u1` | User namespace in the store |
| `DEFAULT_THREAD_ID` | `thread_u1` | Base thread ID (a timestamp suffix is appended at runtime) |

---

## CLI Reference

### Input modes

| Mode | How to activate |
|---|---|
| Text | Default on startup |
| Voice | Type `v` at the prompt |

Switch back from voice to text by typing `t`.

### Commands

| Command | What it does |
|---|---|
| `/profile` | Displays your stored memory profile |
| `/clear` | Clears the terminal and reprints the banner |
| `exit` / `quit` / `bye` | Saves session state, refreshes rollups, shuts down cleanly |
| `Ctrl+C` | Also triggers clean shutdown |

---

## Model alternatives

The default stack is Groq + Ollama. You can swap either component in `.env`.

**Chat model alternatives (Groq):**

```env
CHAT_LLM_MODEL=llama-3.3-70b-versatile   # default — best quality
CHAT_LLM_MODEL=mixtral-8x7b-32768        # longer context
CHAT_LLM_MODEL=gemma2-9b-it              # lighter, faster
```

**Fully local setup (Ollama for both):**

```env
CHAT_LLM_PROVIDER=ollama
CHAT_LLM_MODEL=llama3.2:latest
MEMORY_LLM_PROVIDER=ollama
MEMORY_LLM_MODEL=qwen2.5:3b
```

---

## Voice mode

Voice input uses [faster-whisper](https://github.com/guillaumekientz/faster-whisper) (small model, CPU, int8) with [Silero VAD](https://github.com/snakers4/silero-vad) for automatic silence detection. Speech ends automatically after ~1 second of silence. No button to hold.

Voice output uses `pyttsx3` in a background thread. Speech is non-blocking — you can type the next message while Parker is still speaking.

Install the optional VAD dependency:

```bash
pip install silero-vad
```

---

## Database management

**Reset all memory** (warning: destructive):

```bash
docker compose down -v
docker compose up -d
python main.py  # runs setup() automatically
```

**Inspect stored episodes:**

```bash
python debug_db.py
```

---

## Project structure notes

- Each session gets a unique thread ID (`thread_u1_YYYYMMDD_HHMMSS`). LangGraph checkpointer state is session-scoped. Cross-session memory is handled entirely through the PostgresStore namespaces, not the checkpointer.
- Memory writes never block the chat response. `save_facts`, `save_profile`, `save_projects`, and `write_chat_turn` all run in tracked background threads. `wait_for_background_jobs()` is called on shutdown to drain in-flight writes before the process exits.
- The episodic memory path is summary-only. Raw transcripts are not stored. This is intentional — summaries scale to years of usage; raw transcripts do not.

---

## License

MIT — see [LICENSE](LICENSE).