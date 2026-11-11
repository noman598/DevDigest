# backend/tests/test_curator.py
from datetime import datetime, timedelta
import uuid

from tools.cve_tools import check_cve_vulnerabilities, query_osv_vulnerabilities
from tools.market_tools import get_ai_market_pulse, fetch_token_pricing, fetch_stock_quotes
from storage.models import UserMemory


def test_tools_definitions():
    assert check_cve_vulnerabilities.name == "check_cve_vulnerabilities"
    assert get_ai_market_pulse.name == "get_ai_market_pulse"


def test_token_pricing_fallback():
    # Verify token pricing fallback returns standard rates if network is unavailable
    prices = fetch_token_pricing()
    assert isinstance(prices, dict)
    assert "DeepSeek V3" in prices or "Claude 3.5 Sonnet" in prices


def test_user_memory_structure():
    uid = uuid.uuid4()
    mem = UserMemory(
        id=uuid.uuid4(),
        user_id=uid,
        delivered_history=[
            {"external_id": "fastapi/fastapi", "title": "FastAPI", "delivered_at": datetime.now().isoformat()}
        ],
        recent_topics={"Python": 2, "AI/ML": 1},
        agent_notes="User is exploring API frameworks.",
    )
    assert mem.user_id == uid
    assert len(mem.delivered_history) == 1
    assert mem.recent_topics["Python"] == 2

