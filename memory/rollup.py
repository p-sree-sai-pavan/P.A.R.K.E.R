import time
from datetime import datetime, timedelta
from langchain_core.messages import SystemMessage

from models import memory_llm
from prompts import (
    DAY_ROLLUP_PROMPT,
    WEEK_ROLLUP_PROMPT,
    MONTH_ROLLUP_PROMPT,
    YEAR_ROLLUP_PROMPT,
    DECADE_ROLLUP_PROMPT,
)
from memory.utils import parse_json_object, full_scan, semantic_search


# ── Namespaces ─────────────────────────────────────────────────────────────────

NS_CHAT   = lambda uid: ("user", uid, "mem", "chat")
NS_DAY    = lambda uid: ("user", uid, "mem", "day")
NS_WEEK   = lambda uid: ("user", uid, "mem", "week")
NS_MONTH  = lambda uid: ("user", uid, "mem", "month")
NS_YEAR   = lambda uid: ("user", uid, "mem", "year")
NS_DECADE = lambda uid: ("user", uid, "mem", "decade")

# Key for tracking last rollup state
NS_META   = lambda uid: ("user", uid, "mem", "meta")
META_KEY  = "rollup_state"


# ── Public API ─────────────────────────────────────────────────────────────────

def rollup_if_needed(store, user_id: str):
    """
    Called once on every session start.

    Loads last known rollup state (what was the last date we ran).
    Compares to today. Determines which boundaries were crossed:
        - new day   → roll up yesterday's chats into a day summary
        - new week  → roll up last week's days into a week summary
        - new month → roll up last month's weeks into a month summary
        - new year  → roll up last year's months into a year summary
        - new decade→ roll up last decade's years into a decade summary

    Each rollup only runs if the lower level has data to roll up.
    Cascade: if new month AND new year, both run in order.
    """
    today  = datetime.now()
    state  = _load_meta(store, user_id)
    last   = _parse_last_date(state.get("last_session_date"))

    if last is None:
        # First ever session — just record today, nothing to roll up yet
        _save_meta(store, user_id, today)
        return

    if _same_day(last, today):
        # Same day — no rollup needed
        return

    print(f"[Rollup] New session day detected. Last: {last.date()} Today: {today.date()}")

    # Always roll up the previous day's chats into a day summary
    _rollup_day(store, user_id, last)

    # Check week boundary
    if _crossed_week(last, today):
        print("[Rollup] Week boundary crossed")
        _rollup_week(store, user_id, last)

    # Check month boundary
    if _crossed_month(last, today):
        print("[Rollup] Month boundary crossed")
        _rollup_month(store, user_id, last)

    # Check year boundary
    if _crossed_year(last, today):
        print("[Rollup] Year boundary crossed")
        _rollup_year(store, user_id, last)

    # Check decade boundary
    if _crossed_decade(last, today):
        print("[Rollup] Decade boundary crossed")
        _rollup_decade(store, user_id, last)

    _save_meta(store, user_id, today)


# ── Rollup functions ───────────────────────────────────────────────────────────

def _rollup_day(store, user_id: str, last: datetime):
    """
    Collect all chat entries from yesterday.
    Summarize into a single day entry.
    """
    day_key    = last.strftime("%Y-%m-%d")
    date_label = last.strftime("%A, %B %d %Y")

    # Load all chat entries from that day
    # Chat keys start with the day prefix: "2025-03-19T..."
    all_chats  = full_scan(store, NS_CHAT(user_id))
    day_chats  = [c for c in all_chats if c.key.startswith(day_key)]

    if not day_chats:
        print(f"[Rollup] No chat entries for {day_key} — skipping day rollup")
        return

    sessions_text = _format_entries_for_rollup(day_chats)

    try:
        response = memory_llm.invoke([
            SystemMessage(content=DAY_ROLLUP_PROMPT.format(
                date_label=date_label,
                sessions=sessions_text,
            ))
        ])

        parsed = parse_json_object(response.content)
        if not parsed:
            print(f"[Rollup] Day rollup parse failed for {day_key}")
            return

        store.put(NS_DAY(user_id), day_key, {
            "date_label":      date_label,
            "summary":         parsed.get("summary", ""),
            "key_topics":      parsed.get("key_topics", []),
            "projects_touched":parsed.get("projects_touched", []),
            "total_sessions":  len(day_chats),
            "created_at":      time.time(),
            "text":            " ".join(parsed.get("key_topics", [])),
        })
        print(f"[Rollup] Day summary written: {day_key}")

    except Exception as e:
        print(f"[Rollup] Day rollup failed: {e}")


