# prompts/rollup.py

CHAT_SUMMARY_PROMPT = """Summarize this conversation as a structured memory entry.

OUTPUT — JSON object with exactly these fields:
{{
  "summary": "3-4 sentences. Technical milestones, decisions, problems solved. No filler.",
  "key_topics": ["5 to 8 short semantic tags"],
  "projects_mentioned": ["project name"],
  "decisions": ["specific decision made"],
  "open_threads": ["unresolved follow-up item"]
}}

CONVERSATION:
{conversation}

Return only the JSON object."""


DAY_ROLLUP_PROMPT = """Summarize today's sessions into a single daily memory entry.

OUTPUT:
{{
  "summary": "Arc of the day: what was worked on, what progressed, what changed.",
  "key_topics": ["top 10 themes"],
  "projects_touched": ["project names"],
  "total_sessions": <integer>
}}

DATE: {date_label}
SESSIONS:
{sessions}

Return only the JSON object."""


WEEK_ROLLUP_PROMPT = """Summarize this week into a strategic weekly memory entry.

OUTPUT:
{{
  "summary": "Objectives met, momentum direction, major shifts.",
  "key_topics": ["8 core themes"],
  "projects_touched": ["project names"]
}}

WEEK: {week_label}
DAYS:
{days}

Return only the JSON object."""


MONTH_ROLLUP_PROMPT = """Summarize this month into a strategic monthly memory entry.

OUTPUT:
{{
  "summary": "2-3 sentences: trajectory, milestones, focus areas.",
  "key_topics": ["6 defining themes"],
  "projects_touched": ["project names"]
}}

MONTH: {month_label}
WEEKS:
{weeks}

Return only the JSON object."""


YEAR_ROLLUP_PROMPT = """Summarize this year into a yearly memory entry.

OUTPUT:
{{
  "summary": "1-2 sentences: year's essence and direction.",
  "key_topics": ["5 defining themes"],
  "projects_touched": ["major projects"]
}}

YEAR: {year_label}
MONTHS:
{months}

Return only the JSON object."""


DECADE_ROLLUP_PROMPT = """Summarize this decade from yearly summaries.

OUTPUT:
{{
  "summary": "2-3 sentences: arc-level view of this decade's trajectory.",
  "key_topics": ["5 defining themes"]
}}

DECADE: {decade_label}
YEARS:
{years}

Return only the JSON object."""