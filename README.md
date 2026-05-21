<div align="center">

<img src="parker_logo.png" width="160" alt="Parker Logo" />

# P · A · R · K · E · R
### **P**ersonal **A**I with **R**ecursive **K**nowledge & **E**pisodic **R**ecall

*A premium, production-grade, local-first JARVIS-style companion built with LangGraph. Employs a vector-backed hierarchical summary tree, multi-action desktop/browser orchestration, sound-activity-guided voice loops, and resilient API failovers.*

<br/>

[![Python 3.12](https://img.shields.io/badge/Python-3.12-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![LangGraph](https://img.shields.io/badge/LangGraph-0.2.x-1C3C3C?style=flat-square&logo=langchain&logoColor=white)](https://langchain-ai.github.io/langgraph/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL_+_pgvector-4169E1?style=flat-square&logo=postgresql&logoColor=white)](https://github.com/pgvector/pgvector)
[![Groq](https://img.shields.io/badge/Groq_LLaMA_70B-F55036?style=flat-square&logo=groq&logoColor=white)](https://groq.com)
[![Ollama](https://img.shields.io/badge/Ollama-Local_Embeddings-000000?style=flat-square&logo=ollama&logoColor=white)](https://ollama.com)
[![Gemini Fallback](https://img.shields.io/badge/Gemini-Resilient_Fallback-8E75C2?style=flat-square&logo=google-gemini&logoColor=white)](https://ai.google.dev/)

<br/>

> **"Most AI assistants suffer from cold starts and forget you when the session ends. Parker operates with a continuous, lived consciousness, compounding every conversation forever."**

---

[Core Philosophy](#-core-philosophy) • [LangGraph routing](#-langgraph-routing-state-machine) • [Memory Architecture](#-memory-architecture) • [Execution Senses ("The Hands")](#-execution-senses-the-hands) • [System Resilience](#-system-resilience) • [Codebase Map](#-codebase-navigation-map) • [Quickstart](#-quickstart--deployment) • [CLI Commands](#-cli-commands--controls)

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
    TriggerNode["<b>trigger_node</b><br>Classifies memory & storage needs"]
    RetrieveNode["<b>retrieve_node</b><br>Compiles profile, facts, tasks, & episodes"]
    ChatNode["<b>chat_node</b><br>Formulates response under voice rules"]
    ComputerNode["<b>computer_node</b><br>Executes Playwright, Desktop, or APIs"]
    RememberNode["<b>remember_node</b><br>Spawns background extraction queues"]
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

    %% Subgraph showing concurrent async tasks spawned in remember_node
    subgraph Async Background Pipeline [Triggered in remember_node]
        direction LR
        EP[Profile Writer]
        EF[Facts Extractor]
        EPJ[Project Ledger]
        ET[Task Tracker]
        EE[Episodic Turn Summarizer]
    end
    RememberNode -.-> EP & EF & EPJ & ET & EE
```

### Node Mechanics & execution Lifecycles

| Node | Primary Model | Blocking? | Role & Mechanics |
| :--- | :--- | :---: | :--- |
| **`trigger`** | `trigger_llm` *(Llama-3.3-70B)* | **Yes** | Evaluates input using a structured `MemoryTrigger` output to classify if the prompt needs memory retrieval (`needs_retrieval`) or contains recordable context (`needs_storage`). |
| **`retrieve`** | *Database & Cache* | **Yes** | Queries the database and local embedding cache. It bypasses retrieval entirely for greetings, math, or casual small talk to optimize performance and prevent prompt clutter. |
| **`chat`** | `chat_llm` *(Llama-3.3-70B)* | **Yes** | Formulates the response under strict British butler tone rules. If the model hallucinates or leaks a database/AI disclaimer, an automated **Memory Repair** check intervenes. |
| **`computer`**| *Native Engines* | **Yes** | Executes when `<computer_action>` tags are detected in the chat node output. Once executed, it feeds the results back to the `chat` node as fresh system context. |
| **`remember`**| *Thread Pool* | **No** | Spawns parallel thread-pool jobs to update the profile, facts, tasks, projects ledger, and write turn-level summaries, instantly returning control to the user. |

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

### 4. Episodic Summary Tree
Raw transcripts are never retained. Instead, a background summarizer distills each conversation turn into a structured JSON payload:
```json
{
  "summary": "Migrated the local text-to-speech engine to Kokoro, resolving Windows espeak-ng integration.",
  "key_topics": ["speech synthesis", "kokoro", "espeak-ng"],
  "projects_mentioned": ["Parker AI"],
  "decisions": ["Replace external Chatterbox server with direct local python library"],
  "left_unfinished": ["Fixing the sounddevice channel buffer warning"]
}
```
*   **Rollup Engine**: Upon boundary crossings (startup/shutdown checks), calendar boundaries roll turns into **Day**, **Week**, **Month**, and **Year** summaries.
*   **Semantic Traversal**: To minimize context length and database calls, a top-down tree search crawls the tree starting at Years and branches down only to relevant Months, Weeks, Days, and Turns.
*   **Temporal Short-Circuit**: Common queries referencing specific relative timeframes (e.g., "what did we fix yesterday?") bypass embedding-based semantic retrieval entirely, querying the database directly using target ISO date bounds.

---

## 🎛️ Execution Senses: "The Hands & Mouth"

Parker executes complex desktop, browser, and voice pipelines asynchronously through a suite of integrated orchestration systems:

```
                  ┌────────────── [Parker Senses] ──────────────┐
                  │                                             │
         [Voice Input (STT)]                           [Voice Output (TTS)]
         ├── Sounddevice recording                     ├── Kokoro TTS Model
         ├── Silero VAD (Silence auto-stop)            ├── British Male Voice (bm_george)
         └── Faster-Whisper transcription              └── Threaded audio streaming (mpv)
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

### 🎙️ Speech Synthesis & Voice Loops
*   **Ears (STT)**: Uses `sounddevice` to capture microphone inputs. It runs a `Silero VAD` (Voice Activity Detection) filter in a loop, automatically halting recording when silence is detected for 1.0s. It then transcribes the raw audio locally using `faster-whisper` (Small model quantized in `int8` for fast CPU execution).
*   **Mouth (TTS)**: Replaces remote servers with an offline `Kokoro` pipeline. It runs the British male voice (`bm_george`) matching the butler persona, filtering markdown and code tags before streaming the float32 audio arrays through `sounddevice` with zero gaps.

---

## 🛡️ System Resilience

### 🔄 Resilient Chat Model & Fallback
All LLM prompts are wrapped in a thread-safe `ResilientChatModel`. If the primary provider (Groq LLaMA) encounters network failures, outages, or HTTP 429 Rate Limits, the pipeline transparently fails over to Google Gemini (`gemini-2.5-flash`) via the Google AI SDK to ensure uninterrupted availability.

### 🔑 Multi-Key API Key Rotation
To prevent parallel background rollups, facts extractions, and project updates from triggering rate limits during active conversation, Parker distributes calls across four distinct Groq API key slots:
*   `GROQ_API_KEY_1`: Handles foreground **Chat Generation**.
*   `GROQ_API_KEY_2`: Handles **Rollups** and background **Project Ledger Updates**.
*   `GROQ_API_KEY_3`: Handles background **Facts Extraction** and **Episode Summaries**.
*   `GROQ_API_KEY_4`: Handles foreground **Trigger Routing** and background **Profile Updates**.

### 🔒 Namespace Thread Locks
To safeguard PostgreSQL databases during rapid multi-threaded background writes (e.g. episodic turns, facts, and profile updates saving concurrently), database execution runs under strict namespace-level thread locks (`threading.Lock`), eliminating write collisions and transaction deadlocks.

### 🛠️ JSON Repair Parser
Because LLMs often emit markdown code blocks, pythonic booleans (`True`/`False`), or trailing commas, the agent uses a recursive JSON parser (`clean_and_repair_json`). If `json.loads` fails, it cleans the string and attempts a safe evaluation via python's `ast.literal_eval`.

---

## 📁 Codebase Navigation Map

```
P.A.R.K.E.R/
├── main.py                     # CLI Entrypoint - coordinates startup greeting, console loops, and shutdown hooks
├── graph.py                    # LangGraph Routing - defines trigger, retrieve, chat, computer, and remember nodes
├── retrieval.py                # Context Compiler - aggregates facts, profile, projects, and top-down summary tree
│
├── config.py                   # Configuration - environment variable loading, API credentials, and validation
├── database.py                 # Database Engine - PostgreSQL store initialization and thread-safe namespace locks
├── models.py                   # LLM Models wrapper - handles Groq rotation, Gemini fallbacks, and Ollama embeddings
│
├── interface.py                # Console Render - Rich-based UI panel layouts, status bars, and token trackers
├── ears.py                     # Voice Input (STT) - Silero VAD-based recording and faster-whisper transcribing
├── mouth.py                    # Voice Output (TTS) - Local Kokoro pipeline synthesis and sounddevice audio streaming
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
│   ├── memory.py               # Memory Prompts - parameters for profile, facts, and task extractions
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
Clone the repository and install the dependencies:
```bash
git clone https://github.com/your-username/parker.git
cd parker
pip install -r requirements.txt
playwright install chromium
```

### 2. Configure Local Embeddings
Start the Ollama server locally and pull the embedding model:
```bash
ollama pull mxbai-embed-large
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

# Google AI Studio key for resilient Gemini fallback
GEMINI_API_KEY=AIzaSy...

# ── Database URI ──────────────────────────────────────────────────────────────
DB_URI=postgresql://postgres:postgres@localhost:5442/postgres?sslmode=disable

# ── LLM Settings ──────────────────────────────────────────────────────────────
CHAT_LLM_PROVIDER=groq
CHAT_LLM_MODEL=llama-3.3-70b-versatile
CHAT_LLM_TEMPERATURE=0.7

MEMORY_LLM_PROVIDER=groq
MEMORY_LLM_MODEL=llama-3.3-70b-versatile
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
*   `v` + `Enter`: Switches input type to **Voice Mode** (activates Whisper transcribing and Silero auto-silence recording).
*   `t` + `Enter`: Switches input type back to **Text Mode**.

### Slash Commands
*   `/profile`: Renders a structured panel containing your user traits, primary editors, and OS preferences.
*   `/facts`: Renders your personal facts list, sorted by importance level.
*   `/projects`: Displays a layout containing active development projects, their stacks, and decision log updates.
*   `/tasks`: Renders a prioritized board showing your active reminders (🔴 High, 🔸 Normal, 🔹 Low).
*   `/patterns`: Lists behavioral habits and patterns detected across your chat history.
*   `/clear`: Clears the console interface.
*   `exit` / `quit` / `bye`: Initiates a graceful shutdown (resolves background queues, runs rollups, and closes PostgreSQL connections).

---

<div align="center">
<br/>
Developed by <b>Pavan</b> · IIT Guwahati
</div>
