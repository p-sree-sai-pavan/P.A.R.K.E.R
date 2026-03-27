# memory/rollup/core.py
import threading
from datetime import datetime, timedelta

from memory.utils import get_ns_lock
from .bounds import (
    _crossed_week, _crossed_month,
    _crossed_year, _crossed_decade
)
from .summarizers import (
    _rollup_day, _rollup_week, _rollup_month,
    _rollup_year, _rollup_decade
)

NS_STATE = lambda user_id: ("user", user_id, "state")


def rollup_if_needed(store, user_id: str):
    t = threading.Thread(target=_run_rollup, args=(store, user_id), daemon=True)
    t.start()


def _run_rollup(store, user_id: str):
    with get_ns_lock(("user", user_id, "rollup_lock")):
        last_session_date = None
        state_item = store.get(NS_STATE(user_id), "last_session")
        if state_item:
            last_session_date = state_item.value.get("date")

        from memory.utils import full_scan
        existing_days = full_scan(store, ("user", user_id, "mem", "day"))

        if not last_session_date or not existing_days:
            # Bootstrap for legacy databases: if no state exists or bootstrap failed, start from oldest chat
            all_chats = full_scan(store, ("user", user_id, "mem", "chat"))
            if not all_chats:
                return
            oldest_key = min(c.key for c in all_chats)
            last_session_date = oldest_key.split("T")[0]

        try:
            today_dt = datetime.now()
            last_dt  = datetime.fromisoformat(last_session_date)
            
            # Ensure we don't get stuck in an infinite loop if parsing fails timezone etc,
            # though isoformat usually yields naive datetimes here.
            
            # LOGIC FIX: Iterate through all missing days sequentially to catch gaps
            current_dt = last_dt
            
            # Cap at 100 days just to prevent catastrophic looping if dates are completely corrupted
            max_iterations = 100
            iterations = 0

            while current_dt.date() < today_dt.date() and iterations < max_iterations:
                day_str = current_dt.strftime("%Y-%m-%d")
                
                # Roll up this specific day
                _rollup_day(store, user_id, day_str)

                next_dt = current_dt + timedelta(days=1)

                # Check boundaries crossed moving from current_dt to next_dt
                if _crossed_week(current_dt, next_dt):
                    iso_year, iso_week, _ = current_dt.isocalendar()
                    _rollup_week(store, user_id, f"{iso_year}-W{iso_week:02d}")

                if _crossed_month(current_dt, next_dt):
                    _rollup_month(store, user_id, current_dt.strftime("%Y-%m"))

                if _crossed_year(current_dt, next_dt):
                    _rollup_year(store, user_id, current_dt.strftime("%Y"))
                    
                if _crossed_decade(current_dt, next_dt):
                    decade_start = (current_dt.year // 10) * 10
                    _rollup_decade(store, user_id, f"{decade_start}s")

                current_dt = next_dt
                iterations += 1

        except Exception as e:
            print(f"[Rollup] Failed to complete sequentially: {e}")
