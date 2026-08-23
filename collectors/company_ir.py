"""Company Investor Relations / Newsroom Feed Collector.

Fetches official press releases, newsroom posts, and IR announcements
from official company RSS / Atom feeds.
"""

import logging
import time
from typing import Any, Dict, List
import feedparser

logger = logging.getLogger(__name__)

DEFAULT_USER_AGENT = "StockNewsDashboard/1.0 (Mozilla/5.0; IR Feed Reader; contact: admin@stocknewsdashboard.local)"


def fetch_ir_feed(
    feed_url: str,
    ticker: str,
    company_name: str,
    max_items: int = 30,
    timeout: int = 15,
) -> List[Dict[str, Any]]:
    """Fetch and parse an official company IR RSS/Atom feed."""
    if not feed_url:
        return []

    try:
        # feedparser supports custom request headers via agent/request_headers
        parsed = feedparser.parse(
            feed_url,
            agent=DEFAULT_USER_AGENT,
            request_headers={"User-Agent": DEFAULT_USER_AGENT},
        )

        if parsed.bozo and not parsed.entries:
            logger.warning(
                "Warning parsing IR feed for %s (%s): %s",
                ticker,
                feed_url,
                parsed.bozo_exception,
            )

        entries = parsed.entries[:max_items]
        items: List[Dict[str, Any]] = []

        for entry in entries:
            title = entry.get("title", "").strip()
            link = entry.get("link", "").strip()
            guid = entry.get("id") or link or title

            # Extract date
            pub_date = ""
            pub_time = ""
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                pub_date = time.strftime("%Y-%m-%d", entry.published_parsed)
                pub_time = time.strftime("%Y-%m-%dT%H:%M:%SZ", entry.published_parsed)
            elif hasattr(entry, "updated_parsed") and entry.updated_parsed:
                pub_date = time.strftime("%Y-%m-%d", entry.updated_parsed)
                pub_time = time.strftime("%Y-%m-%dT%H:%M:%SZ", entry.updated_parsed)
            else:
                raw_dt = entry.get("published") or entry.get("updated") or ""
                if raw_dt:
                    # Take first 10 characters if YYYY-MM-DD format
                    pub_date = raw_dt[:10] if len(raw_dt) >= 10 and raw_dt[4] == "-" else raw_dt

            # Summary / Description
            summary = entry.get("summary", "") or entry.get("description", "")
            # Basic HTML tag stripping for summary preview
            if "<" in summary and ">" in summary:
                import re
                summary = re.sub(r"<[^>]+>", "", summary).strip()

            items.append({
                "ticker": ticker.upper(),
                "company_name": company_name,
                "title": title,
                "link": link,
                "guid": guid,
                "published_date": pub_date,
                "published_time": pub_time,
                "summary": summary,
                "source": "company_ir",
                "source_type": "company_announcement",
                "form_or_type": "PRESS_RELEASE",
            })

        return items

    except Exception as e:
        logger.error("Failed to fetch IR feed for %s from %s: %s", ticker, feed_url, e)
        return []


def collect_company_ir(
    watchlist: List[Dict[str, Any]],
    max_items_per_ticker: int = 30,
    delay_seconds: float = 0.2,
) -> List[Dict[str, Any]]:
    """Collect IR announcements for all tickers with ir_feed_url defined."""
    all_items: List[Dict[str, Any]] = []

    for entry in watchlist:
        symbol = entry.get("symbol", "")
        company_name = entry.get("name", symbol)
        feed_url = entry.get("ir_feed_url")

        if not feed_url:
            logger.info("No IR feed URL configured for %s, skipping", symbol)
            continue

        logger.info("Fetching Company IR feed for %s (%s)...", symbol, feed_url)
        items = fetch_ir_feed(feed_url, ticker=symbol, company_name=company_name, max_items=max_items_per_ticker)
        logger.info("Retrieved %d IR items for %s", len(items), symbol)
        all_items.extend(items)

        time.sleep(delay_seconds)

    return all_items
