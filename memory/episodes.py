import re
import time
from datetime import datetime, timedelta

from langchain_core.messages import SystemMessage

from memory.utils import format_messages, full_scan, parse_json_object, semantic_search, start_background_job
from models import episodes_llm
from prompts.rollup import CHAT_SUMMARY_PROMPT


NS_CHAT = lambda uid: ("user", uid, "mem", "chat")
NS_DAY = lambda uid: ("user", uid, "mem", "day")
NS_WEEK = lambda uid: ("user", uid, "mem", "week")
NS_MONTH = lambda uid: ("user", uid, "mem", "month")
NS_YEAR = lambda uid: ("user", uid, "mem", "year")


def write_chat_turn(store, user_id: str, user_message: str, assistant_message: str) -> str | None:
    """
    Persist a summarized chat-level memory entry for one user/assistant turn.

    This module is intentionally summary-only. We do not store exact raw chats.
    """
    user_message = (user_message or "").strip()
    assistant_message = (assistant_message or "").strip()
    if not user_message and not assistant_message:
        return None

    now = datetime.now()
    key = now.isoformat(timespec="milliseconds")
    date_label = now.strftime("%A, %B %d %Y, %I:%M:%S %p")

    entry = _build_chat_summary_entry(
        key,
        date_label,
        user_message=user_message,
        assistant_message=assistant_message,
    )
    store.put(NS_CHAT(user_id), key, entry)
    print(f"[Episodes] Chat summary saved: {key}")
    return key


def write_chat_entry(store, user_id: str, messages: list):
    """
    Backward-compatible wrapper used by older code paths.
    Saves each user/assistant pair as its own summarized chat entry.
    """
    if not messages:
        return

    pending_user = None
    for message in messages:
        if hasattr(message, "type"):
            role = "user" if message.type == "human" else "assistant"
            content = message.content
        elif isinstance(message, dict):
            role = message.get("role")
            content = message.get("content", "")
        else:
            continue

        if role == "user":
            pending_user = content
        elif role == "assistant" and pending_user is not None:
            write_chat_turn(store, user_id, pending_user, content)
            pending_user = None

def write_chat_turn_async(store, user_id, user_input, response):
    start_background_job(
        write_chat_turn, store, user_id, user_input, response,
        name="episode-write"
    )

def normalize_chat_summaries(store, user_id: str):
    """
    Upgrade legacy chat rows into the current summary-only shape.
    """
    for item in full_scan(store, NS_CHAT(user_id)):
        normalized = _normalize_chat_entry(item.key, item.value)
        if normalized != item.value:
            store.put(NS_CHAT(user_id), item.key, normalized)


def load_relevant_episodes(store, user_id: str, query: str) -> list:
    try:
        # 1. Temporal shortcut — "today", "yesterday" → skip tree, go direct
        temporal_hits = _load_temporal_episodes(store, user_id, query)
        if temporal_hits:
            return temporal_hits

        # 2. Explicit date/month mentioned → dive directly
        explicit = _resolve_explicit_date(query)
        if explicit:
            return _dive(store, user_id, query, **explicit)

        # 3. Top-down traversal — year → month → week → day → chat
        return _top_down_search(store, user_id, query)

    except Exception as e:
        print(f"[Episodes] load_relevant_episodes failed: {e}")
        return []


