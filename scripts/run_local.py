"""Master End-to-End Pipeline Runner with Health Safeguards & Anomaly Detection.

Executes all 10 pipeline stages:
1. Load watchlist
2. Run collectors (SEC EDGAR, Company IR, Finnhub News Media)
3. Normalize records into unified schema
4. Deduplicate across sources
5. Supplier & customer cross-referencing
6. Transparent scoring engine
7. Gemini AI / Heuristic 'Why It Matters' summarization
8. Persist to SQLite
9. Health monitoring & moving average anomaly check
10. Render static dashboard & visual analytics (5 static pages)
"""

import argparse
import logging
import os
from pathlib import Path
import sys

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Load .env file if present
env_file = PROJECT_ROOT / ".env"
if env_file.exists():
    with open(env_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip("'\"")
                if k and k not in os.environ:
                    os.environ[k] = v

from collectors.company_ir import collect_company_ir
from collectors.edgar import collect_sec_edgar
from collectors.finnhub_news import collect_finnhub_news
from pipeline.calendar import build_forthcoming_calendar
from pipeline.crossref import apply_supply_chain_cross_references
from pipeline.db import init_db
from pipeline.dedupe import deduplicate_items
from pipeline.economic import collect_economic_indicators
from pipeline.health import (
    record_pipeline_run_health,
    STATUS_CRITICAL,
    STATUS_WARNING,
)
from pipeline.normalize import normalize_items
from pipeline.persist import get_news_stats, save_news_items
from pipeline.render import render_dashboard
from pipeline.score import score_items
from pipeline.summarize import summarize_items
import yaml

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("pipeline_runner")


def main() -> None:
    parser = argparse.ArgumentParser(description="Stock News Dashboard Pipeline Runner")
    parser.add_argument(
        "--fail-on-critical",
        action="store_true",
        default=os.environ.get("FAIL_ON_CRITICAL", "false").lower() in ("true", "1", "yes"),
        help="Exit with non-zero code if health check returns CRITICAL status (for CI/GitHub Actions)",
    )
    args = parser.parse_args()

    print("\n" + "=" * 70)
    print("🚀 Running Stock News Dashboard Pipeline (3 Sources + AI + Health Engine)")
    print("=" * 70 + "\n")

    watchlist_path = PROJECT_ROOT / "data" / "watchlist.yaml"
    db_file = PROJECT_ROOT / "data" / "dashboard.db"
    site_output = PROJECT_ROOT / "site" / "index.html"

    # 1. Load Watchlist
    logger.info("Loading watchlist from %s", watchlist_path)
    with open(watchlist_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    tickers = config.get("tickers", [])
    logger.info("Loaded %d watchlist tickers: %s", len(tickers), ", ".join(t["symbol"] for t in tickers))

    # 2. Initialize Database Schema
    logger.info("Initializing database schema at %s", db_file)
    init_db(str(db_file))

    # 3. Stage 1: Collectors (3 Distinct Sources)
    logger.info("--- Stage 1: Collectors (3 Distinct Sources) ---")
    logger.info("Collecting SEC EDGAR filings (Regulatory)...")
    edgar_raw = collect_sec_edgar(tickers, max_items_per_ticker=30)
    logger.info("SEC EDGAR raw items: %d", len(edgar_raw))

    logger.info("Collecting Company IR announcements (Company Self-Announcements)...")
    ir_raw = collect_company_ir(tickers, max_items_per_ticker=30)
    logger.info("Company IR raw items: %d", len(ir_raw))

    logger.info("Collecting 3rd-Party News Media (Finnhub Journalism)...")
    finnhub_raw = collect_finnhub_news(tickers, max_items_per_ticker=20)
    logger.info("News Media (Finnhub) raw items: %d", len(finnhub_raw))

    raw_items = edgar_raw + ir_raw + finnhub_raw
    logger.info("Total raw items collected across all 3 sources: %d", len(raw_items))

    # 4. Stage 2: Normalize
    logger.info("--- Stage 2: Normalize ---")
    normalized_items = normalize_items(raw_items)
    logger.info("Normalized %d items into common schema", len(normalized_items))

    # 5. Stage 3: Deduplicate
    logger.info("--- Stage 3: Deduplicate ---")
    unique_items, dup_count = deduplicate_items(normalized_items, similarity_threshold=0.75)
    logger.info("Deduplication complete: %d unique items (%d duplicates filtered)", len(unique_items), dup_count)

    # 6. Stage 4: Supply Chain & Customer Cross-Referencing (Category #12)
    logger.info("--- Stage 4: Supplier & Customer Cross-Referencing Engine ---")
    crossref_items = apply_supply_chain_cross_references(unique_items, tickers)
    logger.info("Cross-referencing complete for %d items", len(crossref_items))

    # 7. Stage 5: Scoring Engine
    logger.info("--- Stage 5: Scoring Engine ---")
    scored_items = score_items(crossref_items)
    high_impact = [it for it in scored_items if it.get("score", 0) >= 7.0]
    logger.info("Scored %d items (%d identified as High Impact ≥ 7.0)", len(scored_items), len(high_impact))

    # 8. Stage 6: 'Why It Matters' Summarization (Gemini API)
    logger.info("--- Stage 6: 'Why It Matters' Summarization ---")
    summarized_items = summarize_items(scored_items, batch_size=25)
    logger.info("Summarization complete for %d items", len(summarized_items))

    # 9. Stage 7: Persist News Records
    logger.info("--- Stage 7: Persist News Records ---")
    new_count, total_processed = save_news_items(summarized_items, db_path=str(db_file))
    logger.info("Persistence complete: %d records updated/inserted (%d processed)", new_count, total_processed)

    # 10. Stage 8: Health Monitoring & Telemetry Safeguards
    logger.info("--- Stage 8: Health Monitoring Safeguards ---")
    health_report = record_pipeline_run_health(
        collector_counts={
            "sec_edgar": len(edgar_raw),
            "company_ir": len(ir_raw),
            "news_media": len(finnhub_raw),
        },
        total_raw=len(raw_items),
        total_unique=len(unique_items),
        high_impact_count=len(high_impact),
        db_path=str(db_file),
    )

    # 11. Stage 9: Forthcoming Corporate Calendar (Category #24)
    logger.info("--- Stage 9: Forthcoming Corporate Calendar ---")
    calendar_events = build_forthcoming_calendar(watchlist=tickers, db_path=str(db_file))
    logger.info("Corporate calendar populated: %d upcoming scheduled events", len(calendar_events))

    # 12. Stage 10: Macroeconomic Intelligence Engine (Category #15)
    logger.info("--- Stage 10: FRED Macroeconomic Intelligence Engine ---")
    economic_indicators = collect_economic_indicators(
        watchlist=tickers,
        db_path=str(db_file),
    )
    logger.info("Macroeconomic indicators updated: %d indicators mapped", len(economic_indicators))

    # 13. Stage 11: Render Static Dashboard (5 Static Pages)
    logger.info("--- Stage 11: Render Static Site (5 Pages) ---")
    output_html = render_dashboard(output_path=str(site_output), db_path=str(db_file))
    logger.info("Rendered static dashboard to %s", output_html)

    # 14. Summary Stats
    stats = get_news_stats(db_path=str(db_file))
    print("\n" + "-" * 70)
    print("📊 Pipeline Run & Health Summary")
    print("-" * 70)
    print(f"• System Health Status:       {health_report['status']} ({health_report['health_message']})")
    print(f"• Collector Yields:           SEC EDGAR: {health_report['edgar_count']} | Company IR: {health_report['company_ir_count']} | News Media: {health_report.get('news_media_count', 0)}")
    print(f"• Total Raw Collected:        {health_report['total_raw']} (7-run avg: {health_report['moving_avg_raw']:.0f})")
    print(f"• Total Unique Items in DB:    {stats['total']}")
    print(f"• High Impact Stories (≥ 7.0): {stats['high_priority_count']}")
    print(f"• Average Score:              {stats['avg_score']} / 10.0")
    print(f"• Breakdown by Source:        {stats['by_source']}")
    print(f"• Breakdown by Category:      {stats['by_category']}")
    print(f"• Breakdown by Ticker:        {stats['by_ticker']}")
    print(f"• Generated Dashboard:        {output_html}")
    print("-" * 70)

    if health_report["status"] == STATUS_CRITICAL:
        print(f"❌ PIPELINE HEALTH CRITICAL: {health_report['health_message']}\n")
        if args.fail_on_critical:
            logger.error("Failing run due to --fail-on-critical flag.")
            sys.exit(1)
    elif health_report["status"] == STATUS_WARNING:
        print(f"⚠️ PIPELINE HEALTH WARNING: {health_report['health_message']}\n")
    else:
        print(f"✅ Finished successfully! Open {output_html} in your browser.\n")


if __name__ == "__main__":
    main()
