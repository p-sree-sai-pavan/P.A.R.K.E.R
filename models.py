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
    CHAT_LLM_CTX,
    MEMORY_LLM_PROVIDER, 
    MEMORY_LLM_MODEL, 
    MEMORY_LLM_TEMPERATURE,
    MEMORY_LLM_CTX, 
    EMBEDDING_MODEL, 
    validate_config,
    FALLBACK_LLM_PROVIDER,
    FALLBACK_LLM_MODEL,
    GEMINI_API_KEY,
)


_config_errors = validate_config()
if _config_errors:
    for err in _config_errors:
        print(f"[Config Warning] {err}")

import threading

class ResilientStructuredModel:
    def __init__(self, primary_structured, fallback_structured, name: str):
        self.primary_structured = primary_structured
        self.fallback_structured = fallback_structured
        self.name = name

    def invoke(self, *args, **kwargs):
        try:
            return self.primary_structured.invoke(*args, **kwargs)
        except Exception as e:
            print(f"[{self.name} Structured Warning] Primary LLM failed: {e}. Falling back...")
            return self.fallback_structured.invoke(*args, **kwargs)

class ResilientChatModel:
    def __init__(self, primary_llm, fallback_llm, name: str):
        self.primary_llm = primary_llm
        self.fallback_llm = fallback_llm
        self.name = name

    def invoke(self, *args, **kwargs):
        try:
            return self.primary_llm.invoke(*args, **kwargs)
        except Exception as e:
            print(f"[{self.name} Warning] Primary LLM failed: {e}. Falling back...")
            return self.fallback_llm.invoke(*args, **kwargs)

    def with_structured_output(self, schema, **kwargs):
        primary_structured = self.primary_llm.with_structured_output(schema, **kwargs)
        fallback_structured = self.fallback_llm.with_structured_output(schema, **kwargs)
        return ResilientStructuredModel(primary_structured, fallback_structured, self.name)


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

def _gemini(key: str, model: str = None, temperature: float = None, max_tokens: int = None, timeout: int = None):
    from langchain_google_genai import ChatGoogleGenerativeAI
    if not key:
        raise ValueError("Gemini API key missing. Set GEMINI_API_KEY in .env")
    kwargs = dict(
        google_api_key=key,
        model=model or "gemini-2.5-flash",
        temperature=temperature if temperature is not None else CHAT_LLM_TEMPERATURE,
    )
    if max_tokens:
        kwargs["max_output_tokens"] = max_tokens
    if timeout:
        kwargs["timeout"] = timeout
    return ChatGoogleGenerativeAI(**kwargs)

