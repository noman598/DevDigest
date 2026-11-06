# services/digest_generator.py
from typing import Any, List, Tuple
from langchain_core.prompts import ChatPromptTemplate
from langchain_groq import ChatGroq
from pydantic import BaseModel, Field

from config import config
from services.llm import BudgetUsageCallback
from storage.models import UserProfile

DIGEST_MODEL = "qwen/qwen3.8-27b"


class DigestItem(BaseModel):
    external_id: str = Field(description="content external_id, copied exactly as given")
    one_liner: str = Field(description="punchy 1-sentence explanation of why this matters specifically to this user")


class UserDigest(BaseModel):
    user_id: str = Field(description="the user_id copied exactly as given")
    intro: str = Field(description="1-2 sentence personalized intro for this user's email")
    items: List[DigestItem]


class BatchDigestResult(BaseModel):
    digests: List[UserDigest]


_DIGEST_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        "You are an expert developer news curator. For each user provided below, write a short personalized "
        "intro (1-2 sentences) and a punchy one-line 'why this matters to you' for each of their matched items. "
        "Return one entry per user_id listed.",
    ),
    ("human", "{users_block}"),
])


def _get_digest_chain():
    callbacks = [
        BudgetUsageCallback(
            operation="digest_generation",
            provider="groq",
        )
    ]
    llm = ChatGroq(
        model=DIGEST_MODEL,
        api_key=config.GROQ_API_KEY,
        temperature=0.3,
        max_tokens=4096,
        callbacks=callbacks,
    )
    return _DIGEST_PROMPT | llm.with_structured_output(BatchDigestResult)


async def generate_batch_digest(batch: List[Tuple[UserProfile, List[dict]]]) -> dict[str, dict]:
    """Generates personalized batch digests using LangChain ChatGroq."""
    users_block = ""
    for user, ranked in batch:
        items_text = "\n".join(
            f"  - [{item['external_id']}] {item['title']}: {item['summary']}"
            for item in ranked
        )
        users_block += f"""
User ID: {user.id}
Interests: {', '.join(user.liked_tags or [])}. {user.custom_interests or ''}
Matched items:
{items_text}
---
"""

    chain = _get_digest_chain()
    result: BatchDigestResult = await chain.ainvoke({"users_block": users_block})

    return {
        d.user_id: {
            "intro": d.intro,
            "items": [{"external_id": i.external_id, "one_liner": i.one_liner} for i in d.items],
        }
        for d in result.digests
    }
