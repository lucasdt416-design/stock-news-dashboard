#!/usr/bin/env python3
"""Build a synthetic demo database and render the site from it, with no API keys or network.

Everything here is invented for visual review. Headlines are deliberately generic, news items
are credited to "Demo Wire", links point at example.com, and prices are a seeded random walk.
Economy figures and release dates come from saved copies of the real sources in tests/fixtures/economy.

Usage:
    python scripts/build_demo.py [--db data/demo.db] [--site .capture/site]
"""

import argparse
import datetime as dt
import json
import os
import random
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.environ.get("STOCKPULSE_ROOT") or ROOT)

import yaml  # noqa: E402

from pipeline.calendar import calculate_relative_badge, format_display_date, init_calendar_schema  # noqa: E402
from pipeline.db import get_db_connection, init_db  # noqa: E402
from pipeline.economic import collect_economic_indicators, collect_economic_releases, snapshot_fetch  # noqa: E402
from pipeline.health import init_health_schema  # noqa: E402
from pipeline.persist import save_news_items  # noqa: E402
from pipeline.render import render_dashboard  # noqa: E402
from pipeline.score import score_item  # noqa: E402

SEED = 20260925
WATCHLIST = os.path.join(ROOT, "data", "watchlist.yaml")

# (category, form, source, headline template, takeaway template)
STORIES = [
    ("Earnings & Financials", "8-K", "sec_edgar", "SEC Form 8-K ({low}-8k.htm)",
     "{name} reported quarterly results; review revenue and margin against prior guidance."),
    ("Earnings & Financials", "10-Q", "sec_edgar", "SEC Form 10-Q ({low}-10q.htm)",
     "Routine quarterly report. Check the risk-factor changes before anything else."),
    ("Insider Transactions", "4", "sec_edgar", "SEC Form 4 ({low}-form4.xml)",
     "An officer reported a share transaction under a pre-arranged trading plan; usually routine."),
    ("Insider Transactions", "144", "sec_edgar", "SEC Form 144 ({low}-xsl144.xml)",
     "Notice of a proposed insider sale. Size matters more than the filing itself."),
    ("Regulation & Policy / Litigation", "NEWS", "news_media", "Regulators open a review touching {name}",
     "A review adds uncertainty but rarely changes near-term numbers; watch for a timeline."),
    ("Leadership & Governance", "8-K", "company_ir", "{name} announces a change to its leadership team",
     "Leadership changes matter most when the reason is unstated. Read the full release."),
    ("Supplier & Customer Intelligence", "NEWS", "news_media", "{name} supplier outlines capacity plans for next year",
     "Supplier commentary is an early read on demand, one step removed from the company."),
    ("Product Launches & Technology", "PRESS", "company_ir", "{name} introduces an updated product line",
     "A launch on its own rarely moves estimates; pricing and availability will."),
    ("Capital Structure & Offerings", "8-K", "company_ir", "{name} prices a new senior notes offering",
     "New debt is normal for its size. The rate paid is the useful signal here."),
    ("Guidance & Commentary", "NEWS", "news_media", "Analysts revisit {name} estimates after management commentary",
     "Estimate changes follow the news rather than lead it, so treat this as context."),
]

EVENTS = [
    ("Earnings Call / Results", "SOURCED", "{name} quarterly earnings call", "Results and guidance update."),
    ("Dividend (Payment/Record)", "SOURCED", "{name} ex-dividend date", "Shareholders of record receive the declared dividend."),
    ("Statutory SEC Deadline (Estimated)", "ESTIMATED_RULE", "{name} 10-Q filing deadline", "Based on the SEC filing calendar."),
    ("Investor Conference", "SOURCED", "{name} presents at an investor conference", "Management presentation and audience questions."),
]

CROSS_REF = [
    ("Customer", "{rel} is a key customer of {sym}"),
    ("Supplier", "{rel} is a key supplier to {sym}"),
]


def load_watchlist():
    with open(WATCHLIST, "r", encoding="utf-8") as f:
        return (yaml.safe_load(f) or {}).get("tickers", [])


