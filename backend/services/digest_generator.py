# services/digest_generator.py
import instructor
from groq import Groq
from pydantic import BaseModel, Field

from config import config
from storage.models import UserProfile

_client = instructor.from_groq(Groq(api_key=config.GROQ_API_KEY), mode=instructor.Mode.JSON)
DIGEST_MODEL = "llama-3.3-70b-versatile"


class DigestItem(BaseModel):
    external_id: str = Field(description="repo external_id, copied exactly as given")
    one_liner: str = Field(description="punchy sentence on why this matters to this specific user")


class UserDigest(BaseModel):
    user_id: str = Field(description="the user_id copied exactly as given")
    intro: str = Field(description="1-2 sentence personalized intro for this user's email")
    items: list[DigestItem]


class BatchDigestResult(BaseModel):
    digests: list[UserDigest]


def generate_batch_digest(batch: list[tuple[UserProfile, list[dict]]]) -> dict[str, dict]:

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
"""

    prompt = f"""For each user below, write a short personalized intro (1-2 sentences) and a
punchy one-line "why this matters to you" for each of their matched items.

{users_block}

Return one entry per user_id listed above."""

    result = _client.chat.completions.create(
        model=DIGEST_MODEL,
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
        response_model=BatchDigestResult,
    )

    return {
        d.user_id: {"intro": d.intro, "items": [{"external_id": i.external_id, "one_liner": i.one_liner} for i in d.items]}
        for d in result.digests
    }