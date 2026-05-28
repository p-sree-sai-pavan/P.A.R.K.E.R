"""
graph.py — LangGraph orchestration for Parker AI

Flow:  START → trigger → retrieve → chat → [computer?] → remember → END
"""
from pydantic import BaseModel, Field, field_validator
from typing import TypedDict, Annotated, Optional, Union
import operator
import re
from datetime import datetime

from langchain_core.messages import AIMessage, SystemMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import StateGraph, START, END
from langgraph.store.base import BaseStore

from models import chat_llm, trigger_llm
from prompts.chat import BASE_INSTRUCTIONS, SYSTEM_PROMPT_TEMPLATE
from retrieval import build_context, build_lightweight_context
from memory.unified import save_memory_updates


# ── Computer use (lazy import — won't crash if libs missing) ──────────────────
 
def _try_computer_use(response_text: str) -> Optional[str]:
    """
    Attempt to parse and execute computer actions from Parker's response.
    Returns result string if action(s) were found and executed, None otherwise.
    Silently fails if computer libraries aren't installed.
    """
    try:
        from computer.agent import parse_computer_intents, execute_computer_actions
        intents = parse_computer_intents(response_text)
        if intents:
            return execute_computer_actions(intents)
    except ImportError:
        pass
    except Exception as e:
        return f"[Computer Use] Error: {e}"
    return None


# ── Trigger schema ─────────────────────────────────────────────────────────────

class MemoryTrigger(BaseModel):
    needs_retrieval: Union[bool, str] = Field(
        description="True if memory retrieval is needed to respond properly."
    )
    needs_storage: Union[bool, str] = Field(
        description="True if the message contains new facts, tasks, or project updates."
    )

    @field_validator("needs_retrieval", "needs_storage", mode="before")
    @classmethod
    def coerce_bool(cls, v):
        if isinstance(v, str):
            if v.lower() in ("true", "1", "yes"):
                return True
            if v.lower() in ("false", "0", "no"):
                return False
        return bool(v)


trigger_llm = trigger_llm.with_structured_output(MemoryTrigger)


# ── State ──────────────────────────────────────────────────────────────────────

class AppState(TypedDict):
    messages:     Annotated[list, operator.add]
    _trigger:     Optional[dict]            # D1 fix: honest Optional typing
    _context:     Optional[dict]            # D1 fix
    _computer_result: Optional[str]


# ── Helpers ────────────────────────────────────────────────────────────────────

def _get_content(msg) -> str:
    if hasattr(msg, "content"):
        c = msg.content
        if isinstance(c, list):
            parts = []
            for item in c:
                if isinstance(item, dict):
                    if "text" in item:
                        parts.append(item["text"])
                    elif item.get("type") == "text":
                        parts.append(item.get("text", ""))
                elif isinstance(item, str):
                    parts.append(item)
            return "".join(parts)
        return c
    if isinstance(msg, dict):
        return msg.get("content", "")
    return str(msg)


_FORBIDDEN_MEMORY_PATTERNS = [
    r"\bi don't have the ability to retain information\b",
    r"\bi don't retain information\b",
    r"\bi can't remember past conversations\b",
    r"\bi cannot remember past conversations\b",
    r"\beach time you interact with me,? it's a new start\b",
    r"\bi don't have any information about (our )?previous conversations\b",
    r"\bi don't have the ability to remember\b",
]

_NO_RECORDS_PATTERNS = [
    r"^i don't have records of that yet, pavan\.$",
    r"^i don't recall that, sir\.$",
    r"i don't have any records of (our )?previous conversation",
    r"i don't have any records of our previous conversation topics",
    r"memory lookup for past context didn't yield any specific information",
]

_MEMORY_QUERY_PATTERNS = [
    r"\bremember\b",
    r"\brecall\b",
    r"\bprevious(ly)?\b",
    r"\blast time\b",
    r"\byesterday\b",
    r"\bwhat did (i|you|we)\b",
    r"\bwhen did (i|you|we)\b",
    r"\byou (gave|said|asked|told|suggested|recommended)\b",
    r"\bi (asked|said|told) you\b",
    r"\bwe (talked|discussed|worked|decided)\b",
    r"\bleft off\b",
    r"\bpick up\b",
    r"\blast (chat|session|conversation|time)\b",
    r"\bearlier (today|this week|you said)\b",
]


def _contains_forbidden_memory_disclaimer(text: str) -> bool:
    lowered = text.lower()
    return any(re.search(pattern, lowered) for pattern in _FORBIDDEN_MEMORY_PATTERNS)


def _is_no_records_reply(text: str) -> bool:
    lowered = (text or "").strip().lower()
    return any(re.search(pattern, lowered) for pattern in _NO_RECORDS_PATTERNS)


def _looks_like_memory_query(text: str) -> bool:
    lowered = (text or "").strip().lower()
    if not lowered:
        return False
    return any(re.search(pattern, lowered) for pattern in _MEMORY_QUERY_PATTERNS)


