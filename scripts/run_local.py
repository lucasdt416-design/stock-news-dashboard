#!/usr/bin/env python3
"""Run local end-to-end pipeline: Collect EDGAR filings -> SQLite -> Static HTML."""

import os
import sys
import yaml
import logging

# Ensure project root is on sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from collectors.edgar import collect_edgar_filings
from pipeline.db import init_db
from pipeline.persist import save_filings, get_filing_stats
from pipeline.render import render_dashboard


def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )


def load_watchlist(watchlist_path: str):
    if not os.path.exists(watchlist_path):
        raise FileNotFoundError(f"Watchlist file not found at {watchlist_path}")
    with open(watchlist_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("tickers", [])


def main():
    setup_logging()
    logger = logging.getLogger("run_local")

    print("\n" + "=" * 60)
    print("🚀 Running Stock News Dashboard Pipeline (Phase 1: SEC EDGAR)")
    print("=" * 60 + "\n")

    watchlist_file = os.path.join(PROJECT_ROOT, "data", "watchlist.yaml")
    db_file = os.path.join(PROJECT_ROOT, "data", "dashboard.db")
    site_output = os.path.join(PROJECT_ROOT, "site", "index.html")

    # 1. Load Watchlist
    logger.info("Loading watchlist from %s", watchlist_file)
    tickers = load_watchlist(watchlist_file)
    ticker_symbols = [t["symbol"] for t in tickers]
    logger.info("Loaded %d watchlist tickers: %s", len(tickers), ", ".join(ticker_symbols))

    # 2. Initialize Database
    logger.info("Initializing database schema at %s", db_file)
    init_db(db_file)

    # 3. Collect SEC Filings
    logger.info("Collecting SEC EDGAR filings...")
    filings = collect_edgar_filings(tickers, max_items_per_ticker=30)
    logger.info("Total filings parsed from SEC: %d", len(filings))

    # 4. Persist to SQLite
    logger.info("Saving filings into SQLite database...")
    new_count, total_count = save_filings(filings, db_path=db_file)
    logger.info("Persistence complete: %d new filings added (%d processed)", new_count, total_count)

    # 5. Render Static Site
    logger.info("Rendering static HTML dashboard to %s", site_output)
    output_html = render_dashboard(output_path=site_output, db_path=db_file)

    # 6. Summary Stats
    stats = get_filing_stats(db_path=db_file)
    print("\n" + "-" * 60)
    print("📊 Pipeline Run Summary")
    print("-" * 60)
    print(f"• Total Filings in Database: {stats['total']}")
    print(f"• Latest Filing Date:        {stats['latest_date']}")
    print(f"• Breakdown by Ticker:       {stats['by_ticker']}")
    print(f"• Generated Dashboard:       {output_html}")
    print("-" * 60)
    print(f"✅ Finished successfully! Open {output_html} in your browser.\n")


if __name__ == "__main__":
    main()
