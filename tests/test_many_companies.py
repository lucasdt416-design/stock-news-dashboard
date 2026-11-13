"""Room for hundreds of companies: adding them by ticker, and a site whose pages stay small."""

import json
import re
from datetime import date
from pathlib import Path

import yaml

from collectors.rate_limit import RateLimiter
from collectors.sec_companies import SIC_SECTORS, build_entries, entries_yaml, sector_for_sic, ticker_index, tidy_name
from pipeline.db import init_db
from pipeline.persist import save_news_items
from pipeline.render import (
    FEED_DAYS, HOME_STORIES_PER_COMPANY, SECTOR_METADATA, _feed_window, _home_data, _valid_watchlist,
    get_company_macro_sector, render_dashboard,
)

TICKERS = {
    "0": {"cik_str": 21344, "ticker": "KO", "title": "COCA COLA CO"},
    "1": {"cik_str": 1067983, "ticker": "BRK-B", "title": "BERKSHIRE HATHAWAY INC"},
    "2": {"cik_str": 732717, "ticker": "T", "title": "AT&T INC."},
    "3": {"cik_str": 77476, "ticker": "PEP", "title": "PEPSICO INC"},
}
SUBMISSIONS = {
    "0000021344": {"name": "COCA COLA CO", "sic": "2080", "sicDescription": "BEVERAGES"},
    "0001067983": {"name": "BERKSHIRE HATHAWAY INC", "sic": "6331", "sicDescription": "FIRE, MARINE & CASUALTY INSURANCE"},
    "0000732717": {"name": "AT&T INC.", "sic": "4813", "sicDescription": "TELEPHONE COMMUNICATIONS"},
}


def test_every_industry_lands_in_a_real_sector():
    for _, _, slug in SIC_SECTORS:
        sector = get_company_macro_sector("ZZZZ", slug)
        assert sector in SECTOR_METADATA and sector != "Other", slug
    assert sector_for_sic("3674") == "semiconductors"
    assert sector_for_sic(2086) == "consumer_staples_beverages"
    assert sector_for_sic(6798) == "real_estate_reit" and get_company_macro_sector("X", "real_estate_reit") == "Real Estate"
    assert sector_for_sic(3021) == "consumer_goods_apparel"
    assert sector_for_sic(5810) == "consumer_discretionary_restaurants"
    assert sector_for_sic("") == "other" and sector_for_sic(None) == "other" and sector_for_sic(9999) == "other"
    assert get_company_macro_sector("ZZZZ", "") == "Other", "an unknown company is not filed under Technology"
    expected = {"telecommunications": "Telecom", "retail_ecommerce": "Retail", "semiconductors": "Technology",
                "software_cloud": "Technology", "utilities_power": "Utilities", "energy_oil_gas": "Energy",
                "aerospace_defense": "Aerospace", "financial_insurance": "Finance", "healthcare_services": "Healthcare",
                "industrials_transport": "Industrials", "consumer_staples_food": "Consumer Staples",
                "consumer_goods_autos": "Consumer Goods", "materials_metals": "Materials", "real_estate_reit": "Real Estate"}
    for slug, sector in expected.items():
        assert get_company_macro_sector("ZZZZ", slug) == sector, slug


def test_capital_names_are_tidied_and_mixed_case_is_left_alone():
    assert tidy_name("COCA COLA CO") == "Coca Cola Co."
    assert tidy_name("AT&T INC.") == "AT&T Inc."
    assert tidy_name("ELI LILLY & Co") == "Eli Lilly & Co."
    assert tidy_name("CSX CORP") == "CSX Corp."
    assert tidy_name("BANK OF AMERICA CORP /DE/") == "Bank of America Corp."
    assert tidy_name("US BANCORP \\DE\\") == "US Bancorp"
    assert tidy_name("Salesforce, Inc.") == "Salesforce, Inc."
    assert tidy_name("NIKE, Inc.") == "NIKE, Inc."


def test_entries_are_built_from_the_sec_lists():
    index = ticker_index(TICKERS)
    entries, notes = build_entries(
        [("KO", None), ("BRK.B", None), ("T", "AT&T"), ("PEP", None), ("NOPE", None), ("KO", None)],
        index, lambda cik: SUBMISSIONS.get(cik) or {}, existing=["PEP"])
    assert [(e["symbol"], e["name"], e["cik"], e["sector"]) for e in entries] == [
        ("KO", "Coca Cola Co.", "0000021344", "consumer_staples_beverages"),
        ("BRK-B", "Berkshire Hathaway Inc.", "0001067983", "financial_insurance"),
        ("T", "AT&T", "0000732717", "telecommunications"),
    ]
    assert any("PEP: already" in n for n in notes) and any("NOPE: not on" in n for n in notes)
    assert any("KO: already" in n for n in notes), "a ticker asked for twice is added once"


