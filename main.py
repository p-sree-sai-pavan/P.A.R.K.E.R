import warnings
warnings.filterwarnings("ignore")
warnings.filterwarnings("ignore", message=".*MemoryTrigger.*")
import threading
import builtins
from datetime import datetime
from memory.episodes import write_chat_turn_async


_original_print = builtins.print


def thread_safe_print(*args, **kwargs):
    if threading.current_thread().name != "MainThread":
        msg = " ".join(str(a) for a in args)
        msg_lower = msg.lower()
        has_failure = any(keyword in msg_lower for keyword in ("error", "fail", "warn", "except"))
        if not has_failure:
            if any(tag in msg for tag in ("[Facts]", "[Profile]", "[Projects]", "[Rollup]", "[Episodes]")):
                return
    _original_print(*args, **kwargs)


builtins.print = thread_safe_print

from dotenv import load_dotenv
import interface

interface.setup_environment()
load_dotenv()

from langchain_core.messages import HumanMessage

from graph import build_graph
from mouth import speak
from config import DEFAULT_USER_ID, DEFAULT_THREAD_ID, get_config, CHAT_LLM_MODEL
from database import create_store, create_checkpointer, setup_database, close_connections
from memory.rollup import refresh_active_rollups, rollup_if_needed
from memory.facts import archive_stale_facts
from memory.projects import archive_completed_projects
from memory.episodes import normalize_chat_summaries, write_chat_turn, NS_CHAT
from memory.utils import wait_for_background_jobs, full_scan
from memory.patterns import detect_behavioral_patterns, load_patterns
from memory.tasks import archive_completed_tasks, load_active_tasks


USER_ID = DEFAULT_USER_ID
SESSION_THREAD_ID = f"{DEFAULT_THREAD_ID}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
config = get_config(USER_ID, SESSION_THREAD_ID)

def generate_startup_greeting(store, user_id: str) -> str:
    """
    Fetch weather, active projects, unfinished threads from last chat episode, and pending tasks.
    Run a fast LLM query to produce a 2-sentence JARVIS-style greeting.
    """
    try:
        from computer.apis import get_weather
        weather_info = get_weather()
        loc = weather_info.get("location", "Hanamkonda")
        temp = weather_info.get("temperature")
        cond = weather_info.get("condition", "")
        weather_str = f"{temp}°C, {cond} in {loc}" if temp is not None else "Weather data unavailable"
    except Exception as e:
        print(f"[Greeting] Weather fetch failed: {e}")
        weather_str = "Weather data unavailable"

    try:
        from memory.projects import load_active_projects
        active_projects = load_active_projects(store, user_id)
        proj_names = [p.value.get("name", p.key) for p in active_projects]
        proj_str = ", ".join(proj_names) if proj_names else "none"
    except Exception as e:
        print(f"[Greeting] Projects fetch failed: {e}")
        proj_str = "none"

    try:
        active_tasks = load_active_tasks(store, user_id)
        task_descriptions = [f"{t.value.get('content')} ({t.value.get('priority', 'normal')})" for t in active_tasks]
        tasks_str = "; ".join(task_descriptions[:3]) if task_descriptions else "none"
    except Exception as e:
        print(f"[Greeting] Tasks fetch failed: {e}")
        tasks_str = "none"

    unfinished_str = "none"
    try:
        chats = full_scan(store, NS_CHAT(user_id))
        if chats:
            chats.sort(key=lambda c: c.key, reverse=True)
            last_chat = chats[0].value
            unfinished = last_chat.get("left_unfinished", [])
            if unfinished:
                unfinished_str = "; ".join(unfinished)
    except Exception as e:
        print(f"[Greeting] Last chat fetch failed: {e}")

    try:
        patterns = load_patterns(store, user_id)
        patterns_str = "; ".join(patterns) if patterns else "none"
    except Exception as e:
        print(f"[Greeting] Patterns fetch failed: {e}")
        patterns_str = "none"

    greeting_prompt = f"""You are Parker, a personal AI modeled on JARVIS from Iron Man.
Generate a sharp, dry, one-line startup greeting for Pavan (always address him as "sir").
Demonstrate proactive awareness — pick ONE or TWO of the most relevant items from context and weave them into a single sentence naturally.

CONTEXT:
- Time of Day: {datetime.now().strftime("%I:%M %p")}
- Current Date/Weekday: {datetime.now().strftime("%A, %B %d")}
- Current Weather: {weather_str}
- Active Projects: {proj_str}
- Pending Tasks/Reminders: {tasks_str}
- Unfinished from Last Session: {unfinished_str}
- Observed Behavior Patterns & Habits: {patterns_str}

RULES:
1. MAXIMUM 2 sentences. Prefer 1.
2. Speak like a British butler — calm, dry, precise. No enthusiasm.
3. Do NOT list items mechanically. Pick the most interesting/relevant one and mention it organically.
4. Do NOT end with a question. End as a statement of readiness.
5. No markdown, tags, or emojis. Plain text only.

Greeting:"""

    try:
        from models import chat_llm
        from langchain_core.messages import SystemMessage, HumanMessage
        from memory.utils import get_message_content
        response = chat_llm.invoke([
            SystemMessage(content=greeting_prompt),
            HumanMessage(content="Generate greeting.")
        ])
        greeting = get_message_content(response).strip()
        # Clean any quotes or formatting
        greeting = greeting.replace('"', '').replace("'", "")
        if greeting:
            return greeting
    except Exception as e:
        print(f"[Greeting] Generation failed: {e}")
        
    return (
        "Good evening, Pavan. All systems are online and memory is synchronized. "
        "Ready on your command, sir."
    )


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
        from memory.utils import get_message_content
        return get_message_content(last_msg)
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
        archive_completed_tasks(store, USER_ID)
        detect_behavioral_patterns(store, USER_ID)
        wait_for_background_jobs()
    interface.print_success("Startup hooks complete.")