def _has_useful_memory_context(context: dict) -> bool:
    return any(
        value and value not in {"(none)", "(no profile yet)", "(Memory lookup skipped)"}
        for value in (
            context.get("profile"),
            context.get("critical_facts"),
            context.get("relevant_facts"),
            context.get("active_projects"),
            context.get("relevant_episodes"),
        )
    )


def _repair_memory_response(user_message: str, context: dict, draft: str) -> str:
    if not _has_useful_memory_context(context):
        return "I don't recall that, sir."

    repair_prompt = SystemMessage(content=(
        "Rewrite the assistant reply so it fully complies with Parker's memory rules.\n"
        "Use only the supplied context.\n"
        "Never mention being an AI, memory limitations, or session resets.\n"
        "If the context is insufficient, output exactly: I don't recall that, sir."
    ))

    repair_input = HumanMessage(content=(
        f"User question:\n{user_message}\n\n"
        f"Relevant episodes:\n{context.get('relevant_episodes', '(none)')}\n\n"
        f"Relevant facts:\n{context.get('relevant_facts', '(none)')}\n\n"
        f"Active projects:\n{context.get('active_projects', '(none)')}\n\n"
        f"Draft reply to fix:\n{draft}"
    ))

    try:
        repaired = chat_llm.invoke([repair_prompt, repair_input])
        repaired_text = _get_content(repaired).strip()
        if repaired_text and not _contains_forbidden_memory_disclaimer(repaired_text):
            return repaired_text
    except Exception as e:
        print(f"[Memory Repair Error] {e}")

    return "I don't recall that, sir."


# ── Nodes ──────────────────────────────────────────────────────────────────────

TRIGGER_SYSTEM_PROMPT = """You are a memory router. Decide if the user message needs retrieval or storage.
 
needs_storage = True if the message contains ANY of:
- Personal facts (name, location, university, tools, preferences)
- Project updates, decisions, bugs fixed, progress made
- Explicit statements about what the user does, uses, or prefers
- New tasks, goals, or plans
 
needs_storage = False ONLY for: pure greetings ("hi", "thanks", "ok"), 
single-word acks, math questions with no personal context.
 
When in doubt: needs_storage = True. False negatives destroy memory permanently.
 
needs_retrieval = True if answering well requires knowing past context.
needs_retrieval = False ONLY for: standalone questions answerable without history."""

def trigger_node(state: AppState, config: RunnableConfig, store: BaseStore):
    last_msg = _get_content(state["messages"][-1])

    try:
        recent = state["messages"][-4:]
        history_text = "\n".join(
            f"{'User' if getattr(m,'type','')=='human' else 'Parker'}: {getattr(m,'content',m) if hasattr(m,'content') else m}"
            for m in recent[:-1]
        )
        trigger_input = f"Recent context:\n{history_text}\n\nCurrent message: {last_msg}" if history_text else last_msg

        trigger = trigger_llm.invoke([
            {"role": "system", "content": TRIGGER_SYSTEM_PROMPT},
            {"role": "user",   "content": trigger_input}
        ])
    except Exception as e:
        print(f"[Trigger Error] {e} - defaulting to True")
        trigger = MemoryTrigger(needs_retrieval=True, needs_storage=True)

    trigger_data = trigger.model_dump() if hasattr(trigger, "model_dump") else trigger.dict()
    if _looks_like_memory_query(last_msg):
        trigger_data["needs_retrieval"] = True

    return {"_trigger": trigger_data}


# graph.py — flip the default
RETRIEVAL_SKIP_PATTERNS = [
    r"^(hi|hey|hello|thanks|thank you|ok|okay|sure|got it|bye|cool|nice|great|yes|no|yep|nope)[\s!.]*$",
    r"^(what time is it|what('s| is) \d+\s*[\+\-\*\/])",
    r"^(good (morning|afternoon|evening))[\s!.]*$",
]

def retrieve_node(state: AppState, config: RunnableConfig, store: BaseStore):
    user_id = config["configurable"]["user_id"]
    message = _get_content(state["messages"][-1])
    trigger = state.get("_trigger")

    skip = any(re.match(p, message.strip(), re.I) for p in RETRIEVAL_SKIP_PATTERNS)

    if skip:
        print("[Memory] Retrieval skipped (casual chat) - running lightweight retrieval.")
        context = build_lightweight_context(store, user_id, query=message)
    else:
        print("[Memory] Full retrieval running.")
        recent_history = state["messages"][-12:]
        context = build_context(store, user_id, message,
                                recent_history=recent_history, llm=trigger_llm)

    return {"_context": context}


