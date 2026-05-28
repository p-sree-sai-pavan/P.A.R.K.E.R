import time
from datetime import datetime
from langchain_core.messages import SystemMessage, HumanMessage

from models import profile_llm as patterns_llm  # Use key 4 (profile/trigger key)
from memory.utils import (
    full_scan, get_ns_lock, parse_json_array, start_background_job
)
from memory.episodes import NS_CHAT, NS_DAY

NAMESPACE = lambda user_id: ("user", user_id, "patterns")
PATTERNS_KEY = "detected_patterns"

PATTERN_ANALYSIS_PROMPT = """Analyze the recent session history of Pavan to identify recurring behavioral patterns, stuck loops, habit trends, or persistent struggles.

Look specifically for:
1. Stuck loops: e.g., circling back to the same bug/issue multiple sessions in a row without resolution.
2. Habits: e.g., working very late at night, repeating certain mistakes, preferred workflows.
3. Persistent concerns: e.g., recurring worries about rate limits, performance, or UI alignment.

OUTPUT Format: A flat JSON array of strings. Each string must be a concise, direct, one-sentence observation of a pattern, starting with an active verb or gerund (e.g. "Debugging the memory store for the third session this week", "Preferring quick text commands over voice input"). Keep each under 15 words.
Return [] if no clear patterns are detected.

RECENT HISTORY:
{history}

Return only the JSON array."""


def load_patterns(store, user_id: str) -> list:
    item = store.get(NAMESPACE(user_id), PATTERNS_KEY)
    if item and isinstance(item.value, dict):
        return item.value.get("patterns", [])
    return []


def format_patterns_for_prompt(patterns: list) -> str:
    if not patterns:
        return "(none)"
    return "\n".join(f"- {p}" for p in patterns)


def detect_behavioral_patterns(store, user_id: str):
    """
    Spawns a background job to scan recent history and update observed patterns.
    """
    start_background_job(
        _detect_patterns_sync,
        store,
        user_id,
        name="patterns-detect"
    )


def _detect_patterns_sync(store, user_id: str):
    with get_ns_lock(NAMESPACE(user_id)):
        try:
            # 1. Fetch the last 15 chat episodes
            chats = full_scan(store, NS_CHAT(user_id))
            chats.sort(key=lambda c: c.key, reverse=True)
            recent_chats = chats[:15]

            if not recent_chats:
                return

            # 2. Format history for the LLM
            history_lines = []
            for c in reversed(recent_chats):
                v = c.value
                date_label = v.get("date_label", c.key)
                summary = v.get("summary", "")
                decisions = v.get("decisions", [])
                unfinished = v.get("left_unfinished", [])
                
                line = f"Session {date_label}:\n  Summary: {summary}"
                if decisions:
                    line += f"\n  Decisions: {', '.join(decisions)}"
                if unfinished:
                    line += f"\n  Unfinished: {', '.join(unfinished)}"
                history_lines.append(line)

            history_text = "\n\n".join(history_lines)

            # 3. Call LLM to extract patterns
            response = patterns_llm.invoke([
                SystemMessage(content=PATTERN_ANALYSIS_PROMPT.format(history=history_text)),
                HumanMessage(content="Extract patterns now.")
            ])

            patterns = parse_json_array(response.content)
            
            # Save to store
            store.put(NAMESPACE(user_id), PATTERNS_KEY, {
                "patterns": patterns,
                "updated_at": time.time()
            })
            print(f"[Patterns] Detected {len(patterns)} patterns: {patterns}")

        except Exception as e:
            print(f"[Patterns] Pattern detection failed: {e}")
