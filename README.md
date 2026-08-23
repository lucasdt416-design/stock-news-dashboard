# Personal Stock News Dashboard

An automated intelligence engine that collects multi-source company disclosures (SEC EDGAR submissions and official Company Investor Relations feeds), deduplicates coverage, scores impact using transparent arithmetic, and publishes a static daily briefing.

## Features
- **Multi-Source Ingestion**: Official SEC EDGAR Submissions API & Company IR RSS/Atom feeds (`NVDA`, `AAPL`, `MSFT`).
- **Deduplication Engine**: Canonical URL matching, Unique ID matching, and fuzzy headline similarity.
- **Transparent Scoring Engine**: Rule-based categorization (Earnings, Regulatory, Leadership, Insider, Product) with arithmetic audit breakdown (0.0–10.0).
- **Priority Intelligence Panel**: Highlights top high-impact disclosures at the top of the dashboard.
- **Static Dashboard**: Fast, responsive dark-mode dashboard with real-time ticker and category filtering.
- **Automated Workflow**: Weekday morning cron job via GitHub Actions with SQLite cache persistence and Cloudflare Pages deployment.

## Local Usage

```bash
# 1. Activate virtual environment
source .venv/bin/activate

# 2. Run the pipeline
python scripts/run_local.py

# 3. View the generated dashboard
open site/index.html
```