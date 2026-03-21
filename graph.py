"""
graph.py — LangGraph orchestration for Parker AI

Defines the conversation flow:
  START → trigger → remember → chat → END

- trigger: Decides if memory retrieval/storage is needed
- remember: Extracts and stores new memories (background thread)
- chat: Generates response with context
"""
from pydantic import BaseModel, Field
from typing import TypedDict, Annotated
import operator

from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import StateGraph, START, END
from langgraph.store.base import BaseStore

from models import chat_llm, memory_llm
from prompts import BASE_INSTRUCTIONS, SYSTEM_PROMPT_TEMPLATE
from retrieval import build_context
from memory.facts import save_facts
from memory.profile import save_profile
from memory.tasks import save_tasks
from memory.reminder_gate import run as reminder_gate
from memory.projects import save_projects


# ════════════════════════════════════════════════════════════════════════════════
# Smart Trigger — Decide if memory operations are needed
# ════════════════════════════════════════════════════════════════════════════════

class MemoryTrigger(BaseModel):
    needs_retrieval: bool = Field(
        description="Set to true if you need to recall past conversations, facts, projects, preferences, or scheduled tasks to respond properly. False for casual talk."
    )
    needs_storage: bool = Field(
        description="Set to true if the user's message contains new facts, a new task to remember, or updates to a project. False otherwise."
    )


trigger_llm = memory_llm.with_structured_output(MemoryTrigger)


# ════════════════════════════════════════════════════════════════════════════════
# State Definition
# ════════════════════════════════════════════════════════════════════════════════

class AppState(TypedDict):
    messages: Annotated[list, operator.add]
    _trigger: MemoryTrigger


# ════════════════════════════════════════════════════════════════════════════════
# Helper Functions
# ════════════════════════════════════════════════════════════════════════════════

def _get_content(msg) -> str:
    """Extract content from various message formats."""
    if hasattr(msg, "content"):
        return msg.content
    if isinstance(msg, dict):
        return msg.get("content", "")
    return str(msg)


# ════════════════════════════════════════════════════════════════════════════════
# Graph Nodes
# ════════════════════════════════════════════════════════════════════════════════

def trigger_node(state: AppState, config: RunnableConfig, store: BaseStore):
    """
    Analyze incoming message to determine if memory operations are needed.
    This saves LLM calls for simple greetings/acks.
    """
    last_msg = _get_content(state["messages"][-1])

    try:
        trigger = trigger_llm.invoke([
            {"role": "system", "content": "You are a memory router for a personal AI assistant. Analyze the user message and decide if memory retrieval or storage is needed."},
            {"role": "user", "content": last_msg}
        ])
    except Exception as e:
        print(f"[Trigger Error] {e} - defaulting to True")
        trigger = MemoryTrigger(needs_retrieval=True, needs_storage=True)

    return {"_trigger": trigger}


def remember_node(state: AppState, config: RunnableConfig, store: BaseStore):
    """
    Extract and store new memories from conversation.
    Runs in background thread — non-blocking.
    """
    trigger = state.get("_trigger")
    if trigger and not trigger.needs_storage:
        print("\n[Memory] Storage skipped (no new info).")
        return {}

    print("\n[Memory] Storage triggered in background.")
    user_id = config["configurable"]["user_id"]
    messages = state["messages"]

    # Pass last 4 messages for context
    recent = messages[-4:]
    save_profile(store, user_id, recent)
    save_facts(store, user_id, recent)
    save_tasks(store, user_id, recent)
    save_projects(store, user_id, recent)

    return {}


def chat_node(state: AppState, config: RunnableConfig, store: BaseStore):
    """
    Main response generation node.
    Builds context from memory and generates response.
    """
    user_id = config["configurable"]["user_id"]
    message = _get_content(state["messages"][-1])
    trigger = state.get("_trigger")

    # Skip memory retrieval for casual chat
    if trigger and not trigger.needs_retrieval:
        print("[Memory] Retrieval skipped (casual chat).")
        context = {
            "profile": "(Memory lookup skipped)",
            "active_projects": "(Memory lookup skipped)",
            "critical_facts": "(Memory lookup skipped)",
            "relevant_facts": "(Memory lookup skipped)",
            "approved_reminders": "(Memory lookup skipped)",
            "relevant_episodes": "(Memory lookup skipped)",
            "current_time": "Now",
            "_triggered_tasks": [],
        }
    else:
        print("[Memory] Full retrieval running.")
        recent_history = state["messages"][-12:]
        context = build_context(store, user_id, message, recent_history=recent_history, llm=memory_llm)

    # Build system prompt
    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
        base_instructions=BASE_INSTRUCTIONS,
        profile=context["profile"],
        critical_facts=context["critical_facts"],
        relevant_facts=context["relevant_facts"],
        active_projects=context["active_projects"],
        approved_reminders=context["approved_reminders"],
        relevant_episodes=context["relevant_episodes"],
        current_time=context["current_time"],
    )

    system_msg = SystemMessage(content=system_prompt)
    response = chat_llm.invoke([system_msg] + state["messages"])

    # Handle task completions detected by the reminder gate
    gate_result = context.get("_gate_result", {})

    # Mark tasks the user explicitly completed
    for key in gate_result.get("complete", []):
        from memory.tasks import mark_completed
        mark_completed(store, user_id, key)

    # Increment notify counter for surfaced tasks
    for task in gate_result.get("approved_tasks", []):
        from memory.tasks import increment_notify
        increment_notify(store, user_id, task.key)

    return {"messages": [response]}


# ════════════════════════════════════════════════════════════════════════════════
# Graph Builder
# ════════════════════════════════════════════════════════════════════════════════

def build_graph(store: BaseStore, checkpointer):
    """Build and compile the LangGraph conversation graph."""
    builder = StateGraph(AppState)

    builder.add_node("trigger", trigger_node)
    builder.add_node("remember", remember_node)
    builder.add_node("chat", chat_node)

    builder.add_edge(START, "trigger")
    builder.add_edge("trigger", "remember")
    builder.add_edge("remember", "chat")
    builder.add_edge("chat", END)

    return builder.compile(store=store, checkpointer=checkpointer)


# ════════════════════════════════════════════════════════════════════════════════
# Exports
# ════════════════════════════════════════════════════════════════════════════════

__all__ = [
    "build_graph",
    "AppState",
    "MemoryTrigger",
    "trigger_llm",
    "trigger_node",
    "remember_node",
    "chat_node",
]