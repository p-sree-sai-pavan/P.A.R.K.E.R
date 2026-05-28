<div align="center">

<img src="parker_logo.png" width="160" alt="Parker Logo" />

# P · A · R · K · E · R
### **P**ersonal **A**I with **R**ecursive **K**nowledge & **E**pisodic **R**ecall

*A premium, production-grade, local-first JARVIS-style companion built with LangGraph. Employs a vector-backed hierarchical summary tree, multi-action desktop/browser orchestration, sound-activity-guided voice loops, resilient API failovers, dynamic key-rotating pools, and real-time multimodal live streams.*

<br/>

[![Python 3.11 / 3.12](https://img.shields.io/badge/Python-3.11%20%2F%203.12-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![LangGraph](https://img.shields.io/badge/LangGraph-0.2.x-1C3C3C?style=flat-square&logo=langchain&logoColor=white)](https://langchain-ai.github.io/langgraph/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL_+_pgvector-4169E1?style=flat-square&logo=postgresql&logoColor=white)](https://github.com/pgvector/pgvector)
[![Gemini Live](https://img.shields.io/badge/Gemini_Live-Websocket_Voice-8E75C2?style=flat-square&logo=google-gemini&logoColor=white)](https://ai.google.dev/)
[![Groq Pools](https://img.shields.io/badge/Groq-Key_Rotation_Pools-F55036?style=flat-square&logo=groq&logoColor=white)](https://groq.com)
[![Ollama](https://img.shields.io/badge/Ollama-Local_LLM_%26_Embed-000000?style=flat-square&logo=ollama&logoColor=white)](https://ollama.com)

<br/>

> **"Most AI assistants suffer from cold starts and forget you when the session ends. Parker operates with a continuous, lived consciousness, compounding every conversation forever."**

---

[Core Philosophy](#-core-philosophy-the-lived-consciousness) • [LangGraph State Machine](#-langgraph-routing-state-machine) • [Memory Architecture](#-memory-architecture) • [Execution Senses](#-execution-senses-the-hands-ears--mouth) • [Dynamic Skills Loader](#-openclaw-dynamic-skills-loader) • [System Resilience](#-system-resilience) • [Codebase Navigation Map](#-codebase-navigation-map) • [Quickstart](#-quickstart--deployment) • [CLI Commands](#-cli-commands--controls)

---

</div>

## 🧠 Core Philosophy: The Lived Consciousness

Parker is designed around the **"Continuous Consciousness"** pattern—inspired directly by Stark's **JARVIS**. Traditional LLM wrappers act as passive lookup engines, announcing when they search memory or run tools. Parker maintains a background awareness of your environment, active projects, tasks, and calendar timeline. 

### 🎭 Shift in Interaction Paradigm

| Aspect | Passive Lookup System (Banned) | Lived Consciousness / JARVIS (Required) |
| :--- | :--- | :--- |
| **Memory Access** | *"I searched my database and found that you worked on X yesterday."* | *"You spent yesterday refining the vector schema, sir."* |
| **Tool Execution** | *"Let me execute a weather API query for Hanamkonda..."* | *"The local feed in Hanamkonda is showing 32°C under cloudy skies."* |
| **Limitations** | *"I am a large language model and cannot remember past sessions."* | *"I don't recall that, sir." (No robotic excuses)* |
| **Background Work** | *"I will pull files for that project now."* | *"Already pulling the schematics, sir."* |

---

## 🔁 LangGraph Routing State Machine

Parker's conversational pipeline, state management, and tool executions are orchestrated as a deterministic **LangGraph state machine**.

```mermaid
graph TD
    %% Define Nodes
    StartNode([User Message])
    TriggerNode["<b>trigger_node</b><br/>Classifies memory & storage needs"]
    RetrieveNode["<b>retrieve_node</b><br/>Compiles profile, facts, tasks, skills, & episodes"]
    ChatNode["<b>chat_node</b><br/>Formulates response under voice rules"]
    ComputerNode["<b>computer_node</b><br/>Executes Playwright, Desktop, or APIs"]
    RememberNode["<b>remember_node</b><br/>Spawns background memory save"]
    EndNode([Parker Output])

    %% State flow
    StartNode --> TriggerNode
    TriggerNode --> RetrieveNode
    RetrieveNode --> ChatNode
    ChatNode --> RouteCheck{Action Detected?}
    RouteCheck -- "Yes" --> ComputerNode
    ComputerNode --> ChatNode
    RouteCheck -- "No" --> RememberNode
    RememberNode --> EndNode

    %% Subgraph showing the consolidated Unified memory writer
    subgraph Unified Background Pipeline [Triggered in remember_node]
        direction LR
        UM["Unified Memory Thread<br/>(unified-memory-save)"]
        UM -.-> P[Profile Ledger]
        UM -.-> F[Facts Database]
        UM -.-> PR[Projects Ledger]
        UM -.-> T[Task Tracker]
    end
    RememberNode -.-> UM
```

### Node Mechanics & Execution Lifecycles

| Node | Primary Model | Blocking? | Role & Mechanics |
| :--- | :--- | :---: | :--- |
| **`trigger`** | `trigger_llm` *(Qwen-32B / LLaMA-70B)* | **Yes** | Evaluates input using a structured `MemoryTrigger` output to classify if the prompt needs memory retrieval (`needs_retrieval`) or contains recordable context (`needs_storage`). |
| **`retrieve`** | *Database, Cache & Skills* | **Yes** | Queries the database, local embedding cache, and dynamic skills registry. Bypasses deep semantic search for casual talk or greetings, substituting a lightweight context compiler to maintain low latency. |
| **`chat`** | `chat_llm` *(Ollama Qwen-7B / LLaMA-70B)* | **Yes** | Formulates the response under strict British butler tone rules. If the model hallucinates or leaks a database/AI disclaimer, an automated **Memory Repair** check intervenes. |
| **`computer`**| *Native Engines* | **Yes** | Executes when `<computer_action>` tags are detected in the chat node output. Once executed, it feeds the results back to the `chat` node as fresh system context. |
| **`remember`**| *Thread Pool* | **No** | Spawns a single, atomic background thread (`unified-memory-save`) to extract and commit memory modifications concurrently without blocking the chat loop. |

---

## 🗄️ Memory Architecture

Parker's memory is divided into **four layers**, vector-indexed with PostgreSQL and `pgvector` using local Ollama embeddings.

```
       [Raw Conversation Turns]
                  │
                  ▼ (Post-Turn Async Processing)
       [Layer 4: Episodic Summary Tree]
       ├── Chat Turn Summaries (JSON metadata)
       │     └── Day Rollup Summaries
       │           └── Week Rollup Summaries
       │                 └── Month Rollup Summaries
       │                       └── Year Rollup Summaries
                  │
                  ├───► [Layer 1: Profile Ledger] (JSON Merge Schema)
                  ├───► [Layer 2: Facts Database] (Tiers: Critical, High, Normal, Low)
                  └───► [Layer 3: Projects Ledger] (Decision Log, Stack, Open Threads)
```

### 1. Profile Ledger
Stores stable, long-term personal user attributes (e.g., name, university, primary text editors, operating systems, and core locations) in a unified JSON structure. New information is dynamically merged to overwrite outdated details.

### 2. Facts Database
Stores discrete facts categorized into four importance levels, dictating their retrieval behavior and lifecycle:
*   `critical`: Injected directly into the system prompt as hard active constraints (e.g., allergies, home cities, severe limits).
*   `high`: Semantic-search retrieval on relevant query matches; never archived.
*   `normal`: Semantic-search retrieval; automatically archived to the inactive namespace after 365 days of dormancy.
*   `low`: Semantic-search retrieval; automatically archived to the inactive namespace after 90 days of dormancy.

> [!WARNING]
> **Transient Fact Guard**: The facts extraction pipeline contains strict prompt guards to prevent transient, time-dependent data (e.g., "today's weather is sunny", "current date is Tuesday", or temporary emotional states) from cluttering the facts database.

### 3. Projects Ledger
Keeps an active index of development projects containing:
*   Project name and status (`active`, `paused`, `completed`, `abandoned`).
*   Technological development stack.
*   Running decision ledger mapping timestamped updates (e.g., `2026-05-22T00:20:00: Migrated TTS to Kokoro`).
*   `open_threads`: A list of unresolved bugs, blockers, and next steps.

### 4. Consolidated Unified Memory Loop
Instead of spawning five separate asynchronous background LLM calls (which is slow, expensive, and risks database transaction collisions), Parker utilizes a **Consolidated Memory Extraction Pipeline** (`memory/unified.py`).
*   **Single-Pass Extraction**: Post-conversation, a single background task triggers the `UNIFIED_MEMORY_PROMPT` containing the existing profile, facts, tasks, and project states alongside the current turn dialogue.
*   **Atomic Database Operations**: The memory worker extracts all profile modifications, discrete facts, project changes, and new/completed tasks in a single JSON payload.
*   **Namespace Thread Locks**: Database updates are executed under strict namespace-level thread locks (`threading.Lock` on `facts`, `profile`, `projects`, and `tasks`), preventing write collisions during parallel query processing.
*   **Rollup Engine**: Calendar rollups still run as scheduled background triggers, condensing turns into Day, Week, Month, and Year summaries.
*   **Semantic Traversal**: To minimize context length, a top-down tree search crawls the rollup tree starting at Years and branches down only to relevant Months, Weeks, Days, and Turns.

---

## 🎛️ Execution Senses: "The Hands, Ears, & Mouth"

Parker executes complex desktop, browser, and voice pipelines asynchronously through a suite of integrated orchestration systems:

```
                   ┌────────────── [Parker Senses] ──────────────┐
                   │                                             │
          [Voice Input (STT)]                           [Voice Output (TTS)]
          ├── WebSocket Audio Stream                    ├── WebSocket Audio Stream
          └── Real-time local transcript                └── Real-time local transcript
                   │                                             │
                   └───────────── [Parker Actions] ──────────────┘
                   │                                             │
          [Browser Engine]                              [Desktop Automator]
          ├── Playwright Chromium                       ├── Window Focus Routing
          ├── Interactive elements mapping              ├── Keypress/Click emulation
          └── Search, Click, Type, Page-Read            └── Native app launching
```

### 💻 Computer Use Engine
When the chat node outputs action tags, the execution loop parses them. Parker can chain multiple actions in a single turn:
*   **Web Browser**: Spawns a headless Playwright instance. It scans pages, maps interactive elements (buttons, inputs), inputs texts, clicks targets, and returns markdown-rendered page contents back to the context.
*   **Desktop Automation**: Focuses target windows, retrieves open application trees, sends keystrokes, and executes mouse coordinates or commands.
*   **SearXNG Layer**: A local, federated search instance (`searxng/settings.yml`) running in Docker, falling back to DuckDuckGo search if offline.
*   **Structured APIs**: Routes structured API parameters for `weather`, `forecast`, `stock`, `crypto`, `wiki`, and `news` queries directly through optimized endpoints.

### 🎙️ Gemini Live Multimodal Voice Loop
In Voice Mode, Parker bypasses the separate Whisper STT / Kokoro TTS loop for an immersive, low-latency conversation using the **Gemini Multimodal Live API** (`live_voice.py`).
*   **Real-time WebSocket Pipeline**: Streams 16kHz mono audio input from the user's microphone directly to `gemini-2.0-flash-live-preview` over WebSockets, receiving a 24kHz raw PCM output stream.
*   **Server-side VAD**: Relies on Gemini's native activity detection to automatically detect user voice segments and trigger responses.
*   **Barge-in Support**: If the user interrupts and starts speaking while Parker is talk-streaming, the local speaker queue and sounddevice output stream are instantly cleared and reset, allowing natural conversation.
*   **Memory Injection**: Parker's system instructions and full vector-retrieved memory context (profile, constraints, relevant facts, project ledgers, tasks, and history) are compiled and injected directly as the initial system instruction of the WebSocket session.
*   **Console Echoing**: Spoken input and synthesized replies are mirrored as text transcripts in real-time in the terminal.
*   *Offline fallback*: Parker retains the local Whisper (STT) + Kokoro (TTS) loop as a robust offline/local-only voice synthesis alternative.

---

## 🔌 OpenClaw Dynamic Skills Loader

Parker features an automated, dynamic **Skills Registry** (`memory/skills.py`) aligned with OpenClaw standards. This lets the assistant discover and load specialized execution guides on demand.

*   **Registry Scanner**: Automatically scans `skills/`, `gateway/skills/`, and `gateway/.agents/skills/` for subdirectories containing frontmatter-bounded `SKILL.md` files.
*   **Semantic Relevance Matcher**: Computes keyword-based overlap scores (ignoring common stop words) comparing the user's input query with the names and descriptions of registered skills.
*   **Token Budget Controller**:
    *   Injects only highly relevant skills (ranked with description details) into the prompt context to keep context lengths small and reduce latency.
    *   Falls back to a compact XML layout (omitting descriptions) or omits irrelevant skills entirely if the prompt size exceeds budget limits (default 8,000 characters).
*   **Console Inspection**: Users can inspect all detected skills inside a custom console panel using the `/skills` command.

---

## 🛡️ System Resilience

### 🔄 Groq API Key Rotation Pool
To prevent background workers (Unified Memory save, episodic rollups, and graph triggers) from crashing due to Groq rate limits, Parker runs an automated API rotation system (`models.py`):
*   **Rotated Chat Model**: Implements `RotatedChatModel` and `RotatedStructuredModel` wrappers that maintain a pool of available keys (`GROQ_API_KEY_1` to `GROQ_API_KEY_4`).
*   **API Load Balancing**: When a 429 Rate Limit or Quota Exceeded error is intercepted, the wrapper automatically rotates to the next key and retries the execution.
*   **Ollama Fallback**: If all keys in the rotation pool fail, it falls back to a local Ollama model to ensure continuous operability.

### ⚡ Task-Specific LLM Allocation
Parker splits LLM processing to maximize rate limit efficiency:
*   **Lightweight / Summary Tasks**: Graph triggers, conversational rollups, project ledgers, and episodic turns are offloaded to **Qwen 32B** (`qwen/qwen3-32b`), which features higher rate limit ceilings.
*   **High-Reasoning Tasks**: Facts extraction and profile updates are handled by **LLaMA 3.3 70B** (`llama-3.3-70b-versatile`).

### 🛠️ Robust JSON Repair Parser
Because models may occasionally output trailing commas, markdown fences, or pythonic booleans (`True`/`False`), the database parser runs a recursive `clean_and_repair_json` parser. If standard `json.loads` fails, it falls back to a secure python `ast.literal_eval` parsing structure.

---

## 📁 Codebase Navigation Map

```
P.A.R.K.E.R/
├── main.py                     # CLI Entrypoint - coordinates startup greeting, console loops, and shutdown hooks
├── graph.py                    # LangGraph Routing - defines trigger, retrieve, chat, computer, and remember nodes
├── retrieval.py                # Context Compiler - compiles facts, profile, projects, skills, and rollups
│
├── config.py                   # Configuration - environment variable loading, API credentials, and validation
├── database.py                 # Database Engine - PostgreSQL store initialization and thread-safe namespace locks
├── models.py                   # LLM Models wrapper - handles Groq rotation, Gemini fallbacks, and Ollama embeddings
│
├── interface.py                # Console Render - Rich-based UI panel layouts, status bars, and token trackers
├── live_voice.py               # Gemini Live voice loop - WebSocket live-streaming and multi-device PCM routing
├── ears.py                     # Offline STT - Silero VAD-based recording and faster-whisper transcribing
├── mouth.py                    # Offline TTS - Local Kokoro pipeline synthesis and sounddevice audio streaming
├── make_overview.py            # Docx Exporter - Generates comprehensive DOCX files mapping architecture schemas
│
├── computer/                   # 💻 Tool Orchestration Engine ("The Hands")
│   ├── agent.py                # Action Parser - extracts computer actions and runs the JSON repair parser
│   ├── apis.py                 # Core APIs - structured logic for weather, stocks, crypto, news, and holidays
│   ├── search.py               # Search Core - connects to local SearXNG instance with DuckDuckGo fallback
│   ├── browser.py              # Playwright Wrapper - automates navigations, clicks, types, and reads
│   └── desktop.py              # Windows Automation - handles native applications, window focus, and keyboard inputs
│
├── memory/                     # 🧠 Memory Storage & Maintenance Pipelines
│   ├── unified.py              # Unified Memory - atomic post-turn extraction of profile, facts, tasks, and projects
│   ├── skills.py               # Skills loader - dynamic scanning, keyword ranking, and budget filtering
│   ├── profile.py              # Profile writer - tracks user traits and updates the JSON profile configuration
│   ├── facts.py                # Facts manager - extracts facts, rates importance, and handles stale archives
│   ├── projects.py             # Projects tracker - manages technology stacks, decisions, and open threads
│   ├── tasks.py                # Task board - handles status mapping, priority parsing, and task archiving
│   ├── patterns.py             # Habit detector - analyzes behavior patterns across previous days
│   ├── utils.py                # Memory Utilities - vector search execution, scans, and background queue workers
│   └── rollup/                 # Rollup Tree Scheduler
│       ├── core.py             # Boundary controller - checks elapsed time and triggers calendar rollups
│       ├── summarizers.py      # Summary rollup algorithms (Turns -> Day -> Week -> Month -> Year)
│       └── bounds.py           # ISO calendar calculations for time grouping boundaries
│
├── prompts/                    # 📝 Core LLM Prompts
│   ├── chat.py                 # Main Chat Prompt - guides JARVIS voice limits, options, and live-data guards
│   ├── memory.py               # Memory Prompts - parameters for unified extraction, profiles, and facts
│   └── rollup.py               # Rollup Prompts - structures for day, week, month, and year rollups
│
└── searxng/
    └── settings.yml            # SearXNG configuration for localized search routing
```

---

## 🚀 Quickstart & Deployment

### 📋 System Prerequisites
Ensure your local host machine has the following tools installed:
*   **Python**: Version `3.11` or `3.12` *(Note: Kokoro dependencies do not support Python 3.13+)*
*   **Docker**: Docker Desktop (or equivalent) to run background databases and search containers.
*   **mpv & espeak-ng**: Required on your system path for voice synthesis and audio playback.
    *   *Windows*: Install via [espeak-ng releases](https://github.com/espeak-ng/espeak-ng/releases) and add `espeak-ng.exe` directory to your system Environment `PATH`.

---

### 1. Installation
Clone the repository and install dependencies (including the Google GenAI SDK for the live voice mode):
```bash
git clone https://github.com/your-username/parker.git
cd parker
pip install -r requirements.txt
pip install google-genai
playwright install chromium
```

### 2. Configure Local Embeddings
Start the Ollama server locally and pull the embedding model:
```bash
ollama pull mxbai-embed-large
```
Make sure you also pull your default local model if utilizing Ollama for chat:
```bash
ollama pull qwen2.5:7b
```

### 3. Spin Up Docker Stack
Initialize PostgreSQL (with `pgvector` enabled) and the SearXNG search client:
```bash
docker compose up -d
```

### 4. Setup Environment Config
Copy the environment variables template and configure your API keys:
```bash
cp .env.example .env
```

#### `.env` Template
```env
# ── API Keys ──────────────────────────────────────────────────────────────────
# Distribute across multiple keys to prevent rate limits, or use the same key.
GROQ_API_KEY_1=gsk_...
GROQ_API_KEY_2=gsk_...
GROQ_API_KEY_3=gsk_...
GROQ_API_KEY_4=gsk_...

# Google AI Studio key for resilient Gemini fallback and Live WebSocket Voice loop
GEMINI_API_KEY=AIzaSy...

# ── Database URI ──────────────────────────────────────────────────────────────
DB_URI=postgresql://postgres:postgres@localhost:5442/postgres?sslmode=disable

# ── LLM Settings ──────────────────────────────────────────────────────────────
CHAT_LLM_PROVIDER=ollama
CHAT_LLM_MODEL=qwen2.5:7b
CHAT_LLM_TEMPERATURE=0.7
CHAT_LLM_MAX_TOKENS=1024
CHAT_LLM_CTX=32768
OLLAMA_BASE_URL=http://localhost:11434

MEMORY_LLM_PROVIDER=gemini
MEMORY_LLM_MODEL=gemini-2.5-flash
```

### 5. Launch Parker
Run the startup script:
```bash
# Windows
run_parker.bat

# Linux / macOS
python main.py
```

---

## 🎛️ CLI Commands & Controls

Once the console banner boots up and the status bar is active, you can interact with Parker using both keystrokes and slash commands:

### Keyboard Mode Toggles
*   `v` + `Enter`: Switches input type to **Voice Mode** (starts the live Gemini WebSocket session).
*   `t` + `Enter`: Switches input type back to **Text Mode**.

### Slash Commands
*   `/profile`: Renders a structured panel containing your user traits, primary editors, and OS preferences.
*   `/facts`: Renders your personal facts list, sorted by importance level.
*   `/projects`: Displays a layout containing active development projects, their stacks, and decision log updates.
*   `/tasks`: Renders a prioritized board showing your active reminders (🔴 High, 🔸 Normal, 🔹 Low).
*   `/skills`: Lists all detected OpenClaw skills, their description summaries, and relative file paths.
*   `/patterns`: Lists behavioral habits and patterns detected across your chat history.
*   `/clear`: Clears the console interface.
*   `exit` / `quit` / `bye`: Initiates a graceful shutdown (resolves background queues, runs rollups, and closes PostgreSQL connections).

---

<div align="center">
<br/>
Developed by <b>Pavan</b> · IIT Guwahati
</div>
