"""Finnhub Company News API Collector.

Fetches third-party journalistic coverage (Reuters, Bloomberg, CNBC, MarketWatch,
industry press) mentioning watchlist companies via Finnhub's /company-news endpoint.
This captures independent external events (lawsuits, product recalls, plane crashes,
analyst rating changes) that are not self-reported in SEC filings or Company IR releases.
"""

from datetime import datetime, timedelta, timezone
import json
import logging
import os
import time
from typing import Any, Dict, List, Optional
import urllib.error
import urllib.parse
import urllib.request

logger = logging.getLogger(__name__)

DEFAULT_USER_AGENT = os.environ.get(
    "FINNHUB_USER_AGENT",
    "StockNewsDashboard/1.0 (contact: admin@stocknewsdashboard.local)"
)
FINNHUB_NEWS_URL = "https://finnhub.io/api/v1/company-news"


def fetch_company_news_finnhub(
    symbol: str,
    api_key: str,
    from_date: str,
    to_date: str,
    timeout: int = 10,
    max_items: int = 30,
) -> List[Dict[str, Any]]:
    """Fetch recent news articles for a single stock ticker from Finnhub API."""
    if not api_key:
        return []

    params = {
        "symbol": symbol.upper().strip(),
        "from": from_date,
        "to": to_date,
        "token": api_key.strip(),
    }
    url = f"{FINNHUB_NEWS_URL}?{urllib.parse.urlencode(params)}"

    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": DEFAULT_USER_AGENT,
            "Accept": "application/json",
            "X-Finnhub-Token": api_key.strip(),
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            if response.status != 200:
                logger.warning(
                    "Finnhub API returned status %d for %s", response.status, symbol
                )
                return []
            raw_data = response.read().decode("utf-8")
            data = json.loads(raw_data)

            if not isinstance(data, list):
                logger.warning("Unexpected Finnhub response format for %s: %s", symbol, type(data))
                return []

            items: List[Dict[str, Any]] = []
            for entry in data[:max_items]:
                article_id = entry.get("id") or ""
                headline = (entry.get("headline") or "").strip()
                summary = (entry.get("summary") or "").strip()
                article_url = (entry.get("url") or "").strip()
                publisher = (entry.get("source") or "").strip() or "News Media"
                image_url = entry.get("image") or ""
                category = entry.get("category") or "company news"

                # Parse Unix timestamp
                dt_raw = entry.get("datetime")
                pub_date = ""
                pub_time = ""
                if dt_raw:
                    try:
                        dt = datetime.fromtimestamp(int(dt_raw), tz=timezone.utc)
                        pub_date = dt.strftime("%Y-%m-%d")
                        pub_time = dt.strftime("%Y-%m-%dT%H:%M:%SZ")
                    except Exception:
                        pub_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                        pub_time = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

                if not headline or not article_url:
                    continue

                items.append({
                    "ticker": symbol.upper(),
                    "headline": headline,
                    "summary": summary,
                    "url": article_url,
                    "image_url": image_url,
                    "published_date": pub_date,
                    "published_time": pub_time,
                    "raw_id": str(article_id),
                    "source": "news_media",
                    "source_label": "News Media",
                    "source_type": "press",
                    "publisher": publisher,
                    "form_or_type": publisher if publisher else "NEWS_ARTICLE",
                    "api_category": category,
                })

            return items

    except urllib.error.HTTPError as e:
        if e.code == 401:
            logger.error("Finnhub API 401 Unauthorized: Invalid FINNHUB_API_KEY")
        elif e.code == 429:
            logger.warning("Finnhub API 429 Rate Limit exceeded for %s", symbol)
        else:
            logger.warning("Finnhub HTTP error %d for %s: %s", e.code, symbol, e.reason)
        return []
    except urllib.error.URLError as e:
        logger.warning("Finnhub network connection error for %s: %s", symbol, e.reason)
        return []
    except Exception as e:
        logger.warning("Unexpected error fetching Finnhub news for %s: %s", symbol, e)
        return []


def collect_finnhub_news(
    watchlist: List[Dict[str, Any]],
    days_back: int = 14,
    max_items_per_ticker: int = 25,
    delay_seconds: float = 0.35,
    api_key: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Collect 3rd-party journalism news for all tickers in watchlist using Finnhub."""
    token = api_key or os.environ.get("FINNHUB_API_KEY", "").strip()

    if not token:
        logger.info(
            "FINNHUB_API_KEY environment variable not configured. "
            "Skipping live Finnhub news collection (SEC EDGAR & Company IR feeds active)."
        )
        return []

    now_utc = datetime.now(timezone.utc)
    to_date = now_utc.strftime("%Y-%m-%d")
    from_date = (now_utc - timedelta(days=days_back)).strftime("%Y-%m-%d")

    all_news: List[Dict[str, Any]] = []

    for entry in watchlist:
        symbol = entry.get("symbol", "")
        company_name = entry.get("name", symbol)

        if not symbol:
            continue

        logger.info("Fetching Finnhub News Media for %s (%s to %s)...", symbol, from_date, to_date)
        items = fetch_company_news_finnhub(
            symbol=symbol,
            api_key=token,
            from_date=from_date,
            to_date=to_date,
            max_items=max_items_per_ticker,
        )

        for it in items:
            it["company_name"] = company_name

        logger.info("Retrieved %d News Media items for %s", len(items), symbol)
        all_news.extend(items)

        # Rate limit compliance (Finnhub free tier allows 30 req/min)
        time.sleep(delay_seconds)

    return all_news


# Alias for consistency
collect_news_media = collect_finnhub_news