def _ollama(model: str = None, temperature: float = None, num_ctx: int = None):
    from langchain_ollama import ChatOllama
    return ChatOllama(
        model=model or MEMORY_LLM_MODEL,
        temperature=temperature if temperature is not None else MEMORY_LLM_TEMPERATURE,
        num_ctx=num_ctx or MEMORY_LLM_CTX,
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
elif CHAT_LLM_PROVIDER == "gemini":
    chat_llm = _gemini(
        GEMINI_API_KEY,
        model=CHAT_LLM_MODEL,
        temperature=CHAT_LLM_TEMPERATURE,
        max_tokens=CHAT_LLM_MAX_TOKENS,
        timeout=CHAT_LLM_TIMEOUT,
    )
elif CHAT_LLM_PROVIDER == "ollama":
    chat_llm = _ollama(
        model=CHAT_LLM_MODEL,
        temperature=CHAT_LLM_TEMPERATURE,
        num_ctx=CHAT_LLM_CTX
    )
else:
    raise ValueError(f"Unsupported CHAT_LLM_PROVIDER: {CHAT_LLM_PROVIDER}")


# ── Fallback LLM ─────────────────────────────────────────────────────────────
# Used when the primary Chat LLM encounters rate limits or connection errors.

if FALLBACK_LLM_PROVIDER == "gemini":
    fallback_llm = _gemini(
        GEMINI_API_KEY,
        model=FALLBACK_LLM_MODEL,
        temperature=CHAT_LLM_TEMPERATURE,
        max_tokens=CHAT_LLM_MAX_TOKENS,
        timeout=CHAT_LLM_TIMEOUT,
    )
elif FALLBACK_LLM_PROVIDER == "ollama":
    fallback_llm = _ollama(
        model=FALLBACK_LLM_MODEL,
        temperature=CHAT_LLM_TEMPERATURE,
        num_ctx=CHAT_LLM_CTX
    )
elif FALLBACK_LLM_PROVIDER == "groq":
    fallback_llm = _groq(
        _K1,
        model=FALLBACK_LLM_MODEL,
        temperature=CHAT_LLM_TEMPERATURE,
        max_tokens=CHAT_LLM_MAX_TOKENS,
        timeout=CHAT_LLM_TIMEOUT,
    )
else:
    raise ValueError(f"Unsupported FALLBACK_LLM_PROVIDER: {FALLBACK_LLM_PROVIDER}")


# ── Rollup LLM — key2 solo ────────────────────────────────────────────────────
# Heavy but only runs at startup/shutdown. Day/week/month/year summaries.

if MEMORY_LLM_PROVIDER == "groq":
    rollup_llm = _groq(_K2, model=MEMORY_LLM_MODEL, temperature=0)
elif MEMORY_LLM_PROVIDER == "ollama":
    rollup_llm = _ollama()
elif MEMORY_LLM_PROVIDER == "gemini":
    rollup_llm = _gemini(GEMINI_API_KEY, model=MEMORY_LLM_MODEL, temperature=0)
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
elif MEMORY_LLM_PROVIDER == "gemini":
    facts_llm    = _gemini(GEMINI_API_KEY, model=MEMORY_LLM_MODEL, temperature=0)
    episodes_llm = _gemini(GEMINI_API_KEY, model=MEMORY_LLM_MODEL, temperature=0)
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
elif MEMORY_LLM_PROVIDER == "gemini":
    trigger_llm = _gemini(GEMINI_API_KEY, model=MEMORY_LLM_MODEL, temperature=0)
    profile_llm = _gemini(GEMINI_API_KEY, model=MEMORY_LLM_MODEL, temperature=0)
else:
    raise ValueError(f"Unsupported MEMORY_LLM_PROVIDER: {MEMORY_LLM_PROVIDER}")


# ── Projects LLM — key2 shared with rollup ───────────────────────────────────
# Rollup runs startup/shutdown. Projects runs background after chat.
# Minimal time overlap → safe to share key2.

if MEMORY_LLM_PROVIDER == "groq":
    projects_llm = _groq(_K2, model=MEMORY_LLM_MODEL, temperature=0)
elif MEMORY_LLM_PROVIDER == "ollama":
    projects_llm = _ollama()
elif MEMORY_LLM_PROVIDER == "gemini":
    projects_llm = _gemini(GEMINI_API_KEY, model=MEMORY_LLM_MODEL, temperature=0)
else:
    raise ValueError(f"Unsupported MEMORY_LLM_PROVIDER: {MEMORY_LLM_PROVIDER}")


# ── Resilient Wrappers ─────────────────────────────────────────────────────────

chat_llm = ResilientChatModel(chat_llm, fallback_llm, "ChatModel")
rollup_llm = ResilientChatModel(rollup_llm, fallback_llm, "RollupModel")
facts_llm = ResilientChatModel(facts_llm, fallback_llm, "FactsModel")
episodes_llm = ResilientChatModel(episodes_llm, fallback_llm, "EpisodesModel")
trigger_llm = ResilientChatModel(trigger_llm, fallback_llm, "TriggerModel")
profile_llm = ResilientChatModel(profile_llm, fallback_llm, "ProfileModel")
projects_llm = ResilientChatModel(projects_llm, fallback_llm, "ProjectsModel")

# ── memory_llm alias — kept for any missed import ─────────────────────────────
# Points to key3. If any file still imports memory_llm it won't break.
memory_llm = facts_llm


# ── Embeddings ────────────────────────────────────────────────────────────────

from langchain_ollama import OllamaEmbeddings

embedder = OllamaEmbeddings(model=EMBEDDING_MODEL)

_EMBEDDING_CACHE = {}
_cache_lock = threading.Lock()

def get_embedder():
    return embedder

def embed_fn(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    with _cache_lock:
        to_embed = []
        seen = set()
        for t in texts:
            if t not in _EMBEDDING_CACHE and t not in seen:
                to_embed.append(t)
                seen.add(t)
    if to_embed:
        embeddings = embedder.embed_documents(to_embed)
        with _cache_lock:
            for t, emb in zip(to_embed, embeddings):
                _EMBEDDING_CACHE[t] = emb
    with _cache_lock:
        return [_EMBEDDING_CACHE[t] for t in texts]