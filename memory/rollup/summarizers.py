import time
from datetime import datetime

from langchain_core.messages import SystemMessage

from memory.utils import full_scan, parse_json_object
from models import memory_llm
from prompts.rollup import (
    DAY_ROLLUP_PROMPT,
    WEEK_ROLLUP_PROMPT,
    MONTH_ROLLUP_PROMPT,
    YEAR_ROLLUP_PROMPT,
)

NS_CHAT = lambda user_id: ("user", user_id, "mem", "chat")
NS_DAY = lambda user_id: ("user", user_id, "mem", "day")
NS_WEEK = lambda user_id: ("user", user_id, "mem", "week")
NS_MONTH = lambda user_id: ("user", user_id, "mem", "month")
NS_YEAR = lambda user_id: ("user", user_id, "mem", "year")


def _rollup_day(store, user_id: str, date_str: str):
    chat_items = [
        item for item in full_scan(store, NS_CHAT(user_id))
        if item.key.startswith(date_str)
    ]
    if not chat_items:
        return

    chat_items.sort(key=lambda item: item.key)
    sessions_text = "\n\n".join(
        f"[{item.value.get('date_label', item.key)}] {item.value.get('summary', '')}"
        for item in chat_items
    )

    parsed = _parse_rollup(
        DAY_ROLLUP_PROMPT.format(
            date_label=date_str,
            sessions=sessions_text or "(no activity)",
        )
    )

    summary = parsed.get("summary") or _fallback_summary(chat_items, f"{date_str} day")
    key_topics = parsed.get("key_topics") or _fallback_topics(chat_items)
    projects_touched = parsed.get("projects_touched") or _fallback_projects(chat_items)

    store.put(NS_DAY(user_id), date_str, {
        "level": "day",
        "date": date_str,
        "date_label": date_str,
        "summary": summary,
        "key_topics": key_topics,
        "projects_touched": projects_touched,
        "total_sessions": parsed.get("total_sessions", len(chat_items)),
        "created_at": time.time(),
        "text": _build_rollup_text(summary, key_topics, projects_touched),
    })
    print(f"[Rollup] Saved DAY: {date_str}")


def _rollup_week(store, user_id: str, week_label: str):
    day_items = [
        item for item in full_scan(store, NS_DAY(user_id))
        if _day_in_week(item.key, week_label)
    ]
    if not day_items:
        return

    day_items.sort(key=lambda item: item.key)
    days_text = "\n".join(
        f"{item.key}: {item.value.get('summary', '')}"
        for item in day_items
    )

    parsed = _parse_rollup(
        WEEK_ROLLUP_PROMPT.format(
            week_label=week_label,
            days=days_text or "(no days)",
        )
    )

    summary = parsed.get("summary") or _fallback_summary(day_items, f"week {week_label}")
    key_topics = parsed.get("key_topics") or _fallback_topics(day_items)
    projects_touched = parsed.get("projects_touched") or _fallback_projects(day_items)

    store.put(NS_WEEK(user_id), week_label, {
        "level": "week",
        "date_label": f"Week {week_label}",
        "summary": summary,
        "key_topics": key_topics,
        "projects_touched": projects_touched,
        "created_at": time.time(),
        "text": _build_rollup_text(summary, key_topics, projects_touched),
    })
    print(f"[Rollup] Saved WEEK: {week_label}")


