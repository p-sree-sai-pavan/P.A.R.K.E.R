import os
import re

# OpenClaw-aligned limits
MAX_SKILLS_PROMPT_CHARS = 8000
MAX_SKILLS_IN_PROMPT = 100
COMPACT_WARNING_OVERHEAD = 150

def escape_xml(str_val: str) -> str:
    """Escapes XML special characters."""
    return (
        str_val.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )

def parse_skill_frontmatter(file_path: str) -> dict:
    """
    Parses frontmatter bounded by --- from a SKILL.md file.
    Returns a dict with 'name' and 'description' keys.
    """
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()

        parts = content.split("---", 2)
        if len(parts) < 3:
            return {}

        frontmatter_text = parts[1]
        data = {}
        for line in frontmatter_text.splitlines():
            line = line.strip()
            if not line or ":" not in line:
                continue
            key, val = line.split(":", 1)
            key = key.strip().lower()
            val = val.strip()

            # Strip leading/trailing quotes
            if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
                val = val[1:-1]
            data[key] = val
        return data
    except Exception as e:
        print(f"[Skills Loader] Error parsing frontmatter for {file_path}: {e}")
        return {}

def scan_skills_directory(directory_path: str, relative_prefix: str) -> list:
    """
    Scans a directory for subdirectories containing SKILL.md files.
    Returns a list of dicts with 'name', 'description', and 'filePath'.
    """
    skills = []
    if not os.path.exists(directory_path):
        return skills

    try:
        for entry in os.listdir(directory_path):
            entry_path = os.path.join(directory_path, entry)
            if not os.path.isdir(entry_path) or entry.startswith("."):
                continue

            skill_md_path = os.path.join(entry_path, "SKILL.md")
            if os.path.isfile(skill_md_path):
                frontmatter = parse_skill_frontmatter(skill_md_path)
                name = frontmatter.get("name", entry)
                description = frontmatter.get("description", "")
                
                # Compute display location path relative to root project folder
                # e.g., gateway/skills/weather/SKILL.md
                location = os.path.join(relative_prefix, entry, "SKILL.md").replace("\\", "/")
                
                skills.append({
                    "name": name,
                    "description": description,
                    "filePath": location
                })
    except Exception as e:
        print(f"[Skills Loader] Error scanning {directory_path}: {e}")

    return skills

def rank_skills_by_relevance(skills: list, query: str) -> tuple[list, list]:
    """
    Ranks skills by relevance to a search query using basic keyword matching.
    Returns a tuple of (relevant_skills, other_skills).
    """
    if not query:
        return [], skills

    # Tokenize query and filter stop words
    stop_words = {
        "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for", "with", 
        "is", "are", "was", "were", "be", "how", "what", "why", "where", "who", "which", 
        "can", "do", "does", "did", "please", "parker", "hey", "sir", "connected", "connect"
    }
    words = [w.strip("?,.!-()\"'").lower() for w in query.split()]
    query_words = {w for w in words if w and w not in stop_words}

    if not query_words:
        return [], skills

    scored_skills = []
    for s in skills:
        score = 0
        name_lower = s["name"].lower()
        desc_lower = s["description"].lower()

        # Score calculations
        for qw in query_words:
            if qw in name_lower:
                score += 10
                if name_lower == qw or name_lower.startswith(qw + "-") or name_lower.endswith("-" + qw):
                    score += 15
            if qw in desc_lower:
                score += 2

        scored_skills.append((score, s))

    # Sort: descending score, then ascending name
    scored_skills.sort(key=lambda item: (-item[0], item[1]["name"].lower()))

    relevant = [item[1] for item in scored_skills if item[0] > 0]
    others = [item[1] for item in scored_skills if item[0] == 0]

    return relevant, others

def format_skills_full(skills: list) -> str:
    """Formats the skills in full XML layout (including descriptions)."""
    lines = [
        "\n\nThe following skills provide specialized instructions for specific tasks.",
        "Use the read_file action under sandbox mode to load a skill's file when the task matches its description.",
        "When a skill file references a relative path, resolve it against the skill directory (parent of SKILL.md / dirname of the path) and use that absolute path in tool commands.",
        "",
        "<available_skills>"
    ]
    for s in skills:
        lines.append("  <skill>")
        lines.append(f"    <name>{escape_xml(s['name'])}</name>")
        lines.append(f"    <description>{escape_xml(s['description'])}</description>")
        lines.append(f"    <location>{escape_xml(s['filePath'])}</location>")
        lines.append("  </skill>")
    lines.append("</available_skills>")
    return "\n".join(lines)

def format_skills_compact(skills: list) -> str:
    """Formats the skills in compact XML layout (omitting descriptions)."""
    lines = [
        "\n\nThe following skills provide specialized instructions for specific tasks.",
        "Use the read_file action under sandbox mode to load a skill's file when the task matches its name.",
        "When a skill file references a relative path, resolve it against the skill directory (parent of SKILL.md / dirname of the path) and use that absolute path in tool commands.",
        "",
        "<available_skills>"
    ]
    for s in skills:
        lines.append("  <skill>")
        lines.append(f"    <name>{escape_xml(s['name'])}</name>")
        lines.append(f"    <location>{escape_xml(s['filePath'])}</location>")
        lines.append("  </skill>")
    lines.append("</available_skills>")
    return "\n".join(lines)