def _rollup_week(store, user_id: str, last: datetime):
    """
    Collect all day summaries from last week.
    Summarize into a single week entry.
    """
    iso        = last.isocalendar()
    week_key   = f"{iso[0]}-W{iso[1]:02d}"
    week_label = f"Week {iso[1]}, {last.strftime('%B %Y')}"

    # Load all day entries that fall in this week
    all_days  = full_scan(store, NS_DAY(user_id))
    week_days = [
        d for d in all_days
        if _day_in_week_key(d.key, week_key)
    ]

    if not week_days:
        print(f"[Rollup] No day entries for {week_key} — skipping week rollup")
        return

    days_text = _format_entries_for_rollup(week_days)

    try:
        response = memory_llm.invoke([
            SystemMessage(content=WEEK_ROLLUP_PROMPT.format(
                week_label=week_label,
                days=days_text,
            ))
        ])

        parsed = parse_json_object(response.content)
        if not parsed:
            print(f"[Rollup] Week rollup parse failed for {week_key}")
            return

        store.put(NS_WEEK(user_id), week_key, {
            "week_label":      week_label,
            "summary":         parsed.get("summary", ""),
            "key_topics":      parsed.get("key_topics", []),
            "projects_touched":parsed.get("projects_touched", []),
            "created_at":      time.time(),
            "text":            " ".join(parsed.get("key_topics", [])),
        })
        print(f"[Rollup] Week summary written: {week_key}")

    except Exception as e:
        print(f"[Rollup] Week rollup failed: {e}")


def _rollup_month(store, user_id: str, last: datetime):
    """
    Collect all week summaries from last month.
    Summarize into a single month entry.
    """
    month_key   = last.strftime("%Y-%m")
    month_label = last.strftime("%B %Y")

    # Load all week entries that overlap with this month
    all_weeks   = full_scan(store, NS_WEEK(user_id))
    month_weeks = [
        w for w in all_weeks
        if _week_in_month_key(w.key, month_key)
    ]

    if not month_weeks:
        print(f"[Rollup] No week entries for {month_key} — skipping month rollup")
        return

    weeks_text = _format_entries_for_rollup(month_weeks)

    try:
        response = memory_llm.invoke([
            SystemMessage(content=MONTH_ROLLUP_PROMPT.format(
                month_label=month_label,
                weeks=weeks_text,
            ))
        ])

        parsed = parse_json_object(response.content)
        if not parsed:
            print(f"[Rollup] Month rollup parse failed for {month_key}")
            return

        store.put(NS_MONTH(user_id), month_key, {
            "month_label":     month_label,
            "summary":         parsed.get("summary", ""),
            "key_topics":      parsed.get("key_topics", []),
            "projects_touched":parsed.get("projects_touched", []),
            "created_at":      time.time(),
            "text":            " ".join(parsed.get("key_topics", [])),
        })
        print(f"[Rollup] Month summary written: {month_key}")

    except Exception as e:
        print(f"[Rollup] Month rollup failed: {e}")


def _rollup_year(store, user_id: str, last: datetime):
    """
    Collect all month summaries from last year.
    Summarize into a single year entry.
    """
    year_key   = str(last.year)
    year_label = year_key

    all_months  = full_scan(store, NS_MONTH(user_id))
    year_months = [m for m in all_months if m.key.startswith(year_key)]

    if not year_months:
        print(f"[Rollup] No month entries for {year_key} — skipping year rollup")
        return

    months_text = _format_entries_for_rollup(year_months)

    try:
        response = memory_llm.invoke([
            SystemMessage(content=YEAR_ROLLUP_PROMPT.format(
                year_label=year_label,
                months=months_text,
            ))
        ])

        parsed = parse_json_object(response.content)
        if not parsed:
            print(f"[Rollup] Year rollup parse failed for {year_key}")
            return

        store.put(NS_YEAR(user_id), year_key, {
            "year_label":      year_label,
            "summary":         parsed.get("summary", ""),
            "key_topics":      parsed.get("key_topics", []),
            "projects_touched":parsed.get("projects_touched", []),
            "created_at":      time.time(),
            "text":            " ".join(parsed.get("key_topics", [])),
        })
        print(f"[Rollup] Year summary written: {year_key}")

    except Exception as e:
        print(f"[Rollup] Year rollup failed: {e}")


