"""Lightweight Quick-Lookup Engine for Non-Watchlist Tickers.

Directly queries Finnhub's /quote and /company-news endpoints and parses
pricing + recent headlines without heavyweight scoring, classification, or AI processing.
"""

from datetime import datetime, timedelta
import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

logger = logging.getLogger("quick_lookup")

FINNHUB_QUOTE_URL = "https://finnhub.io/api/v1/quote"
FINNHUB_NEWS_URL = "https://finnhub.io/api/v1/company-news"


def format_time_ago(unix_timestamp: Optional[int]) -> str:
    """Format Unix timestamp into human-readable relative time (e.g. '2h ago')."""
    if not unix_timestamp:
        return ""
    diff_sec = int(datetime.utcnow().timestamp() - unix_timestamp)
    if diff_sec < 60:
        return "Just now"
    if diff_sec < 3600:
        return f"{diff_sec // 60}m ago"
    if diff_sec < 86400:
        return f"{diff_sec // 3600}h ago"
    return f"{diff_sec // 86400}d ago"


def fetch_ticker_quick_lookup(
    ticker: str,
    api_key: Optional[str] = None,
    timeout: int = 8,
) -> Dict[str, Any]:
    """Fetch live quote and 2-3 headlines for any ticker from Finnhub."""
    symbol = (ticker or "").strip().upper()
    if not symbol:
        return {
            "found": False,
            "symbol": symbol,
            "error": "Missing ticker parameter",
        }

    if api_key is not None:
        token = api_key.strip()
    else:
        token = os.environ.get("FINNHUB_API_KEY", "").strip()
        if not token:
            env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
            if os.path.exists(env_path):
                with open(env_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#") and "FINNHUB_API_KEY=" in line:
                            token = line.split("=", 1)[1].strip().strip("'\"")
                            break

    if not token:
        logger.warning("FINNHUB_API_KEY not configured for quick-lookup.")
        return {
            "found": False,
            "symbol": symbol,
            "error": "FINNHUB_API_KEY environment variable not configured",
        }

    # 1. Fetch Quote
    quote_data: Dict[str, Any] = {}
    quote_url = f"{FINNHUB_QUOTE_URL}?symbol={urllib.parse.quote(symbol)}&token={urllib.parse.quote(token)}"
    try:
        req = urllib.request.Request(
            quote_url,
            headers={"User-Agent": "StockNewsDashboard-Lookup/1.0", "Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            quote_data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 401:
            return {"found": False, "symbol": symbol, "error": "Unauthorized: Invalid FINNHUB_API_KEY"}
        logger.warning("Finnhub quote HTTP error for %s: %s", symbol, e)
    except Exception as e:
        logger.warning("Finnhub quote network error for %s: %s", symbol, e)

    # 2. Fetch Recent Headlines (Past 7 days)
    news_items: List[Dict[str, Any]] = []
    now = datetime.utcnow()
    to_date = now.strftime("%Y-%m-%d")
    from_date = (now - timedelta(days=7)).strftime("%Y-%m-%d")
    news_url = f"{FINNHUB_NEWS_URL}?symbol={urllib.parse.quote(symbol)}&from={from_date}&to={to_date}&token={urllib.parse.quote(token)}"
    try:
        req = urllib.request.Request(
            news_url,
            headers={"User-Agent": "StockNewsDashboard-Lookup/1.0", "Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw_news = json.loads(resp.read().decode("utf-8"))
            if isinstance(raw_news, list):
                news_items = raw_news
    except Exception as e:
        logger.warning("Finnhub news network error for %s: %s", symbol, e)

    # Validate if valid price exists
    has_valid_price = bool(
        quote_data and (quote_data.get("c") or quote_data.get("pc") or quote_data.get("h"))
    )
    has_news = bool(news_items)

    if not has_valid_price and not has_news:
        return {
            "found": False,
            "symbol": symbol,
            "message": f'No quote or news found on Finnhub for symbol "{symbol}".',
        }

    # Format 2-3 recent headlines
    top_headlines = []
    for item in news_items[:3]:
        if not isinstance(item, dict):
            continue
        headline = (item.get("headline") or "").strip()
        url = item.get("url") or ""
        if headline and url:
            dt = item.get("datetime")
            top_headlines.append({
                "headline": headline,
                "url": url,
                "source": item.get("source") or "Financial Press",
                "datetime": dt,
                "time_ago": format_time_ago(dt),
                "summary": (item.get("summary") or "").strip(),
            })

    price_dict = None
    if has_valid_price:
        price_dict = {
            "current": float(quote_data.get("c", 0.0) or 0.0),
            "change": float(quote_data.get("d", 0.0) or 0.0),
            "change_pct": float(quote_data.get("dp", 0.0) or 0.0),
            "high": float(quote_data.get("h", 0.0) or 0.0),
            "low": float(quote_data.get("l", 0.0) or 0.0),
            "open": float(quote_data.get("o", 0.0) or 0.0),
            "prev_close": float(quote_data.get("pc", 0.0) or 0.0),
            "timestamp": int(quote_data.get("t") or int(now.timestamp())),
        }

    return {
        "found": True,
        "symbol": symbol,
        "price": price_dict,
        "headlines": top_headlines,
        "queried_at": now.isoformat() + "Z",
    }
