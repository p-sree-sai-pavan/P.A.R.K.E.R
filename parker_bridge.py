import sys
import json
import warnings
warnings.filterwarnings("ignore")

# Redirect stdout to capture only our JSON output. Other prints go to stderr.
_original_stdout = sys.stdout
sys.stdout = sys.stderr

from langchain_core.messages import HumanMessage
from database import create_store, create_checkpointer, setup_database, close_connections
from graph import build_graph
from config import DEFAULT_USER_ID, get_config
from memory.utils import wait_for_background_jobs

def run_bridge():
    try:
        # Read from stdin
        input_data = sys.stdin.read().strip()
        if not input_data:
            print("[Bridge] Empty input received on stdin", file=sys.stderr)
            _original_stdout.write(json.dumps({"status": "error", "error": "Empty input"}))
            return

        params = json.loads(input_data)
        prompt = params.get("prompt", "")
        session_key = params.get("session_key", "default_session")
        user_id = params.get("user_id", DEFAULT_USER_ID)

        print(f"[Bridge] Processing turn for user: {user_id}, session_key: {session_key}", file=sys.stderr)

        # Setup database connection
        store = create_store()
        checkpointer = create_checkpointer()
        setup_database(store, checkpointer)

        # Compile the state graph
        graph = build_graph(store, checkpointer)
        config = get_config(user_id, session_key)

        # Invoke the graph
        result = graph.invoke(
            {"messages": [HumanMessage(content=prompt)]},
            config,
        )

        last_msg = result["messages"][-1]
        reply = ""
        if hasattr(last_msg, "content"):
            reply = last_msg.content
        elif isinstance(last_msg, dict):
            reply = last_msg.get("content", "")

        # Clean persona filters similar to main.py
        import re
        def apply_persona_filters(text: str) -> str:
            if not text:
                return text
            # Strip reasoning monologue <think>...</think> blocks
            cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE)
            fillers = [
                r"^(certainly|absolutely|of course|sure|great|happy to help|no problem|understood|i understand|i see|that makes sense|indeed),?\s*",
                r"^here is the information,?\s*",
                r"^i have retrieved,?\s*",
            ]
            for f in fillers:
                cleaned = re.sub(f, "", cleaned, flags=re.IGNORECASE)
            trailing = [
                r"\bhow does that sound\??$",
                r"\bwould you like me to.*$",
                r"\bis there anything else.*$",
                r"\blet me know if.*$",
                r"\bfeel free to.*$",
            ]
            for t in trailing:
                cleaned = re.sub(t, "", cleaned, flags=re.IGNORECASE)
            return cleaned.strip()

        reply_cleaned = apply_persona_filters(reply)

        # Wait for any background episodic memory extraction queues
        wait_for_background_jobs()
        close_connections()

        # Output the response as JSON back to stdout
        output = {
            "status": "success",
            "reply": reply_cleaned
        }
        _original_stdout.write(json.dumps(output))

    except Exception as e:
        import traceback
        traceback.print_exc(file=sys.stderr)
        output = {
            "status": "error",
            "error": str(e)
        }
        _original_stdout.write(json.dumps(output))

if __name__ == "__main__":
    run_bridge()
