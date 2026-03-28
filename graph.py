"""
graph.py — LangGraph orchestration for Parker AI

Flow:  START → trigger → retrieve → chat → remember → END
"""
from pydantic import BaseModel, Field
from typing import TypedDict, Annotated, Optional
import operator
import re

from langchain_core.messages import AIMessage, SystemMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import StateGraph, START, END
from langgraph.store.base import BaseStore

from models import chat_llm, memory_llm
from prompts.chat import BASE_INSTRUCTIONS, SYSTEM_PROMPT_TEMPLATE
from retrieval import build_context
from memory.facts import save_facts
from memory.profile import save_profile
from memory.projects import save_projects


# ── Trigger schema ─────────────────────────────────────────────────────────────

class MemoryTrigger(BaseModel):
    needs_retrieval: bool = Field(
        description="True if memory retrieval is needed to respond properly."
    )
    needs_storage: bool = Field(
        description="True if the message contains new facts, tasks, or project updates."
    )


trigger_llm = memory_llm.with_structured_output(MemoryTrigger)


# ── State ──────────────────────────────────────────────────────────────────────

class AppState(TypedDict):
    messages:     Annotated[list, operator.add]
    _trigger:     Optional[dict]            # D1 fix: honest Optional typing
    _context:     Optional[dict]            # D1 fix


# ── Helpers ────────────────────────────────────────────────────────────────────

def _get_content(msg) -> str:
    if hasattr(msg, "content"):
        return msg.content
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
    r"i don't have any records of (our )?previous conversation",
    r"i don't have any records of our previous conversation topics",
    r"memory lookup for past context didn't yield any specific information",
]

_MEMORY_QUERY_PATTERNS = [
    r"\bremember\b",
    r"\brecall\b",
    r"\bbefore\b",
    r"\bprevious\b",
    r"\bearlier\b",
    r"\byesterday\b",
    r"\blast time\b",
    r"\bagain\b",
    r"\bchat\b",
    r"\bconversation\b",
    r"\bwhat did (i|you|we)\b",
    r"\bwhen did (i|you|we)\b",
    r"\byou (gave|said|asked|told)\b",
    r"\bi (asked|said|told)\b",
    r"\bwe (did|talked|discussed|worked)\b",
    r"\b(question|questions|answer|answers|message|messages)\b",
    r"\bcontinue\b",
    r"\bpick up\b",
    r"\bleft off\b",
    r"\blast chat\b",
    r"\bprevious chat\b",
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
        return "I don't have records of that yet, Pavan."

    repair_prompt = SystemMessage(content=(
        "Rewrite the assistant reply so it fully complies with Parker's memory rules.\n"
        "Use only the supplied context.\n"
        "Never mention being an AI, memory limitations, or session resets.\n"
        "If the context is insufficient, output exactly: I don't have records of that yet, Pavan."
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
    except Exception:
        pass

    return "I don't have records of that yet, Pavan."


# ── Nodes ──────────────────────────────────────────────────────────────────────

def trigger_node(state: AppState, config: RunnableConfig, store: BaseStore):
    last_msg = _get_content(state["messages"][-1])

    try:
        trigger = trigger_llm.invoke([
            {"role": "system", "content": "You are a memory router for a personal AI assistant. Analyze the user message and decide if memory retrieval or storage is needed."},
            {"role": "user",   "content": last_msg}
        ])
    except Exception as e:
        print(f"[Trigger Error] {e} - defaulting to True")
        trigger = MemoryTrigger(needs_retrieval=True, needs_storage=True)

    trigger_data = trigger.model_dump() if hasattr(trigger, "model_dump") else trigger.dict()
    if _looks_like_memory_query(last_msg):
        trigger_data["needs_retrieval"] = True

    return {"_trigger": trigger_data}


def retrieve_node(state: AppState, config: RunnableConfig, store: BaseStore):
    user_id = config["configurable"]["user_id"]
    message = _get_content(state["messages"][-1])
    trigger = state.get("_trigger")

    if trigger and not trigger.get("needs_retrieval", True):
        print("[Memory] Retrieval skipped (casual chat).")
        context = {
            "profile":           "(Memory lookup skipped)",
            "active_projects":   "(Memory lookup skipped)",
            "critical_facts":    "(Memory lookup skipped)",
            "relevant_facts":    "(Memory lookup skipped)",
            "relevant_episodes": "(Memory lookup skipped)",
            "current_time":      "Now",
        }
    else:
        print("[Memory] Full retrieval running.")
        recent_history = state["messages"][-12:]
        context        = build_context(store, user_id, message, recent_history=recent_history, llm=memory_llm)

    return {"_context": context}


def chat_node(state: AppState, config: RunnableConfig, store: BaseStore):
    context = state.get("_context") or {}
    user_message = _get_content(state["messages"][-1])

    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
        base_instructions=BASE_INSTRUCTIONS,
        profile=context.get("profile", ""),
        critical_facts=context.get("critical_facts", ""),
        relevant_facts=context.get("relevant_facts", ""),
        active_projects=context.get("active_projects", ""),
        relevant_episodes=context.get("relevant_episodes", ""),
        current_time=context.get("current_time", "Now"),
    )

    system_msg = SystemMessage(content=system_prompt)
    response   = chat_llm.invoke([system_msg] + state["messages"])

    response_text = _get_content(response).strip()
    if _contains_forbidden_memory_disclaimer(response_text) or (
        _is_no_records_reply(response_text) and _has_useful_memory_context(context)
    ):
        response = AIMessage(content=_repair_memory_response(user_message, context, response_text))

    return {"messages": [response]}


def remember_node(state: AppState, config: RunnableConfig, store: BaseStore):
    user_id     = config["configurable"]["user_id"]
    trigger     = state.get("_trigger")

    if trigger and not trigger.get("needs_storage", True):
        print("\n[Memory] Storage skipped (no new info).")
        return {}

    print("\n[Memory] Storage triggered.")
    recent = state["messages"][-4:]
    save_profile(store, user_id, recent)
    save_facts(store, user_id, recent)
    save_projects(store, user_id, recent)

    return {}


# ── Graph builder ──────────────────────────────────────────────────────────────

def build_graph(store: BaseStore, checkpointer):
    builder = StateGraph(AppState)

    builder.add_node("trigger",  trigger_node)
    builder.add_node("retrieve", retrieve_node)
    builder.add_node("chat",     chat_node)
    builder.add_node("remember", remember_node)

    builder.add_edge(START,      "trigger")
    builder.add_edge("trigger",  "retrieve")
    builder.add_edge("retrieve", "chat")
    builder.add_edge("chat",     "remember")
    builder.add_edge("remember", END)

    return builder.compile(store=store, checkpointer=checkpointer)


__all__ = [
    "build_graph", "AppState", "MemoryTrigger",
    "trigger_llm", "trigger_node", "retrieve_node", "remember_node", "chat_node",
]
