# backend/debug_run.py
import asyncio
from graphs.content_graph import content_graph

async def main():
    print("\n🚀 Starting LangGraph Content Pipeline in DEBUG Mode...\n")
    
    # 1. Define initial state (test with hacker_news or all)
    initial_state = {
        "source_name": "ai_news_rss",
        "raw_items": [],
        "new_items_count": 0,
        "enrich_stats": {},
        "embed_stats": {},
        "status": "pending",
    }

    # 2. Stream step-by-step through every node
    async for output in content_graph.astream(initial_state):
        for node_name, node_state in output.items():
            print(f"\n{'='*60}")
            print(f"📍 COMPLETED NODE: [{node_name}]")
            print(f"{'='*60}")
            
            # Print what this specific node produced
            for key, val in node_state.items():
                if key == "raw_items":
                    print(f"  • {key}: {len(val)} items scraped")
                    if val:
                        print(f"    👉 First item: {val[0].title}")
                else:
                    print(f"  • {key}: {val}")
            
            # Pause between each step so you can inspect!
            input("\n👉 Press [Enter] to execute the next node...")

if __name__ == "__main__":
    asyncio.run(main())