def _rollup_decade(store, user_id: str, last: datetime):
    """
    Collect all year summaries from last decade.
    Summarize into a single decade entry.
    """
    decade_base  = (last.year // 10) * 10
    decade_key   = f"{decade_base}s"
    decade_label = decade_key

    all_years    = full_scan(store, NS_YEAR(user_id))
    decade_years = [
        y for y in all_years
        if decade_base <= int(y.key) < decade_base + 10
    ]

    if not decade_years:
        print(f"[Rollup] No year entries for {decade_key} — skipping decade rollup")
        return

    years_text = _format_entries_for_rollup(decade_years)

    try:
        response = memory_llm.invoke([
            SystemMessage(content=DECADE_ROLLUP_PROMPT.format(
                decade_label=decade_label,
                years=years_text,
            ))
        ])

        parsed = parse_json_object(response.content)
        if not parsed:
            print(f"[Rollup] Decade rollup parse failed for {decade_key}")
            return

        store.put(NS_DECADE(user_id), decade_key, {
            "decade_label": decade_label,
            "summary":      parsed.get("summary", ""),
            "key_topics":   parsed.get("key_topics", []),
            "created_at":   time.time(),
            "text":         " ".join(parsed.get("key_topics", [])),
        })
        print(f"[Rollup] Decade summary written: {decade_key}")

    except Exception as e:
        print(f"[Rollup] Decade rollup failed: {e}")


# ── Meta state ─────────────────────────────────────────────────────────────────

def _load_meta(store, user_id: str) -> dict:
    try:
        items = full_scan(store, NS_META(user_id))
        return items[0].value if items else {}
    except Exception:
        return {}


def _save_meta(store, user_id: str, today: datetime):
    try:
        store.put(NS_META(user_id), META_KEY, {
            "last_session_date": today.strftime("%Y-%m-%d"),
            "updated_at":        time.time(),
        })
    except Exception as e:
        print(f"[Rollup] Meta save failed: {e}")


def _parse_last_date(date_str: str | None) -> datetime | None:
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str, "%Y-%m-%d")
    except Exception:
        return None


# ── Boundary detection ─────────────────────────────────────────────────────────
# All derived from the two dates — no hardcoded thresholds.

def _same_day(last: datetime, today: datetime) -> bool:
    return last.date() == today.date()


def _crossed_week(last: datetime, today: datetime) -> bool:
    return last.isocalendar()[1] != today.isocalendar()[1] or last.year != today.year


def _crossed_month(last: datetime, today: datetime) -> bool:
    return last.month != today.month or last.year != today.year


def _crossed_year(last: datetime, today: datetime) -> bool:
    return last.year != today.year


def _crossed_decade(last: datetime, today: datetime) -> bool:
    return (last.year // 10) != (today.year // 10)


# ── Time helpers ───────────────────────────────────────────────────────────────

def _day_in_week_key(day_key: str, week_key: str) -> bool:
    """day_key: "2025-03-19"  week_key: "2025-W12" """
    try:
        date       = datetime.strptime(day_key, "%Y-%m-%d")
        year, week = week_key.split("-W")
        return (
            date.isocalendar()[0] == int(year) and
            date.isocalendar()[1] == int(week)
        )
    except Exception:
        return False


def _week_in_month_key(week_key: str, month_key: str) -> bool:
    """week_key: "2025-W12"  month_key: "2025-03" """
    try:
        year, week = week_key.split("-W")
        monday     = datetime.fromisocalendar(int(year), int(week), 1)
        sunday     = datetime.fromisocalendar(int(year), int(week), 7)
        return (
            monday.strftime("%Y-%m") == month_key or
            sunday.strftime("%Y-%m") == month_key
        )
    except Exception:
        return False


# ── Format helper ──────────────────────────────────────────────────────────────

def _format_entries_for_rollup(items: list) -> str:
    """
    Format a list of store items into readable text for the LLM rollup prompt.
    Uses summary field if available, falls back to key_topics.
    """
    lines = []
    for item in sorted(items, key=lambda i: i.key):
        v       = item.value
        label   = v.get("date_label") or v.get("week_label") or \
                  v.get("month_label") or v.get("year_label") or item.key
        summary = v.get("summary", "")
        topics  = v.get("key_topics", [])

        lines.append(f"[{label}]")
        if summary:
            lines.append(f"  {summary}")
        elif topics:
            lines.append(f"  Topics: {', '.join(topics)}")
        lines.append("")

    return "\n".join(lines).strip()