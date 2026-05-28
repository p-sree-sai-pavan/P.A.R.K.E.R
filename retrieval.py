import re
from datetime import datetime

from memory.profile import load_profile, format_for_prompt as format_profile
from memory.facts import (
    load_critical_facts,
    load_relevant_facts,
    load_archive_relevant,
    format_critical_for_prompt,
    format_relevant_for_prompt,
)
from memory.projects import (
    load_active_projects,
    load_relevant_projects,
    format_active_for_prompt,
    format_relevant_for_prompt as format_relevant_projects_for_prompt,
)
from memory.episodes import load_relevant_episodes, format_for_prompt as format_episodes
from memory.tasks import load_relevant_tasks, format_tasks_for_prompt
from memory.patterns import load_patterns, format_patterns_for_prompt
from computer.telemetry import get_system_telemetry, format_telemetry_for_prompt


_FOLLOWUP_MEMORY_PATTERNS = [
    r"\bagain\b",
    r"\bbefore\b",
    r"\bprevious\b",
    r"\bearlier\b",
    r"\byesterday\b",
    r"\bit\b",
    r"\bthat\b",
    r"\bthose\b",
    r"\bthem\b",
    r"\bchat\b",
    r"\bconversation\b",
]


def build_context(store, user_id: str, message: str, recent_history: list = None, llm=None) -> dict:
    """
    Assembles the memory context for this turn.
    """
    profile = load_profile(store, user_id)
    profile_text = format_profile(profile)

    active_projects = load_active_projects(store, user_id)
    relevant_projects = load_relevant_projects(store, user_id, query=message)
    active_project_names = [p.value.get("name", p.key) for p in active_projects]
    projects_text = format_active_for_prompt(active_projects)

    active_project_keys = {p.key for p in active_projects}
    historical_projects = [
        p for p in relevant_projects
        if p.key not in active_project_keys
    ]
    if historical_projects:
        projects_text = (
            f"{projects_text}\n\nRelated project history:\n"
            f"{format_relevant_projects_for_prompt(historical_projects)}"
        )

    critical_items = load_critical_facts(store, user_id)
    critical_text = format_critical_for_prompt(critical_items)

    relevant_items = load_relevant_facts(
        store,
        user_id,
        query=message,
        active_project_names=active_project_names,
    )
    archive_items = load_archive_relevant(store, user_id, query=message)

    critical_keys = {item.key for item in critical_items}
    existing_keys = {item.key for item in relevant_items} | critical_keys
    for item in archive_items:
        if item.key not in existing_keys:
            relevant_items.append(item)

    relevant_text = format_relevant_for_prompt(relevant_items)

    episode_query = _build_episode_query(message, recent_history or [])
    episodes = load_relevant_episodes(store, user_id, query=episode_query)
    episodes_text = format_episodes(episodes)

    tasks = load_relevant_tasks(store, user_id, query=message)
    tasks_text = format_tasks_for_prompt(tasks)

    patterns = load_patterns(store, user_id)
    patterns_text = format_patterns_for_prompt(patterns)

    now = datetime.now()
    current_time = now.strftime("%A, %B %d %Y, %I:%M %p")
    
    telemetry_data = get_system_telemetry()
    telemetry_text = format_telemetry_for_prompt(telemetry_data)

    from memory.skills import get_available_skills_prompt
    skills_text = get_available_skills_prompt(query=message)

    return {
        "profile": profile_text,
        "active_projects": projects_text,
        "critical_facts": critical_text,
        "relevant_facts": relevant_text,
        "relevant_episodes": episodes_text,
        "pending_tasks": tasks_text,
        "observed_patterns": patterns_text,
        "skills": skills_text,
        "current_time": current_time,
        "telemetry": telemetry_text,
    }


def build_lightweight_context(store, user_id: str, query: str = None) -> dict:
    """
    Loads profile, critical facts, active projects, active tasks, and patterns 
    without doing any semantic vector search (avoiding Ollama embedding latency).
    """
    profile = load_profile(store, user_id)
    profile_text = format_profile(profile)

    active_projects = load_active_projects(store, user_id)
    projects_text = format_active_for_prompt(active_projects)

    critical_items = load_critical_facts(store, user_id)
    critical_text = format_critical_for_prompt(critical_items)

    patterns = load_patterns(store, user_id)
    patterns_text = format_patterns_for_prompt(patterns)

    # Directly load active tasks (no semantic matches)
    from memory.tasks import load_active_tasks
    tasks = load_active_tasks(store, user_id)
    tasks_text = format_tasks_for_prompt(tasks)

    telemetry_data = get_system_telemetry()
    telemetry_text = format_telemetry_for_prompt(telemetry_data)

    now = datetime.now()
    current_time = now.strftime("%A, %B %d %Y, %I:%M %p")

    from memory.skills import get_available_skills_prompt
    skills_text = get_available_skills_prompt(query=query)

    return {
        "profile": profile_text,
        "active_projects": projects_text,
        "critical_facts": critical_text,
        "relevant_facts": "",
        "relevant_episodes": "",
        "pending_tasks": tasks_text,
        "observed_patterns": patterns_text,
        "skills": skills_text,
        "current_time": current_time,
        "telemetry": telemetry_text,
    }


def _build_episode_query(message: str, recent_history: list) -> str:
    base = (message or "").strip()
    if not base:
        return ""

    parts = [base]
    if not _should_expand_episode_query(base):
        return base

    for msg in reversed(recent_history[:-1]):
        content = _message_content(msg).strip()
        if not content:
            continue
        if content == base:
            continue
        if content.lower() in ("i don't have records of that yet, pavan.", "i don't recall that, sir."):
            continue
        parts.append(content)
        if len(parts) >= 4:
            break

    seen = []
    for part in parts:
        if part not in seen:
            seen.append(part)
    return "\n".join(seen)


def _should_expand_episode_query(message: str) -> bool:
    lowered = message.lower()
    short_message = len(lowered.split()) <= 10
    return short_message or any(re.search(pattern, lowered) for pattern in _FOLLOWUP_MEMORY_PATTERNS)


def _message_content(msg) -> str:
    if hasattr(msg, "content"):
        c = msg.content
        if isinstance(c, list):
            parts = []
            for item in c:
                if isinstance(item, dict):
                    if "text" in item:
                        parts.append(item["text"])
                    elif item.get("type") == "text":
                        parts.append(item.get("text", ""))
                elif isinstance(item, str):
                    parts.append(item)
            return "".join(parts)
        return c or ""
    if isinstance(msg, dict):
        return msg.get("content", "") or ""
    return str(msg)
