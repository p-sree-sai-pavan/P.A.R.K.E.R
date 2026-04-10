import re
import time
from datetime import datetime, timedelta

from langchain_core.messages import SystemMessage

from memory.utils import format_messages, full_scan, parse_json_object, semantic_search, start_background_job
from models import memory_llm
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
    """
    Retrieve summary memories by drilling down the tree:
    year -> month -> week -> day -> chat.
    """
    try:
        temporal_hits = _load_temporal_episodes(store, user_id, query)
        if temporal_hits:
            return temporal_hits

        year_hits = semantic_search(store, NS_YEAR(user_id), query=query, limit=4)
        relevant_years = _extract_keys(year_hits)

        month_candidates = semantic_search(store, NS_MONTH(user_id), query=query, limit=24)
        month_hits = _filter_months_by_years(month_candidates, relevant_years) if relevant_years else month_candidates
        relevant_months = _extract_keys(month_hits)

        week_candidates = semantic_search(store, NS_WEEK(user_id), query=query, limit=24)
        week_hits = _filter_weeks_by_months(week_candidates, relevant_months) if relevant_months else week_candidates
        relevant_weeks = _extract_keys(week_hits)

        day_candidates = semantic_search(store, NS_DAY(user_id), query=query, limit=24)
        day_hits = _filter_days_by_weeks(day_candidates, relevant_weeks) if relevant_weeks else day_candidates
        relevant_days = {item.key for item in day_hits}

        chat_candidates = semantic_search(store, NS_CHAT(user_id), query=query, limit=40)
        if relevant_days:
            chat_hits = [
                item for item in chat_candidates
                if any(item.key.startswith(day_key) for day_key in relevant_days)
            ]
            if not chat_hits:
                chat_hits = chat_candidates[:6]
        else:
            chat_hits = chat_candidates[:6]

        return _merge_episode_hits(
            chat_hits=chat_hits,
            day_hits=day_hits,
            week_hits=week_hits,
            month_hits=month_hits,
            year_hits=year_hits,
        )

    except Exception as e:
        print(f"[Episodes] load_relevant_episodes failed: {e}")
        return []


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
        # format_for_prompt — also pull projects_touched and key_topics for rollup levels
        projects = value.get("projects_touched") or value.get("projects_mentioned", [])
        topics = value.get("key_topics", [])


        lines.append(f"[{level} | {date_label}]")
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
        response = memory_llm.invoke([
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


def _merge_episode_hits(*, chat_hits: list, day_hits: list, week_hits: list, month_hits: list, year_hits: list) -> list:
    results = []
    results.extend(year_hits[:1])
    results.extend(month_hits[:1])
    results.extend(week_hits[:1])
    results.extend(day_hits[:2])
    results.extend(chat_hits[:4])
    return _dedupe_items(results)[:7]


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
