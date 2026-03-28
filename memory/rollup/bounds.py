# memory/rollup/bounds.py
from datetime import datetime

def _crossed_day(last: datetime, today: datetime) -> bool:
    return last.date() != today.date()

def _crossed_week(last: datetime, today: datetime) -> bool:
    # ISO calendar week: (year, week_num, weekday)
    last_iso = last.isocalendar()
    today_iso = today.isocalendar()
    # If the ISO year or ISO week number is different, we crossed a week boundary
    return last_iso[0] != today_iso[0] or last_iso[1] != today_iso[1]

def _crossed_month(last: datetime, today: datetime) -> bool:
    return last.month != today.month or last.year != today.year

def _crossed_year(last: datetime, today: datetime) -> bool:
    return last.year != today.year
