"""
models.py — LLM instances for Parker AI

Dynamic key-rotating pools for Groq.
Independent Chat Model on Gemini.
Ollama Fallbacks.
"""

import os
import threading
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

# ── Smart defaults for Groq rate limit optimization ─────────────────────────
TRIGGER_LLM_MODEL = os.getenv("TRIGGER_LLM_MODEL")
ROLLUP_LLM_MODEL = os.getenv("ROLLUP_LLM_MODEL")
PROJECTS_LLM_MODEL = os.getenv("PROJECTS_LLM_MODEL")
EPISODES_LLM_MODEL = os.getenv("EPISODES_LLM_MODEL")
FACTS_LLM_MODEL = os.getenv("FACTS_LLM_MODEL")
PROFILE_LLM_MODEL = os.getenv("PROFILE_LLM_MODEL")

if MEMORY_LLM_PROVIDER == "groq":
    # Offload tasks to Qwen 32B (500k TPD, robust function calling and summaries)
    TRIGGER_LLM_MODEL = TRIGGER_LLM_MODEL or "qwen/qwen3-32b"
    ROLLUP_LLM_MODEL = ROLLUP_LLM_MODEL or "qwen/qwen3-32b"
    PROJECTS_LLM_MODEL = PROJECTS_LLM_MODEL or "qwen/qwen3-32b"
    EPISODES_LLM_MODEL = EPISODES_LLM_MODEL or "qwen/qwen3-32b"
    # Reserve Llama-3.3-70b-versatile (100k TPD) for high-reasoning tasks (facts/profile)
    FACTS_LLM_MODEL = FACTS_LLM_MODEL or MEMORY_LLM_MODEL or "llama-3.3-70b-versatile"
    PROFILE_LLM_MODEL = PROFILE_LLM_MODEL or MEMORY_LLM_MODEL or "llama-3.3-70b-versatile"
else:
    TRIGGER_LLM_MODEL = TRIGGER_LLM_MODEL or MEMORY_LLM_MODEL
    ROLLUP_LLM_MODEL = ROLLUP_LLM_MODEL or MEMORY_LLM_MODEL
    PROJECTS_LLM_MODEL = PROJECTS_LLM_MODEL or MEMORY_LLM_MODEL
    EPISODES_LLM_MODEL = EPISODES_LLM_MODEL or MEMORY_LLM_MODEL
    FACTS_LLM_MODEL = FACTS_LLM_MODEL or MEMORY_LLM_MODEL
    PROFILE_LLM_MODEL = PROFILE_LLM_MODEL or MEMORY_LLM_MODEL


class RotatedStructuredModel:
    def __init__(self, primary_structured_list: list, fallback_structured, name: str):
        self.instances = primary_structured_list
        self.fallback_structured = fallback_structured
        self.name = name
        self._index = 0
        self._lock = threading.Lock()

    def _get_next_instance(self):
        with self._lock:
            inst = self.instances[self._index]
            self._index = (self._index + 1) % len(self.instances)
            return inst

    def invoke(self, *args, **kwargs):
        last_err = None
        for i in range(len(self.instances)):
            inst = self._get_next_instance()
            try:
                return inst.invoke(*args, **kwargs)
            except Exception as e:
                err_msg = str(e).lower()
                if any(k in err_msg for k in ("rate", "429", "limit", "quota")):
                    print(f"[{self.name} Structured Info] API key index {self._index} rate limited. Retrying with next key in rotation...")
                    last_err = e
                    continue
                else:
                    last_err = e
                    break
        print(f"[{self.name} Structured Warning] All rotated keys rate limited: {last_err}. Falling back to Ollama...")
        return self.fallback_structured.invoke(*args, **kwargs)


class RotatedChatModel:
    def __init__(self, primary_llm_list: list, fallback_llm, name: str):
        self.instances = primary_llm_list
        self.fallback_llm = fallback_llm
        self.name = name
        self._index = 0
        self._lock = threading.Lock()

    def _get_next_instance(self):
        with self._lock:
            inst = self.instances[self._index]
            self._index = (self._index + 1) % len(self.instances)
            return inst

    def invoke(self, *args, **kwargs):
        last_err = None
        for i in range(len(self.instances)):
            inst = self._get_next_instance()
            try:
                return inst.invoke(*args, **kwargs)
            except Exception as e:
                err_msg = str(e).lower()
                if any(k in err_msg for k in ("rate", "429", "limit", "quota")):
                    print(f"[{self.name} Info] API key index {self._index} rate limited. Retrying with next key in rotation...")
                    last_err = e
                    continue
                else:
                    last_err = e
                    break
        print(f"[{self.name} Warning] All rotated keys rate limited: {last_err}. Falling back to Ollama...")
        return self.fallback_llm.invoke(*args, **kwargs)

    def with_structured_output(self, schema, **kwargs):
        structured_instances = [inst.with_structured_output(schema, **kwargs) for inst in self.instances]
        fallback_structured = self.fallback_llm.with_structured_output(schema, **kwargs)
        return RotatedStructuredModel(structured_instances, fallback_structured, self.name)


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

def _groq_pool(model: str, temperature: float = 0):
    """
    Creates a load-balanced pool of ChatGroq instances from the 4 configured keys.
    """
    pool = []
    # De-duplicate keys so we don't double-add if some variables default to K1
    unique_keys = []
    for k in [_K1, _K2, _K3, _K4]:
        if k and k not in unique_keys:
            unique_keys.append(k)
    
    if not unique_keys:
        raise ValueError("No Groq API keys found in environment. Check .env")
        
    for key in unique_keys:
        pool.append(_groq(key, model=model, temperature=temperature))
    return pool

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