def test_a_failed_lookup_still_adds_the_company():
    def broken(cik):
        raise OSError("network down")
    entries, _ = build_entries([("KO", None)], ticker_index(TICKERS), broken, existing=[])
    assert entries[0]["name"] == "Coca Cola Co." and entries[0]["sector"] == "other"


def test_appended_entries_keep_the_watchlist_valid(tmp_path):
    original = Path("data/watchlist.yaml").read_text(encoding="utf-8")
    path = tmp_path / "watchlist.yaml"
    entries, _ = build_entries([("KO", None), ("T", 'Quote " and: colon')], ticker_index(TICKERS),
                               lambda cik: SUBMISSIONS.get(cik) or {}, existing=[])
    path.write_text(original + entries_yaml(entries), encoding="utf-8")
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))["tickers"]
    assert loaded[-1] == {"symbol": "T", "name": 'Quote " and: colon', "cik": "0000732717",
                          "sector": "telecommunications"}
    assert loaded[-2]["symbol"] == "KO" and len(loaded) == len(yaml.safe_load(original)["tickers"]) + 2


def test_bad_watchlist_entries_are_skipped_not_fatal():
    kept = _valid_watchlist([
        {"symbol": "nvda", "name": "NVIDIA"}, {"symbol": "NVDA", "name": "again"}, {"symbol": "<x>", "name": "bad"},
        {"symbol": "AAPL"}, None, {"symbol": "BRK.B", "name": "Berkshire"}, {"symbol": "BRK-B", "name": "same page"},
    ])
    assert [c["symbol"] for c in kept] == ["NVDA", "BRK.B"]
    assert kept[0]["sector"] == ""


def test_the_feed_window_counts_back_from_the_newest_story():
    items = [{"published_date": d, "score": s} for d, s in
             (("2026-01-31", 1), ("2026-01-01", 9), ("2025-12-31", 9), ("2030-01-01", 9), ("", 9))]
    window = _feed_window(items, today=date(2026, 6, 1))
    assert [it["published_date"] for it in window] == ["2026-01-01", "2026-01-31"], "most important first, 30 days back"
    assert _feed_window([], today=date(2026, 6, 1)) == []
    assert FEED_DAYS == 30


def test_home_carries_a_few_stories_per_company():
    companies = [{"symbol": "AAA", "name": "A"}, {"symbol": "BBB", "name": "B", "competitors": ["AAA", "Someone"]}]
    items = [{"item_uid": f"a{i}", "ticker": "AAA", "score": i, "published_date": "2026-05-01",
              "created_at": "2026-05-01 10:00:00", "summary": "x" * 500} for i in range(20)]
    items.append({"item_uid": "b", "ticker": "BBB", "related_tickers_list": ["AAA"], "score": 1,
                  "published_date": "2026-05-02", "created_at": "2026-05-02 10:00:00"})
    data = _home_data(items, companies, today=date(2026, 6, 1))
    aaa = [it for it in data["items"] if it["ticker"] == "AAA"]
    assert len(aaa) == HOME_STORIES_PER_COMPANY and min(it["score"] for it in aaa) == 14
    assert any(it["ticker"] == "BBB" for it in data["items"])
    assert "summary" not in data["items"][0], "only the fields Home uses"
    assert len(data["arrivals"]) == 21 and ["2026-05-02 10:00:00", ["BBB", "AAA"]] in data["arrivals"]
    assert data["companies"][1]["competitors"] == ["AAA"]


def test_rate_limiter_waits_only_when_the_budget_is_spent():
    now = [0.0]
    slept = []

    def sleep(seconds):
        slept.append(seconds)
        now[0] += seconds

    limiter = RateLimiter(3, 60, clock=lambda: now[0], sleep=sleep)
    for _ in range(3):
        limiter.wait()
    assert slept == []
    now[0] = 10.0
    limiter.wait()
    assert slept == [50.0], "the fourth call waits until the first is a minute old"


def _big_site(tmp_path, count=120):
    watchlist = [{"symbol": f"C{i:03d}", "name": f"Company {i}", "sector": "materials_chemicals" if i % 2 else "software_cloud"}
                 for i in range(count)]
    watchlist += [{"symbol": "BRK.B", "name": "Berkshire Hathaway Inc."}, {"symbol": "KO", "name": "Coca Cola Co."}]
    wl_path = tmp_path / "watchlist.yaml"
    wl_path.write_text(yaml.safe_dump({"tickers": watchlist}), encoding="utf-8")
    db = str(tmp_path / "t.db")
    init_db(db)
    items = []
    for i in range(count):
        for n in range(12):
            items.append({"item_uid": f"{i}-{n}", "ticker": f"C{i:03d}", "company_name": f"Company {i}",
                          "source": "sec_edgar", "source_label": "SEC EDGAR", "source_type": "regulatory_filing",
                          "headline": f"Company {i} filing {n}", "summary": "Revenue rose 5% to $2 billion.",
                          "url": f"https://www.sec.gov/{i}/{n}", "published_date": f"2026-{10 if n < 6 else 8}-{n + 1:02d}",
                          "form_or_type": "8-K", "category": "Earnings & Financials", "score": float(n % 10)})
    save_news_items(items, db_path=db)
    out = tmp_path / "site" / "index.html"
    render_dashboard(output_path=str(out), db_path=db, performance_data={}, watchlist_path=str(wl_path))
    return out.parent


