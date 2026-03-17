import uuid
from langchain_ollama import OllamaEmbeddings
from langgraph.store.postgres import PostgresStore
from langgraph.checkpoint.postgres import PostgresSaver
from long import build_graph
from ears import listen
from mouth import speak

DB_URI = "postgresql://postgres:postgres@localhost:5442/postgres?sslmode=disable"
config = {
    "configurable": {
        "user_id": "u1",
        "thread_id": "thread_u1"   # persistent conversation
    }
}
embedder = OllamaEmbeddings(model="mxbai-embed-large")

def embed_fn(texts: list[str]) -> list[list[float]]:
    return embedder.embed_documents(texts)

def ask(graph, prompt: str) -> str:
    result = graph.invoke(
        {"messages": [{"role": "user", "content": prompt}]},
        config,
    )
    return result["messages"][-1].content if result["messages"] else ""

if __name__ == "__main__":
    with PostgresStore.from_conn_string(
        DB_URI,
        index={                        # ← this is the only new thing
            "dims": 1024,               # nomic-embed-text vector size
            "embed": embed_fn,         # your local ollama embedder
            "fields": ["data"]         # embed the "data" field of your memories
        }
    ) as store, \
        PostgresSaver.from_conn_string(DB_URI) as checkpointer:

        store.setup()
        checkpointer.setup()
        graph = build_graph(store, checkpointer)

        print("🤖 Parker is online!")
        print("Commands: 't' = text mode | 'v' = voice mode | 'exit' = quit\n")

        mode = "text"   # default mode
        print(f"Current mode: TEXT. Type 'v' to switch to voice.\n")

        try:
            while True:
                if mode == "text":
                    user_input = input("user (t): ").strip()
                    if user_input.lower() == "v":
                        mode = "voice"
                        print("🎙️  Switched to VOICE mode. Type 't' to switch back.\n")
                        continue
                else:  # voice mode
                    cmd = input("user (v) — press Enter to speak, or type 't' to switch: ").strip()
                    if cmd.lower() == "t":
                        mode = "text"
                        print("⌨️  Switched to TEXT mode. Type 'v' to switch to voice.\n")
                        continue
                    user_input = listen()   # ← records mic
                if not user_input:
                    print("Didn't catch that, try again.")
                    continue
                if user_input.lower() in ("quit", "exit", "bye"):
                    speak("Goodbye!")
                    print("👋 Goodbye!")
                    break

                response = ask(graph, user_input)
                print(f"\nParker: {response}\n")
                speak(response)

        except KeyboardInterrupt:
            print("\n👋 Parker Shutting Down...")