# ── Chat LLM — Single Cloud Instance ──────────────────────────────────────────

if CHAT_LLM_PROVIDER == "groq":
    _chat_base = _groq(_K1, model=CHAT_LLM_MODEL, temperature=CHAT_LLM_TEMPERATURE, max_tokens=CHAT_LLM_MAX_TOKENS, timeout=CHAT_LLM_TIMEOUT)
elif CHAT_LLM_PROVIDER == "ollama":
    _chat_base = _ollama(model=CHAT_LLM_MODEL, temperature=CHAT_LLM_TEMPERATURE, num_ctx=CHAT_LLM_CTX)
elif CHAT_LLM_PROVIDER == "gemini":
    _chat_base = _gemini(GEMINI_API_KEY, model=CHAT_LLM_MODEL, temperature=CHAT_LLM_TEMPERATURE, max_tokens=CHAT_LLM_MAX_TOKENS, timeout=CHAT_LLM_TIMEOUT)
else:
    raise ValueError(f"Unsupported CHAT_LLM_PROVIDER: {CHAT_LLM_PROVIDER}")


# ── Fallback LLM ─────────────────────────────────────────────────────────────
# Local Ollama fallback for all models (highly resilient, zero cost/limit)

if FALLBACK_LLM_PROVIDER == "gemini":
    fallback_llm = _gemini(GEMINI_API_KEY, model=FALLBACK_LLM_MODEL, temperature=CHAT_LLM_TEMPERATURE, max_tokens=CHAT_LLM_MAX_TOKENS, timeout=CHAT_LLM_TIMEOUT)
elif FALLBACK_LLM_PROVIDER == "ollama":
    fallback_llm = _ollama(model=FALLBACK_LLM_MODEL, temperature=CHAT_LLM_TEMPERATURE, num_ctx=CHAT_LLM_CTX)
elif FALLBACK_LLM_PROVIDER == "groq":
    fallback_llm = _groq(_K1, model=FALLBACK_LLM_MODEL, temperature=CHAT_LLM_TEMPERATURE, max_tokens=CHAT_LLM_MAX_TOKENS, timeout=CHAT_LLM_TIMEOUT)
else:
    raise ValueError(f"Unsupported FALLBACK_LLM_PROVIDER: {FALLBACK_LLM_PROVIDER}")


# ── Setup pools for Memory Workers ───────────────────────────────────────────

if MEMORY_LLM_PROVIDER == "groq":
    rollup_llm   = RotatedChatModel(_groq_pool(ROLLUP_LLM_MODEL, 0), fallback_llm, "RollupModel")
    facts_llm    = RotatedChatModel(_groq_pool(FACTS_LLM_MODEL, 0), fallback_llm, "FactsModel")
    episodes_llm = RotatedChatModel(_groq_pool(EPISODES_LLM_MODEL, 0), fallback_llm, "EpisodesModel")
    trigger_llm  = RotatedChatModel(_groq_pool(TRIGGER_LLM_MODEL, 0), fallback_llm, "TriggerModel")
    profile_llm  = RotatedChatModel(_groq_pool(PROFILE_LLM_MODEL, 0), fallback_llm, "ProfileModel")
    projects_llm = RotatedChatModel(_groq_pool(PROJECTS_LLM_MODEL, 0), fallback_llm, "ProjectsModel")

elif MEMORY_LLM_PROVIDER == "ollama":
    rollup_llm   = RotatedChatModel([_ollama(model=ROLLUP_LLM_MODEL)], fallback_llm, "RollupModel")
    facts_llm    = RotatedChatModel([_ollama(model=FACTS_LLM_MODEL)], fallback_llm, "FactsModel")
    episodes_llm = RotatedChatModel([_ollama(model=EPISODES_LLM_MODEL)], fallback_llm, "EpisodesModel")
    trigger_llm  = RotatedChatModel([_ollama(model=TRIGGER_LLM_MODEL)], fallback_llm, "TriggerModel")
    profile_llm  = RotatedChatModel([_ollama(model=PROFILE_LLM_MODEL)], fallback_llm, "ProfileModel")
    projects_llm = RotatedChatModel([_ollama(model=PROJECTS_LLM_MODEL)], fallback_llm, "ProjectsModel")

elif MEMORY_LLM_PROVIDER == "gemini":
    rollup_llm   = RotatedChatModel([_gemini(GEMINI_API_KEY, model=ROLLUP_LLM_MODEL, temperature=0)], fallback_llm, "RollupModel")
    facts_llm    = RotatedChatModel([_gemini(GEMINI_API_KEY, model=FACTS_LLM_MODEL, temperature=0)], fallback_llm, "FactsModel")
    episodes_llm = RotatedChatModel([_gemini(GEMINI_API_KEY, model=EPISODES_LLM_MODEL, temperature=0)], fallback_llm, "EpisodesModel")
    trigger_llm  = RotatedChatModel([_gemini(GEMINI_API_KEY, model=TRIGGER_LLM_MODEL, temperature=0)], fallback_llm, "TriggerModel")
    profile_llm  = RotatedChatModel([_gemini(GEMINI_API_KEY, model=PROFILE_LLM_MODEL, temperature=0)], fallback_llm, "ProfileModel")
    projects_llm = RotatedChatModel([_gemini(GEMINI_API_KEY, model=PROJECTS_LLM_MODEL, temperature=0)], fallback_llm, "ProjectsModel")

else:
    raise ValueError(f"Unsupported MEMORY_LLM_PROVIDER: {MEMORY_LLM_PROVIDER}")


# Wrap Chat LLM in Rotated wrapper for resilience (single element pool)
chat_llm = RotatedChatModel([_chat_base], fallback_llm, "ChatModel")

# Alias kept for backward-compatibility
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