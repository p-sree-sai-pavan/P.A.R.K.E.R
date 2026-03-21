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
    _context: dict          # built by retrieve_node, consumed by chat_node
    _gate_result: dict      # built by retrieve_node, consumed by post-chat logic


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
#
# Flow:  START → trigger → retrieve → chat → remember → END
#
# - trigger:  decides if memory ops are needed  (fast, no streaming leak)
# - retrieve: builds context from memory store  (LLM calls here stay hidden)
# - chat:     generates the user-facing response (ONLY node that streams)
# - remember: extracts & stores new memories     (runs AFTER response)
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


def retrieve_node(state: AppState, config: RunnableConfig, store: BaseStore):
    """
    Build the memory context for the response.
    Separated from chat_node so internal LLM calls (reminder gate, etc.)
    don't leak into stream_mode='messages' output.
    """
    user_id = config["configurable"]["user_id"]
    message = _get_content(state["messages"][-1])
    trigger = state.get("_trigger")

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
        }
        gate_result = {}
    else:
        print("[Memory] Full retrieval running.")
        recent_history = state["messages"][-12:]
        context = build_context(store, user_id, message, recent_history=recent_history, llm=memory_llm)
        gate_result = context.pop("_gate_result", {})

    return {"_context": context, "_gate_result": gate_result}


def chat_node(state: AppState, config: RunnableConfig, store: BaseStore):
    """
    Generate the user-facing response.
    This node contains ONLY the chat LLM call — nothing else —
    so stream_mode='messages' streams only the actual response.
    """
    context = state.get("_context", {})
    user_id = config["configurable"]["user_id"]

    # Build system prompt from the context prepared by retrieve_node
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
    response = chat_llm.invoke([system_msg] + state["messages"])

    return {"messages": [response]}


def remember_node(state: AppState, config: RunnableConfig, store: BaseStore):
    """
    Extract and store new memories from conversation.
    Runs AFTER chat_node so it doesn't block the response.
    Also handles task completions from the gate result.
    """
    user_id = config["configurable"]["user_id"]
    trigger = state.get("_trigger")

    # Handle task completions detected by the reminder gate
    gate_result = state.get("_gate_result", {})
    if gate_result:
        for key in gate_result.get("complete", []):
            from memory.tasks import mark_completed
            mark_completed(store, user_id, key)

        for task in gate_result.get("approved_tasks", []):
            from memory.tasks import increment_notify
            increment_notify(store, user_id, task.key)

    # Extract and store new memories
    if trigger and not trigger.needs_storage:
        print("\n[Memory] Storage skipped (no new info).")
        return {}

    print("\n[Memory] Storage triggered.")
    messages = state["messages"]
    recent = messages[-4:]
    save_profile(store, user_id, recent)
    save_facts(store, user_id, recent)
    save_tasks(store, user_id, recent)
    save_projects(store, user_id, recent)

    return {}


# ════════════════════════════════════════════════════════════════════════════════
# Graph Builder
# ════════════════════════════════════════════════════════════════════════════════

def build_graph(store: BaseStore, checkpointer):
    """Build and compile the LangGraph conversation graph.

    Flow:  START → trigger → retrieve → chat → remember → END
    """
    builder = StateGraph(AppState)

    builder.add_node("trigger", trigger_node)
    builder.add_node("retrieve", retrieve_node)
    builder.add_node("chat", chat_node)
    builder.add_node("remember", remember_node)

    builder.add_edge(START, "trigger")
    builder.add_edge("trigger", "retrieve")
    builder.add_edge("retrieve", "chat")
    builder.add_edge("chat", "remember")
    builder.add_edge("remember", END)

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
    "retrieve_node",
    "remember_node",
    "chat_node",
]