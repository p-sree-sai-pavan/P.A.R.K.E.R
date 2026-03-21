from dotenv import load_dotenv
load_dotenv()

import threading
from graph import build_graph
from ears import listen
from mouth import speak
from config import DEFAULT_USER_ID, DEFAULT_THREAD_ID, get_config
from database import create_store, create_checkpointer, setup_database
from memory.rollup   import rollup_if_needed
from memory.tasks    import tick_sessions
from memory.facts    import archive_stale_facts
from memory.projects import archive_completed_projects
from memory.episodes import write_chat_entry
from reminder import start_reminder_thread


USER_ID   = DEFAULT_USER_ID
THREAD_ID = DEFAULT_THREAD_ID
config    = get_config(USER_ID, THREAD_ID)



from langchain_core.messages import HumanMessage

def ask(graph, prompt: str) -> str:
    result = graph.invoke(
        {"messages": [HumanMessage(content=prompt)]},
        config,
    )
    # Check if last message is an object or dict
    last_msg = result["messages"][-1]
    if hasattr(last_msg, "content"):
        return last_msg.content
    if isinstance(last_msg, dict):
        return last_msg.get("content", "")
    return ""


def session_start(store):
    """
    Runs once when Parker comes online.
    Order matters — rollup before archive, archive before conversation.
    """
    print("[Startup] Running session start hooks...")

    # 1. Roll up any time boundaries crossed since last session
    # (day → week → month → year → decade)
    rollup_if_needed(store, USER_ID)

    # 2. Tick session counters for task snooze logic
    tick_sessions(store, USER_ID)

    # 3. Archive stale low-importance facts
    archive_stale_facts(store, USER_ID)

    # 4. Archive completed/abandoned projects
    archive_completed_projects(store, USER_ID)

    print("[Startup] Done.\n")


def session_end(store, messages: list):
    """
    Runs once when user exits.
    Blocking — intentional. User is leaving, 2-3 seconds is fine.
    """
    if not messages:
        return

    print("\n[Shutdown] Writing session memory...")
    write_chat_entry(store, USER_ID, messages)
    print("[Shutdown] Done.")


if __name__ == "__main__":
    store       = create_store()
    checkpointer = create_checkpointer()
    setup_database(store, checkpointer)

    graph = build_graph(store, checkpointer)
    start_reminder_thread(store, USER_ID, ask, graph, speak)

    # Session start hooks
    session_start(store)

    print("Parker is online.")
    print("Commands: 't' = text mode | 'v' = voice mode | 'exit' = quit\n")

    mode     = "text"
    messages = []   # track messages for session_end write

    print("Current mode: TEXT. Type 'v' to switch to voice.\n")

    try:
        while True:
            if mode == "text":
                user_input = input("you (t): ").strip()
                if user_input.lower() == "v":
                    mode = "voice"
                    print("Switched to VOICE mode. Type 't' to switch back.\n")
                    continue
            else:
                cmd = input("you (v) — press Enter to speak, or type 't' to switch: ").strip()
                if cmd.lower() == "t":
                    mode = "text"
                    print("Switched to TEXT mode. Type 'v' to switch to voice.\n")
                    continue
                user_input = listen()

            if not user_input:
                print("Didn't catch that, try again.")
                continue

            if user_input.lower() in ("quit", "exit", "bye"):
                speak("Goodbye!")
                print("Goodbye!")
                break

            # Track messages for session_end
            messages.append({"role": "user", "content": user_input})

            response = ask(graph, user_input)

            messages.append({"role": "assistant", "content": response})

            print(f"\nParker: {response}\n")
            speak(response)

    except KeyboardInterrupt:
        print("\nParker shutting down...")

    finally:
        # Always write session memory even on Ctrl+C
        session_end(store, messages)
