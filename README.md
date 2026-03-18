<div align="center">
  <img src="https://img.shields.io/badge/Python-3.11+-blue.svg" alt="Python">
  <img src="https://img.shields.io/badge/UI-PySide6-41CD52.svg" alt="PySide6">
  <img src="https://img.shields.io/badge/AI-Ollama%20(Local)-white.svg" alt="Ollama">
  <img src="https://img.shields.io/badge/Database-PostgreSQL-336791.svg" alt="PostgreSQL">
  <h1>P.A.R.K.E.R.</h1>
  <p><strong>Private, Autonomous, Responsive Knowledge Engine with Recall</strong></p>
  <p>A completely local, ultra-fast AI companion with infinite memory, native voice interaction, and a premium dark-themed desktop UI.</p>
</div>

---

## 🚀 Overview

Parker is a modular AI assistant designed to live entirely on your machine. He learns from your interactions, builds a long-term implicit memory of who you are, and communicates with you through voice and text. No cloud APIs, no data mining, zero subscription fees.

By combining the reasoning power of `qwen2.5:7b` via **Ollama**, infinite persistent memory via **LangGraph + PostgreSQL**, and lightning-fast voice processing, Parker acts as a true personal companion.

---

## ✨ Features

- 🧠 **Infinite Implicit Memory**: Parker extracts and saves facts, habits, and preferences dynamically into PostgreSQL using `mxbai-embed-large` vector embeddings. He remembers you without you ever saying "remember this".
- 🎙️ **Native Voice Interaction**: Built-in microphone processing using `faster-whisper` (transcription) and `silero-vad` (voice activity detection). Talk naturally—Parker knows exactly when you stop speaking.
- 🗣️ **Local Text-to-Speech**: Instant, lag-free voice responses using Windows SAPI5 (`pyttsx3`) handled gracefully on a background thread.
- 🎨 **Premium Local Desktop App**: A seamless, ChatGPT-style chat interface built in pure `PySide6`. Features a high-contrast Vercel-style dark theme, auto-resizing text boxes, Markdown streaming, and real-time generation stops.
- 🔒 **100% Private**: Everything runs locally. Your voice, chat history, and extracted memories never leave your machine.

---

## 🏗️ Architecture

Parker's anatomy is split into clean, single-purpose Python modules:

| Component | Responsibility | Tech Stack |
|-----------|---------------|------------|
| `app.py`  | **The Face.** The premium PySide6 Desktop GUI, handling all visual interactions, streaming rendering, and chat components. | `PySide6` |
| `long.py` | **The Brain.** Manages state machines, system prompting, Ollama generation, and dynamic memory extraction. | `LangGraph`, `LangChain`, `Ollama` |
| `ears.py` | **The Senses.** Listens to your microphone. Automatically detects silence and transcribes audio to text instantly. | `faster-whisper`, `silero-vad` |
| `mouth.py`| **The Voice.** Takes text and speaks it out loud natively using Windows TTS. Non-blocking and thread-safe. | `pyttsx3`, `SAPI5` |
| `main.py` | **The Core/CLI.** The terminal-only version of Parker if you prefer working entirely from the command line. | `Python` |

---

## ⚙️ Installation & Setup

### 1. Requirements
Ensure you have the following installed on your system:
- **Python 3.11+**
- **Docker** (for PostgreSQL)
- **Ollama** (for running the local LLMs)

### 2. Start the Database
Parker uses PostgreSQL with pgvector natively to manage chat checkpoints and memory embeddings.
```bash
docker compose up -d
```

### 3. Pull the AI Models
Parker relies on Ollama for both reasoning and memory embedding:
```bash
ollama pull qwen2.5:7b
ollama pull mxbai-embed-large
```

### 4. Install Dependencies
```bash
pip install PySide6 langchain-core langchain-ollama langgraph psycopg pyttsx3 faster-whisper silero-vad sounddevice scipy numpy python-dotenv
```

---

## 🎮 Usage

### Launch the Desktop App (Recommended)
This gives you the premium ChatGPT-style interface with voice capabilities.
```bash
python app.py
```
* **Text Mode:** Type freely, press `Shift+Enter` for newlines, `Enter` to send.
* **Voice Mode:** Click the `🎙` button to speak. Parker stops listening as soon as you stop talking.
* **Stop Generation:** Click the `⏹` button to halt Parker if he talks too long.

### Launch the Terminal Interface
For a strict CLI experience:
```bash
python main.py
```

---

## 🛠️ Performance Tuning

If you notice Parker is generating responses slowly, you can tweak the context window inside `long.py`:
```python
chat_llm = ChatOllama(model="qwen2.5:7b", num_ctx=4096)
```
Lowering `num_ctx` (e.g. `2048`) will drastically speed up inference on lower-end hardware.

---

## 📄 License
This project is licensed under the MIT License.
