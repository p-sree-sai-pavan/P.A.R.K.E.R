<div align="center">

<img src="parker_icon.png" width="120" alt="Parker icon" />

# P.A.R.K.E.R.

### Personal AI with persistent memory

[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![LangGraph](https://img.shields.io/badge/LangGraph-Orchestrated-1C3C3C?style=for-the-badge&logo=langchain&logoColor=white)](https://langchain-ai.github.io/langgraph/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-pgvector-4169E1?style=for-the-badge&logo=postgresql&logoColor=white)](https://github.com/pgvector/pgvector)
[![Groq](https://img.shields.io/badge/Groq-Chat_Model-F55036?style=for-the-badge)](https://groq.com)
[![Ollama](https://img.shields.io/badge/Ollama-Memory_Model-000000?style=for-the-badge)](https://ollama.com)

**Parker is a CLI-first AI assistant that remembers who you are, what you are building, and what you talked about before.**

It uses structured memory instead of relying on a single chat window, so context can grow across sessions without collapsing into one long transcript.

[Highlights](#highlights) | [Memory System](#memory-system) | [Architecture](#architecture) | [Quickstart](#quickstart)

</div>

---

## Highlights

| Capability | What Parker does |
|---|---|
| Persistent identity memory | Learns stable details about you through profile memory |
| Fact memory | Saves important user facts and retrieves them when relevant |
| Project memory | Tracks active and related projects across multiple sessions |
| Episodic memory tree | Stores chat summaries and rolls them into day, week, month, and year summaries |
| Semantic retrieval | Uses pgvector embeddings to find relevant memories, not just keyword matches |
| Dual-model design | Uses a strong chat model for replies and a smaller memory model for extraction and summarization |
| Terminal experience | Runs in a Rich-powered CLI with both text and voice interaction |

## Why Parker

Most assistants only remember the current conversation window.

Parker is built around a memory pipeline:

- each chat turn becomes a searchable summary
- chat summaries are rolled up into higher-level time summaries
- retrieval moves through the memory tree instead of blindly scanning everything
- profile, facts, and projects are injected alongside episodic context

That gives Parker a more stable way to answer questions like:

- What do you know about me?
- What project was I working on last week?
- What were we discussing yesterday?
- What decisions did I make around this project before?

## Memory System

Parker's episodic memory is organized as a time hierarchy:

```text
chat -> day -> week -> month -> year
```

### How it works

1. Every successful turn is summarized and saved at the chat level.
2. Completed time periods are rolled upward into day, week, month, and year summaries.
3. Retrieval searches the higher levels first and then narrows toward the most relevant lower-level summaries.

### Memory layers

- `profile`
  - stable identity and preference information
- `facts`
  - discrete important facts about the user
- `projects`
  - active work, decisions, and related history
- `episodes`
  - summary-based conversational memory across time

## Architecture

### Runtime flow

```text
START -> trigger -> retrieve -> chat -> remember -> END
```

### Node roles

| Node | Purpose |
|---|---|
| `trigger` | Decides whether the current message needs retrieval and storage |
| `retrieve` | Builds context from profile, facts, projects, episodes, and current time |
| `chat` | Produces the user-facing response |
| `remember` | Updates profile, facts, and projects after the reply |

### Core files

| File | Responsibility |
|---|---|
| `main.py` | CLI runtime, session flow, input/output loop |
| `graph.py` | LangGraph orchestration |
| `retrieval.py` | Memory context assembly |
| `database.py` | PostgreSQL store, vectors, and checkpointer setup |
| `memory/episodes.py` | Chat summary storage and episodic retrieval |
| `memory/rollup/core.py` | Rollup scheduling and refresh |
| `memory/rollup/summarizers.py` | Day, week, month, and year summary generation |

## Model Stack

| Component | Default role |
|---|---|
| Chat model | User-facing response generation |
| Memory model | Trigger routing, extraction, chat summarization, and rollups |
| Embedding model | Semantic search over stored memory |

By default, the repo is configured around:

- Groq for the main chat model
- Ollama Qwen for memory work
- Ollama embeddings for vector search

## Interface

Parker is built as a terminal-native assistant.

- Rich-based terminal UI
- text mode for quick chat
- voice mode with speech-to-text
- spoken replies through local text-to-speech

## Quickstart

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Pull the Ollama models

```bash
ollama pull qwen2.5:3b
ollama pull mxbai-embed-large
```

### 3. Start PostgreSQL with pgvector

```bash
docker compose up -d
```

### 4. Configure environment variables

```bash
cp .env.example .env
```

Add your Groq key if you are using the default chat provider:

```env
GROQ_API_KEY=gsk_your_key_here
```

### 5. Run Parker

```bash
python main.py
```

On Windows you can also launch:

```bash
run_parker.bat
```

## Configuration

Important `.env` settings:

- `CHAT_LLM_PROVIDER`
- `CHAT_LLM_MODEL`
- `CHAT_LLM_TEMPERATURE`
- `CHAT_LLM_MAX_TOKENS`
- `MEMORY_LLM_PROVIDER`
- `MEMORY_LLM_MODEL`
- `EMBEDDING_MODEL`
- `EMBEDDING_DIMS`
- `DB_URI`
- `DB_MAX_RETRIES`
- `DB_RETRY_DELAY`
- `GROQ_API_KEY`

See [`.env.example`](.env.example) for the full template.

## Example Prompts

- What do you know about me?
- What are my active projects right now?
- What were we talking about yesterday?
- What did I focus on this month?
- Do you remember anything about my branch or university?

## Project Layout

```text
Parker/
|-- main.py
|-- graph.py
|-- retrieval.py
|-- database.py
|-- models.py
|-- interface.py
|-- ears.py
|-- mouth.py
|-- prompts/
|   |-- chat.py
|   `-- rollup.py
|-- memory/
|   |-- episodes.py
|   |-- facts.py
|   |-- profile.py
|   |-- projects.py
|   |-- utils.py
|   `-- rollup/
|       |-- __init__.py
|       |-- bounds.py
|       |-- core.py
|       `-- summarizers.py
|-- docker-compose.yml
|-- requirements.txt
`-- run_parker.bat
```

## Notes

- The current episodic memory path is summary-based rather than exact raw transcript replay.
- The memory tree is designed for retrieval quality and long-session scalability.
- For the cleanest behavior after architecture changes, resetting the database is recommended.

## License

MIT