def chat_node(state: AppState, config: RunnableConfig, store: BaseStore):
    context = state.get("_context") or {}
    user_message = _get_content(state["messages"][-1])

    computer_result = state.get("_computer_result")
    extra_messages = []
    if computer_result:
        extra_messages = [HumanMessage(content=(
            f"[SEARCH RESULT — use this to answer, do not mention searching]\n\n{computer_result}"
        ))]
    
    def _section(title, content):
        if not content or content in ("(none)", "(no profile yet)", ""):
            return ""
        return f"## {title}\n{content}\n\n"

    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
        base_instructions=BASE_INSTRUCTIONS,
        current_time=context.get("current_time", "Now"),
        profile=_section("YOUR PROFILE OF PAVAN", context.get("profile", "")),
        critical_facts=_section("HARD CONSTRAINTS", context.get("critical_facts", "")),
        relevant_facts=_section("THINGS YOU REMEMBER ABOUT PAVAN", context.get("relevant_facts", "")),
        active_projects=_section("PROJECTS YOU ARE CURRENTLY TRACKING", context.get("active_projects", "")),
        pending_tasks=_section("YOUR ACTIVE TASK LIST", context.get("pending_tasks", "")),
        observed_patterns=_section("OBSERVED BEHAVIOR PATTERNS & HABITS", context.get("observed_patterns", "")),
        relevant_episodes=_section("YOUR RECENT RECOLLECTIONS (CHRONOLOGICAL)\nEach entry below has an exact key (ISO timestamp or date). Use these for any date reference — never guess.", context.get("relevant_episodes", "")),
        skills=_section("AVAILABLE OPENCLAW SKILLS", context.get("skills", "")),
        telemetry=_section("LIVE ENVIRONMENT TELEMETRY", context.get("telemetry", "")),
    )

    system_msg = SystemMessage(content=system_prompt)

    MAX_HISTORY = 20
    trimmed_messages = state["messages"][-MAX_HISTORY:]

    response = chat_llm.invoke([system_msg] + trimmed_messages + extra_messages)

    try:
        usage = response.response_metadata.get("token_usage", {})
        from interface import update_token_usage
        update_token_usage(
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
        )
    except Exception:
        pass
 
    response_text = _get_content(response).strip()
    if _contains_forbidden_memory_disclaimer(response_text) or (
        _is_no_records_reply(response_text) and _has_useful_memory_context(context)
    ):
        response = AIMessage(content=_repair_memory_response(user_message, context, response_text))
 
    return {"messages": [response], "_computer_result": None}  # clear previous result
 
 
def computer_node(state: AppState, config: RunnableConfig, store: BaseStore):
    """
    Execute computer use action if Parker's response contains one.
    Injects result back into state for the next chat turn.
    """
    last_response = _get_content(state["messages"][-1])
    result = _try_computer_use(last_response)
 
    if result:
        print(f"[Computer] Action(s) executed. Result: {result[:80]}...")
        # Strip the action tag from the visible response
        from computer.agent import strip_action_tag
        clean_response = strip_action_tag(last_response)
 
        # Replace last message with cleaned version
        cleaned_messages = list(state["messages"][:-1]) + [AIMessage(content=clean_response)]
        return {
            "messages": cleaned_messages,           # no new messages
            "_computer_result": result,
        }
 
    return {"_computer_result": None}
 


from memory.episodes import write_chat_turn_async

def remember_node(state, config, store):
    # Forced storage enabled: remember everything, zero bias
    user_id = config.get("configurable", {}).get("user_id", "default_user")
    messages = state["messages"]
    current_turn = []
    for msg in reversed(messages):
        current_turn.insert(0, msg)
        if hasattr(msg, "type") and msg.type == "human":
            break

    save_memory_updates(store, user_id, current_turn)

    if len(current_turn) >= 2:
        user_msg = _get_content(current_turn[0])
        assistant_msg = _get_content(current_turn[-1])
        write_chat_turn_async(store, user_id, user_msg, assistant_msg)

    return {}


# ── Routing ────────────────────────────────────────────────────────────────────
 
def _should_use_computer(state: AppState) -> str:
    """
    After chat_node: check if Parker's response contains any computer action tags.
    Routes to computer_node if yes, remember_node if no.
    """
    last_response = _get_content(state["messages"][-1])
    try:
        from computer.agent import parse_computer_intents
        if parse_computer_intents(last_response):
            print("[Computer] Action(s) detected in response — routing to computer_node.")
            return "computer"
    except ImportError:
        pass
    return "remember"


# ── Graph builder ──────────────────────────────────────────────────────────────

def build_graph(store: BaseStore, checkpointer):
    builder = StateGraph(AppState)

    builder.add_node("trigger",  trigger_node)
    builder.add_node("retrieve", retrieve_node)
    builder.add_node("chat",     chat_node)
    builder.add_node("computer", computer_node)
    builder.add_node("remember", remember_node)

    builder.add_edge(START,      "trigger")
    builder.add_edge("trigger",  "retrieve")
    builder.add_edge("retrieve", "chat")
    # After chat: branch to computer if action detected, else remember
    builder.add_conditional_edges(
        "chat",
        _should_use_computer,
        {
            "computer": "computer",
            "remember": "remember",
        }
    )
    builder.add_edge("computer", "chat")
    builder.add_edge("remember", END)

    return builder.compile(store=store, checkpointer=checkpointer)


__all__ = [
    "build_graph", "AppState", "MemoryTrigger",
    "trigger_llm", "trigger_node", "retrieve_node", "remember_node",
    "chat_node", "computer_node",
]