def _top_down_search(store, user_id: str, query: str) -> list:
    """
    Traverse the tree top-down. Only go deeper in branches that are relevant.
    Stops as soon as it finds enough context — no unnecessary fetching.
    """
    # Step 1: search years
    year_hits = semantic_search(store, NS_YEAR(user_id), query=query, limit=10)
    if not year_hits:
        return []

    relevant_years = [y.key for y in year_hits]

    # Step 2: search months, filter to relevant years only
    all_months = semantic_search(store, NS_MONTH(user_id), query=query, limit=24)
    month_hits = [m for m in all_months if any(m.key.startswith(y) for y in relevant_years)]
    if not month_hits:
        month_hits = all_months[:3]  # fallback

    relevant_months = [m.key for m in month_hits]

    # Step 3: search weeks, filter to relevant months
    all_weeks = semantic_search(store, NS_WEEK(user_id), query=query, limit=24)
    week_hits = [w for w in all_weeks if any(_week_in_month(w.key, m) for m in relevant_months)]
    if not week_hits:
        week_hits = all_weeks[:3]

    relevant_weeks = [w.key for w in week_hits]

    # Step 4: search days, filter to relevant weeks
    all_days = semantic_search(store, NS_DAY(user_id), query=query, limit=30)
    day_hits = [d for d in all_days if any(_day_in_week(d.key, w) for w in relevant_weeks)]
    if not day_hits:
        day_hits = all_days[:3]

    relevant_days = [d.key for d in day_hits]

    # Step 5: search chats, filter to relevant days only
    all_chats = semantic_search(store, NS_CHAT(user_id), query=query, limit=50)
    chat_hits = [c for c in all_chats if any(c.key.startswith(d) for d in relevant_days)]
    if not chat_hits:
        chat_hits = all_chats[:5]

    # Return: one summary per level for context + actual chat entries
    return _dedupe_items(
        year_hits[:1] +
        month_hits[:1] +
        week_hits[:1] +
        day_hits[:2] +
        chat_hits[:10]
    )


def _dive(store, user_id: str, query: str, year=None, month=None, day=None) -> list:
    """
    User specified a date/month/year explicitly — dive directly to that level.
    No semantic search needed at higher levels.
    """
    results = []

    if year:
        item = store.get(NS_YEAR(user_id), year)
        if item:
            results.append(item)

    if month:
        item = store.get(NS_MONTH(user_id), month)
        if item:
            results.append(item)
        # get all days in that month
        all_days = full_scan(store, NS_DAY(user_id))
        day_hits = [d for d in all_days if d.key.startswith(month)]
        day_hits.sort(key=lambda x: x.key)
        results.extend(day_hits)
        # get chats for those days
        all_chats = full_scan(store, NS_CHAT(user_id))
        for d in day_hits:
            day_chats = sorted(
                [c for c in all_chats if c.key.startswith(d.key)],
                key=lambda x: x.key
            )
            results.extend(day_chats[:3])

    if day:
        item = store.get(NS_DAY(user_id), day)
        if item:
            results.append(item)
        all_chats = full_scan(store, NS_CHAT(user_id))
        day_chats = sorted(
            [c for c in all_chats if c.key.startswith(day)],
            key=lambda x: x.key
        )
        results.extend(day_chats)

    return _dedupe_items(results)


def _resolve_explicit_date(query: str) -> dict | None:
    """
    Detect if user mentioned a specific year, month, or date.
    Returns dict like {"year": "2026"} or {"month": "2026-04"} or {"day": "2026-04-10"}
    """
    import re
    from datetime import datetime

    text = query.lower()

    # Full date: "april 10", "10th april", "april 10 2026"
    months_map = {
        "january": "01", "february": "02", "march": "03", "april": "04",
        "may": "05", "june": "06", "july": "07", "august": "08",
        "september": "09", "october": "10", "november": "11", "december": "12"
    }

    # Check for month name + day number
    for month_name, month_num in months_map.items():
        if month_name in text:
            day_match = re.search(r'\b(\d{1,2})(st|nd|rd|th)?\b', text)
            year_match = re.search(r'\b(202\d)\b', text)
            year = year_match.group(1) if year_match else str(datetime.now().year)
            if day_match:
                day = day_match.group(1).zfill(2)
                return {"day": f"{year}-{month_num}-{day}"}
            return {"month": f"{year}-{month_num}"}

    # Check for just a year
    year_match = re.search(r'\b(202\d)\b', text)
    if year_match:
        return {"year": year_match.group(1)}

    return None


