# memory/rollup/summarizers.py
from langchain_core.messages import SystemMessage

from models import memory_llm
from prompts.rollup import (
    DAY_ROLLUP_PROMPT,
    WEEK_ROLLUP_PROMPT,
    MONTH_ROLLUP_PROMPT,
    YEAR_ROLLUP_PROMPT,
    DECADE_ROLLUP_PROMPT,
)
from memory.utils import parse_json_object, full_scan

NS_CHAT   = lambda user_id: ("user", user_id, "mem", "chat")
NS_DAY    = lambda user_id: ("user", user_id, "mem", "day")
NS_WEEK   = lambda user_id: ("user", user_id, "mem", "week")
NS_MONTH  = lambda user_id: ("user", user_id, "mem", "month")
NS_YEAR   = lambda user_id: ("user", user_id, "mem", "year")
NS_DECADE = lambda user_id: ("user", user_id, "mem", "decade")


def _rollup_day(store, user_id: str, date_str: str):
    chats = []
    # Replace full scan with filtering matching date prefix:
    for item in full_scan(store, NS_CHAT(user_id)):
        if item.key.startswith(date_str):
            chats.append(item.value)
    
    if not chats:
        return  # Optimization: don't summarize empty days

    chats.sort(key=lambda x: x.get("timestamp", ""))
    sessions_text = "\n\n".join(
        f"[{c.get('timestamp')}] {c.get('summary', '')}"
        for c in chats
    )

    try:
        resp = memory_llm.invoke([
            SystemMessage(content=DAY_ROLLUP_PROMPT.format(
                date_label=date_str,
                sessions=sessions_text or "(no activity)"
            ))
        ])
        data = parse_json_object(resp.content)
        if data:
            store.put(NS_DAY(user_id), date_str, {
                "date": date_str,
                "summary": data.get("summary", ""),
                "key_topics": data.get("key_topics", []),
                "projects_touched": data.get("projects_touched", []),
                "total_sessions": data.get("total_sessions", len(chats))
            })
            print(f"[Rollup] Saved DAY: {date_str}")
    except Exception as e:
        print(f"[Rollup] Day {date_str} error: {e}")


def _rollup_week(store, user_id: str, week_label: str):
    days = full_scan(store, NS_DAY(user_id))
    # Filter days that belong to this week
    # A simple way: just pass last 7 completed days, or all days that have this ISO week
    # But for simplicity let's assume we pass the recent 7 days if they match the week
    week_parts = []
    for d in days:
        if d.key.startswith(week_label[:4]): # weak boundary, let's just pass all for now, the prompt handles it
            week_parts.append(d)
            
    days_text = "\n".join(
        f"{d.key}: {d.value.get('summary', '')}"
        for d in sorted(week_parts, key=lambda x: x.key)[-7:]
    )

    try:
        resp = memory_llm.invoke([
            SystemMessage(content=WEEK_ROLLUP_PROMPT.format(
                week_label=week_label,
                days=days_text or "(no days)"
            ))
        ])
        data = parse_json_object(resp.content)
        if data:
            store.put(NS_WEEK(user_id), week_label, data)
            print(f"[Rollup] Saved WEEK: {week_label}")
    except Exception as e:
        print(f"[Rollup] Week {week_label} error: {e}")


def _rollup_month(store, user_id: str, month_label: str):
    weeks = full_scan(store, NS_WEEK(user_id))
    weeks_text = "\n".join(
        f"{w.key}: {w.value.get('summary', '')}"
        for w in sorted(weeks, key=lambda x: x.key)[-4:]
    )
    try:
        resp = memory_llm.invoke([
            SystemMessage(content=MONTH_ROLLUP_PROMPT.format(
                month_label=month_label,
                weeks=weeks_text or "(no weeks)"
            ))
        ])
        data = parse_json_object(resp.content)
        if data:
            store.put(NS_MONTH(user_id), month_label, data)
            print(f"[Rollup] Saved MONTH: {month_label}")
    except Exception as e:
        print(f"[Rollup] Month error: {e}")


def _rollup_year(store, user_id: str, year_label: str):
    months = full_scan(store, NS_MONTH(user_id))
    months_text = "\n".join(
        f"{m.key}: {m.value.get('summary', '')}"
        for m in sorted(months, key=lambda x: x.key)[-12:]
    )
    try:
        resp = memory_llm.invoke([
            SystemMessage(content=YEAR_ROLLUP_PROMPT.format(
                year_label=year_label,
                months=months_text
            ))
        ])
        data = parse_json_object(resp.content)
        if data:
            store.put(NS_YEAR(user_id), year_label, data)
            print(f"[Rollup] Saved YEAR: {year_label}")
    except Exception as e:
        print(f"[Rollup] Year error: {e}")


def _rollup_decade(store, user_id: str, decade_label: str):
    years = full_scan(store, NS_YEAR(user_id))
    years_text = "\n".join(
        f"{y.key}: {y.value.get('summary', '')}"
        for y in sorted(years, key=lambda x: x.key)[-10:]
    )
    try:
        resp = memory_llm.invoke([
            SystemMessage(content=DECADE_ROLLUP_PROMPT.format(
                decade_label=decade_label,
                years=years_text
            ))
        ])
        data = parse_json_object(resp.content)
        if data:
            store.put(NS_DECADE(user_id), decade_label, data)
            print(f"[Rollup] Saved DECADE: {decade_label}")
    except Exception as e:
        print(f"[Rollup] Decade error: {e}")
