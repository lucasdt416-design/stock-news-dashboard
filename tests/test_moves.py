"""Moves: biggest days, set against the S&P 500 and peers, with what was published around them."""

from datetime import date, timedelta

from pipeline.db import init_db
from pipeline.moves import build_deck, verdict
from pipeline.persist import save_news_items
from pipeline.render import render_dashboard

DAYS = [(date(2026, 8, 3) + timedelta(days=i)).isoformat() for i in range(30)]


def series(symbol, moves):
    """Closes starting at 100, moving by the given percent on given day indexes, else +-0.3% alternating."""
    closes, price = [], 100.0
    for i, d in enumerate(DAYS):
        if i:
            price *= 1 + moves.get(i, 0.3 if i % 2 else -0.3) / 100
        closes.append({"date": d, "close": round(price, 4)})
    return {"symbol": symbol, "series": closes}


def perf():
    return {
        "benchmark": series("SPY", {10: -3.0, 20: 0.1}),
        "companies": {
            "NVDA": {"target": series("NVDA", {10: -3.2, 20: 9.0, 25: -6.0}),
                     "competitors": [series("AMD", {10: -3.0, 25: -6.5}), series("INTC", {10: -2.8, 25: -5.5})]},
            "AAPL": {"target": series("AAPL", {}), "competitors": []},
        },
    }


COMPANIES = [{"symbol": "NVDA", "name": "NVIDIA Corporation"}, {"symbol": "AAPL", "name": "Apple Inc."}]


def test_a_shared_day_is_called_shared_and_a_lone_day_is_its_own():
    assert verdict(-3.2, -3.0, -2.9) == "market"
    assert verdict(-6.0, -0.2, -6.0) == "peers"
    assert verdict(9.0, 0.1, 0.4) == "own"
    assert verdict(-3.2, 0.5, None) == "own", "the market went the other way"
    assert verdict(-1.2, -0.8, None) == "own", "a 0.8% S&P day isn't the market moving"


def test_biggest_days_and_what_was_published_then():
    items = [
        {"ticker": "NVDA", "headline": "NVIDIA reports record revenue", "published_date": DAYS[19], "score": 9.0,
         "source": "sec_edgar", "category": "Earnings & Financials", "url": "https://www.sec.gov/x"},
        {"ticker": "NVDA", "headline": "Weak filler", "published_date": DAYS[20], "score": 2.0, "source": "news_media"},
        {"ticker": "NVDA", "headline": "Too early", "published_date": DAYS[15], "score": 9.0, "source": "news_media"},
    ]
    deck = build_deck(perf(), items, COMPANIES, today=date(2026, 9, 1))
    nvda = next(c for c in deck["cards"] if c["symbol"] == "NVDA")
    days = {d["date"]: d for d in nvda["days"]}
    assert list(days) == [DAYS[10], DAYS[20], DAYS[25]], "in date order, numbered on the chart"
    assert days[DAYS[10]]["verdict"] == "market" and days[DAYS[10]]["market"] == -3.0
    assert days[DAYS[25]]["verdict"] == "peers" and days[DAYS[25]]["peer_names"] == ["AMD", "INTC"]
    jump = days[DAYS[20]]
    assert jump["verdict"] == "own" and jump["move"] == 9.0
    assert [s["headline"] for s in jump["stories"]] == ["NVIDIA reports record revenue"], "the evening before counts; weak and early don't"
    assert jump["stories"][0]["kind"] == "results"
    assert days[DAYS[10]]["stories"] == [], "no story is made up for a day with none"
    assert [d["n"] for d in nvda["chart"]["dots"]] == [1, 2, 3]
    assert nvda["chart"]["stock"].startswith("M") and nvda["chart"]["market"]


def test_quiet_companies_have_no_big_days_and_the_deck_leads_with_what_stood_out():
    deck = build_deck(perf(), [], COMPANIES, today=date(2026, 9, 1))
    aapl = next(c for c in deck["cards"] if c["symbol"] == "AAPL")
    assert aapl["days"] == [] and aapl["typical"] == 0.3
    lead = deck["lead"]
    assert lead["date"] == DAYS[-1] and lead["count"] == 2 and lead["up"] + lead["down"] <= 2


def test_companies_without_prices_or_off_the_watchlist_get_no_card():
    data = perf()
    data["companies"]["ZZZZ"] = data["companies"]["AAPL"]
    data["companies"]["AAPL"] = {"target": {"series": data["benchmark"]["series"][:5]}}
    assert [c["symbol"] for c in build_deck(data, [], COMPANIES)["cards"]] == ["NVDA"]
    assert build_deck({}, [], COMPANIES) == {"cards": [], "lead": None}


def test_the_moves_page(tmp_path):
    db = str(tmp_path / "t.db")
    init_db(db)
    save_news_items([{"item_uid": "m1", "ticker": "NVDA", "company_name": "NVIDIA Corporation", "source": "sec_edgar",
                      "source_label": "SEC EDGAR", "source_type": "regulatory_filing", "headline": "NVIDIA reports record revenue",
                      "summary": "", "url": "https://www.sec.gov/x", "published_date": DAYS[19], "form_or_type": "10-Q",
                      "category": "Earnings & Financials", "score": 9.0}], db_path=db)
    site = tmp_path / "site"
    render_dashboard(output_path=str(site / "index.html"), db_path=db, performance_data=perf())
    page = (site / "moves.html").read_text(encoding="utf-8")
    assert '<article class="move-card" id="move-NVDA" data-ticker="NVDA"' in page
    assert "Its own move: S&amp;P 500 +0.1%" in page and "With the market: S&amp;P 500 −3.0%" in page
    assert "With its peers: AMD, INTC" in page
    assert "NVIDIA reports record revenue" in page and "Results, day before" in page
    assert "No stories saved from that day or the day before." in page
    assert '<a href="moves.html" class="mobile-tab-link' in page
    home = (site / "index.html").read_text(encoding="utf-8")
    assert 'href="moves.html"' in home

    render_dashboard(output_path=str(site / "index.html"), db_path=db, performance_data={})
    assert "No prices yet" in (site / "moves.html").read_text(encoding="utf-8")