def format_for_prompt(episodes: list) -> str:
    if not episodes:
        return "(none)"

    lines = []
    for episode in episodes:
        value = episode.value
        level = str(value.get("level") or _infer_level(episode.key)).upper()
        date_label = value.get("date_label", episode.key)
        summary = value.get("summary", "")
        decisions = value.get("decisions", [])
        unfinished = value.get("left_unfinished", [])
        projects = value.get("projects_touched") or value.get("projects_mentioned", [])
        topics = value.get("key_topics", [])

        # Show exact key so LLM always knows the precise date
        lines.append(f"[{level} | {date_label} | key: {episode.key}]")
        if summary:
            lines.append(f"  {summary}")
        if decisions:
            for decision in decisions:
                lines.append(f"  Decided: {decision}")
        if unfinished:
            for item in unfinished:
                lines.append(f"  Left unfinished: {item}")
        if projects:
            lines.append(f"  Projects: {', '.join(projects)}")
        if topics:
            lines.append(f"  Topics: {', '.join(topics[:5])}")
        lines.append("")

    return "\n".join(lines).strip()


def _build_chat_summary_entry(key: str, date_label: str, *, user_message: str, assistant_message: str) -> dict:
    summary = ""
    key_topics: list[str] = []
    projects_mentioned: list[str] = []
    decisions: list[str] = []
    open_threads: list[str] = []

    try:
        conversation = format_messages([
            {"role": "user", "content": user_message},
            {"role": "assistant", "content": assistant_message},
        ])
        response = episodes_llm.invoke([
            SystemMessage(content=CHAT_SUMMARY_PROMPT.format(conversation=conversation))
        ])
        parsed = parse_json_object(response.content)
        if parsed:
            summary = parsed.get("summary", "") or ""
            key_topics = parsed.get("key_topics", []) or []
            projects_mentioned = parsed.get("projects_mentioned", []) or []
            decisions = parsed.get("decisions", []) or []
            open_threads = parsed.get("open_threads", []) or []
    except Exception as e:
        print(f"[Episodes] Chat summary generation failed for {key}: {e}")

    if not summary:
        key_topics = key_topics or _extract_fallback_topics(user_message, assistant_message)
        summary = _build_fallback_summary(key_topics)

    return {
        "level": "chat",
        "timestamp": key,
        "date": key.split("T")[0],
        "date_label": date_label,
        "summary": summary,
        "key_topics": key_topics,
        "projects_mentioned": projects_mentioned,
        "decisions": decisions,
        "left_unfinished": open_threads,
        "created_at": time.time(),
        "text": _build_index_text(summary, key_topics, projects_mentioned, decisions, open_threads),
    }


def _normalize_chat_entry(key: str, value: dict) -> dict:
    summary = (value.get("summary") or "").strip()
    key_topics = value.get("key_topics", []) or []
    projects_mentioned = (
        value.get("projects_mentioned")
        or value.get("projects_touched")
        or []
    )
    decisions = value.get("decisions", []) or []
    left_unfinished = value.get("left_unfinished") or value.get("open_threads") or []

    if not summary:
        summary = _coerce_legacy_summary(value, key_topics)

    return {
        "level": "chat",
        "timestamp": value.get("timestamp", key),
        "date": value.get("date", key.split("T")[0] if "T" in key else key),
        "date_label": value.get("date_label", key),
        "summary": summary,
        "key_topics": key_topics,
        "projects_mentioned": projects_mentioned,
        "decisions": decisions,
        "left_unfinished": left_unfinished,
        "created_at": value.get("created_at", time.time()),
        "text": _build_index_text(summary, key_topics, projects_mentioned, decisions, left_unfinished),
    }


def _load_temporal_episodes(store, user_id: str, query: str) -> list:
    target = _resolve_temporal_target(query)
    if not target:
        return []

    date_key = target["date"].strftime("%Y-%m-%d")
    target_time = target.get("time")

    day_item = store.get(NS_DAY(user_id), date_key)
    chat_items = [
        item for item in full_scan(store, NS_CHAT(user_id))
        if item.key.startswith(date_key)
    ]

    if target_time is not None:
        chat_items.sort(
            key=lambda item: (
                _minutes_between(item.key, target_time),
                item.key,
            )
        )
    else:
        chat_items.sort(key=lambda item: item.key, reverse=True)

    results = []
    if day_item is not None:
        results.append(day_item)
    results.extend(chat_items[:6])
    return _dedupe_items(results)[:7]