def session_end(store):
    interface.print_system("Refreshing summary tree...")
    refresh_active_rollups(store, USER_ID)
    interface.print_system("Saving session state...")
    store.put(("user", USER_ID, "state"), "last_session", {
        "date": datetime.now().strftime("%Y-%m-%d")
    })
    interface.print_success("Session state saved.")


# ── Asynchronous & Proactive Helpers ──────────────────────────────────────────
import queue
import time
import re
from live_voice import (
    start_live_voice_session,
    stop_live_voice_session,
    is_live_session_active,
)


def _build_live_system_prompt(store) -> str:
    """Build the full Parker system prompt with memory context for the Live session."""
    from prompts.chat import BASE_INSTRUCTIONS, SYSTEM_PROMPT_TEMPLATE
    from retrieval import build_context
    from config import USER_ID
    from datetime import datetime

    context = build_context(store, USER_ID, message="[voice session start]", recent_history=[])

    def _section(title, content):
        if not content or content in ("(none)", "(no profile yet)", ""):
            return ""
        return f"## {title}\n{content}\n\n"

    return SYSTEM_PROMPT_TEMPLATE.format(
        base_instructions=BASE_INSTRUCTIONS,
        current_time=datetime.now().strftime("%A, %B %d, %Y — %I:%M %p"),
        profile=_section("YOUR PROFILE OF PAVAN", context.get("profile", "")),
        critical_facts=_section("HARD CONSTRAINTS", context.get("critical_facts", "")),
        relevant_facts=_section("THINGS YOU REMEMBER ABOUT PAVAN", context.get("relevant_facts", "")),
        active_projects=_section("PROJECTS YOU ARE CURRENTLY TRACKING", context.get("active_projects", "")),
        pending_tasks=_section("YOUR ACTIVE TASK LIST", context.get("pending_tasks", "")),
        observed_patterns=_section("OBSERVED BEHAVIOR PATTERNS & HABITS", context.get("observed_patterns", "")),
        relevant_episodes=_section(
            "YOUR RECENT RECOLLECTIONS (CHRONOLOGICAL)\nEach entry below has an exact key (ISO timestamp or date). Use these for any date reference — never guess.",
            context.get("relevant_episodes", ""),
        ),
        telemetry=_section("LIVE ENVIRONMENT TELEMETRY", context.get("telemetry", "")),
    )


def update_listener_mode(current_mode, input_queue, store=None):
    if current_mode == "voice":
        if not is_live_session_active():
            system_prompt = _build_live_system_prompt(store) if store else ""
            start_live_voice_session(
                system_prompt=system_prompt,
                on_user_transcript=lambda t: interface.print_user(f"[You] {t}"),
                on_parker_transcript=lambda t: interface.print_parker(f"{t}"),
                on_session_end=lambda: interface.print_system("[Live Voice] Session ended."),
            )
    else:
        if is_live_session_active():
            stop_live_voice_session()


