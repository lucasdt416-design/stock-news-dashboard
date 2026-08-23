# Personal Stock News Dashboard — Build Plan

> Reference document for AI coding assistants and contributors. Source spec: `stock-news-dashboard-build-guide.md`
> and its plain-language companion. This file translates that spec into an actionable, phased build plan.
> **No code has been written yet except the EDGAR collector (see Phase 1).** This is planning only.

## 0. Project one-liner

A program collects news about a chosen list of company shares overnight, removes duplicate stories,
classifies and scores what remains, and publishes the survivors to a single static web page reviewed each morning.
Not financial advice; every output must be verifiable against a primary source.

## 1. Tech stack (decisions + reasoning)

| Layer | Choice | Reasoning |
|---|---|---|
| Backend / collection language | Python | Best library support for finance data + scraping |
| Scheduler | GitHub Actions (cron) | Free, no server to maintain |
| Storage | SQLite (single file) | Zero-maintenance, sufficient for personal scale |
| Frontend | **Next.js (React), static export** | Component-based UI for portfolio value, but built once and exported to plain HTML/CSS/JS — no live server, matches the guide's "nothing runs when a visitor arrives" requirement. Fallback: plain HTML/CSS templates if Next.js adds friction. |
| Hosting | Cloudflare Pages / Netlify / GitHub Pages | Free, HTTPS included |
| Classification | Fixed rules first, LLM for leftovers only | Rules are free/fast/predictable; LLM handles the ~20% rules can't resolve |

**Open decision for you :** confirm Next.js is the right call vs. plain static HTML. Next.js is more
portfolio-impressive and easier to build a polished UI in, but is a heavier tool to learn if neither of you knows React yet.

## 2. System architecture (pipeline)

Each stage does one job and hands off to the next — new sources can be added later without touching downstream stages.

```
Collectors → Normalize → Deduplicate → Classify → Score → Persist (SQLite) → Render (static site)
```

| Stage | Responsibility |
|---|---|
| Collectors | One module per source. Each returns a list of news items. Failures are isolated — one broken source doesn't stop the run. |
| Normalize | Reshape every item into one common schema regardless of source. |
| Deduplicate | Match by URL → headline similarity → semantic similarity, in that order. |
| Classify | Rule-based first; LLM batch call (~20 headlines/request) for anything rules can't resolve. |
| Score | 0–10 importance rating (see §6). |
| Persist | Write to SQLite. |
| Render | Build static HTML pages from the database. |

## 3. Repo / file structure (proposed)

```
/collectors/          # one file per source (edgar.py, company_ir.py, fmp.py, ...)
/pipeline/
  normalize.py
  dedupe.py
  classify.py
  score.py
  persist.py
/data/
  watchlist.yaml       # hand-maintained, see §4
  dashboard.db          # SQLite, generated
/site/                 # Next.js app (or plain HTML templates)
/.github/workflows/
  daily-run.yml         # GitHub Actions cron job
/scripts/
  run_local.py          # manual trigger for testing without waiting for cron
```

## 4. The watchlist file (`watchlist.yaml`)

The single most important hand-maintained file. Not just tickers — relationships that make filtering possible.

```yaml
tickers:
  - symbol: NVDA
    name: NVIDIA Corporation
    cik: "0001045810"
    sector: semiconductors
    regulators: [BIS, SEC]
    key_customers: [MSFT, META, AMZN, GOOGL]
    key_suppliers: [TSM, ASML, SK Hynix]
    competitors: [AMD, INTC, AVGO]
    macro_sensitivities: [export_controls_china, datacenter_capex]
    notes: "Watch hyperscaler capital spending guidance closely."
```
~10 min of manual research per company. Determines dashboard quality more than any code decision.

## 5. News categories to classify into (24 total)

**Core 4:** Leadership & governance · Regulation & policy · Relevant world news · Earnings

**Additional 20:** Insider transactions · Analyst actions · Guidance revisions · M&A / partnerships ·
Capital structure changes · Credit rating changes · Litigation · Supplier/customer news ·
Competitor news · Product launches & approvals · Economic conditions (only where a documented
sensitivity exists) · Short interest / options activity · Institutional ownership · Index inclusion/exclusion ·
Labour actions · Cybersecurity incidents · Executive commentary · Short-seller reports ·
Sentiment/discussion volume · Forthcoming calendar (results dates, dividend dates, lock-ups, deadlines)

