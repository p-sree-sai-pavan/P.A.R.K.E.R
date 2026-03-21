# api/main.py
import sys
import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

# Handle imports from parent directory
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

# Load Parker core logic
from config import DEFAULT_USER_ID, get_config
from database import create_store, create_checkpointer, setup_database
from graph import build_graph
from memory.tasks import load_pending_tasks
from memory.projects import load_active_projects
from memory.profile import load_profile

USER_ID = DEFAULT_USER_ID
config  = get_config(USER_ID)

store        = create_store()
checkpointer = create_checkpointer()
graph        = build_graph(store, checkpointer)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup tasks
    setup_database(store, checkpointer)
    yield
    # Shutdown tasks

app = FastAPI(title="Parker API", lifespan=lifespan)

# Allow all origins for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatRequest(BaseModel):
    message: str

@app.get("/")
async def root():
    return {"status": "online", "service": "Parker Intelligence API"}

@app.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket):
    await websocket.accept()
    from langchain_core.messages import HumanMessage
    try:
        while True:
            data = await websocket.receive_text()
            # Simple wrapper to stream LangGraph output
            # In a real scenario, we would use graph.astream()
            async for event in graph.astream(
                {"messages": [HumanMessage(content=data)]},
                config,
                stream_mode="messages"
            ):
                msg, metadata = event
                if hasattr(msg, "content"):
                    await websocket.send_json({
                        "type": "token",
                        "content": msg.content,
                        "node": metadata.get("langgraph_node")
                    })
            
            await websocket.send_json({"type": "done"})
            
    except WebSocketDisconnect:
        print("Client disconnected")
    except Exception as e:
        await websocket.send_json({"type": "error", "content": str(e)})

@app.post("/chat")
async def chat(req: ChatRequest):
    """
    Standard chat endpoint (non-streaming for now, streaming to be added via WebSockets).
    """
    try:
        from langchain_core.messages import HumanMessage
        result = graph.invoke(
            {"messages": [HumanMessage(content=req.message)]},
            config,
        )
        last_msg = result["messages"][-1]
        content = last_msg.content if hasattr(last_msg, "content") else str(last_msg)
        return {"response": content}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/memory/tasks")
async def get_tasks():
    return load_pending_tasks(store, USER_ID)

@app.get("/memory/projects")
async def get_projects():
    return load_active_projects(store, USER_ID)

@app.get("/memory/profile")
async def get_profile():
    return load_profile(store, USER_ID)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
