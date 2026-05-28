# prompts/memory.py

UNIFIED_MEMORY_PROMPT = """You extract profile updates, facts, tasks, and project status from a conversation.

INPUTS:
- Current Date/Time: {current_time}
- Existing Profile:
{existing_profile}
- Existing Facts:
{existing_facts}
- Existing Tasks:
{existing_tasks}
- Existing Projects:
{existing_projects}

CONVERSATION:
{conversation}

OUTPUT FORMAT:
Return a single JSON object with the following schema:
{{
  "profile_updates": {{
    "key1": "new_value" // stable identity details (name, university, location, branch, core tools, hard preferences)
  }},
  "facts": [
    {{
      "category": "snake_case_key",
      "content": "Single standalone sentence. Present tense. Self-contained.",
      "importance": "critical | high | normal | low",
      "action": "add | update | skip"
    }}
  ],
  "tasks": [
    {{
      "key": "unique_snake_case_id",
      "content": "Clear actionable description.",
      "type": "reminder | event | goal",
      "condition": "specific_time | time_range | on_mention | before_next_session | none",
      "priority": "urgent | high | normal | low",
      "due": "ISO 8601 datetime or null",
      "action": "add | complete | skip"
    }}
  ],
  "projects": [
    {{
      "name": "Project Name",
      "status": "active | paused | completed | abandoned",
      "summary": "2-3 sentences: what it is, current state, what changed this session.",
      "stack": ["tool1", "tool2"],
      "open_threads": ["unresolved question or pending decision"],
      "decisions": ["decision made this session"],
      "action": "add | update | skip"
    }}
  ]
}}

RULES:
1. Return empty values (e.g. empty profile_updates dict, empty facts/tasks/projects lists) if nothing changed or needs updating.
2. Only extract facts and commitments that are EXPLICITLY stated or directly implied. No assumptions.
3. NEVER store transient time-dependent info (such as today's date, current time, weather, or temporary emotional states) as facts.
4. Pure JSON only. No markdown formatting, explanation, or backticks.
"""

PROFILE_EXTRACTION_PROMPT = """You extract stable identity facts about a user.
OUTPUT: A flat JSON object. Only include keys that are NEW or CHANGED. Return {} if nothing changed.
"""
FACTS_EXTRACTION_PROMPT = """You extract discrete facts from a conversation.
"""
TASK_EXTRACTION_PROMPT = """You extract tasks, reminders, and commitments.
"""
PROJECT_EXTRACTION_PROMPT = """You identify and update ongoing projects.
"""