# 🌌 P.A.R.K.E.R AI
### *Personal Assistant for Retrieval, Knowledge, and Episodic Reasoning*

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![PostgreSQL](https://img.shields.io/badge/Database-PostgreSQL-336791.svg)](https://www.postgresql.org/)
[![LangGraph](https://img.shields.io/badge/Framework-LangGraph-orange.svg)](https://langchain-ai.github.io/langgraph/)

**Parker AI** is a state-of-the-art personal assistant designed to be more than just a chatbot. It features a deep, persistent memory system powered by **LangGraph** and **PostgreSQL**, designed to recall past conversations, manage long-term projects, and proactively handle tasks.

---

## ✨ Key Features

- **🧠 Deep Episodic Memory**: Uses semantic vector search to recall context from days or weeks ago.
- **🛡️ The Memory Gate**: An autonomous sub-system that filters noise and only stores meaningful tasks, facts, and preferences.
- **🚀 Dual-Interface Power**:
  - **Premium Desktop App**: A sleek PySide6-based GUI with streaming markdown, dark mode, and voice support.
  - **Scalable API**: A robust FastAPI backend with WebSocket support for real-time streaming.
- **⚡ Hybrid LLM Orchestration**: Combines the speed of **Groq** for chat with the privacy and cost-efficiency of **Ollama** for memory extraction.
- **📋 Smart Task Engine**: Automatically detects "remind me" intents, calculates due times, and surfaces reminders naturally in conversation.
- **🎙️ Native Voice**: Built-in speech-to-text (STT) and text-to-speech (TTS) for hands-free interaction.

---

## 🏗️ Architecture

Parker uses a modular, graph-based architecture to ensure reliable and context-aware responses.

- **`app.py`**: The main Desktop GUI (PySide6).
- **`graph.py`**: The LangGraph state machine orchestrating the `trigger → remember → chat` flow.
- **`memory/`**: The core intelligence layer, including task management, fact extraction, and profile rollup.
- **`api/`**: FastAPI server for remote integration and web-based frontends.
- **`database.py`**: Centralized PostgreSQL management with `pgvector` support.

---

## 🚀 Getting Started

### 1. Prerequisites
- **Python 3.10+**
- **Docker Desktop** (for PostgreSQL)
- **Ollama** (for local embeddings and memory extraction)
- **Groq API Key** (for fast chat responses)

### 2. Setup
```bash
# Clone the repository
git clone https://github.com/p-sree-sai-pavan/P.A.R.K.E.R.git
cd P.A.R.K.E.R

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env and add your GROQ_API_KEY
```

### 3. Launching
Parker is designed for easy startup:

**Windows (Recommended):**
Simply run the included batch file:
```cmd
run_parker.bat
```
*This will automatically start the Docker database and launch the GUI.*

**Manual:**
```bash
docker compose up -d
python app.py
```

---

## ⚙️ Configuration

Parker is highly configurable via `.env`:

| Variable | Description | Default |
|----------|-------------|---------|
| `DB_URI` | PostgreSQL connection string | `localhost:5442` |
| `CHAT_LLM_PROVIDER` | LLM for responses (`groq` or `ollama`) | `groq` |
| `MEMORY_LLM_PROVIDER` | LLM for extraction | `ollama` |
| `GROQ_API_KEY` | Your Groq Cloud API Key | (required) |

---

## 🤝 Contributing

Contributions are what make the open-source community such an amazing place to learn, inspire, and create. Any contributions you make are **greatly appreciated**.

1. Fork the Project
2. Create your Feature Branch (`git checkout -b feature/AmazingFeature`)
3. Commit your Changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the Branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

---

## 📄 License
Distributed under the MIT License. See `LICENSE` for more information.

---
*Developed by [P Sree Sai Pavan](https://github.com/p-sree-sai-pavan)*
