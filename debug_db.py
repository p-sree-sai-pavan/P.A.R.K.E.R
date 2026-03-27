import os
import asyncio
from database import create_store
from config import DEFAULT_USER_ID
from memory.utils import semantic_search
from memory.episodes import load_relevant_episodes

def main():
    store = create_store()
    namespace = ("user", DEFAULT_USER_ID, "mem", "chat")
    
    query = "list all the dates where we have conversation"
    print(f"Executing search for: '{query}'")
    hits = semantic_search(store, namespace, query=query, limit=10)
    print(f"Found {len(hits)} direct hits.")
    for h in hits:
        print(f"HIT: {h.key} | score: {getattr(h, 'score', 'N/A')}")
        
    print("-- Testing load_relevant_episodes --")
    episodes = load_relevant_episodes(store, DEFAULT_USER_ID, query)
    print(f"load_relevant_episodes returned {len(episodes)} items.")
    for e in episodes:
        print(f"EPISODE: {e.key}")

if __name__ == "__main__":
    main()
