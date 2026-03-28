import warnings
warnings.filterwarnings("ignore")
warnings.filterwarnings("ignore", message=".*MemoryTrigger.*")
import threading
import builtins
from datetime import datetime

_original_print = builtins.print


def thread_safe_print(*args, **kwargs):
    if threading.current_thread().name == "MainThread":
        _original_print(*args, **kwargs)


builtins.print = thread_safe_print

from dotenv import load_dotenv
import interface

interface.setup_environment()
load_dotenv()

from langchain_core.messages import HumanMessage

from graph import build_graph
from ears import listen
from mouth import speak
from config import DEFAULT_USER_ID, DEFAULT_THREAD_ID, get_config, CHAT_LLM_MODEL
from database import create_store, create_checkpointer, setup_database, close_connections
from memory.rollup import refresh_active_rollups, rollup_if_needed
from memory.facts import archive_stale_facts
from memory.projects import archive_completed_projects
from memory.episodes import normalize_chat_summaries, write_chat_turn
from memory.utils import wait_for_background_jobs


USER_ID = DEFAULT_USER_ID
SESSION_THREAD_ID = f"{DEFAULT_THREAD_ID}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
config = get_config(USER_ID, SESSION_THREAD_ID)


def ask(graph, prompt: str, custom_config=None, show_spinner=True) -> str:
    try:
        if show_spinner:
            with interface.get_spinner("Parker is thinking..."):
                result = graph.invoke(
                    {"messages": [HumanMessage(content=prompt)]},
                    custom_config or config,
                )
        else:
            result = graph.invoke(
                {"messages": [HumanMessage(content=prompt)]},
                custom_config or config,
            )

        last_msg = result["messages"][-1]
        if hasattr(last_msg, "content"):
            return last_msg.content
        if isinstance(last_msg, dict):
            return last_msg.get("content", "")
        return ""
    except Exception as e:
        err_str = str(e)
        if "429" in err_str or "rate limit" in err_str.lower() or "rate_limit_exceeded" in err_str:
            interface.print_error("Groq API Rate Limit Exceeded.\nPlease wait a moment before sending another message.")
        else:
            interface.print_error(f"Failed to generate response: {err_str}")
        return "(API Error - Please retry)"


def session_start(store):
    interface.print_system("[Startup] Running session start hooks...")

    with interface.get_spinner("Running background rollups and maintenance..."):
        normalize_chat_summaries(store, USER_ID)
        rollup_if_needed(store, USER_ID)
        archive_stale_facts(store, USER_ID)
        archive_completed_projects(store, USER_ID)

    interface.print_success("Startup hooks complete.")


def session_end(store):
    interface.print_system("Refreshing summary tree...")
    refresh_active_rollups(store, USER_ID)

    interface.print_system("Saving session state...")
    store.put(("user", USER_ID, "state"), "last_session", {
        "date": datetime.now().strftime("%Y-%m-%d")
    })
    interface.print_success("Session state saved.")


if __name__ == "__main__":
    store = create_store()
    checkpointer = create_checkpointer()
    setup_database(store, checkpointer)

    graph = build_graph(store, checkpointer)
    session_start(store)

    interface.clear_screen()
    interface.print_parker_banner()
    interface.print_status_bar(model=CHAT_LLM_MODEL, memory="Active")
    interface.console.print()
    interface.print_commands_table()
    interface.print_divider()

    mode = "text"

    """
main.py — Parker AI CLI runtime
Updated to use the improved interface.py rendering.
Only the session loop is shown — startup/shutdown code is unchanged.
"""

# ── (after all the existing imports and setup) ─────────────────────────────────
# Replace the `while True` loop inside `if __name__ == "__main__":` with this:

    try:
        while True:
            # ── Get input ─────────────────────────────────────────────────────
            if mode == "text":
                user_input = interface.console.input(
                    interface.get_user_prompt("text")
                ).strip()
            else:
                interface.console.input(
                    interface.get_user_prompt("voice")
                )
                user_input = listen()

            if not user_input:
                interface.print_warning("Didn't catch that — try again.")
                continue

            # ── Commands ──────────────────────────────────────────────────────
            lower = user_input.lower()

            if lower in ("quit", "exit", "bye"):
                speak("Goodbye!")
                interface.print_goodbye()
                break

            if lower == "v":
                mode = "voice"
                interface.print_mode_switch("voice")
                interface.print_status_bar(model=CHAT_LLM_MODEL, memory="Active", mode=mode)
                continue

            if lower == "t":
                mode = "text"
                interface.print_mode_switch("text")
                interface.print_status_bar(model=CHAT_LLM_MODEL, memory="Active", mode=mode)
                continue

            if lower == "/clear":
                interface.clear_screen()
                interface.print_parker_banner()
                interface.print_status_bar(model=CHAT_LLM_MODEL, memory="Active", mode=mode)
                interface.print_commands_table()
                interface.print_divider()
                continue

            if lower == "/profile":
                from memory.profile import load_profile
                prof = load_profile(store, USER_ID)
                interface.print_profile_panel(prof)
                continue

            if lower == "/facts":
                from memory.facts import full_scan, NAMESPACE
                raw = full_scan(store, NAMESPACE(USER_ID))
                facts_list = [{"key": i.key, "content": i.value.get("content",""), "importance": i.value.get("importance","normal")} for i in raw]
                interface.print_facts_panel(facts_list)
                continue

            if lower == "/projects":
                from memory.projects import load_active_projects
                projs = load_active_projects(store, USER_ID)
                interface.print_projects_panel(projs)
                continue

            # ── Echo user message ─────────────────────────────────────────────
            interface.print_user(user_input)

            # ── Generate response ─────────────────────────────────────────────
            response = ask(graph, user_input)

            if response != "(API Error - Please retry)":
                write_chat_turn(store, USER_ID, user_input, response)
                interface.print_parker(response)         # BUG FIX: only speak in voice mode
                speak(response)

    except KeyboardInterrupt:
        interface.print_system("Parker shutting down…")

    finally:
        session_end(store)
        interface.print_system("Waiting for background memory writes…")
        wait_for_background_jobs()
        close_connections()
