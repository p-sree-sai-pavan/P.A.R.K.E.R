"""
models.py — LLM instances for Parker AI
Each task gets its own Groq key to avoid rate limit conflicts.

Key assignment:
  key1 → chat_llm          (heaviest, serial, every message)
  key2 → rollup_llm        (heavy, startup/shutdown only)
  key3 → facts_llm + episodes_llm  (medium, background)
  key4 → trigger_llm + profile_llm (tiny+small, mixed)
"""

import os
from config import (
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

_config_errors = validate_config()
if _config_errors:
    for err in _config_errors:
        print(f"[Config Warning] {err}")

# ── Load keys ──────────────────────────────────────────────────────────────────

_K1 = os.getenv("GROQ_API_KEY_1", os.getenv("GROQ_API_KEY", ""))
_K2 = os.getenv("GROQ_API_KEY_2", _K1)
_K3 = os.getenv("GROQ_API_KEY_3", _K1)
_K4 = os.getenv("GROQ_API_KEY_4", _K1)

def _groq(key: str, model: str = None, temperature: float = None, max_tokens: int = None, timeout: int = None):
    from langchain_groq import ChatGroq
    if not key:
        raise ValueError("Groq API key missing. Check .env")
    kwargs = dict(
        api_key=key,
        model=model or CHAT_LLM_MODEL,
        temperature=temperature if temperature is not None else CHAT_LLM_TEMPERATURE,
    )
    if max_tokens:
        kwargs["max_tokens"] = max_tokens
    if timeout:
        kwargs["timeout"] = timeout
    return ChatGroq(**kwargs)

def _ollama(model: str = None, temperature: float = None):
    from langchain_ollama import ChatOllama
    return ChatOllama(
        model=model or MEMORY_LLM_MODEL,
        temperature=temperature if temperature is not None else MEMORY_LLM_TEMPERATURE,
        num_ctx=MEMORY_LLM_CTX,
    )


# ── Chat LLM — key1 solo ───────────────────────────────────────────────────────
# Heaviest: full memory context + conversation history + long responses

if CHAT_LLM_PROVIDER == "groq":
    chat_llm = _groq(
        _K1,
        model=CHAT_LLM_MODEL,
        temperature=CHAT_LLM_TEMPERATURE,
        max_tokens=CHAT_LLM_MAX_TOKENS,
        timeout=CHAT_LLM_TIMEOUT,
    )
elif CHAT_LLM_PROVIDER == "ollama":
    chat_llm = _ollama(model=CHAT_LLM_MODEL, temperature=CHAT_LLM_TEMPERATURE)
else:
    raise ValueError(f"Unsupported CHAT_LLM_PROVIDER: {CHAT_LLM_PROVIDER}")


# ── Rollup LLM — key2 solo ────────────────────────────────────────────────────
# Heavy but only runs at startup/shutdown. Day/week/month/year summaries.

if MEMORY_LLM_PROVIDER == "groq":
    rollup_llm = _groq(_K2, model=MEMORY_LLM_MODEL, temperature=0)
elif MEMORY_LLM_PROVIDER == "ollama":
    rollup_llm = _ollama()
else:
    raise ValueError(f"Unsupported MEMORY_LLM_PROVIDER: {MEMORY_LLM_PROVIDER}")


# ── Facts + Episodes LLM — key3 shared ───────────────────────────────────────
# Both run in background after each chat turn. Medium token load.

if MEMORY_LLM_PROVIDER == "groq":
    facts_llm    = _groq(_K3, model=MEMORY_LLM_MODEL, temperature=0)
    episodes_llm = _groq(_K3, model=MEMORY_LLM_MODEL, temperature=0)
elif MEMORY_LLM_PROVIDER == "ollama":
    facts_llm    = _ollama()
    episodes_llm = _ollama()
else:
    raise ValueError(f"Unsupported MEMORY_LLM_PROVIDER: {MEMORY_LLM_PROVIDER}")


# ── Trigger + Profile LLM — key4 shared ──────────────────────────────────────
# Trigger: tiny, serial (runs before every chat).
# Profile: small, background. Minimal overlap.

if MEMORY_LLM_PROVIDER == "groq":
    trigger_llm = _groq(_K4, model=MEMORY_LLM_MODEL, temperature=0)
    profile_llm = _groq(_K4, model=MEMORY_LLM_MODEL, temperature=0)
elif MEMORY_LLM_PROVIDER == "ollama":
    trigger_llm = _ollama()
    profile_llm = _ollama()
else:
    raise ValueError(f"Unsupported MEMORY_LLM_PROVIDER: {MEMORY_LLM_PROVIDER}")


# ── Projects LLM — key2 shared with rollup ───────────────────────────────────
# Rollup runs startup/shutdown. Projects runs background after chat.
# Minimal time overlap → safe to share key2.

if MEMORY_LLM_PROVIDER == "groq":
    projects_llm = _groq(_K2, model=MEMORY_LLM_MODEL, temperature=0)
elif MEMORY_LLM_PROVIDER == "ollama":
    projects_llm = _ollama()
else:
    raise ValueError(f"Unsupported MEMORY_LLM_PROVIDER: {MEMORY_LLM_PROVIDER}")


# ── memory_llm alias — kept for any missed import ─────────────────────────────
# Points to key3. If any file still imports memory_llm it won't break.
memory_llm = facts_llm


# ── Embeddings ────────────────────────────────────────────────────────────────

from langchain_ollama import OllamaEmbeddings

embedder = OllamaEmbeddings(model=EMBEDDING_MODEL)

def get_embedder():
    return embedder

def embed_fn(texts: list[str]) -> list[list[float]]:
    return embedder.embed_documents(texts)