def apply_persona_filters(text: str) -> str:
    """
    Strips polite AI chatbot filler, reasoning monologue, and trailing questions.
    """
    if not text:
        return text
    
    # 0. Strip reasoning monologue <think>...</think> blocks
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE)
    
    # 1. Banned leading filler
    fillers = [
        r"^(certainly|absolutely|of course|sure|great|happy to help|no problem|understood|i understand|i see|that makes sense|indeed),?\s*",
        r"^here is the information,?\s*",
        r"^i have retrieved,?\s*",
    ]
    for f in fillers:
        cleaned = re.sub(f, "", cleaned, flags=re.IGNORECASE)
        
    # 2. Banned trailing questions or polite helper queries
    trailing = [
        r"\bhow does that sound\??$",
        r"\bwould you like me to.*$",
        r"\bis there anything else.*$",
        r"\blet me know if.*$",
        r"\bfeel free to.*$",
    ]
    for t in trailing:
        cleaned = re.sub(t, "", cleaned, flags=re.IGNORECASE)
        
    return cleaned.strip()


def parse_due_date(due_str: str):
    if not due_str:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(due_str.strip(), fmt)
            if fmt == "%Y-%m-%d":
                dt = dt.replace(hour=23, minute=59, second=59)
            return dt
        except ValueError:
            continue
    return None


def send_telegram_notification(message: str):
    import os
    import requests
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_ALLOWED_USER")
    if not token or not chat_id:
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message
    }
    try:
        res = requests.post(url, json=payload, timeout=10)
        res.raise_for_status()
    except Exception as e:
        print(f"[Telegram Notifier Warning] Failed to send notification: {e}")


def proactive_monitor_loop(store, input_queue):
    notified_overdue_tasks = set()
    notified_late_night = False
    
    while True:
        # Check environment and tasks every 30 seconds
        for _ in range(30):
            time.sleep(1)
            
        try:
            # 1. Overdue tasks check
            active_tasks = load_active_tasks(store, USER_ID)
            now = datetime.now()
            
            for task in active_tasks:
                due_str = task.value.get("due")
                if due_str:
                    due_dt = parse_due_date(due_str)
                    if due_dt and now > due_dt:
                        task_key = task.key
                        if task_key not in notified_overdue_tasks:
                            notified_overdue_tasks.add(task_key)
                            content = task.value.get("content", "")
                            alert_msg = f"Sir, your task '{content}' was due at {due_str}. It is currently overdue."
                            
                            # Interrupt speech
                            stop_speaking()
                            
                            # Print, speak, and send Telegram message
                            print()
                            interface.print_parker(alert_msg)
                            speak(alert_msg)
                            send_telegram_notification(alert_msg)
                            
            # 2. Late night alert check
            hour = now.hour
            if (hour >= 23 or hour < 4) and not notified_late_night:
                from computer.telemetry import get_active_window_title, get_git_status
                window = get_active_window_title().lower()
                
                # Check if user is coding
                is_coding = any(editor in window for editor in ("vs code", "visual studio", "sublime", "pycharm", "vim", "terminal", "powershell", "command prompt", "git"))
                if is_coding:
                    git_status = get_git_status()
                    uncommitted = git_status != "Clean (No modifications)" and "not a git" not in git_status.lower()
                    
                    if uncommitted:
                        alert_msg = f"Sir, it is past midnight ({now.strftime('%I:%M %p')}) and you are still coding. I notice you have uncommitted changes in your repository. I suggest committing and calling it a night."
                    else:
                        alert_msg = f"Sir, it is past midnight ({now.strftime('%I:%M %p')}) and you are still coding in {get_active_window_title()}. I suggest calling it a night."
                        
                    stop_speaking()
                    print()
                    interface.print_parker(alert_msg)
                    speak(alert_msg)
                    send_telegram_notification(alert_msg)
                    notified_late_night = True
                    
            if 8 <= hour < 20:
                notified_late_night = False
                
        except Exception as e:
            pass