def make_items(companies, today, rng):
    items = []
    weights = [max(1, 9 - i // 3) for i in range(len(companies))]
    for n in range(120):
        co = rng.choices(companies, weights=weights)[0]
        cat, form, source, head, take = rng.choice(STORIES)
        sym, name = co["symbol"], co["name"]
        age = int(rng.triangular(0, 42, 3))
        pub = today - dt.timedelta(days=age)
        label = {"sec_edgar": "SEC EDGAR", "company_ir": "Company Release", "news_media": "Demo Wire"}[source]
        kind = {"sec_edgar": "regulatory_filing", "company_ir": "company_announcement", "news_media": "press"}[source]
        peers = [c["symbol"] for c in companies if c["symbol"] != sym]
        refs = []
        for rel in rng.sample(peers, k=rng.choice([0, 0, 0, 1, 2, 5])):
            relation, note = rng.choice(CROSS_REF)
            refs.append({
                "related_ticker": rel, "related_company": rel, "relation_type": relation,
                "matched_entity": rel, "impact_note": note.format(rel=rel, sym=sym),
            })
        item = {
            "item_uid": f"demo-{n:03d}",
            "ticker": sym,
            "company_name": name,
            "source": source,
            "source_label": label,
            "source_type": kind,
            "headline": head.format(name=name, low=sym.lower()),
            "summary": f"{name} said revenue reached ${rng.randint(2, 90)}.{rng.randint(1, 9)} billion, "
                       f"{rng.randint(2, 31)}% more than a year ago. Synthetic demo record.",
            "url": f"https://example.com/demo/{sym.lower()}/{n}",
            "published_date": pub.isoformat(),
            "published_time": f"{rng.randint(6, 21):02d}:{rng.choice(['00', '15', '30', '45'])}:00",
            "form_or_type": form,
            "raw_id": f"demo-{n}",
            "category": cat,
            "llm_summary": take.format(name=name),
            "related_tickers": [r["related_ticker"] for r in refs],
            "cross_references": refs,
            "cross_ref_summary": "; ".join(r["impact_note"] for r in refs),
        }
        items.append(score_item(item))
    # Stress fixtures: an ampersand-heavy long headline, and an HTML payload that must stay inert.
    long_item = dict(items[0], item_uid="demo-long", url="https://example.com/demo/long",
                     headline="Procter & Gamble's fabric & home care unit reviews a multi-year supply arrangement "
                              "covering several regions, packaging lines & regional distributors",
                     ticker="PG", company_name="The Procter & Gamble Company", source="news_media",
                     source_label="Demo Wire", source_type="press", form_or_type="NEWS")
    xss_item = dict(items[1], item_uid="demo-xss", url="https://example.com/demo/xss",
                    headline="Demo escaping check for company text", score=0.5,
                    summary='Escaping check at $5 billion <img src=x onerror="window.__xss=1"> stays inert.',
                    llm_summary='Escaping check <img src=x onerror="window.__xss=1"> & "quotes" stay inert.',
                    category='Demo <img src=x onerror="window.__xss=1">')
    items += [score_item(long_item), xss_item]
    return items


def seed_calendar(conn, companies, today, rng):
    init_calendar_schema(conn)
    now = dt.datetime.now().isoformat()
    picks = rng.sample(companies, k=min(24, len(companies)))
    # A separate generator, so changing event dates leaves the demo's prices and run counts alone.
    date_rng = random.Random(SEED + 1)
    rows = []
    for i, co in enumerate(picks):
        etype, stype, head, details = EVENTS[i % len(EVENTS)]
        # Real calendars cluster around earnings season, so the demo should not be evenly spaced.
        offset = 1 if i == 0 else int(date_rng.triangular(2, 62, 18))
        rows.append((co, etype, stype, head.format(name=co["name"]), details, today + dt.timedelta(days=offset)))
    # An inert payload in event text, so the search dropdown's escaping is exercised.
    rows.append((picks[0], "Investor Conference", "SOURCED", 'Demo event <img src=x onerror="window.__xss=1">',
                 "Must render as text.", today + dt.timedelta(days=80)))
    for co, etype, stype, head, details, date in rows:
        conn.execute(
            """INSERT INTO calendar_events (ticker, company_name, event_type, source_type, event_date,
               display_date, relative_badge, headline, details, source_url, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (co["symbol"], co["name"], etype, stype, date.isoformat(), format_display_date(date.isoformat()),
             calculate_relative_badge(date.isoformat(), today), head, details,
             f"https://example.com/demo/cal/{co['symbol'].lower()}", now),
        )


def seed_runs(conn, today, rng):
    init_health_schema(conn)
    for i in range(5, 0, -1):
        day = today - dt.timedelta(days=i - 1)
        edgar, ir, news = rng.randint(40, 70), rng.randint(5, 15), rng.randint(20, 50)
        total = edgar + ir + news
        conn.execute(
            """INSERT INTO pipeline_runs (run_timestamp, edgar_count, company_ir_count, news_media_count, total_raw,
               total_unique, high_impact_count, status, health_message, moving_avg_raw)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (f"{day.isoformat()}T11:04:00", edgar, ir, news, total, int(total * 0.7), rng.randint(3, 9),
             "HEALTHY", "Demo run: all sources returned items.", round(total * 0.98, 1)),
        )


def walk(symbol, today, rng, days=64):
    price = rng.uniform(40, 600)
    drift = rng.uniform(-0.002, 0.003)
    series = []
    for i in range(days):
        day = today - dt.timedelta(days=days - i)
        price *= 1 + rng.gauss(drift, 0.014)
        series.append({"date": day.isoformat(), "timestamp": int(dt.datetime(day.year, day.month, day.day).timestamp()),
                       "close": round(price, 2)})
    base = series[0]["close"]
    for pt in series:
        pt["pct_change"] = round((pt["close"] - base) / base * 100, 2)
    return {"symbol": symbol, "latest_price": series[-1]["close"], "base_price": base,
            "total_pct_change": series[-1]["pct_change"], "series": series}


def make_performance(companies, today, rng):
    """Same shape as collectors.stock_prices.collect_comparative_performance, but synthetic."""
    spy = walk("SPY", today, rng)
    bundles = {}
    for co in companies:
        sym = co["symbol"]
        target = walk(sym, today, rng)
        comps = [c for c in co.get("competitors", []) if isinstance(c, str) and c.isupper() and len(c) <= 5][:3]
        comp_hist = [walk(c, today, rng) for c in comps]
        avg = round(sum(c["total_pct_change"] for c in comp_hist) / len(comp_hist), 2) if comp_hist else 0.0
        vs_peers = round(target["total_pct_change"] - avg, 2)
        if vs_peers >= 8:
            assessment, kind = "Strong Outperformance vs Peers", "positive"
        elif vs_peers <= -8:
            assessment, kind = "Lagging Peer Group", "negative"
        elif abs(vs_peers) < 4:
            assessment, kind = "In-Line with Competitors", "neutral"
        elif vs_peers > 0:
            assessment, kind = "Moderate Outperformance", "positive"
        else:
            assessment, kind = "Moderate Underperformance", "negative"
        bundles[sym] = {
            "symbol": sym, "name": co.get("name", sym), "sector": co.get("sector", ""), "target": target,
            "competitors": comp_hist, "benchmark": spy, "avg_competitor_pct": avg, "alpha_vs_peers": vs_peers,
            "alpha_vs_spy": round(target["total_pct_change"] - spy["total_pct_change"], 2),
            "assessment": assessment, "assessment_type": kind,
        }
    return {"benchmark": spy, "companies": bundles}


def build(db_path, site_dir):
    for key in ("FRED_API_KEY", "GEMINI_API_KEY", "FINNHUB_API_KEY"):
        os.environ.pop(key, None)
    if os.path.exists(db_path):
        os.remove(db_path)
    rng = random.Random(SEED)
    today = dt.date.today()
    companies = load_watchlist()
    init_db(db_path)
    save_news_items(make_items(companies, today, rng), db_path=db_path)
    conn = get_db_connection(db_path)
    with conn:
        seed_calendar(conn, companies, today, rng)
        seed_runs(conn, today, rng)
    conn.close()
    economy = snapshot_fetch(os.path.join(ROOT, "tests", "fixtures", "economy"))
    collect_economic_indicators(db_path=db_path, fetch=economy)
    collect_economic_releases(db_path=db_path, fetch=economy, today=dt.date(2026, 11, 6))
    perf = make_performance(companies, today, rng)
    os.makedirs(site_dir, exist_ok=True)
    render_dashboard(output_path=os.path.join(site_dir, "index.html"), db_path=db_path, performance_data=perf)
    return json.dumps({"db": db_path, "site": site_dir, "companies": len(companies)})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=os.path.join(ROOT, "data", "demo.db"))
    parser.add_argument("--site", default=os.path.join(ROOT, ".capture", "site"))
    args = parser.parse_args()
    print(build(os.path.abspath(args.db), os.path.abspath(args.site)))
