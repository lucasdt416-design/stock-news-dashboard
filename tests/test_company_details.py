"""Customers, suppliers and competitors: each company once, real companies only, nothing out of date."""

import re
from pathlib import Path

import yaml

from pipeline.crossref import apply_supply_chain_cross_references, mentions, short_name
from pipeline.db import init_db
from pipeline.render import render_dashboard

DATA = yaml.safe_load(Path("data/watchlist.yaml").read_text(encoding="utf-8"))
WATCHLIST = DATA["tickers"]
ALIASES = DATA["aliases"]
KNOWN = {c["symbol"] for c in WATCHLIST}
LISTS = ("key_customers", "key_suppliers", "competitors")

# Checked 2026-11-08: these are gone, renamed, merged or not companies at all.
OUT_OF_DATE = {"WBA", "MTU", "BLL", "BERY", "Spirit AeroSystems", "SPR", "AmerisourceBergen", "Raytheon",
               "Hertz", "Samsung Foundry", "Catalent"}
NOT_COMPANIES = re.compile(r"consumers|members|shoppers|subscribers|guests|operators|clients|depositors|borrowers|"
                           r"advertisers|developers|creators|fortune 500|ecosystem|ratepayers|homeowners|contractors|"
                           r"managers|drivers|moviegoers|governments|systems|networks|agencies|^enterprise", re.I)


def test_no_company_is_named_twice_in_one_list():
    for c in WATCHLIST:
        for key in LISTS:
            entries = c.get(key) or []
            spellings = [s.lower() for e in entries for s in [e] + ALIASES.get(e, [])]
            assert len(spellings) == len(set(spellings)), (c["symbol"], key, entries)
            for e in entries:
                names = {w["name"].lower() for w in WATCHLIST if w["symbol"] in entries}
                assert e.lower() not in names, f"{c['symbol']}: {e} is on the watchlist, so use its ticker"


def test_only_real_companies_and_nothing_out_of_date():
    for c in WATCHLIST:
        for key in LISTS:
            for e in c.get(key) or []:
                assert e not in OUT_OF_DATE, (c["symbol"], e)
                if e not in KNOWN:
                    assert not NOT_COMPANIES.search(e), (c["symbol"], key, e)
        assert "notes" not in c, f"{c['symbol']}: notes were opinion, and several were out of date"
        assert "hess_acquisition_arbitration" not in (c.get("macro_sensitivities") or [])


def test_every_alias_belongs_to_a_named_company():
    named = {e for c in WATCHLIST for key in LISTS for e in c.get(key) or []}
    assert set(ALIASES) <= named


def test_tickers_match_only_in_capitals():
    assert mentions("Lowe's shares rose; LOW is up", "LOW")
    assert not mentions("prices hit a new low", "LOW")
    assert not mentions("so far, so good", "SO")
    assert not mentions("don't", "T")
    assert mentions("Taiwan Semiconductor said", "taiwan semiconductor")


def test_another_spelling_finds_the_company_once():
    items = [{"ticker": "NVDA", "headline": "Taiwan Semiconductor (TSM) raises prices for NVIDIA", "summary": "",
              "category": "Company Announcement"}]
    out = apply_supply_chain_cross_references(items, watchlist_path="data/watchlist.yaml")
    assert [m["related_ticker"] for m in out[0]["cross_references"]] == ["TSMC"]


def test_company_page_lists_each_company_once(tmp_path):
    db = str(tmp_path / "t.db")
    init_db(db)
    out = tmp_path / "site" / "index.html"
    render_dashboard(output_path=str(out), db_path=db, performance_data={})
    page = (out.parent / "company-nvda.html").read_text(encoding="utf-8")
    box = page[page.index("Customers, suppliers and competitors"):]
    box = box[:box.index("</section>")]
    text = re.sub(r"<[^>]+>", " ", box)
    assert "Microsoft" not in text and text.count("MSFT") == 1, "named once, by ticker, linked"
    assert "TSMC" in text and "Taiwan Semiconductor" not in text and "ASML" not in text


def test_watchlist_names_are_shortened_the_way_news_writes_them():
    assert short_name("Meta Platforms, Inc.") == "Meta"
    assert short_name("JPMorgan Chase & Co.") == "JPMorgan Chase"
    assert short_name("The Goldman Sachs Group, Inc.") == "Goldman Sachs"
    assert short_name("Amazon.com, Inc.") == "Amazon"
    assert short_name("Johnson & Johnson") == "Johnson & Johnson"
    for c in WATCHLIST:
        assert "," not in short_name(c["name"]) and not short_name(c["name"]).endswith("&"), c["name"]


def test_a_partner_named_in_words_is_found():
    items = [{"ticker": "AMD", "headline": "AMD and Meta Advance Strategic Partnership to Power Meta’s Infrastructure",
              "summary": "", "category": "Company Announcement"}]
    out = apply_supply_chain_cross_references(items, watchlist_path="data/watchlist.yaml")
    assert [(m["related_ticker"], m["relation_type"]) for m in out[0]["cross_references"]] == [("META", "Customer")]
