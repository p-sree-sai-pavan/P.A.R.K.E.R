import time
from datetime import datetime
from langchain_core.messages import SystemMessage

from models import memory_llm
from prompts.rollup import CHAT_SUMMARY_PROMPT
from memory.utils import (
    format_messages, parse_json_object,
    semantic_search
)


# ── Namespaces ─────────────────────────────────────────────────────────────────
# Each level is a separate namespace.
# Rollup.py writes day/week/month/year/decade.
# This file writes chat entries and reads across all levels.

NS_CHAT   = lambda uid: ("user", uid, "mem", "chat")
NS_DAY    = lambda uid: ("user", uid, "mem", "day")
NS_WEEK   = lambda uid: ("user", uid, "mem", "week")
NS_MONTH  = lambda uid: ("user", uid, "mem", "month")
NS_YEAR   = lambda uid: ("user", uid, "mem", "year")
NS_DECADE = lambda uid: ("user", uid, "mem", "decade")


# ── Write ──────────────────────────────────────────────────────────────────────

def write_chat_entry(store, user_id: str, messages: list):
    """
    Write a summary of this session to the chat namespace.
    Called at session end — blocking, intentional.
    Takes ~2-3 seconds. User is exiting so latency is acceptable.

    Key format: ISO datetime — "2025-03-19T14:32"
    Embedded on: key_topics (not full summary — more precise search target)
    """
    if not messages:
        return

    try:
        conversation = format_messages(messages)
        now          = datetime.now()
        key          = now.strftime("%Y-%m-%dT%H:%M")
        date_label   = now.strftime("%A, %B %d %Y, %I:%M %p")

        response = memory_llm.invoke([
            SystemMessage(content=CHAT_SUMMARY_PROMPT.format(
                conversation=conversation,
            ))
        ])

        parsed = parse_json_object(response.content)
        if not parsed:
            print("[Episodes] Chat summary parsing failed — skipping write")
            return

        entry = {
            "date_label":         date_label,
            "summary":            parsed.get("summary", ""),
            "key_topics":         parsed.get("key_topics", []),
            "projects_mentioned": parsed.get("projects_mentioned", []),
            "decisions":          parsed.get("decisions", []),
            "left_unfinished":    parsed.get("open_threads", []),
            "created_at":         time.time(),
            # text field is what PostgresStore embeds for semantic search
            # key_topics is a more precise embedding target than full summary
            "text":               " ".join(parsed.get("key_topics", [])),
        }

        store.put(NS_CHAT(user_id), key, entry)
        print(f"[Episodes] Chat entry written: {key}")

    except Exception as e:
        print(f"[Episodes] write_chat_entry failed: {e}")


# ── Read ───────────────────────────────────────────────────────────────────────

def load_relevant_episodes(store, user_id: str, query: str) -> list:
    """
    Hierarchical drill-down search.

    Strategy:
    1. Search decade/year summaries — find which years are relevant
    2. Search month summaries within those years — narrow further
    3. Search week summaries within those months — narrow further
    4. Search day and chat entries within those weeks — return these

    At each level we collect the top matches and use their time labels
    to filter the next level. This avoids searching all 700+ chat entries
    directly — we only search ~10-15 entries total across all levels.

    Returns a mix of day summaries and chat entries, most specific first.
    """
    try:
        # Level 1 — decade and year (broadest)
        # Small collections — full scan is fine, no vector needed yet
        decade_hits = semantic_search(store, NS_DECADE(user_id), query=query, limit=2)
        year_hits   = semantic_search(store, NS_YEAR(user_id),   query=query, limit=3)

        # Collect relevant year labels from hits e.g. ["2024", "2025"]
        relevant_years = _extract_time_labels(year_hits)
        if not relevant_years and decade_hits:
            # No year hits but decade hit — search all years in that decade
            relevant_years = _years_from_decade(decade_hits)

        # Level 2 — months within relevant years
        month_hits = []
        if relevant_years:
            all_months = semantic_search(store, NS_MONTH(user_id), query=query, limit=50)
            month_hits = [
                m for m in all_months
                if any(m.key.startswith(y) for y in relevant_years)
            ]
        else:
            # No year signal — search all months directly
            month_hits = semantic_search(store, NS_MONTH(user_id), query=query, limit=20)

        relevant_months = _extract_time_labels(month_hits)

        # Level 3 — weeks within relevant months
        week_hits = []
        if relevant_months:
            all_weeks = semantic_search(store, NS_WEEK(user_id), query=query, limit=50)
            week_hits = [
                w for w in all_weeks
                if any(_week_in_month(w.key, m) for m in relevant_months)
            ]
        else:
            week_hits = semantic_search(store, NS_WEEK(user_id), query=query, limit=20)

        relevant_weeks = _extract_time_labels(week_hits)

        # Level 4 — days within relevant weeks
        day_hits = []
        if relevant_weeks:
            all_days = semantic_search(store, NS_DAY(user_id), query=query, limit=50)
            day_hits = [
                d for d in all_days
                if any(_day_in_week(d.key, w) for w in relevant_weeks)
            ]
        else:
            day_hits = semantic_search(store, NS_DAY(user_id), query=query, limit=20)

        relevant_days = [d.key for d in day_hits]  # e.g. ["2025-03-19"]

        # Level 5 — individual chat entries within relevant days
        chat_hits = []
        if relevant_days:
            all_chats = semantic_search(store, NS_CHAT(user_id), query=query, limit=50)
            chat_hits = [
                c for c in all_chats
                if any(c.key.startswith(day) for day in relevant_days)
            ]
        else:
            # No day signal — semantic search directly on chat entries
            chat_hits = semantic_search(store, NS_CHAT(user_id), query=query, limit=20)

        # Return most specific first: chat entries, then day summaries
        results = chat_hits + day_hits
        return results[:7]  # cap total injected into prompt

    except Exception as e:
        print(f"[Episodes] load_relevant_episodes failed: {e}")
        return []