def _rollup_month(store, user_id: str, month_label: str):
    week_items = [
        item for item in full_scan(store, NS_WEEK(user_id))
        if _week_in_month(item.key, month_label)
    ]
    if not week_items:
        return

    week_items.sort(key=lambda item: item.key)
    weeks_text = "\n".join(
        f"{item.key}: {item.value.get('summary', '')}"
        for item in week_items
    )

    parsed = _parse_rollup(
        MONTH_ROLLUP_PROMPT.format(
            month_label=month_label,
            weeks=weeks_text or "(no weeks)",
        )
    )

    summary = parsed.get("summary") or _fallback_summary(week_items, f"month {month_label}")
    key_topics = parsed.get("key_topics") or _fallback_topics(week_items)
    projects_touched = parsed.get("projects_touched") or _fallback_projects(week_items)

    store.put(NS_MONTH(user_id), month_label, {
        "level": "month",
        "date_label": month_label,
        "summary": summary,
        "key_topics": key_topics,
        "projects_touched": projects_touched,
        "created_at": time.time(),
        "text": _build_rollup_text(summary, key_topics, projects_touched),
    })
    print(f"[Rollup] Saved MONTH: {month_label}")


def _rollup_year(store, user_id: str, year_label: str):
    month_items = [
        item for item in full_scan(store, NS_MONTH(user_id))
        if item.key.startswith(year_label + "-")
    ]
    if not month_items:
        return

    month_items.sort(key=lambda item: item.key)
    months_text = "\n".join(
        f"{item.key}: {item.value.get('summary', '')}"
        for item in month_items
    )

    parsed = _parse_rollup(
        YEAR_ROLLUP_PROMPT.format(
            year_label=year_label,
            months=months_text or "(no months)",
        )
    )

    summary = parsed.get("summary") or _fallback_summary(month_items, f"year {year_label}")
    key_topics = parsed.get("key_topics") or _fallback_topics(month_items)
    projects_touched = parsed.get("projects_touched") or _fallback_projects(month_items)

    store.put(NS_YEAR(user_id), year_label, {
        "level": "year",
        "date_label": year_label,
        "summary": summary,
        "key_topics": key_topics,
        "projects_touched": projects_touched,
        "created_at": time.time(),
        "text": _build_rollup_text(summary, key_topics, projects_touched),
    })
    print(f"[Rollup] Saved YEAR: {year_label}")


def _parse_rollup(prompt: str) -> dict:
    try:
        response = memory_llm.invoke([SystemMessage(content=prompt)])
        return parse_json_object(response.content)
    except Exception as e:
        print(f"[Rollup] Summary generation error: {e}")
        return {}


def _day_in_week(day_key: str, week_label: str) -> bool:
    try:
        date = datetime.strptime(day_key, "%Y-%m-%d")
        year, week_num = week_label.split("-W")
        iso_year, iso_week, _ = date.isocalendar()
        return iso_year == int(year) and iso_week == int(week_num)
    except Exception:
        return False


def _week_in_month(week_key: str, month_label: str) -> bool:
    try:
        year, week_num = week_key.split("-W")
        monday = datetime.fromisocalendar(int(year), int(week_num), 1)
        sunday = datetime.fromisocalendar(int(year), int(week_num), 7)
        return (
            monday.strftime("%Y-%m") == month_label or
            sunday.strftime("%Y-%m") == month_label
        )
    except Exception:
        return False


def _fallback_summary(items: list, label: str) -> str:
    snippets = [
        item.value.get("summary", "").strip()
        for item in items
        if item.value.get("summary", "").strip()
    ]
    if not snippets:
        return f"Activity recorded for {label}."

    joined = " ".join(snippets[:4]).strip()
    if len(joined) > 400:
        joined = joined[:397].rstrip() + "..."
    return joined


def _fallback_topics(items: list) -> list[str]:
    seen = []
    for item in items:
        for topic in item.value.get("key_topics", []):
            if topic and topic not in seen:
                seen.append(topic)
            if len(seen) >= 10:
                return seen
    return seen


def _fallback_projects(items: list) -> list[str]:
    seen = []
    for item in items:
        for field in ("projects_touched", "projects_mentioned"):
            for project in item.value.get(field, []):
                if project and project not in seen:
                    seen.append(project)
    return seen


def _build_rollup_text(summary: str, *parts: list[str]) -> str:
    tokens = [summary]
    for group in parts:
        tokens.extend(group)
    return " ".join(token for token in tokens if token).strip()
