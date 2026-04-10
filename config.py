"""
config.py — Centralized configuration for Parker AI
All settings loaded from environment variables with sensible defaults.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root
_env_path = Path(__file__).parent / ".env"
load_dotenv(_env_path)


# ════════════════════════════════════════════════════════════════════════════════
# Database Configuration
# ════════════════════════════════════════════════════════════════════════════════

REMINDER_POLL_INTERVAL = int(os.getenv("REMINDER_POLL_INTERVAL", "30"))

DB_URI = os.getenv(
    "DB_URI",
    "postgresql://postgres:postgres@localhost:5442/postgres?sslmode=disable"
)

# Connection retry settings
DB_MAX_RETRIES = int(os.getenv("DB_MAX_RETRIES", "3"))
DB_RETRY_DELAY = float(os.getenv("DB_RETRY_DELAY", "2.0"))

# User / session defaults
USER_NAME = os.getenv("USER_NAME", "Pavan")
DEFAULT_USER_ID   = os.getenv("DEFAULT_USER_ID", "u1")
DEFAULT_THREAD_ID = os.getenv("DEFAULT_THREAD_ID", "thread_u1")


# ════════════════════════════════════════════════════════════════════════════════
# LLM Configuration
# ════════════════════════════════════════════════════════════════════════════════

# Chat LLM — High quality responses
CHAT_LLM_PROVIDER = os.getenv("CHAT_LLM_PROVIDER", "groq")
CHAT_LLM_MODEL = os.getenv("CHAT_LLM_MODEL", "llama-3.3-70b-versatile")
CHAT_LLM_TEMPERATURE = float(os.getenv("CHAT_LLM_TEMPERATURE", "0.7"))
CHAT_LLM_MAX_TOKENS = int(os.getenv("CHAT_LLM_MAX_TOKENS", "1024"))
CHAT_LLM_TIMEOUT = int(os.getenv("CHAT_LLM_TIMEOUT", "60"))  # seconds

# Memory LLM — Fast local extraction
MEMORY_LLM_PROVIDER = os.getenv("MEMORY_LLM_PROVIDER", "ollama")
MEMORY_LLM_MODEL = os.getenv("MEMORY_LLM_MODEL", "qwen2.5:3b")
MEMORY_LLM_TEMPERATURE = float(os.getenv("MEMORY_LLM_TEMPERATURE", "0"))
MEMORY_LLM_CTX = int(os.getenv("MEMORY_LLM_CTX", "2048"))

# Embeddings
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "mxbai-embed-large")
EMBEDDING_DIMS = int(os.getenv("EMBEDDING_DIMS", "1024"))



# ════════════════════════════════════════════════════════════════════════════════
# Reminder Configuration
# ════════════════════════════════════════════════════════════════════════════════



# ════════════════════════════════════════════════════════════════════════════════
# API Keys (validated on startup)
# ════════════════════════════════════════════════════════════════════════════════

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")


# ════════════════════════════════════════════════════════════════════════════════
# Validation
# ════════════════════════════════════════════════════════════════════════════════

def validate_config():
    """Validate configuration on startup. Returns list of missing items."""
    missing = []

    if CHAT_LLM_PROVIDER == "groq" and not GROQ_API_KEY:
        missing.append("GROQ_API_KEY is required when using Groq provider")

    return missing


# ════════════════════════════════════════════════════════════════════════════════
# LangGraph Config (for export)
# ════════════════════════════════════════════════════════════════════════════════

def get_config(user_id: str = None, thread_id: str = None) -> dict:
    """Get LangGraph config with user and thread IDs."""
    return {
        "configurable": {
            "user_id": user_id or DEFAULT_USER_ID,
            "thread_id": thread_id or DEFAULT_THREAD_ID,
        }
    }


# Default config instance for convenience
config = get_config()
