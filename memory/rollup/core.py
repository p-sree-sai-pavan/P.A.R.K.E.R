from datetime import datetime, timedelta

from memory.utils import full_scan, get_ns_lock
from .bounds import _crossed_month, _crossed_week, _crossed_year
from .summarizers import _rollup_day, _rollup_month, _rollup_week, _rollup_year

NS_CHAT = lambda user_id: ("user", user_id, "mem", "chat")
NS_DAY = lambda user_id: ("user", user_id, "mem", "day")
NS_STATE = lambda user_id: ("user", user_id, "state")


def rollup_if_needed(store, user_id: str):
    with get_ns_lock(("user", user_id, "rollup_lock")):
        _rollup_closed_periods(store, user_id)


def refresh_active_rollups(store, user_id: str):
    """
    Refresh the current open summary tree from existing chat/day/week/month data.
    This keeps the hierarchy available even before a time boundary is crossed.
    """
    with get_ns_lock(("user", user_id, "rollup_lock")):
        now = datetime.now()
        day_key = now.strftime("%Y-%m-%d")
        iso_year, iso_week, _ = now.isocalendar()
        week_key = f"{iso_year}-W{iso_week:02d}"
        month_key = now.strftime("%Y-%m")
        year_key = now.strftime("%Y")

        _rollup_day(store, user_id, day_key)
        _rollup_week(store, user_id, week_key)
        _rollup_month(store, user_id, month_key)
        _rollup_year(store, user_id, year_key)


def _rollup_closed_periods(store, user_id: str):
    last_session_date = None
    state_item = store.get(NS_STATE(user_id), "last_session")
    if state_item:
        last_session_date = state_item.value.get("date")

    if not last_session_date:
        existing_days = full_scan(store, NS_DAY(user_id))
        if existing_days:
            last_session_date = min(item.key for item in existing_days)

    if not last_session_date:
        all_chats = full_scan(store, NS_CHAT(user_id))
        if not all_chats:
            return
        last_session_date = min(chat.key for chat in all_chats).split("T")[0]

    try:
        today_dt = datetime.now()
        last_dt = datetime.fromisoformat(last_session_date)

        if last_dt.date() >= today_dt.date():
            return

        current_dt = last_dt
        days_to_process = (today_dt.date() - last_dt.date()).days
        max_iterations = min(days_to_process + 1, 3660)

        for _ in range(max_iterations):
            if current_dt.date() >= today_dt.date():
                break

            day_str = current_dt.strftime("%Y-%m-%d")
            _rollup_day(store, user_id, day_str)

            next_dt = current_dt + timedelta(days=1)
            if _crossed_week(current_dt, next_dt):
                iso_year, iso_week, _ = current_dt.isocalendar()
                _rollup_week(store, user_id, f"{iso_year}-W{iso_week:02d}")

            if _crossed_month(current_dt, next_dt):
                _rollup_month(store, user_id, current_dt.strftime("%Y-%m"))

            if _crossed_year(current_dt, next_dt):
                _rollup_year(store, user_id, current_dt.strftime("%Y"))

            current_dt = next_dt

    except Exception as e:
        print(f"[Rollup] Failed to complete sequentially: {e}")
