# backend/tools/market_tools.py
from typing import Any, Dict, List, Optional
import httpx
from langchain_core.tools import tool

from config import config
from utils.logger import log

OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"
YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart"

# Key models to track for token market shifts
TRACKED_MODELS = {
    "deepseek/deepseek-chat": "DeepSeek V3",
    "meta-llama/llama-3.3-70b-instruct": "Llama 3.3 70B",
    "anthropic/claude-3.5-sonnet": "Claude 3.5 Sonnet",
    "openai/gpt-4o-mini": "GPT-4o Mini",
}

# Major AI/Tech stocks to track
TRACKED_STOCKS = ["NVDA", "MSFT", "GOOGL"]


def fetch_token_pricing() -> Dict[str, str]:
    """Fetches real-time model token pricing per 1M tokens from OpenRouter public API."""
    pricing: Dict[str, str] = {}
    try:
        with httpx.Client(timeout=6.0) as client:
            resp = client.get(OPENROUTER_MODELS_URL)
            if resp.status_code == 200:
                data = resp.json().get("data", [])
                by_id = {m.get("id"): m for m in data if m.get("id")}
                for model_id, label in TRACKED_MODELS.items():
                    if model_id in by_id:
                        p_info = by_id[model_id].get("pricing", {})
                        # pricing in OpenRouter is per token, multiply by 1,000,000 for per 1M tokens
                        try:
                            prompt_1m = float(p_info.get("prompt", 0)) * 1_000_000
                            comp_1m = float(p_info.get("completion", 0)) * 1_000_000
                            pricing[label] = f"${prompt_1m:.2f} / ${comp_1m:.2f} (in/out)"
                        except Exception:
                            continue
    except Exception as e:
        log.debug("market_tools.token_pricing_failed", error=str(e))

    # Fallback standard pricing if external call throttled
    if not pricing:
        pricing = {
            "DeepSeek V3": "$0.14 / $0.28 (in/out)",
            "Llama 3.3 70B": "$0.12 / $0.30 (in/out)",
            "Claude 3.5 Sonnet": "$3.00 / $15.00 (in/out)",
            "GPT-4o Mini": "$0.15 / $0.60 (in/out)",
        }
    return pricing


def fetch_stock_quotes() -> Dict[str, str]:
    """Fetches 24h stock movement for key AI leaders via Yahoo public chart API."""
    quotes: Dict[str, str] = {}
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

    try:
        with httpx.Client(timeout=5.0, headers=headers) as client:
            for sym in TRACKED_STOCKS:
                try:
                    url = f"{YAHOO_CHART_URL}/{sym}?interval=1d&range=2d"
                    resp = client.get(url)
                    if resp.status_code == 200:
                        res = resp.json().get("chart", {}).get("result", [])
                        if res:
                            meta = res[0].get("meta", {})
                            regular_price = meta.get("regularMarketPrice")
                            prev_close = meta.get("previousClose") or meta.get("chartPreviousClose")
                            if regular_price and prev_close:
                                pct_change = ((regular_price - prev_close) / prev_close) * 100
                                sign = "+" if pct_change >= 0 else ""
                                quotes[sym] = f"${regular_price:.2f} ({sign}{pct_change:.1f}%)"
                except Exception:
                    continue
    except Exception as e:
        log.debug("market_tools.stocks_failed", error=str(e))

    return quotes


@tool
def get_ai_market_pulse(include_stocks: bool = True) -> str:
    """
    Fetches the latest real-time AI & Tech Market Pulse:
    1. Live token pricing per 1M tokens for leading AI models (DeepSeek, Llama 3.3, Claude, GPT-4o).
    2. 24h market movements for key AI hardware & cloud leaders (NVDA, MSFT, GOOGL).
    Call this tool when curating digests for users with interests in 'AI/ML', 'LLMs', or 'Startups'
    to provide an executive market snapshot.

    Args:
        include_stocks: Whether to include tech stock tickers alongside model token pricing.

    Returns:
        A concise 2-line summary of live AI token pricing and stock movements (~70 tokens).
    """
    tokens = fetch_token_pricing()
    token_str = " | ".join(f"{name}: {cost}" for name, cost in list(tokens.items())[:3])

    lines = [f"• Model Token Rates (per 1M tokens): {token_str}"]

    if include_stocks:
        stocks = fetch_stock_quotes()
        if stocks:
            stock_str = " | ".join(f"{sym}: {chg}" for sym, chg in stocks.items())
            lines.append(f"• AI Tech Barometer: {stock_str}")

    return "📊 Today's AI & Tech Pulse:\n" + "\n".join(lines)

