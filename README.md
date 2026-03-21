<div align="center">

<img src="parker_icon.png" width="120" alt="Parker AI Logo" />

# P.A.R.K.E.R.

### **Personal AI with Retrieval, Knowledge, Episodic memory & Reminders**

[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![LangGraph](https://img.shields.io/badge/LangGraph-Orchestrated-1C3C3C?style=for-the-badge&logo=langchain&logoColor=white)](https://langchain-ai.github.io/langgraph/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-pgvector-4169E1?style=for-the-badge&logo=postgresql&logoColor=white)](https://github.com/pgvector/pgvector)
[![Groq](https://img.shields.io/badge/Groq-Llama_3.3_70B-F55036?style=for-the-badge)](https://groq.com)
[![Ollama](https://img.shields.io/badge/Ollama-Local_LLM-000000?style=for-the-badge)](https://ollama.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-A855F7?style=for-the-badge)](LICENSE)

**An AI assistant that actually remembers you.**
Not a chatbot with a context window — a persistent memory system that learns who you are,
tracks your projects, manages reminders without nagging, and recalls conversations from months ago.

[Features](#-features) · [Architecture](#%EF%B8%8F-architecture) · [Quickstart](#-quickstart) · [Configuration](#%EF%B8%8F-configuration) · [Memory System](#-the-memory-system) · [API](#-api-reference)

---

</div>

## ✨ Features

<table>
<tr>
<td width="50%">

### 🧠 Persistent Memory
- **Profile learning** — automatically extracts and updates who you are
- **Fact extraction** — stores discrete facts with importance levels (`critical` → `low`)
- **Project tracking** — multi-session projects with decisions log, stack, and open threads
- **Episodic memory** — hierarchical rollup: `chat → day → week → month → year → decade`
- **Semantic search** — finds relevant memories via pgvector embeddings, not keyword matching

</td>
<td width="50%">

### 🔔 Intelligent Reminders
- **Psychology-based gating** — never nags, never fires on greetings/acknowledgments
- **Data-driven conditions** — `specific_time`, `time_range`, `on_mention`, `before_next_session`
- **Priority-based snooze** — urgent resurfaces every session, low waits 5 sessions
- **Completion detection** — "I already did that" → auto-marks done, never mentions again
- **Candidate promotion** — vague tasks become candidates, only promoted on reconfirmation

</td>
</tr>
<tr>
<td width="50%">

### 🎙️ Multimodal I/O
- **Voice input** — Whisper (faster-whisper) + Silero VAD for auto-stop on silence
- **Voice output** — pyttsx3 text-to-speech, fully local, zero latency
- **Desktop GUI** — PySide6 premium dark theme with streaming markdown
- **CLI mode** — text/voice switchable terminal interface
- **API server** — FastAPI + WebSocket for streaming integration

</td>
<td width="50%">

### ⚡ Dual-LLM Architecture
- **Chat LLM** — Groq Llama 3.3 70B for high-quality responses
- **Memory LLM** — Ollama Qwen 2.5 3B for fast, local extraction
- **Smart trigger** — skips memory operations on casual chat (saves LLM calls)
- **Streaming** — token-by-token response streaming in GUI and WebSocket
- **Background processing** — memory extraction runs after response, never blocks

</td>
</tr>
</table>

---

## 🏗️ Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                          ENTRY POINTS                                │
│  ┌──────────┐   ┌──────────┐   ┌──────────────┐   ┌──────────────┐  │
│  │ app.py   │   │ main.py  │   │ api/main.py  │   │ reminder.py  │  │
│  │ (GUI)    │   │ (CLI)    │   │ (FastAPI)    │   │ (Poller)     │  │
│  └────┬─────┘   └────┬─────┘   └──────┬───────┘   └──────┬───────┘  │
│       │              │                │                   │          │
│       └──────────────┴────────────────┴───────────────────┘          │
│                              │                                       │
│                    ┌─────────▼──────────┐                            │
│                    │     graph.py       │  LangGraph Orchestration    │
│                    │  (State Machine)   │                            │
│                    └─────────┬──────────┘                            │
│                              │                                       │
│         ┌────────────────────┼────────────────────┐                  │
│         ▼                    ▼                    ▼                  │
│  ┌─────────────┐   ┌────────────────┐   ┌──────────────┐           │
│  │  trigger     │   │   retrieve     │   │    chat      │           │
│  │  (Memory LLM)│   │  (retrieval.py)│   │  (Chat LLM)  │           │
│  │  Should I    │   │  Build 7-layer │   │  Generate     │           │
│  │  remember?   │   │  context       │   │  response     │           │
│  └──────┬───────┘   └────────┬───────┘   └──────┬───────┘           │
│         │                    │                   │                   │
│         │                    │                   ▼                   │
│         │                    │           ┌──────────────┐            │
│         │                    │           │   remember   │            │
│         │                    │           │  Extract &   │            │
│         │                    │           │  store new   │            │
│         │                    │           │  memories    │            │
│         │                    │           └──────────────┘            │
│         │                    │                                       │
│         │                    ▼                                       │
│  ┌──────┴────────────────────────────────────────────────────────┐   │
│  │                    MEMORY LAYER (memory/)                     │   │
│  │  ┌──────────┐ ┌────────┐ ┌────────┐ ┌──────────┐ ┌────────┐  │   │
│  │  │ profile  │ │ facts  │ │ tasks  │ │ projects │ │episodes│  │   │
│  │  │ (.py)    │ │ (.py)  │ │ (.py)  │ │ (.py)    │ │ (.py)  │  │   │
│  │  └──────────┘ └────────┘ └────────┘ └──────────┘ └────────┘  │   │
│  │  ┌──────────┐ ┌────────────────┐ ┌──────────┐ ┌───────────┐  │   │
│  │  │  gate    │ │ reminder_gate  │ │  rollup  │ │  utils    │  │   │
│  │  │ (store)  │ │ (display)      │ │ (5-level)│ │ (shared)  │  │   │
│  │  └──────────┘ └────────────────┘ └──────────┘ └───────────┘  │   │
│  └───────────────────────────┬───────────────────────────────────┘   │
│                              │                                       │
│                    ┌─────────▼──────────┐                            │
│                    │   PostgreSQL       │  pgvector + LangGraph       │
│                    │   (database.py)    │  Store & Checkpointer      │
│                    └────────────────────┘                            │
└──────────────────────────────────────────────────────────────────────┘
```

### Graph Flow

```
START → trigger → retrieve → chat → remember → END
```

| Node | LLM | Purpose |
|------|-----|---------|
| **trigger** | Memory LLM | Decides if retrieval/storage is needed (skips on "hello", "ok") |
| **retrieve** | Memory LLM | Builds 7-layer context: profile, projects, critical facts, relevant facts, reminders, episodes, time |
| **chat** | Chat LLM | Generates the user-facing response — **only node that streams** |
| **remember** | Memory LLM | Extracts facts, profile updates, tasks, project changes in background threads |

---

## 🚀 Quickstart

### Prerequisites

| Requirement | Purpose |
|-------------|---------|
| [Python 3.11+](https://python.org) | Runtime |
| [Docker Desktop](https://docker.com) | PostgreSQL + pgvector database |
| [Ollama](https://ollama.com) | Local memory LLM + embeddings |
| [Groq API Key](https://console.groq.com) | Chat LLM (free tier available) |

### 1. Clone & Install

```bash
git clone https://github.com/p-sree-sai-pavan/P.A.R.K.E.R.git
cd P.A.R.K.E.R
pip install -r requirements.txt
```

### 2. Pull Ollama Models

```bash
ollama pull qwen2.5:3b          # Memory extraction LLM
ollama pull mxbai-embed-large   # Embedding model (1024 dims)
```

### 3. Start Database

```bash
docker compose up -d
```

> This starts pgvector/pgvector:pg16 on port **5442**.

### 4. Configure Environment

```bash
cp .env.example .env
```

Edit `.env` and add your Groq API key:

```env
GROQ_API_KEY=gsk_your_key_here
```

### 5. Launch

<table>
<tr>
<td align="center"><b>🖥️ Desktop GUI</b></td>
<td align="center"><b>⌨️ Terminal CLI</b></td>
<td align="center"><b>🌐 API Server</b></td>
</tr>
<tr>
<td>

```bash
python app.py
```

or double-click `run_parker.bat`

</td>
<td>

```bash
python main.py
```

Supports text + voice mode switching

</td>
<td>

```bash
python api/main.py
```

FastAPI on `http://localhost:8000`

</td>
</tr>
</table>

---

## ⚙️ Configuration

All settings are managed via environment variables (`.env` file). See [`.env.example`](.env.example) for the full template.

### LLM Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `CHAT_LLM_PROVIDER` | `groq` | Chat LLM provider (`groq` or `ollama`) |
| `CHAT_LLM_MODEL` | `llama-3.3-70b-versatile` | Chat model name |
| `CHAT_LLM_TEMPERATURE` | `0.7` | Response creativity (0.0–1.0) |
| `CHAT_LLM_MAX_TOKENS` | `1024` | Max response length |
| `MEMORY_LLM_PROVIDER` | `ollama` | Memory LLM provider (`ollama` or `groq`) |
| `MEMORY_LLM_MODEL` | `qwen2.5:3b` | Memory extraction model |
| `EMBEDDING_MODEL` | `mxbai-embed-large` | Ollama embedding model |
| `EMBEDDING_DIMS` | `1024` | Embedding dimensions |

### Database Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `DB_URI` | `postgresql://postgres:postgres@localhost:5442/postgres` | PostgreSQL connection string |
| `DB_MAX_RETRIES` | `3` | Connection retry attempts |
| `DB_RETRY_DELAY` | `2.0` | Delay between retries (seconds) |

### API Keys

| Variable | Required | Description |
|----------|----------|-------------|
| `GROQ_API_KEY` | Yes (if using Groq) | Get free at [console.groq.com](https://console.groq.com) |

---

## 🧠 The Memory System

Parker's memory isn't a monolithic blob. It's five specialized modules, each with its own storage strategy, search method, and lifecycle.

### Memory Modules

```mermaid
graph TD
    A["👤 Profile"] -->|"Single document, always loaded"| DB[(PostgreSQL + pgvector)]
    B["📝 Facts"] -->|"Categorized, importance-ranked"| DB
    C["✅ Tasks"] -->|"Condition-driven, snooze logic"| DB
    D["📁 Projects"] -->|"Multi-session, decision log"| DB
    E["📖 Episodes"] -->|"Hierarchical rollup"| DB

    style A fill:#818cf8,stroke:#4f46e5,color:#fff
    style B fill:#34d399,stroke:#059669,color:#fff
    style C fill:#fb923c,stroke:#ea580c,color:#fff
    style D fill:#f472b6,stroke:#db2777,color:#fff
    style E fill:#60a5fa,stroke:#2563eb,color:#fff
```

<table>
<tr>
<th>Module</th>
<th>What it stores</th>
<th>Load strategy</th>
<th>Lifecycle</th>
</tr>
<tr>
<td><b>Profile</b></td>
<td>Name, university, tools, preferences</td>
<td>Full load every turn</td>
<td>Permanent — overwritten on change</td>
</tr>
<tr>
<td><b>Facts</b></td>
<td>Discrete knowledge with importance</td>
<td>Critical: full scan · Others: semantic search</td>
<td><code>critical/high</code>: permanent · <code>normal</code>: archive at 365d · <code>low</code>: archive at 90d</td>
</tr>
<tr>
<td><b>Tasks</b></td>
<td>Reminders, goals, events</td>
<td>Full scan + condition engine + reminder gate</td>
<td>Completed → fades after <code>fade_after_days</code> · Recurring → resets on completion</td>
</tr>
<tr>
<td><b>Projects</b></td>
<td>Multi-step ongoing work</td>
<td>Active: full scan · Historical: semantic search</td>
<td>Completed/abandoned → auto-archived on session start</td>
</tr>
<tr>
<td><b>Episodes</b></td>
<td>Conversation summaries</td>
<td>Hierarchical drill-down: decade → year → month → week → day → chat</td>
<td>Auto-rolled up on time boundary crossings</td>
</tr>
</table>

### Episodic Rollup Hierarchy

Parker compresses conversations over time, just like human memory:

```
Session end → Chat entry written (raw summary)
New day     → Yesterday's chats    → Day summary
New week    → Last week's days     → Week summary
New month   → Last month's weeks   → Month summary
New year    → Last year's months   → Year summary
New decade  → Last decade's years  → Decade summary
```

> **Search strategy:** When you ask "what did I work on last March?", Parker doesn't scan all 700 chat entries. It drills down: `decade → year → month → week → day → chat`, searching only 10–15 entries total.

### Reminder Pipeline

```
User message
    │
    ▼
check_conditions()          ← Time/keyword/condition matching
    │
    ▼
reminder_gate.run()         ← Psychology-based suppression
    │                         • Greeting? → suppress all
    │                         • "ok"? → suppress all
    │                         • Already discussed? → suppress
    │                         • User completed it? → mark done
    │
    ▼
Approved reminders only → injected into system prompt
```

### Memory Gate (Storage)

Not everything the LLM extracts becomes a real memory:

```
LLM extracts task
    │
    ▼
gate.evaluate_item()
    │
    ├── due time set?          → STORE  (100% intent)
    ├── urgent/high priority?  → STORE  (95% confidence)
    ├── time-bound condition?  → STORE  (95% confidence)
    ├── speculative language?  → REJECT ("maybe", "thinking about")
    ├── too short?             → REJECT (< 2 words)
    ├── conditioned reminder?  → STORE  (85% confidence)
    └── unconditioned?         → CANDIDATE (65% confidence)
                                    │
                                    ▼
                            Candidate promoted if:
                            • User mentions it again  OR
                            • Confidence reaches 0.8+
```

---

## 🌐 API Reference

Start the API server with `python api/main.py` (runs on `http://localhost:8000`).

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/` | Health check — returns `{"status": "online"}` |
| `POST` | `/chat` | Send message, get response |
| `WS` | `/ws/chat` | WebSocket streaming chat |
| `GET` | `/memory/tasks` | List all pending tasks |
| `GET` | `/memory/projects` | List all active projects |
| `GET` | `/memory/profile` | Get user profile |

### Chat Request

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "What projects am I working on?"}'
```

### WebSocket Streaming

```javascript
const ws = new WebSocket("ws://localhost:8000/ws/chat");
ws.send("Help me debug this function");
ws.onmessage = (e) => {
  const data = JSON.parse(e.data);
  if (data.type === "token") process.stdout.write(data.content);
  if (data.type === "done") console.log("\n--- Done ---");
};
```

---

## 📁 Project Structure

```
P.A.R.K.E.R/
├── app.py                  # Desktop GUI (PySide6) — premium dark theme
├── main.py                 # CLI entry point — text/voice modes
├── graph.py                # LangGraph state machine orchestration
├── models.py               # Dual-LLM configuration (Groq + Ollama)
├── prompts.py              # All system & extraction prompts
├── retrieval.py            # 7-layer context assembly for each turn
├── database.py             # PostgreSQL connection management
├── config.py               # Centralized env-based configuration
├── ears.py                 # Voice input — Whisper + Silero VAD
├── mouth.py                # Voice output — pyttsx3 TTS
├── reminder.py             # Background reminder polling thread
│
├── memory/                 # Memory subsystem
│   ├── profile.py          # User identity (single document)
│   ├── facts.py            # Facts with importance & archival
│   ├── tasks.py            # Task extraction, conditions, snooze
│   ├── projects.py         # Multi-session project tracking
│   ├── episodes.py         # Episodic memory with drill-down search
│   ├── rollup.py           # 5-level temporal rollup engine
│   ├── gate.py             # Storage gate — reject/candidate/store
│   ├── reminder_gate.py    # Display gate — suppress nagging
│   └── utils.py            # Shared: search, parse, format
│
├── api/
│   └── main.py             # FastAPI server with WebSocket streaming
│
├── docker-compose.yaml     # pgvector PostgreSQL container
├── requirements.txt        # Python dependencies
├── .env.example            # Environment variable template
├── run_parker.bat          # Windows one-click launcher
└── parker_icon.png         # Application icon
```

---

## 🧩 Tech Stack

| Layer | Technology | Role |
|-------|-----------|------|
| **Orchestration** | LangGraph | State machine for conversation flow |
| **Chat LLM** | Groq (Llama 3.3 70B) | High-quality response generation |
| **Memory LLM** | Ollama (Qwen 2.5 3B) | Fast local extraction & summarization |
| **Embeddings** | Ollama (mxbai-embed-large) | 1024-dim vectors for semantic search |
| **Database** | PostgreSQL + pgvector | Persistent storage + vector similarity |
| **Checkpointing** | LangGraph PostgresSaver | Conversation history across sessions |
| **Voice Input** | faster-whisper + Silero VAD | Speech-to-text with auto-stop |
| **Voice Output** | pyttsx3 (SAPI5) | Local text-to-speech |
| **Desktop GUI** | PySide6 (Qt) | Premium dark-themed interface |
| **API** | FastAPI + WebSockets | REST + streaming endpoints |
| **Infrastructure** | Docker Compose | One-command database setup |

---

## 🧪 Design Principles

> These aren't just guidelines — they're hard constraints enforced at every layer.

### 1. **Memory is passive, never a script**
Memory informs responses only when it improves accuracy. Parker never volunteers "You have a goal to..." unprompted.

### 2. **Nagging destroys trust faster than being unhelpful**
A reminder shown at the wrong time is worse than no reminder. Every reminder passes through a psychology-based gate before reaching the user.

### 3. **Completion = closure**
When you say "I finished that", the topic is dead for the session. No re-confirmation, no "great job!", no follow-up questions.

### 4. **Acknowledgments are not queries**
"ok", "got it", "thanks" are conversational closes. They never trigger reminders or new information.

### 5. **Current message is absolute ground truth**
What you're saying right now always overrides what memory says you said before.

---

## 🔍 How Context is Built Per Turn

Every time you send a message, `retrieval.py` assembles this context for the LLM:

```
1. Profile          → always full, no search
2. Active projects  → always full (used as search context for facts)
3. Critical facts   → always full (non-negotiable constraints)
4. Relevant facts   → semantic search (message + project names)
5. Archive facts    → semantic search (low-priority surface)
6. Tasks/Reminders  → condition check → reminder gate → approved only
7. Episodes         → hierarchical drill-down search
8. Current time     → injected last
```

---

## 🤝 Contributing

1. **Fork** the repository
2. **Create** a feature branch (`git checkout -b feat/your-feature`)
3. **Commit** your changes (`git commit -m "feat: add new feature"`)
4. **Push** to your branch (`git push origin feat/your-feature`)
5. **Open** a Pull Request

### Development Setup

```bash
# Clone your fork
git clone https://github.com/YOUR_USERNAME/P.A.R.K.E.R.git
cd P.A.R.K.E.R

# Create virtual environment
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # macOS/Linux

# Install dependencies
pip install -r requirements.txt

# Pull required Ollama models
ollama pull qwen2.5:3b
ollama pull mxbai-embed-large

# Start database
docker compose up -d

# Configure environment
cp .env.example .env
# Edit .env with your GROQ_API_KEY

# Run
python app.py
```

---

## 📄 License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.

---

<div align="center">

**Built with intent by [Pavan](https://github.com/p-sree-sai-pavan)**

*Parker doesn't just chat — it remembers.*

</div>
