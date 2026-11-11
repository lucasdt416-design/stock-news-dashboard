"""The history function names sectors with the same words the rest of the site uses."""

import re
from pathlib import Path

from pipeline.render import SECTOR_METADATA

SOURCE = (Path(__file__).resolve().parent.parent / "functions" / "api" / "history.js").read_text(encoding="utf-8")


def _table():
    block = re.search(r"export const INDUSTRY_SECTORS = \{(.*?)\n\};", SOURCE, re.S).group(1)
    return dict(re.findall(r'^\s*"([^"]+)": "([^"]+)",$', block, re.M))


def test_every_industry_maps_to_a_sector_the_site_has():
    table = _table()
    assert len(table) >= 40
    for industry, sector in table.items():
        assert sector in SECTOR_METADATA and sector != "Other", (industry, sector)


def test_the_function_and_the_collector_read_yahoo_the_same_way():
    # Both keep finished months only and refuse anything that isn't a dollar stock or fund.
    for needle in ("month >= currentMonth", 'meta.currency !== "USD"', 'meta.dataGranularity !== "1mo"',
                   "period1=0&period2=", "toPrecision(6)"):
        assert needle in SOURCE, needle
