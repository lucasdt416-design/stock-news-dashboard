"""Lightweight Quick-Lookup Engine for Non-Watchlist Tickers.

Directly queries Finnhub's /quote, /company-news, and /search endpoints and parses
pricing + recent headlines without heavyweight scoring, classification, or AI processing.
Supports both stock tickers (e.g. NFLX, TSM) and company names (e.g. Netflix, Spotify).
"""

from datetime import datetime, timedelta
import json
import logging
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

logger = logging.getLogger("quick_lookup")

FINNHUB_QUOTE_URL = "https://finnhub.io/api/v1/quote"
FINNHUB_NEWS_URL = "https://finnhub.io/api/v1/company-news"
FINNHUB_SEARCH_URL = "https://finnhub.io/api/v1/search"


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
    """Fetch live quote and 2-3 headlines for any ticker or company name from Finnhub."""
    raw_query = (ticker or "").strip()
    if not raw_query:
        return {
            "found": False,
            "symbol": raw_query,
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
            "symbol": raw_query.upper(),
            "error": "FINNHUB_API_KEY environment variable not configured",
        }

    is_direct_ticker_candidate = bool(re.match(r"^[A-Za-z0-9.\-]{1,6}$", raw_query))
    resolved_symbol = raw_query.upper()
    resolved_company_name = None
    resolved_from = None
    need_symbol_search = not is_direct_ticker_candidate

    def _fetch_quote_and_news(sym: str) -> tuple:
        q_data = {}
        n_items = []
        # Fetch Quote
        q_url = f"{FINNHUB_QUOTE_URL}?symbol={urllib.parse.quote(sym)}&token={urllib.parse.quote(token)}"
        try:
            req = urllib.request.Request(
                q_url,
                headers={"User-Agent": "StockNewsDashboard-Lookup/1.0", "Accept": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                q_data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 401:
                raise PermissionError("Unauthorized: Invalid FINNHUB_API_KEY")
            logger.warning("Finnhub quote HTTP error for %s: %s", sym, e)
        except Exception as e:
            logger.warning("Finnhub quote network error for %s: %s", sym, e)

        # Fetch News
        now_dt = datetime.utcnow()
        to_date_str = now_dt.strftime("%Y-%m-%d")
        from_date_str = (now_dt - timedelta(days=7)).strftime("%Y-%m-%d")
        n_url = f"{FINNHUB_NEWS_URL}?symbol={urllib.parse.quote(sym)}&from={from_date_str}&to={to_date_str}&token={urllib.parse.quote(token)}"
        try:
            req = urllib.request.Request(
                n_url,
                headers={"User-Agent": "StockNewsDashboard-Lookup/1.0", "Accept": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw_n = json.loads(resp.read().decode("utf-8"))
                if isinstance(raw_n, list):
                    n_items = raw_n
        except urllib.error.HTTPError as e:
            if e.code == 401:
                raise PermissionError("Unauthorized: Invalid FINNHUB_API_KEY")
            logger.warning("Finnhub news HTTP error for %s: %s", sym, e)
        except Exception as e:
            logger.warning("Finnhub news network error for %s: %s", sym, e)

        return q_data, n_items

    quote_data: Dict[str, Any] = {}
    news_items: List[Dict[str, Any]] = []

    try:
        if is_direct_ticker_candidate:
            quote_data, news_items = _fetch_quote_and_news(resolved_symbol)
            has_valid_price = bool(
                quote_data and (quote_data.get("c") or quote_data.get("pc") or quote_data.get("h"))
            )
            has_news = bool(news_items)
            if not has_valid_price and not has_news:
                need_symbol_search = True

        if need_symbol_search:
            s_url = f"{FINNHUB_SEARCH_URL}?q={urllib.parse.quote(raw_query)}&token={urllib.parse.quote(token)}"
            try:
                req = urllib.request.Request(
                    s_url,
                    headers={"User-Agent": "StockNewsDashboard-Lookup/1.0", "Accept": "application/json"},
                )
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    s_data = json.loads(resp.read().decode("utf-8"))
                    results = s_data.get("result", []) if isinstance(s_data, dict) else []
                    if results:
                        # Priority matching
                        best = None
                        for r in results:
                            sym = r.get("symbol", "")
                            if sym.upper() == raw_query.upper():
                                best = r
                                break
                        if not best:
                            for r in results:
                                if r.get("type") == "Common Stock" and "." not in r.get("symbol", ""):
                                    best = r
                                    break
                        if not best:
                            for r in results:
                                if r.get("type") in ("Common Stock", "EQS") and r.get("symbol"):
                                    best = r
                                    break
                        if not best:
                            best = results[0]

                        if best and best.get("symbol"):
                            resolved_symbol = best["symbol"].upper()
                            resolved_company_name = best.get("description")
                            resolved_from = raw_query
                            quote_data, news_items = _fetch_quote_and_news(resolved_symbol)
            except urllib.error.HTTPError as e:
                if e.code == 401:
                    return {"found": False, "symbol": resolved_symbol, "error": "Unauthorized: Invalid FINNHUB_API_KEY"}
                logger.warning("Finnhub search HTTP error for %s: %s", raw_query, e)
            except Exception as e:
                logger.warning("Finnhub search network error for %s: %s", raw_query, e)

    except PermissionError as e:
        return {"found": False, "symbol": resolved_symbol, "error": str(e)}

    # Validate if valid price or news exists
    has_valid_price = bool(
        quote_data and (quote_data.get("c") or quote_data.get("pc") or quote_data.get("h"))
    )
    has_news = bool(news_items)

    if not has_valid_price and not has_news:
        return {
            "found": False,
            "symbol": resolved_symbol or raw_query.upper(),
            "resolved_from": resolved_from,
            "message": f'No quote or news found on Finnhub for "{raw_query}".',
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

    now = datetime.utcnow()
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
        "symbol": resolved_symbol,
        "company_name": resolved_company_name,
        "resolved_from": resolved_from,
        "price": price_dict,
        "headlines": top_headlines,
        "queried_at": now.isoformat() + "Z",
    }
