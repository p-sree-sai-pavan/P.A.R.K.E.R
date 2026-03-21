import json
import threading
from langchain_core.messages import SystemMessage

from models import memory_llm
from prompts import PROFILE_EXTRACTION_PROMPT
from memory.utils import format_messages, parse_json_object, full_scan


PROFILE_KEY = "profile"
NAMESPACE   = lambda user_id: ("user", user_id, "profile")


def load_profile(store, user_id: str) -> dict:
    """
    Profile is always a single document — plain scan, no semantic search.
    """
    items = full_scan(store, NAMESPACE(user_id))
    return items[0].value if items else {}


def save_profile(store, user_id: str, messages: list):
    t = threading.Thread(
        target=_extract_and_save,
        args=(store, user_id, messages),
        daemon=True,
    )
    t.start()


def _extract_and_save(store, user_id: str, messages: list):
    try:
        existing     = load_profile(store, user_id)
        conversation = format_messages(messages)

        response = memory_llm.invoke([
            SystemMessage(content=PROFILE_EXTRACTION_PROMPT.format(
                existing_profile=json.dumps(existing, indent=2) if existing else "(empty)",
                conversation=conversation,
            ))
        ])

        extracted = parse_json_object(response.content)
        if not extracted:
            return

        updated = existing.copy()
        for key, value in extracted.items():
            if value not in (None, "", [], {}):
                updated[key] = value

        store.put(NAMESPACE(user_id), PROFILE_KEY, updated)
        print(f"[Profile] Updated: {list(extracted.keys())}")

    except Exception as e:
        print(f"[Profile] Failed: {e}")


def format_for_prompt(profile: dict) -> str:
    if not profile:
        return "(no profile yet)"
    return "\n".join(f"{k}: {v}" for k, v in profile.items())