def format_skills_hybrid(relevant: list, others: list) -> str:
    """Formats the skills in a hybrid layout (relevant skills full, other skills compact)."""
    lines = [
        "\n\nThe following skills provide specialized instructions for specific tasks.",
        "Use the read_file action under sandbox mode to load a skill's file when the task matches its name/description.",
        "When a skill file references a relative path, resolve it against the skill directory (parent of SKILL.md / dirname of the path) and use that absolute path in tool commands.",
        "",
        "<available_skills>"
    ]
    # Relevant skills formatted in full layout
    for s in relevant:
        lines.append("  <skill>")
        lines.append(f"    <name>{escape_xml(s['name'])}</name>")
        lines.append(f"    <description>{escape_xml(s['description'])}</description>")
        lines.append(f"    <location>{escape_xml(s['filePath'])}</location>")
        lines.append("  </skill>")
    # All other skills formatted in compact layout
    for s in others:
        lines.append("  <skill>")
        lines.append(f"    <name>{escape_xml(s['name'])}</name>")
        lines.append(f"    <location>{escape_xml(s['filePath'])}</location>")
        lines.append("  </skill>")
    lines.append("</available_skills>")
    return "\n".join(lines)

def get_available_skills_prompt(query: str = None) -> str:
    """
    Scans all OpenClaw skills folders and returns the formatted XML block
    using OpenClaw prompt sizing rules, compact formatting, and truncation algorithms.
    """
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    
    # Paths to the skills directories
    gateway_skills_dir = os.path.join(project_root, "gateway", "skills")
    gateway_agents_skills_dir = os.path.join(project_root, "gateway", ".agents", "skills")
    local_skills_dir = os.path.join(project_root, "skills")

    # Merge skills based on precedence hierarchy (local workspace overrides gateway/bundled)
    skills_map = {}
    
    # 1. Bundled / Gateway skills
    for s in scan_skills_directory(gateway_skills_dir, "gateway/skills"):
        skills_map[s["name"].lower()] = s
        
    # 2. Agents maintenance skills
    for s in scan_skills_directory(gateway_agents_skills_dir, "gateway/.agents/skills"):
        skills_map[s["name"].lower()] = s
        
    # 3. Workspace skills (highest precedence)
    for s in scan_skills_directory(local_skills_dir, "skills"):
        skills_map[s["name"].lower()] = s

    if not skills_map:
        return ""

    # Sort alphabetically by name
    sorted_names = sorted(skills_map.keys())
    all_skills = [skills_map[name] for name in sorted_names]

    # Enforce max skills count limit
    total_skills = len(all_skills)
    skills_slice = all_skills[:MAX_SKILLS_IN_PROMPT]
    truncated = total_skills > len(skills_slice)

    # Rank skills by relevance if query is provided
    relevant, others = rank_skills_by_relevance(skills_slice, query) if query else ([], skills_slice)

    # Limit maximum relevant skills with full descriptions to 5 to prevent prompt explosion
    MAX_RELEVANT_FULL = 5
    if len(relevant) > MAX_RELEVANT_FULL:
        others = relevant[MAX_RELEVANT_FULL:] + others
        relevant = relevant[:MAX_RELEVANT_FULL]

    # Check if the user is explicitly asking to list/show available skills
    list_skills_request = False
    if query:
        query_cleaned = query.lower()
        if any(phrase in query_cleaned for phrase in ("list skills", "show skills", "what skills", "available skills", "help skills")):
            list_skills_request = True

    if not relevant and not list_skills_request:
        # If no skills are relevant, we don't inject any available skills block to keep the prompt clean and fast.
        return ""

    if list_skills_request:
        # Check budget for compact format of all skills
        compact_budget = MAX_SKILLS_PROMPT_CHARS - COMPACT_WARNING_OVERHEAD
        compact_prompt = format_skills_compact(skills_slice)
        if len(compact_prompt) <= compact_budget:
            warning = "💡 All available skills listed in compact format:"
            if truncated:
                warning = f"⚠️ Skills truncated: included {len(skills_slice)} of {total_skills} (compact format, descriptions omitted)."
            return f"{warning}\n{compact_prompt}"

        # If compact exceeds budget, binary search the prefix
        lo = 0
        hi = len(skills_slice)
        while lo < hi:
            mid = (lo + hi + 1) // 2
            candidate_prompt = format_skills_compact(skills_slice[:mid])
            if len(candidate_prompt) <= compact_budget:
                lo = mid
            else:
                hi = mid - 1

        final_skills = skills_slice[:lo]
        warning = f"⚠️ Skills truncated: included {lo} of {total_skills} (compact format, descriptions omitted)."
        return f"{warning}\n{format_skills_compact(final_skills)}"
    else:
        # Only inject the relevant skills in full format to prevent token bloat
        warning = "💡 Relevant skills injected for this query:"
        return f"{warning}\n{format_skills_full(relevant)}"


def get_all_skills() -> list:
    """
    Returns all detected skills as a list of dicts with name, description, and location.
    """
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    gateway_skills_dir = os.path.join(project_root, "gateway", "skills")
    gateway_agents_skills_dir = os.path.join(project_root, "gateway", ".agents", "skills")
    local_skills_dir = os.path.join(project_root, "skills")

    skills_map = {}
    for s in scan_skills_directory(gateway_skills_dir, "gateway/skills"):
        skills_map[s["name"].lower()] = s
    for s in scan_skills_directory(gateway_agents_skills_dir, "gateway/.agents/skills"):
        skills_map[s["name"].lower()] = s
    for s in scan_skills_directory(local_skills_dir, "skills"):
        skills_map[s["name"].lower()] = s

    sorted_names = sorted(skills_map.keys())
    return [
        {
            "name": skills_map[name]["name"],
            "description": skills_map[name]["description"],
            "location": skills_map[name]["filePath"]
        }
        for name in sorted_names
    ]
