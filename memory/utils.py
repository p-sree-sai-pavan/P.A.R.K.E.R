import re
import json
import time
import threading


# ── Namespace locks (D2 fix) ───────────────────────────────────────────────────
# Prevents concurrent read-write races when multiple background threads
# write to the same namespace simultaneously.

_ns_locks: dict       = {}
_ns_locks_lock        = threading.Lock()

_background_jobs: set[threading.Thread] = set()
_background_jobs_lock = threading.Lock()
FULL_SCAN_LIMIT = 5000

def get_ns_lock(namespace: tuple) -> threading.Lock:
    key = str(namespace)
    with _ns_locks_lock:
        if key not in _ns_locks:
            _ns_locks[key] = threading.Lock()
        return _ns_locks[key]


def start_background_job(target, *args, name: str | None = None, daemon: bool = True, **kwargs) -> threading.Thread:
    """
    Start a tracked background thread so shutdown can wait for in-flight writes.
    """
    thread_ref: dict[str, threading.Thread] = {}

    def runner():
        try:
            target(*args, **kwargs)
        finally:
            thread = thread_ref.get("thread")
            if thread is not None:
                with _background_jobs_lock:
                    _background_jobs.discard(thread)

    thread = threading.Thread(target=runner, name=name, daemon=daemon)
    thread_ref["thread"] = thread

    with _background_jobs_lock:
        _background_jobs.add(thread)

    thread.start()
    return thread


def wait_for_background_jobs(timeout: float = 15.0):
    """
    Best-effort drain for tracked background work before shutdown.
    """
    deadline = time.time() + max(0.0, timeout)

    while True:
        with _background_jobs_lock:
            jobs = [job for job in _background_jobs if job.is_alive()]

        if not jobs:
            return

        remaining = deadline - time.time()
        if remaining <= 0:
            return

        for job in jobs:
            job.join(timeout=min(0.2, remaining))


# ── Message formatting ─────────────────────────────────────────────────────────

def format_messages(messages: list) -> str:
    lines = []
    for m in messages:
        if hasattr(m, "type"):
            role = "User" if m.type == "human" else "Parker"
            lines.append(f"{role}: {m.content}")
        elif isinstance(m, dict):
            role = "User" if m.get("role") == "user" else "Parker"
            lines.append(f"{role}: {m.get('content', '')}")
    return "\n".join(lines)


# ── JSON parsing ───────────────────────────────────────────────────────────────

def parse_json_object(text: str) -> dict:
    try:
        text   = _strip_fences(text)
        result = json.loads(text)
        return result if isinstance(result, dict) else {}
    except Exception:
        return {}


def parse_json_array(text: str) -> list:
    try:
        text   = _strip_fences(text)
        result = json.loads(text)
        return result if isinstance(result, list) else []
    except Exception:
        return []


# ── Store helpers ──────────────────────────────────────────────────────────────

def semantic_search(store, namespace: tuple, query: str, limit: int) -> list:
    try:
        return store.search(namespace, query=query, limit=limit)
    except Exception as e:
        print(f"[Search] Semantic search failed on {namespace}: {e}")
        return []


def full_scan(store, namespace: tuple, limit: int = FULL_SCAN_LIMIT) -> list:
    try:
        items = store.search(namespace, limit=limit)
        deduped = {}
        for item in items:
            existing = deduped.get(item.key)
            if existing is None or _item_richness(item) >= _item_richness(existing):
                deduped[item.key] = item
        return list(deduped.values())
    except Exception as e:
        print(f"[Search] Full scan failed on {namespace}: {e}")
        return []


def deduplicate(items_a: list, items_b: list) -> list:
    seen = {}
    for item in items_a:
        seen[item.key] = item
    for item in items_b:
        if item.key not in seen:
            seen[item.key] = item
    return list(seen.values())


# ── Internal ───────────────────────────────────────────────────────────────────

def _strip_fences(text: str) -> str:
    """
    M3 fix: use regex instead of split() to reliably extract JSON
    from markdown fences regardless of spacing or multiple blocks.
    """
    text = text.strip()
    match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if match:
        return match.group(1).strip()
    return text


def _item_richness(item) -> int:
    value = getattr(item, "value", None)
    if not isinstance(value, dict):
        return 0

    score = 0
    for key, val in value.items():
        if val in (None, "", [], {}, ()):
            continue
        score += 2 if key in {"summary", "level", "text"} else 1
    return score
