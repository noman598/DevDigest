"""
services/llm/limiter.py
In-app budget and token rate limiter.
Ensures the app does not exceed daily or monthly LLM token budgets,
and provides a LangChain callback to record token usage to PostgreSQL.
"""
from datetime import datetime, timezone
import time
from typing import Any, Dict, List, Optional
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult
from sqlalchemy import func

from config import config
from storage.db import SessionLocal
from storage.models import LLMUsageLog
from utils.logger import log

# Default fallback budgets if not explicitly defined in config / .env
DEFAULT_DAILY_TOKEN_BUDGET = 1_000_000       # ~1M tokens / day
DEFAULT_MONTHLY_TOKEN_BUDGET = 25_000_000    # ~25M tokens / month
DEFAULT_USER_DAILY_LIMIT = 50_000            # ~50k tokens / user / day


def get_tokens_used_since(session, since: datetime, user_id: Optional[int] = None) -> int:
    """Calculates total tokens consumed by successful LLM operations since a given datetime."""
    query = session.query(func.sum(LLMUsageLog.total_tokens)).filter(
        LLMUsageLog.created_at >= since,
        LLMUsageLog.status == "success",
    )
    if user_id is not None:
        query = query.filter(LLMUsageLog.user_id == user_id)
    return query.scalar() or 0


def record_llm_usage(
    session,
    provider: str,
    model: str,
    operation: str,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    latency_ms: Optional[int] = None,
    status: str = "success",
    error_message: Optional[str] = None,
    content_item_id: Optional[Any] = None,
    user_id: Optional[Any] = None,
) -> None:
    """Logs LLM token usage to the database. Never raises on failure."""
    try:
        # Safeguard: LLMUsageLog integer foreign key columns ignore UUID string inputs
        cid = content_item_id if isinstance(content_item_id, int) else None
        uid = user_id if isinstance(user_id, int) else None

        session.add(
            LLMUsageLog(
                provider=provider,
                model=model,
                operation=operation,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
                latency_ms=latency_ms,
                status=status,
                error_message=error_message,
                content_item_id=cid,
                user_id=uid,
                created_at=datetime.now(),
            )
        )
        session.commit()
    except Exception as e:
        session.rollback()
        log.error("llm_usage_log_failed", error=str(e))


def check_daily_budget(session) -> bool:
    """Checks whether the application has exceeded its daily token budget."""
    daily_budget = getattr(config, "DAILY_TOKEN_BUDGET", DEFAULT_DAILY_TOKEN_BUDGET)
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    used = get_tokens_used_since(session, today_start)
    if used >= daily_budget:
        log.warning("llm.daily_budget_exceeded", used=used, budget=daily_budget)
        return False
    return True


def check_monthly_budget(session) -> bool:
    """Checks whether the application has exceeded its monthly token budget."""
    monthly_budget = getattr(config, "MONTHLY_TOKEN_BUDGET", DEFAULT_MONTHLY_TOKEN_BUDGET)
    month_start = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    used = get_tokens_used_since(session, month_start)
    if used >= monthly_budget:
        log.warning("llm.monthly_budget_exceeded", used=used, budget=monthly_budget)
        return False
    return True


def check_user_daily_limit(session, user_id: int) -> bool:
    """Checks whether a specific user has exceeded their daily quota."""
    user_limit = getattr(config, "PER_USER_DAILY_TOKEN_LIMIT", DEFAULT_USER_DAILY_LIMIT)
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    used = get_tokens_used_since(session, today_start, user_id=user_id)
    if used >= user_limit:
        log.warning("llm.user_daily_limit_exceeded", user_id=user_id, used=used, limit=user_limit)
        return False
    return True


def is_within_budget(session, user_id: Optional[int] = None) -> bool:
    """
    Master budget gatekeeper.
    Call this before executing expensive batch LLM operations.
    """
    if not check_daily_budget(session):
        return False
    if not check_monthly_budget(session):
        return False
    if user_id is not None and not check_user_daily_limit(session, user_id):
        return False
    return True


class BudgetUsageCallback(BaseCallbackHandler):
    """
    LangChain callback handler that records token usage to PostgreSQL
    for budget tracking and cost monitoring.
    """

    def __init__(
        self,
        operation: str,
        provider: str = "groq",
        content_item_id: Optional[Any] = None,
        user_id: Optional[Any] = None,
    ):
        super().__init__()
        self.operation = operation
        self.provider = provider
        self.content_item_id = content_item_id
        self.user_id = user_id
        self._start_time: float = 0.0

    def on_llm_start(
        self,
        serialized: Dict[str, Any],
        prompts: List[str],
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        self._start_time = time.monotonic()

    def on_llm_end(
        self,
        response: LLMResult,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        latency_ms = int((time.monotonic() - self._start_time) * 1000)
        prompt_tokens = 0
        completion_tokens = 0
        model_name = "groq"

        if response.llm_output:
            token_usage = response.llm_output.get("token_usage", {})
            prompt_tokens = token_usage.get("prompt_tokens", 0)
            completion_tokens = token_usage.get("completion_tokens", 0)
            model_name = response.llm_output.get("model_name", "groq")

        if not prompt_tokens and response.generations and response.generations[0]:
            gen_info = response.generations[0][0].generation_info or {}
            usage = gen_info.get("usage", {})
            prompt_tokens = usage.get("prompt_tokens", 0)
            completion_tokens = usage.get("completion_tokens", 0)

        with SessionLocal() as session:
            record_llm_usage(
                session=session,
                provider=self.provider,
                model=model_name,
                operation=self.operation,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                latency_ms=latency_ms,
                status="success",
                content_item_id=self.content_item_id,
                user_id=self.user_id,
            )

    def on_llm_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        latency_ms = int((time.monotonic() - self._start_time) * 1000)
        with SessionLocal() as session:
            record_llm_usage(
                session=session,
                provider=self.provider,
                model="groq",
                operation=self.operation,
                latency_ms=latency_ms,
                status="failed",
                error_message=str(error),
                content_item_id=self.content_item_id,
                user_id=self.user_id,
            )
