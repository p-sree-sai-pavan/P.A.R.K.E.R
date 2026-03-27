"""
graph.py — LangGraph orchestration for Parker AI

Flow:  START → trigger → retrieve → chat → remember → END
"""
from pydantic import BaseModel, Field
from typing import TypedDict, Annotated, Optional
import operator

from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import StateGraph, START, END
from langgraph.store.base import BaseStore

from models import chat_llm, memory_llm
from prompts.chat import BASE_INSTRUCTIONS, SYSTEM_PROMPT_TEMPLATE
from retrieval import build_context
from memory.facts import save_facts
from memory.profile import save_profile
from memory.tasks import save_tasks, mark_completed, increment_notify
from memory.reminder_gate import run as reminder_gate
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
    _gate_result: Optional[dict]            # D1 fix


# ── Helpers ────────────────────────────────────────────────────────────────────

def _get_content(msg) -> str:
    if hasattr(msg, "content"):
        return msg.content
    if isinstance(msg, dict):
        return msg.get("content", "")
    return str(msg)


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

    return {"_trigger": trigger.model_dump() if hasattr(trigger, "model_dump") else trigger.dict()}


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
            "approved_reminders":"(Memory lookup skipped)",
            "relevant_episodes": "(Memory lookup skipped)",
            "current_time":      "Now",
        }
        gate_result = {}
    else:
        print("[Memory] Full retrieval running.")
        recent_history = state["messages"][-12:]
        context        = build_context(store, user_id, message, recent_history=recent_history, llm=memory_llm)
        gate_result    = context.pop("_gate_result", {})

    return {"_context": context, "_gate_result": gate_result}


def chat_node(state: AppState, config: RunnableConfig, store: BaseStore):
    context = state.get("_context") or {}

    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
        base_instructions=BASE_INSTRUCTIONS,
        profile=context.get("profile", ""),
        critical_facts=context.get("critical_facts", ""),
        relevant_facts=context.get("relevant_facts", ""),
        active_projects=context.get("active_projects", ""),
        approved_reminders=context.get("approved_reminders", ""),
        relevant_episodes=context.get("relevant_episodes", ""),
        current_time=context.get("current_time", "Now"),
    )

    system_msg = SystemMessage(content=system_prompt)
    response   = chat_llm.invoke([system_msg] + state["messages"])

    return {"messages": [response]}


def remember_node(state: AppState, config: RunnableConfig, store: BaseStore):
    user_id     = config["configurable"]["user_id"]
    trigger     = state.get("_trigger")
    gate_result = state.get("_gate_result") or {}

    # Handle task completions from gate
    for key in gate_result.get("complete", []):
        mark_completed(store, user_id, key)

    for task in gate_result.get("approved_tasks", []):
        increment_notify(store, user_id, task.key)

    if trigger and not trigger.get("needs_storage", True):
        print("\n[Memory] Storage skipped (no new info).")
        return {}

    print("\n[Memory] Storage triggered.")
    recent = state["messages"][-4:]
    save_profile(store, user_id, recent)
    save_facts(store, user_id, recent)
    save_tasks(store, user_id, recent)
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