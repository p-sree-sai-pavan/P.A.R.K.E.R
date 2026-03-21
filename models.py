"""
models.py — LLM Configuration for Parker AI
Loads configuration from config.py (which reads from environment variables).
"""
from config import (
    GROQ_API_KEY,
    CHAT_LLM_PROVIDER,
    CHAT_LLM_MODEL,
    CHAT_LLM_TEMPERATURE,
    CHAT_LLM_MAX_TOKENS,
    CHAT_LLM_TIMEOUT,
    MEMORY_LLM_PROVIDER,
    MEMORY_LLM_MODEL,
    MEMORY_LLM_TEMPERATURE,
    MEMORY_LLM_CTX,
    EMBEDDING_MODEL,
    validate_config,
)

# Validate configuration on import
_config_errors = validate_config()
if _config_errors:
    for err in _config_errors:
        print(f"[Config Warning] {err}")

# ════════════════════════════════════════════════════════════════════════════════
# Chat LLM — High quality responses (Groq by default)
# ════════════════════════════════════════════════════════════════════════════════

if CHAT_LLM_PROVIDER == "groq":
    from langchain_groq import ChatGroq

    if not GROQ_API_KEY:
        raise ValueError("GROQ_API_KEY is required when using Groq provider. Set it in .env file.")

    chat_llm = ChatGroq(
        api_key=GROQ_API_KEY,
        model=CHAT_LLM_MODEL,
        temperature=CHAT_LLM_TEMPERATURE,
        max_tokens=CHAT_LLM_MAX_TOKENS,
        timeout=CHAT_LLM_TIMEOUT,
    )

elif CHAT_LLM_PROVIDER == "ollama":
    from langchain_ollama import ChatOllama

    chat_llm = ChatOllama(
        model=CHAT_LLM_MODEL,
        temperature=CHAT_LLM_TEMPERATURE,
        num_predict=CHAT_LLM_MAX_TOKENS,
    )

else:
    raise ValueError(f"Unsupported CHAT_LLM_PROVIDER: {CHAT_LLM_PROVIDER}")


# ════════════════════════════════════════════════════════════════════════════════
# Memory LLM — Fast local extraction (Ollama by default)
# ════════════════════════════════════════════════════════════════════════════════

if MEMORY_LLM_PROVIDER == "ollama":
    from langchain_ollama import ChatOllama

    memory_llm = ChatOllama(
        model=MEMORY_LLM_MODEL,
        temperature=MEMORY_LLM_TEMPERATURE,
        num_ctx=MEMORY_LLM_CTX,
    )

elif MEMORY_LLM_PROVIDER == "groq":
    from langchain_groq import ChatGroq

    if not GROQ_API_KEY:
        raise ValueError("GROQ_API_KEY is required when using Groq provider.")

    memory_llm = ChatGroq(
        api_key=GROQ_API_KEY,
        model=MEMORY_LLM_MODEL,
        temperature=MEMORY_LLM_TEMPERATURE,
    )

else:
    raise ValueError(f"Unsupported MEMORY_LLM_PROVIDER: {MEMORY_LLM_PROVIDER}")


# ════════════════════════════════════════════════════════════════════════════════
# Embeddings (Ollama by default)
# ════════════════════════════════════════════════════════════════════════════════

from langchain_ollama import OllamaEmbeddings

embedder = OllamaEmbeddings(model=EMBEDDING_MODEL)


def get_embedder():
    """Get the embedder instance for vector search."""
    return embedder


def embed_fn(texts: list[str]) -> list[list[float]]:
    """Embed texts using the configured embedding model."""
    return embedder.embed_documents(texts)