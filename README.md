# 📊 Stock News & SEC Intelligence Dashboard

[![Live Demo](https://img.shields.io/badge/Live%20Demo-stock--news--dashboard.pages.dev-blue?style=for-the-badge&logo=cloudflare)](https://stock-news-dashboard.pages.dev)
[![Python](https://img.shields.io/badge/Python-3.11-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![Gemini](https://img.shields.io/badge/AI-Gemini%202.5%20Flash-4E75F6?style=for-the-badge&logo=google-gemini&logoColor=white)](https://ai.google.dev/)
[![Cloudflare Pages](https://img.shields.io/badge/Deployed%20to-Cloudflare%20Pages-F38020?style=for-the-badge&logo=cloudflare)](https://stock-news-dashboard.pages.dev)
[![Automation](https://img.shields.io/badge/CI%2FCD-GitHub%20Actions%20Cron-2088FF?style=for-the-badge&logo=githubactions&logoColor=white)](https://github.com/lucasdt416-design/stock-news-dashboard/actions)

An automated financial intelligence engine that ingests corporate disclosures across official **SEC EDGAR submissions** and **Company Investor Relations feeds** (`NVDA`, `AAPL`, `MSFT`), deduplicates cross-source coverage, scores investor importance (0.0–10.0) via transparent arithmetic, generates plain-English *"Why It Matters"* takeaways using the **Gemini API**, and publishes an interactive daily static briefing to **Cloudflare Pages** every weekday morning.

🔗 **Live Production Dashboard:** [https://stock-news-dashboard.pages.dev](https://stock-news-dashboard.pages.dev)

---

## 💡 Why I Built This

Financial newsfeeds are flooded with syndicated wire spam, while official filings are obscured behind cryptic form numbers (*Form 4*, *Form 8-K*, *Rule 144*) that give no immediate context on investor impact. 

I designed this project to act as a **zero-cost, automated personal hedge-fund news desk**:
- **Filters the noise**: Drops duplicate stories covered by multiple wires and newsrooms.
- **Translates filings into English**: Replaces raw filing names with concrete investor takeaways (e.g. distinguishing a routine scheduled 10b5-1 executive sale from a major unscheduled material event).
- **Ranks by true importance**: Surfaces high-impact regulatory and earnings disclosures to the top before you start your trading day.
- **Zero server overhead & $0 cost**: Runs purely via GitHub Actions, SQLite caching, and Cloudflare Pages.

---

## 🏗️ Architecture & Pipeline Flow

```
┌────────────────────────────────────────────────────────┐
│                   Data Collectors                      │
│   • SEC EDGAR Submissions API (Forms 4, 8-K, 10-Q...)  │
│   • Official Company IR Feeds (RSS / Atom Newsrooms)   │
└──────────────────────────┬─────────────────────────────┘
                           │
                           ▼
┌────────────────────────────────────────────────────────┐
│              Normalization & Deduplication             │
│   • Common schema unification                          │
│   • Multi-tier deduplication (Canonical URL & Fuzzy)   │
└──────────────────────────┬─────────────────────────────┘
                           │
                           ▼
┌────────────────────────────────────────────────────────┐
│                 Rule-Based Classifier                  │
│   • 10 Categories (Earnings, Regulatory, Leadership...)│
└──────────────────────────┬─────────────────────────────┘
                           │
                           ▼
┌────────────────────────────────────────────────────────┐
│            Transparent Scoring Engine (0.0-10.0)       │
│   • Category Base (1-8) + Source Authority (+3/+2/+1)  │
│   • Recency Bonus (+2/+1/-1) + Headline Entity (+1)    │
└──────────────────────────┬─────────────────────────────┘
                           │
                           ▼
┌────────────────────────────────────────────────────────┐
│         AI 'Why It Matters' Summarizer (Gemini API)     │
│   • Batched JSON calls (~20 items/batch, $0 cost)      │
│   • Contextual fallback engine on network/quota error  │
└──────────────────────────┬─────────────────────────────┘
                           │
                           ▼
┌────────────────────────────────────────────────────────┐
│          SQLite Storage & Static Site Generator        │
│   • Persistent SQLite DB (preserved via GitHub Cache)  │
│   • Static HTML compilation with Chart.js analytics    │
└──────────────────────────┬─────────────────────────────┘
                           │
                           ▼
┌────────────────────────────────────────────────────────┐
│        GitHub Actions CI/CD ➔ Cloudflare Pages         │
│   • Scheduled cron: Weekdays at 6:00 AM EST (11:00 UTC)│
│   • Production deploy via Cloudflare Wrangler          │
└────────────────────────────────────────────────────────┘
```

---

## ✨ Key Features

- **⚡ Priority Intelligence Panel**: Spotlight grid displaying the top 8 highest-scored stories with color-coded score pills and category tags.
- **💡 AI "Why It Matters" Takeaways**: Every item includes a single-sentence plain-English investor explanation powered by Gemini 2.5 Flash.
- **📈 Interactive Visual Analytics**:
  - **Frequency Sparkline**: Tracks multi-company filing and news velocity over time (`NVDA`, `AAPL`, `MSFT`).
  - **Category Donut Chart**: Breaks down the distribution of disclosures across active categories.
- **🎯 Transparent Scoring Arithmetic**: Every score displays its full breakdown on hover (e.g. `Base 8 + SEC Edgar 3 + Recency 2 = 10.0`).
- **🔍 Client-Side Instant Filtering**: Live filter pills by Ticker, Category, and Source with instant full-text search.
- **🛡️ Resilient Architecture**: Guaranteed uptime with intelligent heuristic fallbacks if external APIs are unavailable.

---

## 🛠️ Tech Stack

| Layer | Technologies |
|---|---|
| **Core & Pipeline** | Python 3.11, Jinja2, PyYAML, Feedparser |
| **AI / LLM** | Google Gemini API (`gemini-2.5-flash` with structured batching) |
| **Database** | SQLite3 (indexes on `score DESC`, `published_date DESC`, `ticker`) |
| **Visualizations** | Chart.js 4.4 (loaded via CDN, zero-build dependency) |
| **Frontend** | Semantic HTML5, Custom Responsive CSS (Dark Mode Glassmorphism) |
| **Automation** | GitHub Actions (Weekday morning cron schedule + DB cache restore/save) |
| **Hosting & CDN** | Cloudflare Pages (Deployed via Wrangler) |

---

## 🚀 Local Development Setup

### 1. Clone & Setup Environment

```bash
# Clone the repository
git clone https://github.com/lucasdt416-design/stock-news-dashboard.git
cd stock-news-dashboard

# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Watchlist & Keys (Optional)

- Edit tickers in `data/watchlist.yaml` (supports any US-listed ticker with CIK and IR feed URL).
- Set your Gemini API key (optional — includes built-in offline heuristic fallback):
  ```bash
  export GEMINI_API_KEY="your-gemini-api-key"
  ```

### 3. Run the End-to-End Pipeline

```bash
python scripts/run_local.py
```

### 4. View Dashboard

```bash
open site/index.html
```

---

## ⚙️ Automated GitHub Actions Workflow

The pipeline runs automatically via [.github/workflows/daily-run.yml](.github/workflows/daily-run.yml):
- **Cron Schedule**: Monday–Friday at 11:00 UTC (6:00 AM EST / 7:00 AM EDT).
- **Manual Trigger**: `workflow_dispatch` button enabled in the Actions tab.
- **State Persistence**: Uses `actions/cache@v4` to restore and save `data/dashboard.db` between runs, preserving deduplication history and historical scores across builds.
- **Zero-Friction Deployment**: Deploys directly to Cloudflare Pages on completion.

---

## 📄 License

MIT License — free to use, modify, and distribute.