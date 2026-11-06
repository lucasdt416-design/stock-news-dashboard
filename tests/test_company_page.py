"""Company page: latest results from the filing, stories in tabs, insider trades in one line."""

import re
from pathlib import Path

from pipeline.db import init_db
from pipeline.persist import save_news_items
from pipeline.render import _insider_rollup, _latest_results, render_dashboard

TENK = ("Year ended Sep 26, 2026: revenue $478.8 billion, up 15%; net income $132.2 billion, up 18%; "
        "diluted earnings per share $8.98, up 20%. Changes are against the same period a year earlier.")
TENQ_LOSS = "Quarter ended Sep 30, 2026: revenue $24.2 billion, up 4%; net loss $116.0 million; diluted earnings per share -$0.26."


def _filing(uid, ticker, form, summary, date="2026-11-03", category="Earnings & Financials"):
    return {"item_uid": uid, "ticker": ticker, "company_name": ticker, "source": "sec_edgar", "source_label": "SEC EDGAR",
            "source_type": "regulatory_filing", "headline": f"{ticker} {form}", "summary": summary,
            "url": f"https://www.sec.gov/{uid}", "published_date": date, "form_or_type": form, "category": category, "score": 5.0}


def test_latest_results_reads_the_filing_sentence():
    r = _latest_results("AAPL", [_filing("a", "AAPL", "10-K", TENK)])
    assert r["period"] == "Year ended Sep 26, 2026"
    assert [(f["label"], f["value"], f["change"], f["tone"]) for f in r["figures"]] == [
        ("Revenue", "$478.8 billion", "up 15%", "tone-up"),
        ("Net income", "$132.2 billion", "up 18%", "tone-up"),
        ("Earnings per share", "$8.98", "up 20%", "tone-up"),
    ]
    assert r["compared"]


def test_latest_results_handles_a_loss_without_inventing_a_change():
    r = _latest_results("BA", [_filing("b", "BA", "10-Q", TENQ_LOSS)])
    figs = {f["label"]: f for f in r["figures"]}
    assert figs["Net loss"]["value"] == "$116.0 million" and figs["Net loss"]["change"] == ""
    assert figs["Earnings per share"]["value"] == "-$0.26"


def test_latest_results_uses_the_newest_report_of_that_company_only():
    older = TENK.replace("$478.8", "$400.0")
    items = [
        _filing("old", "AAPL", "10-Q", older.replace("Year", "Quarter"), date="2026-08-01"),
        _filing("new", "AAPL", "10-K", TENK, date="2026-11-03"),
        _filing("other", "MSFT", "10-Q", TENK.replace("$478.8", "$999.9"), date="2026-11-05"),
    ]
    assert _latest_results("AAPL", items)["figures"][0]["value"] == "$478.8 billion"


def test_no_results_rather_than_a_guess():
    assert _latest_results("AAPL", []) is None
    assert _latest_results("AAPL", [_filing("x", "AAPL", "10-Q", "Official SEC submission (10-Q). Accession: 1")]) is None
    assert _latest_results("AAPL", [_filing("y", "AAPL", "8-K", TENK)]) is None


def _trade(uid, text, date="2026-10-01", ticker="AAPL"):
    return _filing(uid, ticker, "4", text, date=date, category="Insider Transactions")


def test_insider_rollup_adds_up_sales_and_plans():
    items = [
        _trade("1", "Jennifer Newstead (SVP) sold 2,399 shares at $325.75, about $781,474, under a pre-arranged trading plan. Now holds 29,997 shares.", "2026-08-11"),
        _trade("2", "Timothy D Cook (Executive Chair) sold 191,753 shares at an average of $332.96, about $63.8 million, under a pre-arranged trading plan."),
        _trade("3", "Sabih Khan (COO) was granted 47,645 restricted stock units."),
        _trade("4", "Someone else sold 10 shares at $1.00, about $1.5 billion.", ticker="MSFT"),
    ]
    r = _insider_rollup("AAPL", items)
    assert r["sentence"] == "Insiders sold about $64.6 million in 2 trades, all pre-arranged. No open-market purchases."
    assert r["since"] == "2026-08-11" and r["count"] == 3


def test_insider_rollup_mixes_purchases_and_unplanned_sales():
    items = [
        _trade("1", "A (Director) bought 1,000 shares at $50.00, about $50,000."),
        _trade("2", "B (CFO) sold 2,000 shares at $60.00, about $120,000, under a pre-arranged trading plan."),
        _trade("3", "C (CEO) sold 1,000 shares at $60.00, about $60,000."),
    ]
    sentence = _insider_rollup("X", [dict(i, ticker="X") for i in items])["sentence"]
    assert sentence == "Insiders sold about $180,000 in 2 trades, 1 of them pre-arranged, and bought about $50,000 in 1 trade."


def test_insider_rollup_without_trades_says_so():
    r = _insider_rollup("AAPL", [_trade("1", "Sabih Khan (COO) was granted 47,645 restricted stock units.")])
    assert r["sentence"] == "1 insider filing, none an open-market trade."
    assert _insider_rollup("AAPL", []) is None


def _site(tmp_path, items):
    db = str(tmp_path / "t.db")
    init_db(db)
    save_news_items(items, db_path=db)
    out = tmp_path / "site" / "index.html"
    render_dashboard(output_path=str(out), db_path=db, performance_data={})
    return (out.parent / "company.html").read_text(encoding="utf-8")


def test_company_page_has_tabs_results_and_rollup(tmp_path):
    html = _site(tmp_path, [
        _filing("k", "AAPL", "10-K", TENK),
        _trade("t", "Jennifer Newstead (SVP) sold 2,399 shares at $325.75, about $781,474, under a pre-arranged trading plan."),
    ])
    profile = html[html.index('id="profile-AAPL"'):html.index('id="profile-', html.index('id="profile-AAPL"') + 20)]
    assert "Latest results" in profile and "$478.8 billion" in profile
    for tab in ("news", "filings", "insider"):
        assert f'data-click="setCompanyTab" data-ticker="AAPL" data-tab="{tab}"' in profile
    assert re.search(r'<p class="company-rollup" data-tab-only="insider"[^>]*>Insiders sold about \$781,474 in 1 trade, pre-arranged\.', profile)
    # Without JavaScript every story stays visible: nothing is hidden by the server.
    assert not re.search(r'<article class="company-news-item[^"]*"[^>]*hidden', profile)
    assert "company-kpi-ribbon" not in profile


def test_company_page_without_a_report_shows_no_results_section(tmp_path):
    html = _site(tmp_path, [])
    profile = html[html.index('id="profile-NVDA"'):html.index('id="profile-', html.index('id="profile-NVDA"') + 20)]
    assert "Latest results" not in profile
