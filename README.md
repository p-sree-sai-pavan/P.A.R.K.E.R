# P.A.R.K.E.R.

Persistent AI assistant with a real memory system.

Parker is a CLI-first assistant that remembers you across sessions using PostgreSQL, pgvector, and a hierarchical episodic memory tree:

`chat -> day -> week -> month -> year`

The current repo is intentionally simple:

- no web UI
- no GUI app
- no reminder system
- no task engine

The focus is memory, retrieval, and clean terminal chat.

## What It Does

- Stores long-lived profile information
- Stores important facts about you
- Tracks projects across sessions
- Stores chat-level summaries for each exchange
- Rolls chat summaries up into day, week, month, and year summaries
- Retrieves through the memory tree instead of scanning everything
- Supports text mode and voice mode in the terminal

## Current Architecture

### Runtime

- `main.py`
  - CLI entry point
  - terminal UI
  - session startup and shutdown
- `graph.py`
  - LangGraph flow
  - trigger -> retrieve -> chat -> remember
- `retrieval.py`
  - builds memory context for the chat model
- `database.py`
  - PostgreSQL store, vector index, and checkpointer setup

### Memory Modules

- `memory/profile.py`
  - stable identity and preference memory
- `memory/facts.py`
  - discrete user facts
- `memory/projects.py`
  - multi-session project memory
- `memory/episodes.py`
  - chat summary storage and episodic retrieval
- `memory/rollup/core.py`
  - rollup orchestration
- `memory/rollup/summarizers.py`
  - day, week, month, and year summary generation
- `memory/utils.py`
  - shared store helpers

### Models

- Chat model
  - primary user-facing response generation
- Memory model
  - trigger routing
  - memory extraction
  - episode summarization
  - rollup summarization
- Embedding model
  - semantic retrieval in pgvector

## Memory Flow

Each successful turn is summarized and stored at the chat level.

Over time Parker rolls those summaries upward:

- new day -> previous day's chats -> day summary
- new week -> previous week's days -> week summary
- new month -> previous month's weeks -> month summary
- new year -> previous year's months -> year summary

When you ask a memory-related question, Parker searches the memory tree for relevant summaries instead of trying to stuff all past chats into the prompt.

## Graph Flow

```text
START -> trigger -> retrieve -> chat -> remember -> END
```

- `trigger`
  - decides whether retrieval and storage are needed
- `retrieve`
  - builds memory context from profile, facts, projects, episodes, and current time
- `chat`
  - produces the user-facing answer
- `remember`
  - updates profile, facts, and projects in background threads

## Requirements

- Python 3.11+
- Docker Desktop
- Ollama
- Groq API key if using Groq for the chat model

## Quickstart

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Pull Ollama models

```bash
ollama pull qwen2.5:3b
ollama pull mxbai-embed-large
```

### 3. Start the database

```bash
docker compose up -d
```

This starts PostgreSQL with pgvector on port `5442`.

### 4. Configure `.env`

Copy the example file and add your API key if needed:

```bash
cp .env.example .env
```

Example:

```env
GROQ_API_KEY=gsk_your_key_here
```

### 5. Run Parker

```bash
python main.py
```

On Windows you can also use:

```bash
run_parker.bat
```

## Configuration

Settings live in `.env`.

Key variables:

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

- The active episodic memory path is summary-based, not exact raw-transcript replay.
- For the cleanest behavior after large architecture changes, reset the database and start fresh.
- Voice input and output are still supported in the terminal runtime.

## License

MIT