## 6. Scoring formula (transparent arithmetic, not a black box)

Base score per category (suggested starting weights): Earnings/M&A/activist stakes = 8, Regulatory action = 7,
Leadership changes/credit downgrades = 6, Analyst actions = 3, Sentiment = 1.

Adjustments:
| Factor | Effect |
|---|---|
| Regulatory filing source | +3 |
| Company announcement source | +2 |
| Established press source | +1 |
| Under 6 hours old | +2 |
| Under 24 hours old | +1 |
| Price move > 2x typical range | +3 |
| Company named in headline (not just mentioned) | +1 |
| Duplicate of already-seen item | −4 |

**Known failure mode to avoid:** a bonus that applies to nearly every item just flattens everything toward 10 without
changing the ranking. Apply source-authority bonuses only when comparing across different source types, and treat
recency as a staleness *penalty* rather than a freshness *reward* (on a daily run, almost everything is fresh).

## 7. Data sources

**Free/official (preferred):** SEC EDGAR (filings — no key, no cost, 10 req/sec limit, must self-identify),
Federal Register, company IR feeds (added manually, one per company), FDA/FTC/DOJ/FCC feeds, FRED (economic data).

**Commercial (pick 1–2, not all):** Financial Modeling Prep, Polygon, Finnhub, Alpha Vantage, Marketaux, GDELT,
Benzinga, Tiingo — all have free tiers sufficient for personal scale.

**Scraping — last resort only, and only if:**
- `robots.txt` and ToS explicitly allow it
- rate-limited to ~1 request per few seconds per site, with jitter
- your program identifies itself + a contact address
- you check "has this changed" (ETag) before re-downloading
- you store only headline/link/timestamp/short excerpt — never full article text
- each scraper is isolated so it fails without breaking the rest of the run

## 8. Tasks that cannot be delegated to AI / require a human

- Registering for any data provider account, accepting ToS, providing payment info + spend limits
- Creating the repo, hosting account, and connecting them
- Buying/configuring a domain (optional)
- Storing API keys in the hosting platform's secret storage (never commit keys to the repo)
- Choosing companies and filling in `watchlist.yaml` relationship data
- Setting the importance threshold for what shows on the front page
- Confirming each source's collection is actually permitted
- Checking employer rules on personal trading/outside tools if either of you works in financial services
- Weekly: skim run summary for a source that silently returned 0 items
- Monthly: check API usage against free-tier limits, update dependencies, archive old items
- Periodic "missed-signal review": manually read the unfiltered feed for one company and check nothing important got filtered out

## 9. Build order

| Phase | Scope | Done when |
|---|---|---|
| **Phase 1** (done) | EDGAR collector, watchlist schema, SQLite schema, one plain page | Recent filings for watchlist companies visible in browser |
| **Phase 2** | Company IR feeds, one commercial news API, results calendar, deduplication | Multiple sources flow into one place without repeats |
| **Phase 3** | Rule-based classifier, scoring engine, priority panel | Tool becomes genuinely useful daily |
| **Phase 4** | LLM fallback classification, economic panel, supplier/customer cross-refs, health monitoring, real hosting + domain | System is finished and can run unattended |
| **Ongoing** | Tune score weights against real use, add sector-specific sources | — |

**Guiding principle:** ship Phase 1's plain page before designing Phase 4's polish. A mediocre dashboard checked
daily beats a perfect one that's never finished.

## 10. Known troubleshooting patterns

| Symptom | Likely cause | Fix |
|---|---|---|
| A source returns nothing | Page layout changed / API deprecated | Inspect raw response, update collector |
| Requests refused | Rate-limited or blocked | Slow down, verify self-identification + key validity |
| Site builds empty | Nothing written to DB, or reading wrong path | Check DB row count first |
| Duplicates everywhere | Dedup threshold too strict | Relax matching, add semantic comparison |
| Everything scored "critical" | Score weights drifted / bonus applying near-universally | Recalibrate against a known quiet day |
| An obvious story is missing | Source failed silently, or category not covered | Missed-signal review, then add source |

## 11. Open questions for you to resolve before/during Phase 2

- Confirm Next.js vs plain static HTML for the frontend
- Which 1–2 commercial data providers to use
- Initial watchlist — which companies
- Who owns which repo permissions / secrets
- Rough visual direction for the portfolio-facing site (this doesn't need to be decided yet, but worth a sketch before Phase 4)