def _resolve_temporal_target(query: str) -> dict | None:
    text = (query or "").strip().lower()
    if not text:
        return None

    now = datetime.now()
    if "yesterday" in text:
        target_date = now.date() - timedelta(days=1)
    elif re.search(r"\btoday\b", text):
        target_date = now.date()
    else:
        return None

    target_time = None
    if any(phrase in text for phrase in (
        "exactly at this time",
        "at this time",
        "same time",
        "this exact time",
    )):
        target_time = now.time().replace(second=0, microsecond=0)

    return {"date": target_date, "time": target_time}


def _merge_episode_hits(*, chat_hits, day_hits, week_hits, month_hits, year_hits):
    results = []
    results.extend(year_hits[:1])
    results.extend(month_hits[:1])
    results.extend(week_hits[:1])
    results.extend(day_hits[:3])
    results.extend(chat_hits[:10])
    return _dedupe_items(results)[:15]


def _dedupe_items(items: list) -> list:
    seen = {}
    for item in items:
        seen[item.key] = item
    return list(seen.values())


def _extract_keys(items: list) -> list[str]:
    return [item.key for item in items]


def _filter_months_by_years(items: list, years: list[str]) -> list:
    if not years:
        return items
    return [
        item for item in items
        if any(item.key.startswith(year + "-") for year in years)
    ]


def _filter_weeks_by_months(items: list, months: list[str]) -> list:
    if not months:
        return items
    return [
        item for item in items
        if any(_week_in_month(item.key, month) for month in months)
    ]


def _filter_days_by_weeks(items: list, weeks: list[str]) -> list:
    if not weeks:
        return items
    return [
        item for item in items
        if any(_day_in_week(item.key, week) for week in weeks)
    ]


def _week_in_month(week_key: str, month_key: str) -> bool:
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
    try:
        date = datetime.strptime(day_key, "%Y-%m-%d")
        year, week_num = week_key.split("-W")
        iso_year, iso_week, _ = date.isocalendar()
        return iso_year == int(year) and iso_week == int(week_num)
    except Exception:
        return False


def _minutes_between(chat_key: str, target_time) -> int:
    try:
        chat_dt = datetime.fromisoformat(chat_key)
        chat_minutes = chat_dt.hour * 60 + chat_dt.minute
        target_minutes = target_time.hour * 60 + target_time.minute
        return abs(chat_minutes - target_minutes)
    except Exception:
        return 10 ** 9


def _build_index_text(
    summary: str,
    key_topics: list[str],
    projects_mentioned: list[str],
    decisions: list[str],
    open_threads: list[str],
) -> str:
    parts = [summary]
    parts.extend(key_topics)
    parts.extend(projects_mentioned)
    parts.extend(decisions)
    parts.extend(open_threads)
    return " ".join(part for part in parts if part).strip()


def _build_fallback_summary(key_topics: list[str]) -> str:
    if key_topics:
        return f"Conversation about {', '.join(key_topics[:4])}."
    return "Conversation saved."


def _coerce_legacy_summary(value: dict, key_topics: list[str]) -> str:
    if key_topics:
        return _build_fallback_summary(key_topics)

    text = (value.get("text") or "").strip()
    if text:
        words = text.split()
        snippet = " ".join(words[:14]).strip()
        if snippet:
            if len(words) > 14:
                snippet += "..."
            return f"Conversation about {snippet}"

    return "Conversation saved."


def _extract_fallback_topics(user_message: str, assistant_message: str) -> list[str]:
    text = f"{user_message} {assistant_message}".lower()
    tokens = re.findall(r"[a-z0-9_+-]{3,}", text)
    seen = []
    stopwords = {
        "about", "again", "also", "been", "could", "from", "have",
        "here", "just", "like", "need", "that", "them", "they", "this",
        "what", "when", "where", "which", "with", "would", "your", "you",
        "parker",
    }
    for token in tokens:
        if token in stopwords or token.isdigit():
            continue
        if token not in seen:
            seen.append(token)
        if len(seen) >= 8:
            break
    return seen


def _infer_level(key: str) -> str:
    if "T" in key:
        return "chat"
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", key):
        return "day"
    if re.fullmatch(r"\d{4}-W\d{2}", key):
        return "week"
    if re.fullmatch(r"\d{4}-\d{2}", key):
        return "month"
    if re.fullmatch(r"\d{4}", key):
        return "year"
    return "memory"
