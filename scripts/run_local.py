"""Master End-to-End Pipeline Runner with Health Safeguards & Anomaly Detection.

Executes all 8 pipeline stages:
1. Load watchlist
2. Run collectors (SEC EDGAR, Company IR)
3. Normalize records
4. Deduplicate across sources
5. Transparent scoring engine
6. Gemini AI / Heuristic 'Why It Matters' summarization
7. Persist to SQLite
8. Health monitoring & moving average anomaly check
9. Render static dashboard & visual analytics
"""

import argparse
import logging
import os
import sys
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from collectors.edgar import collect_sec_edgar
from collectors.company_ir import collect_company_ir
from pipeline.db import init_db
from pipeline.health import record_pipeline_run_health, STATUS_CRITICAL, STATUS_WARNING
from pipeline.normalize import normalize_items
from pipeline.dedupe import deduplicate_items
from pipeline.score import score_items
from pipeline.summarize import summarize_items
from pipeline.calendar import build_forthcoming_calendar
from pipeline.persist import save_news_items, get_news_stats
from pipeline.render import render_dashboard
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
    print("🚀 Running Stock News Dashboard Pipeline (Scoring + AI + Health Engine)")
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

    # 3. Stage 1: Collectors
    logger.info("--- Stage 1: Collectors ---")
    logger.info("Collecting SEC EDGAR filings...")
    edgar_raw = collect_sec_edgar(tickers, max_items_per_ticker=30)
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
    summarized_items = summarize_items(scored_items, batch_size=25)
    logger.info("Summarization complete for %d items", len(summarized_items))

    # 8. Stage 6: Persist News Records
    logger.info("--- Stage 6: Persist News Records ---")
    new_count, total_processed = save_news_items(summarized_items, db_path=str(db_file))
    logger.info("Persistence complete: %d records updated/inserted (%d processed)", new_count, total_processed)

    # 9. Stage 7: Health Monitoring & Telemetry Safeguards
    logger.info("--- Stage 7: Health Monitoring Safeguards ---")
    health_report = record_pipeline_run_health(
        collector_counts={
            "sec_edgar": len(edgar_raw),
            "company_ir": len(ir_raw),
        },
        total_raw=len(raw_items),
        total_unique=len(unique_items),
        high_impact_count=len(high_impact),
        db_path=str(db_file),
    )

    # 10. Stage 8: Forthcoming Corporate Calendar (Category #24)
    logger.info("--- Stage 8: Forthcoming Corporate Calendar ---")
    calendar_events = build_forthcoming_calendar(watchlist=tickers, db_path=str(db_file))
    logger.info("Corporate calendar populated: %d upcoming scheduled events", len(calendar_events))

    # 11. Stage 9: Render Static Dashboard
    logger.info("--- Stage 9: Render Static Site ---")
    output_html = render_dashboard(output_path=str(site_output), db_path=str(db_file))
    logger.info("Rendered static dashboard to %s", output_html)

    # 11. Summary Stats
    stats = get_news_stats(db_path=str(db_file))
    print("\n" + "-" * 70)
    print("📊 Pipeline Run & Health Summary")
    print("-" * 70)
    print(f"• System Health Status:       {health_report['status']} ({health_report['health_message']})")
    print(f"• Collector Yields:           SEC EDGAR: {health_report['edgar_count']} | Company IR: {health_report['company_ir_count']}")
    print(f"• Total Raw Collected:        {health_report['total_raw']} (7-run avg: {health_report['moving_avg_raw']:.0f})")
    print(f"• Total Unique Items in DB:    {stats['total']}")
    print(f"• High Impact Stories (≥ 7.0): {stats['high_priority_count']}")
    print(f"• Average Score:              {stats['avg_score']} / 10.0")
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
