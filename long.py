from dotenv import load_dotenv
load_dotenv()

import threading
from typing import List
from pydantic import BaseModel, Field

from langchain_ollama import ChatOllama
from langchain_ollama import OllamaEmbeddings
from langchain_core.messages import SystemMessage
from langchain_core.runnables import RunnableConfig

from langgraph.graph import StateGraph, START, END, MessagesState
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.store.base import BaseStore


SYSTEM_PROMPT_TEMPLATE = """You are Parker, a personal AI built for one person.

IDENTITY:
- Honest, direct, warm. No flattery, no filler, no closing lines like "feel free to ask"
- Admit mistakes openly. Push back when the user is wrong. Agree when they're right
- Verify before recommending. Say "I don't know" when true
- Match the user's energy exactly — short reply when they're brief, deep when they're curious

MEMORY:
- Treat memory as a living model of the user — not a list of facts to recite
- Weave memory naturally into responses. Never announce it ("I remember you said...")
- Reference their stack, projects, and preferences only when directly relevant
- Never re-explain something they already know
- If memory contradicts what they say now, trust what they say now

USER MEMORY:
{user_details_content}"""

memory_llm = ChatOllama(model="qwen2.5:7b", temperature=0)
chat_llm = ChatOllama(model="qwen2.5:7b")
embedder = OllamaEmbeddings(model="mxbai-embed-large")

class MemoryItem(BaseModel):
    category: str = Field(
        description="Snake_case category key e.g. name, primary_language, current_project, os_preference, communication_style"
    )
    text: str = Field(description="Atomic user memory as a short sentence")
    is_new: bool = Field(description="True if this memory is new info. False if duplicate.")

class MemoryDecision(BaseModel):
    should_write: bool = Field(description="whether to store any memory")
    memories: List[MemoryItem] = Field(default_factory=list, description="Atomic user memories to store")

memory_extractor = memory_llm.with_structured_output(MemoryDecision)

MEMORY_PROMPT = """Build and maintain a living model of this user.
Extract anything they explicitly stated — facts, preferences, habits, opinions, decisions, goals, frustrations.
Invent a precise snake_case category key per fact. Same category overwrites automatically.
is_new=true only if genuinely adds new information.
One atomic fact per item. Nothing worth storing = empty list. Never infer.

CURRENT MEMORY:
{user_details_content}"""

def embed(text: str) -> list[float]:
    return embedder.embed_query(text)

def _write_memories_bg(last_msg: str, user_details: str, namespace, store: BaseStore):
    decision: MemoryDecision = memory_extractor.invoke([
        SystemMessage(content=MEMORY_PROMPT.format(user_details_content=user_details)),
        {"role": "user", "content": last_msg},
    ])
    if decision.should_write:
        for mem in decision.memories:
            if mem.is_new:
                store.put(namespace, mem.category, {"data": mem.text})

def remember_node(state: MessagesState, config: RunnableConfig, store: BaseStore):

    user_id = config["configurable"]["user_id"]
    namespace = ("user", user_id, "details")

    items = store.search(namespace)
    existing = "\n".join(it.value["data"] for it in items) if items else "(empty)"
    # take latest user message
    last_msg = state["messages"][-1].content

    t = threading.Thread(
        target=_write_memories_bg,
        args=(last_msg, existing, namespace, store),
        daemon=True
    )
    t.start()
    return {}


def chat_node(state: MessagesState, config: RunnableConfig, store: BaseStore):
    user_id = config["configurable"]["user_id"]
    namespace = ("user", user_id, "details")

    last_msg = state["messages"][-1].content

    items = store.search(namespace, query=last_msg, limit=8) 
    user_details = "\n".join(it.value.get("data","") for it in items) if items else "(empty)"

    system_msg = SystemMessage(content=SYSTEM_PROMPT_TEMPLATE.format(user_details_content=user_details or "(empty)"))

    response = chat_llm.invoke([system_msg] + state["messages"])
    return {"messages": [response]}

def build_graph(store: BaseStore, checkpointer):
    builder = StateGraph(MessagesState)
    builder.add_node("remember", remember_node)
    builder.add_node("chat", chat_node)

    builder.add_edge(START, "remember")
    builder.add_edge("remember", "chat")
    builder.add_edge("chat", END)
    
    return builder.compile(store=store, checkpointer=checkpointer)
