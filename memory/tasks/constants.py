# memory/tasks/constants.py

NAMESPACE    = lambda user_id: ("user", user_id, "tasks")
ARCHIVE_NS   = lambda user_id: ("user", user_id, "tasks_archive")
CANDIDATE_NS = lambda user_id: ("user", user_id, "candidates", "tasks")

SNOOZE_BY_PRIORITY = {
    "urgent": 0,
    "high":   1,
    "normal": 2,
    "low":    5,
}
