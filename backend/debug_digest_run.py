# backend/debug_digest_run.py
"""
Interactive step-by-step debugger for Flow 3 (Personalized Digest Pipeline).
Uses LangGraph's .astream() to pause at every node, allowing you to inspect:
1. pgvector candidate retrieval
2. Dislike filtering & semantic ranking
3. LLM personalized intro & 'Why it matters' generation
4. Final email rendering & Brevo delivery
"""

import argparse
import asyncio
from typing import Optional

from graphs.digest_graph import digest_graph
from graphs.state import UserDigestState
from storage.db import SessionLocal as get_session
from storage.models import UserProfile, UserEmbedding


def get_first_active_user(target_email: Optional[str] = None):
    """Fetches an active embedded user from PostgreSQL."""
    with get_session() as session:
        query = session.query(UserProfile).filter(
            UserProfile.is_active == True,
            UserProfile.embedding_status == "embedded",
        )
        if target_email:
            query = query.filter(UserProfile.email == target_email)

        user = query.first()
        if not user:
            return None, None

        user_emb = (
            session.query(UserEmbedding)
            .filter(UserEmbedding.user_id == user.id)
            .order_by(UserEmbedding.created_at.desc())
            .first()
        )
        if not user_emb:
            return user, None

        return user, user_emb.embedding.tolist()


async def debug_digest(target_email: Optional[str] = None):
    print("\n" + "=" * 70)
    print("🚀 STARTING FLOW 3 (DIGEST PIPELINE) IN DEBUG MODE")
    print("=" * 70)

    user, embedding = get_first_active_user(target_email)

    if not user:
        print("\n❌ No active embedded user found in the database.")
        print("Tip: Run Flow 1 first, or check user_profiles table in your DB.")
        return

    if not embedding:
        print(f"\n❌ User '{user.email}' found, but no vector embedding exists in user_embeddings.")
        return

    print(f"\n👤 Target User for Digest:")
    print(f"  • Name:             {user.name or 'Anonymous'}")
    print(f"  • Email:            {user.email}")
    print(f"  • Liked Tags:       {user.liked_tags or []}")
    print(f"  • Disliked Tags:    {user.disliked_tags or []}")
    print(f"  • Interests:        {user.custom_interests or 'None'}")
    print(f"  • Include Insights: {user.include_why_matters}")
    print(f"  • Embedding Dims:   {len(embedding)}")

    # Initial State for LangGraph
    initial_state: UserDigestState = {
        "user_id": str(user.id),
        "user_name": user.name,
        "user_email": user.email,
        "user_embedding": embedding,
        "liked_tags": user.liked_tags or [],
        "disliked_tags": user.disliked_tags or [],
        "include_why_matters": bool(user.include_why_matters),
        "candidates": [],
        "ranked_items": [],
    }

    input("\n👉 Press [Enter] to start Node 1 (pgvector candidate retrieval)...")

    step_number = 1
    async for output in digest_graph.astream(initial_state):
        for node_name, node_state in output.items():
            print(f"\n" + "-" * 70)
            print(f"📍 [STEP {step_number}] COMPLETED NODE: {node_name}")
            print("-" * 70)

            # Node 1: Retrieval
            if node_name == "retrieve_candidates_node":
                candidates = node_state.get("candidates", [])
                print(f"🔍 Found {len(candidates)} candidate items via pgvector cosine distance.")
                for i, row in enumerate(candidates[:5], 1):
                    dist = getattr(row, "distance", None) or (row.get("distance") if isinstance(row, dict) else "N/A")
                    dist_str = f"{dist:.4f}" if isinstance(dist, float) else str(dist)
                    title = getattr(row, "title", None) or (row.get("title") if isinstance(row, dict) else "N/A")
                    print(f"   [{i}] (dist: {dist_str}) {title[:60]}")

            # Node 2: Filter & Rank
            elif node_name == "filter_and_rank_node":
                ranked = node_state.get("ranked_items", [])
                print(f"⚖️ Ranked Top {len(ranked)} items (after filtering disliked tags & scoring popularity):")
                for i, item in enumerate(ranked, 1):
                    score = item.get("final_score", 0)
                    title = item.get("title") or item.get("external_id")
                    tech = item.get("tech_stack", [])
                    print(f"   [{i}] Score: {score:.3f} | {title[:50]} | Tech: {tech[:3]}")

            # Node 3: LLM Digest Generation
            elif node_name == "llm_digest_node":
                digest = node_state.get("digest", {})
                print(f"🧠 ChatGroq generated personalized digest:")
                print(f"   • Intro: \"{digest.get('intro', '')}\"")
                print(f"   • Personalized 'Why it matters' one-liners:")
                for it in digest.get("items", []):
                    print(f"     👉 [{it.get('external_id')}]: {it.get('one_liner')}")

            # Node 3 (Fallback/Zero-cost): Templated Digest
            elif node_name == "templated_digest_node":
                digest = node_state.get("digest", {})
                print(f"📄 Templated Digest generated (zero LLM cost):")
                print(f"   • Intro: {digest.get('intro')}")
                for it in digest.get("items", []):
                    print(f"     👉 {it.get('one_liner')}")

            # Node 4: Email Delivery
            elif node_name == "send_email_node":
                sent = node_state.get("email_sent", False)
                err = node_state.get("error")
                html = node_state.get("email_html", "")
                if sent:
                    print(f"📧 Email successfully delivered via Brevo to: {user.email}")
                    print(f"   • HTML content size: {len(html)} bytes")
                else:
                    print(f"⚠️ Email was not sent. Reason: {err}")

            # Node 4 (Alternative): Skipped Delivery
            elif node_name == "skip_delivery_node":
                print(f"⏭️ Delivery skipped: {node_state.get('error', 'No candidate items matched user tastes')}")

            else:
                for k, v in node_state.items():
                    print(f"  • {k}: {v}")

            step_number += 1
            input("\n👉 Press [Enter] to proceed to next node...")

    print("\n" + "=" * 70)
    print("🎉 FLOW 3 DEBUG RUN FINISHED!")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Debug Flow 3 (Digest Pipeline) step-by-step")
    parser.add_argument("--email", type=str, default=None, help="Target user email (defaults to first active user in DB)")
    args = parser.parse_args()

    asyncio.run(debug_digest(target_email=args.email))