# ── Format ─────────────────────────────────────────────────────────────────────

def format_for_prompt(episodes: list) -> str:
    """
    Format episode entries for system prompt.
    Parker is instructed to reference these explicitly by date.
    """
    if not episodes:
        return "(none)"

    lines = []
    for ep in episodes:
        v          = ep.value
        date_label = v.get("date_label", ep.key)
        summary    = v.get("summary", "")
        decisions  = v.get("decisions", [])
        unfinished = v.get("left_unfinished", [])

        lines.append(f"[{date_label}]")
        if summary:
            lines.append(f"  {summary}")
        if decisions:
            for d in decisions:
                lines.append(f"  Decided: {d}")
        if unfinished:
            for u in unfinished:
                lines.append(f"  Left unfinished: {u}")
        lines.append("")

    return "\n".join(lines).strip()


# ── Time helpers ───────────────────────────────────────────────────────────────
# All time logic is derived from key formats — no hardcoded values.
# Key formats:
#   chat:   "2025-03-19T14:32"
#   day:    "2025-03-19"
#   week:   "2025-W12"
#   month:  "2025-03"
#   year:   "2025"
#   decade: "2020s"

def _extract_time_labels(items: list) -> list:
    """Extract key values from search results."""
    return [item.key for item in items]


def _years_from_decade(decade_hits: list) -> list:
    """
    Given decade hits like ["2020s"], return list of year strings.
    e.g. "2020s" → ["2020","2021","2022","2023","2024","2025","2026","2027","2028","2029"]
    """
    years = []
    for item in decade_hits:
        decade_key = item.key  # e.g. "2020s"
        try:
            base = int(decade_key.replace("s", ""))
            years += [str(base + i) for i in range(10)]
        except Exception:
            pass
    return years


def _week_in_month(week_key: str, month_key: str) -> bool:
    """
    Check if a week key falls within a month.
    week_key:  "2025-W12"
    month_key: "2025-03"
    Checks both Monday and Sunday of the week — boundary weeks
    that span two months must not be silently dropped.
    """
    try:
        year, week_num = week_key.split("-W")
        monday = datetime.fromisocalendar(int(year), int(week_num), 1)
        sunday = datetime.fromisocalendar(int(year), int(week_num), 7)
        return (
            monday.strftime("%Y-%m") == month_key or
            sunday.strftime("%Y-%m") == month_key
        )
    except Exception:
        return False


def _day_in_week(day_key: str, week_key: str) -> bool:
    """
    Check if a day key falls within a week.
    day_key:  "2025-03-19"
    week_key: "2025-W12"
    """
    try:
        date   = datetime.strptime(day_key, "%Y-%m-%d")
        year, week_num = week_key.split("-W")
        return (
            date.isocalendar()[0] == int(year) and
            date.isocalendar()[1] == int(week_num)
        )
    except Exception:
        return False