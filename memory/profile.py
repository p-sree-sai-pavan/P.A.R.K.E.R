import json
from langchain_core.messages import SystemMessage

from models import profile_llm
from prompts.memory import PROFILE_EXTRACTION_PROMPT
from memory.utils import (
    format_messages,
    parse_json_object,
    full_scan,
    get_ns_lock,
    start_background_job,
)


PROFILE_KEY = "profile"
NAMESPACE   = lambda user_id: ("user", user_id, "profile")


def load_profile(store, user_id: str) -> dict:
    items = full_scan(store, NAMESPACE(user_id))
    return items[0].value if items else {}


def save_profile(store, user_id: str, messages: list):
    start_background_job(
        _extract_and_save,
        store,
        user_id,
        messages,
        name="profile-save",
    )


def _extract_and_save(store, user_id: str, messages: list):
    # D2 fix: lock namespace before read-modify-write
    with get_ns_lock(NAMESPACE(user_id)):
        try:
            existing     = load_profile(store, user_id)
            conversation = format_messages(messages)

            response = profile_llm.invoke([
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
