#!/usr/bin/env python3
"""Run local end-to-end pipeline:
Collectors -> Normalize -> Deduplicate -> Score -> Summarize (Gemini LLM) -> Persist -> Render.
"""

import logging
import os
import sys
import yaml

# Ensure project root is on sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from collectors.company_ir import collect_company_ir
from collectors.edgar import collect_edgar_filings
from pipeline.db import init_db
from pipeline.dedupe import deduplicate_items
from pipeline.normalize import normalize_items
from pipeline.persist import get_news_stats, save_news_items
from pipeline.render import render_dashboard
from pipeline.score import score_items
from pipeline.summarize import summarize_items


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

    print("\n" + "=" * 70)
    print("🚀 Running Stock News Dashboard Pipeline (Scoring + AI 'Why It Matters')")
    print("=" * 70 + "\n")

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

    # 3. Stage 1: Collectors
    logger.info("--- Stage 1: Collectors ---")
    logger.info("Collecting SEC EDGAR filings...")
    edgar_raw = collect_edgar_filings(tickers, max_items_per_ticker=30)
    logger.info("SEC EDGAR raw items: %d", len(edgar_raw))

    logger.info("Collecting Company IR announcements...")
    ir_raw = collect_company_ir(tickers, max_items_per_ticker=30)
    logger.info("Company IR raw items: %d", len(ir_raw))

    raw_items = edgar_raw + ir_raw
    logger.info("Total raw items collected across all sources: %d", len(raw_items))

    # 4. Stage 2: Normalize
    logger.info("--- Stage 2: Normalize ---")
    normalized_items = normalize_items(raw_items)
    logger.info("Normalized %d items into common schema", len(normalized_items))

    # 5. Stage 3: Deduplicate
    logger.info("--- Stage 3: Deduplicate ---")
    unique_items, dup_count = deduplicate_items(normalized_items, similarity_threshold=0.75)
    logger.info("Deduplication complete: %d unique items (%d duplicates filtered)", len(unique_items), dup_count)

    # 6. Stage 4: Scoring Engine
    logger.info("--- Stage 4: Scoring Engine ---")
    scored_items = score_items(unique_items)
    high_impact = [it for it in scored_items if it.get("score", 0) >= 7.0]
    logger.info("Scored %d items (%d identified as High Impact ≥ 7.0)", len(scored_items), len(high_impact))

    # 7. Stage 5: 'Why It Matters' Summarization (Gemini API)
    logger.info("--- Stage 5: 'Why It Matters' Summarization ---")
    summarized_items = summarize_items(scored_items, batch_size=20)
    logger.info("Summarization complete for %d items", len(summarized_items))

    # 8. Stage 6: Persist
    logger.info("--- Stage 6: Persist ---")
    new_count, total_processed = save_news_items(summarized_items, db_path=db_file)
    logger.info("Persistence complete: %d records updated/inserted (%d processed)", new_count, total_processed)

    # 9. Stage 7: Render Static Site
    logger.info("--- Stage 7: Render ---")
    output_html = render_dashboard(output_path=site_output, db_path=db_file)
    logger.info("Rendered static dashboard to %s", output_html)

    # 10. Summary Stats
    stats = get_news_stats(db_path=db_file)
    print("\n" + "-" * 70)
    print("📊 Pipeline Run Summary")
    print("-" * 70)
    print(f"• Total Unique Items in DB:    {stats['total']}")
    print(f"• High Impact Stories (≥ 7.0): {stats['high_priority_count']}")
    print(f"• Average Score:              {stats['avg_score']} / 10.0")
    print(f"• Breakdown by Category:      {stats['by_category']}")
    print(f"• Breakdown by Source:        {stats['by_source']}")
    print(f"• Breakdown by Ticker:        {stats['by_ticker']}")
    print(f"• Generated Dashboard:        {output_html}")
    print("-" * 70)
    print(f"✅ Finished successfully! Open {output_html} in your browser.\n")


if __name__ == "__main__":
    main()