def test_a_long_watchlist_gets_one_small_page_per_company(tmp_path):
    site = _big_site(tmp_path)
    pages = sorted(site.glob("company-*.html"))
    assert len(pages) == 122
    assert (site / "company-brk-b.html").exists() and (site / "company-ko.html").exists()
    one = (site / "company-c007.html").read_text(encoding="utf-8")
    assert one.count('class="company-news-item') == 12, "all of its own stories, nobody else's"
    assert "Company 8 filing" not in one
    headers = (site / "_headers").read_text(encoding="utf-8")
    assert len(re.findall(r"^\S", headers, re.M)) < 100
    directory = (site / "company.html").read_text(encoding="utf-8")
    assert 'href="company-brk-b.html"' in directory
    assert "<h2 class=\"company-browser-sector-name\">Materials</h2>" in directory
    assert "<h2 class=\"company-browser-sector-name\">Other</h2>" in directory, "no sector given"


def test_a_long_watchlist_keeps_home_and_the_feed_small(tmp_path):
    site = _big_site(tmp_path)
    feed = (site / "news.html").read_text(encoding="utf-8")
    data = json.loads(re.search(r'<script type="application/json" id="feedData">(.*?)</script>', feed, re.S).group(1))
    assert len(data) == 120 * 6, "the last 30 days only; older stories stay on company pages"
    assert {d["sector"] for d in data} == {"Materials", "Technology"}, "a story takes its company's sector"
    body = feed[:feed.index('<script type="application/json" id="feedData">')]
    assert body.count('<article class="news-row') == 40, "the server writes the first rows; the script builds the rest"
    home = (site / "index.html").read_text(encoding="utf-8")
    home_data = json.loads(re.search(r"const HOME_DATA = (.*?);\n", home).group(1))
    assert len(home_data["items"]) == 120 * HOME_STORIES_PER_COMPANY
    assert len(home) < 2_000_000


def test_a_new_company_shows_no_empty_sections(tmp_path):
    site = _big_site(tmp_path, count=2)
    page = (site / "company-brk-b.html").read_text(encoding="utf-8")
    body = page[page.index('id="profile-BRK.B"'):page.index("</article>")]
    for empty in ("What in the economy affects it", "Customers, suppliers and competitors",
                  "comparative-perf-card", 'class="company-tabs', "company-feed-search-input"):
        assert empty not in body, empty
    assert "No stories recorded for BRK.B in this period." in body


def test_a_long_watchlist_can_be_narrowed_to_one_sector_and_put_in_order(tmp_path):
    site = _big_site(tmp_path)
    directory = (site / "company.html").read_text(encoding="utf-8")
    # One choice per sector that has companies, each with how many, and they add up to the whole list.
    choices = re.findall(r'data-sector="([^"]+)" data-click="setCompanySector"[^>]*>[^<]*<span class="pill-count">(\d+)</span>', directory)
    counts = dict(choices)
    assert counts.pop("ALL") == "122"
    assert sum(int(n) for n in counts.values()) == 122
    for name, count in counts.items():
        section = re.search(rf'<section class="company-browser-sector" data-sector="{re.escape(name)}">(.*?)</section>', directory, re.S)
        assert section and section.group(1).count('<a class="company-browser-card ') == int(count), name
    # Every company carries what the orders need.
    cards = re.findall(r'<a class="company-browser-card [^>]*>', directory)
    assert len(cards) == 122 and all('data-stories="' in c and 'data-ahead="' in c and 'data-name="' in c for c in cards)
    for order in ("listed", "name", "stories"):
        assert f'data-click="sortCompanies" data-sort="{order}"' in directory


def test_the_feed_offers_each_kind_of_story_up_front(tmp_path):
    site = _big_site(tmp_path)
    feed = (site / "news.html").read_text(encoding="utf-8")
    bar = re.search(r'<div class="kind-bar" id="feedKinds".*?</div>', feed, re.S).group(0)
    assert re.findall(r'data-kind="(\w+)"', bar) == ["ALL", "results", "news", "releases", "insider", "filings"]
    # The row is outside the folded-away filters, so it is on show without a click.
    assert feed.index('id="feedKinds"') < feed.index('id="feedFilters"')