def cli_input_loop(input_queue, mode_holder):
    while True:
        try:
            current_mode = mode_holder["mode"]
            prompt = interface.get_user_prompt(current_mode)
            user_input = interface.console.input(prompt).strip()
            if user_input:
                input_queue.put({"type": "text", "text": user_input})
        except (KeyboardInterrupt, EOFError):
            input_queue.put({"type": "exit"})
            break


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

    # Intro — print and speak
    with interface.get_spinner("Parker is computing greeting..."):
        intro = generate_startup_greeting(store, USER_ID)
        from computer.telemetry import get_system_telemetry
        telemetry = get_system_telemetry()
    intro_cleaned = apply_persona_filters(intro)
    interface.print_parker(intro_cleaned)
    interface.print_telemetry_dashboard(telemetry)
    speak(intro_cleaned)

    # State containers
    mode_holder = {"mode": "text"}
    input_queue = queue.Queue()

    # Start CLI input thread
    cli_thread = threading.Thread(
        target=cli_input_loop,
        args=(input_queue, mode_holder),
        name="CLIInputThread",
        daemon=True
    )
    cli_thread.start()

    # Start proactive background monitor thread
    monitor_thread = threading.Thread(
        target=proactive_monitor_loop,
        args=(store, input_queue),
        name="ProactiveMonitorThread",
        daemon=True
    )
    monitor_thread.start()

    try:
        while True:
            # Wait for any input (text from CLI, or voice from Continuous Listener)
            try:
                event = input_queue.get(timeout=1.0)
            except queue.Empty:
                continue

            if event["type"] == "exit":
                speak("Goodbye, Pavan.")
                interface.print_goodbye()
                break

            user_input = event["text"]
            lower = user_input.lower()

            if lower in ("quit", "exit", "bye"):
                speak("Goodbye, Pavan.")
                interface.print_goodbye()
                break

            if lower == "v":
                mode_holder["mode"] = "voice"
                update_listener_mode("voice", input_queue, store)
                interface.print_mode_switch("voice")
                interface.print_status_bar(model=CHAT_LLM_MODEL, memory="Active", mode="voice")
                continue

            if lower == "t":
                mode_holder["mode"] = "text"
                update_listener_mode("text", input_queue, store)
                interface.print_mode_switch("text")
                interface.print_status_bar(model=CHAT_LLM_MODEL, memory="Active", mode="text")
                continue

            if lower == "/clear":
                interface.clear_screen()
                interface.print_parker_banner()
                interface.print_status_bar(model=CHAT_LLM_MODEL, memory="Active", mode=mode_holder["mode"])
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
                facts_list = [{"key": i.key, "content": i.value.get("content", ""), "importance": i.value.get("importance", "normal")} for i in raw]
                interface.print_facts_panel(facts_list)
                continue

            if lower == "/projects":
                from memory.projects import load_active_projects
                projs = load_active_projects(store, USER_ID)
                interface.print_projects_panel(projs)
                continue

            if lower == "/tasks":
                raw = load_active_tasks(store, USER_ID)
                interface.print_tasks_panel(raw)
                continue

            if lower in ("/skills", "/skill"):
                from memory.skills import get_all_skills
                skills_list = get_all_skills()
                interface.print_skills_panel(skills_list)
                continue

            if lower == "/patterns":
                from memory.patterns import load_patterns
                raw = load_patterns(store, USER_ID)
                interface.print_patterns_panel(raw)
                continue

            if lower == "/telemetry":
                from computer.telemetry import get_system_telemetry
                telemetry = get_system_telemetry()
                interface.print_telemetry_dashboard(telemetry)
                continue

            if lower.startswith("/import "):
                parts = user_input.split(" ", 1)
                if len(parts) < 2:
                    interface.print_error("Please specify the file path: /import <filepath>")
                    continue
                file_path = parts[1].strip()
                if (file_path.startswith('"') and file_path.endswith('"')) or (file_path.startswith("'") and file_path.endswith("'")):
                    file_path = file_path[1:-1]
                try:
                    from import_memory import run_import
                    with interface.get_spinner(f"Importing memories from {file_path}..."):
                        stats = run_import(file_path, USER_ID)
                    
                    t = interface.Table(show_header=True, header_style="ac.bold", box=interface.box.ROUNDED, border_style="border")
                    t.add_column("Category", style="pk")
                    t.add_column("Items Imported", style="tx.bold", justify="right")
                    for k, v in stats.items():
                        t.add_row(k, str(v))
                    
                    interface.console.print()
                    interface.console.print(interface.Padding(t, (0, 4, 0, 4)))
                    interface.print_success("Import completed successfully.")
                except Exception as e:
                    interface.print_error(f"Import failed: {str(e)}")
                continue

            # Echo voice inputs to the console so Pavan sees what Whisper heard
            if event["type"] == "voice":
                interface.print_user(user_input)

            # Generate response
            response = ask(graph, user_input)

            if response != "(API Error - Please retry)":
                response_cleaned = apply_persona_filters(response)
                interface.print_parker(response_cleaned)
                interface.print_status_bar(model=CHAT_LLM_MODEL, memory="Active", mode=mode_holder["mode"])
                speak(response_cleaned)

    except KeyboardInterrupt:
        interface.print_system("Parker shutting down…")

    finally:
        # Stop Gemini Live voice session if active
        update_listener_mode("text", input_queue, store)
        interface.print_system("Waiting for background memory writes…")
        wait_for_background_jobs()
        session_end(store)
        close_connections()