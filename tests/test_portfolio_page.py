"""The Your portfolio page: built from plain script files with no build step, under the same rules as every page."""

import json
import re

import pytest

from pipeline import portfolio_page
from pipeline.db import init_db
from pipeline.portfolio_page import PORTFOLIO_SCRIPTS, portfolio_data, portfolio_scripts
from pipeline.render import SECTOR_METADATA, render_dashboard


@pytest.fixture(scope="module")
def page(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("portfolio")
    db = str(tmp / "t.db")
    init_db(db)
    render_dashboard(output_path=str(tmp / "site" / "index.html"), db_path=db, performance_data={})
    return (tmp / "site" / "portfolio.html").read_text(encoding="utf-8")


def test_the_page_is_rendered_with_its_scripts_inline(page):
    assert "<title>StockPulse — Your portfolio</title>" in page
    assert page.count("<script") == 2, "the theme script and one page script, nothing loaded from elsewhere"
    assert " src=" not in re.sub(r"<link[^>]*>", "", page)
    for name in PORTFOLIO_SCRIPTS:
        first_line = open(f"pipeline/{name}", encoding="utf-8").readline().strip()
        assert first_line in page, name
    assert "{% raw %}" not in page and "{%" not in page


def test_page_data_names_the_site_sectors_and_other_share_classes(page):
    data = json.loads(re.search(r"const PF_DATA = (\{.*?\});\n", page).group(1))
    assert data["sectors"] == list(SECTOR_METADATA)
    assert data["other"] == {"GOOG": "GOOGL"}
    nvda = data["companies"]["NVDA"]
    assert "datacenter_capex" in nvda["th"] and "MSFT" in nvda["cu"] and "TSMC" in nvda["su"] and "AMD" in nvda["co"]
    assert len(data["companies"]) >= 100, "every followed company has an entry, even an empty one"


def test_other_tickers_never_shadow_a_listed_company():
    companies = [{"symbol": "AAA", "other_tickers": ["bbb", "CCC", ""]}, {"symbol": "CCC"}, {"symbol": "DDD", "other_tickers": None}]
    data = portfolio_data(companies, ["X"])
    assert data["sectors"] == ["X"] and data["other"] == {"BBB": "AAA"}


def test_only_what_the_watchlist_says_reaches_the_page():
    companies = [
        {"symbol": "AAA", "macro_sensitivities": ["oil"], "economic_sensitivities": ["inflation"],
         "key_customers": ["bbb", "Outside Co", 7, ""], "key_suppliers": None, "competitors": ["BBB", "ZZZ"]},
        {"symbol": "BBB"},
    ]
    assert portfolio_data(companies, [])["companies"] == {
        "AAA": {"th": ["oil"], "ec": ["inflation"], "cu": ["BBB", "Outside Co"], "co": ["BBB"]},
        "BBB": {},
    }


def test_every_watchlist_company_can_be_picked_and_names_are_escaped(page):
    options = re.findall(r'<option value="([^"]+)">', page)
    assert "NVDA" in options and "BRK-B" in options and len(options) >= 100
    assert "Johnson &amp; Johnson" in page


@pytest.mark.parametrize("banned", ["{% endraw %}", "</script>", "<!-- x"])
def test_a_script_that_could_end_its_block_is_refused(tmp_path, monkeypatch, banned):
    (tmp_path / "bad.js").write_text(f"const x = '{banned}';", encoding="utf-8")
    monkeypatch.setattr(portfolio_page, "_HERE", str(tmp_path))
    with pytest.raises(ValueError):
        portfolio_page._script("bad.js")


def test_the_scripts_build_the_page_without_innerhtml():
    script = portfolio_scripts()
    for unsafe in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval(", "new Function"):
        assert unsafe not in script, unsafe
    assert "textContent" in script
