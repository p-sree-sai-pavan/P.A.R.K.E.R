from datetime import datetime

from memory.profile   import load_profile, format_for_prompt as format_profile
from memory.facts     import (
    load_critical_facts,
    load_relevant_facts,
    load_archive_relevant,
    format_critical_for_prompt,
    format_relevant_for_prompt,
)
from memory.tasks           import check_conditions
from memory.reminder_gate    import run as reminder_gate, format_approved_for_prompt
from memory.projects  import (
    load_active_projects,
    load_relevant_projects,
    format_active_for_prompt,
)
from memory.episodes  import load_relevant_episodes, format_for_prompt as format_episodes


def build_context(store, user_id: str, message: str, recent_history: list = None, llm=None) -> dict:
    """
    Assembles everything that goes into the system prompt for this turn.

    Called once per turn in chat_node.
    Returns a dict — each key maps to a section in SYSTEM_PROMPT_TEMPLATE.

    Load order matters:
    1. Profile          — always full, no search
    2. Active projects  — always full, no search (used as search context for facts)
    3. Critical facts   — always full, no search
    4. Relevant facts   — semantic search using message + active project names
    5. Archive facts    — semantic search, low-priority surface
    6. Tasks            — condition check + semantic search
    7. Episodes         — hierarchical drill-down search
    8. Current time     — injected last
    """

    # ── 1. Profile ─────────────────────────────────────────────────────────────
    profile      = load_profile(store, user_id)
    profile_text = format_profile(profile)

    # ── 2. Active projects ─────────────────────────────────────────────────────
    # Loaded before facts — project names are used as additional search context
    active_projects      = load_active_projects(store, user_id)
    active_project_names = [p.value.get("name", p.key) for p in active_projects]
    projects_text        = format_active_for_prompt(active_projects)

    # ── 3. Critical facts — always injected ────────────────────────────────────
    critical_items = load_critical_facts(store, user_id)
    critical_text  = format_critical_for_prompt(critical_items)

    # ── 4. Relevant facts — semantic search ────────────────────────────────────
    relevant_items = load_relevant_facts(
        store, user_id,
        query=message,
        active_project_names=active_project_names,
    )
    # Also check archived facts for anything relevant
    archive_items  = load_archive_relevant(store, user_id, query=message)

    # Merge archive into relevant — archive items go last (lower priority)
    existing_keys  = {i.key for i in relevant_items}
    for item in archive_items:
        if item.key not in existing_keys:
            relevant_items.append(item)

    relevant_text = format_relevant_for_prompt(relevant_items)

    # ── 5. Tasks — run through reminder gate before injecting into prompt ───────
    # check_conditions returns all due tasks based on time/condition
    # reminder_gate filters them: suppresses on greetings, acks, already-seen
    due_tasks   = check_conditions(store, user_id, message=message)
    gate_result = reminder_gate(
        llm            = llm,
        user_message   = message,
        recent_history = recent_history or [],
        due_tasks      = due_tasks,
    )
    approved_tasks = gate_result["approved_tasks"]
    tasks_text     = format_approved_for_prompt(approved_tasks)

    # ── 6. Episodes — hierarchical drill-down ──────────────────────────────────
    episodes       = load_relevant_episodes(store, user_id, query=message)
    episodes_text  = format_episodes(episodes)

    # ── 7. Current time ────────────────────────────────────────────────────────
    now          = datetime.now()
    current_time = now.strftime("%A, %B %d %Y, %I:%M %p")

    return {
        "profile":          profile_text,
        "active_projects":  projects_text,
        "critical_facts":   critical_text,
        "relevant_facts":   relevant_text,
        "approved_reminders": tasks_text,
        "relevant_episodes":episodes_text,
        "current_time":     current_time,
        # Pass gate result so graph.py can:
        # - call mark_completed for gate_result["complete"]
        # - call increment_notify for approved tasks after response
        "_gate_result": gate_result,
    }