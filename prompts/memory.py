# prompts/memory.py

PROFILE_EXTRACTION_PROMPT = """You extract stable identity facts about a user.

OUTPUT: A flat JSON object. Only include keys that are NEW or CHANGED. Return {{}} if nothing changed.

RULES:
1. Only extract facts that define WHO the person is: name, university, location, branch, core tools, health, relationships, hard preferences.
2. Only extract EXPLICITLY stated facts. Zero inference.
3. Values under 15 words each.
4. snake_case keys only.
5. If a new value contradicts an existing one, include the key with the new value (overwrites).

EXAMPLE INPUT: "I just moved from VSCode to neovim, IIT Guwahati ECE."
EXAMPLE OUTPUT: {{"preferred_editor": "neovim", "university": "IIT Guwahati", "branch": "ECE"}}

DO NOT extract: inferred traits, vague habits, emotional states.

EXISTING PROFILE:
{existing_profile}

CONVERSATION:
{conversation}

Return only the JSON object. No explanation. No markdown."""


FACTS_EXTRACTION_PROMPT = """You extract discrete facts from a conversation into structured memory.

OUTPUT: A JSON array of fact objects.

EACH OBJECT SCHEMA:
{{
  "category": "snake_case_key",
  "content": "Single standalone sentence. Present tense. Self-contained.",
  "importance": "critical | high | normal | low",
  "confidence": "certain | inferred",
  "action": "add | update | skip"
}}

IMPORTANCE GUIDE:
- critical: affects every future response (hard constraint, disability, non-negotiable preference)
- high: current active focus, urgent situation, or key decision this session
- normal: useful background
- low: passing mention

CONFIDENCE:
- certain: user stated it directly
- inferred: obviously implied (use sparingly)

ACTION GUIDE:
- add: new fact not in existing facts
- update: contradicts or refines an existing fact
- skip: already known, no meaningful change

CONFLICT RULE: New fact contradicts existing → action = "update". New wins. No duplicates.

RULES:
1. One fact per object. Never combine.
2. Explicitly stated or obviously implied only.
3. Prefer "update" over duplicate "add".
4. Return [] if nothing worth storing.
5. Pure JSON array only. No markdown.

EXISTING FACTS:
{existing_facts}

CONVERSATION:
{conversation}

Return only the JSON array."""


TASK_EXTRACTION_PROMPT = """You extract tasks, reminders, and commitments from a conversation.

CURRENT TIME: {current_time}

OUTPUT: A JSON array of task objects.

EACH OBJECT SCHEMA:
{{
  "key": "unique_snake_case_id",
  "content": "Clear actionable description.",
  "type": "reminder | event | goal",
  "condition": "specific_time | time_range | on_mention | before_next_session | none",
  "condition_hours": [start_hour, end_hour] or null,
  "condition_days": [0,1,2,3,4,5,6] or null,
  "recurrence_rule": "daily | weekly | weekdays | weekends | null",
  "keywords": ["3 to 5 trigger words"],
  "priority": "urgent | high | normal | low",
  "due": "ISO 8601 datetime computed from CURRENT TIME, or null",
  "fade_after_days": integer or null,
  "action": "add | complete | skip"
}}

CONDITION GUIDE:
- specific_time: exact time → compute due from CURRENT TIME
- time_range: recurring window → condition_hours + recurrence_rule
- on_mention: fires when topic appears → set keywords
- before_next_session: do before next session
- none: no trigger

DUE FIELD RULES:
- "in 2 minutes"     → CURRENT TIME + 2 min
- "at 3pm"           → today 15:00 (or tomorrow if past)
- "tomorrow morning" → tomorrow 08:00
- "next Monday"      → next Monday 09:00
- "remind me daily"  → null, recurrence_rule = "daily"
- No time reference  → null

RECURRENCE: recurrence_rule for recurring tasks, not repeated due.

RULES:
1. Clear, unambiguous intent only.
2. "I finished X" / "done" / "already did that" → action = "complete", key + action only.
3. Return [] if no tasks.
4. Pure JSON array only.

EXISTING TASKS:
{existing_tasks}

CONVERSATION:
{conversation}

Return only the JSON array."""


PROJECT_EXTRACTION_PROMPT = """You identify and update ongoing projects from a conversation.

A project = multi-step goal-oriented work spanning multiple sessions.

OUTPUT: A JSON array of project objects.

EACH OBJECT SCHEMA:
{{
  "name": "Descriptive Project Name",
  "status": "active | paused | completed | abandoned",
  "summary": "2-3 sentences: what it is, current state, what changed this session.",
  "stack": ["tool1", "tool2"],
  "open_threads": ["unresolved question or pending decision"],
  "decisions": ["decision made THIS session only"],
  "action": "add | update | skip"
}}

RULES:
1. Real projects only. Not one-off tasks or passing tool mentions.
2. decisions[] = THIS conversation only.
3. open_threads[] = still unresolved after this session.
4. Return [] if no project activity.
5. Pure JSON array only.

EXISTING PROJECTS:
{existing_projects}

CONVERSATION:
{conversation}

Return only the JSON array."""