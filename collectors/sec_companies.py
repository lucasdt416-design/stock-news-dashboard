"""Look up companies on the SEC's free lists, so adding one to the watchlist needs only its ticker.

The SEC publishes every listed company's ticker, name and CIK (company_tickers.json) and, per
company, its industry code (SIC). That is enough for a watchlist entry: the name for display, the
CIK for its filings, and a sector worked out from the industry code. No key or account is needed.
"""

import json
import logging
import re
import time
import urllib.request
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
DEFAULT_USER_AGENT = "StockNewsDashboard/1.0 (contact: admin@stocknewsdashboard.local)"

# Industry codes to sector names, first match wins. The names start with a prefix that
# pipeline/render.py maps straight to a macro sector (see SECTOR_PREFIXES there).
SIC_SECTORS: List[Tuple[int, int, str]] = [
    (3674, 3674, "semiconductors"),
    (7370, 7379, "software_cloud"),
    (2833, 2836, "healthcare_pharmaceuticals"),
    (3826, 3826, "healthcare_medical_devices"),
    (3841, 3851, "healthcare_medical_devices"),
    (8000, 8099, "healthcare_services"),
    (6324, 6324, "healthcare_managed_care"),
    (6000, 6199, "financial_banking"),
    (6200, 6299, "financial_investment_banking"),
    (6300, 6411, "financial_insurance"),
    (6500, 6599, "real_estate"),
    (6798, 6798, "real_estate_reit"),
    (6700, 6799, "financial_holding"),
    (1300, 1399, "energy_oil_gas"),
    (2900, 2999, "energy_oil_gas"),
    (1000, 1499, "materials_mining"),
    (2600, 2699, "materials_paper_packaging"),
    (2800, 2829, "materials_chemicals"),
    (2840, 2844, "consumer_staples_household"),
    (2850, 2899, "materials_chemicals"),
    (3200, 3299, "materials_building"),
    (3300, 3399, "materials_metals"),
    (2080, 2086, "consumer_staples_beverages"),
    (2000, 2099, "consumer_staples_food"),
    (2100, 2199, "consumer_staples_tobacco"),
    (2200, 2399, "consumer_goods_apparel"),
    (3021, 3021, "consumer_goods_apparel"),
    (3000, 3099, "materials_plastics"),
    (3100, 3199, "consumer_goods_apparel"),
    (3711, 3716, "consumer_goods_autos"),
    (3940, 3949, "consumer_goods_leisure"),
    (1531, 1531, "consumer_goods_homebuilders"),
    (3720, 3729, "aerospace_defense"),
    (3760, 3769, "aerospace_defense"),
    (3812, 3812, "aerospace_defense"),
    (3570, 3579, "tech_hardware"),
    (3600, 3699, "tech_hardware"),
    (3500, 3569, "industrials_machinery"),
    (3580, 3599, "industrials_machinery"),
    (3700, 3799, "industrials_transport_equipment"),
    (1500, 1799, "industrials_construction"),
    (4000, 4799, "industrials_transport"),
    (4833, 4833, "entertainment_media"),
    (4800, 4899, "telecommunications"),
    (4900, 4999, "utilities_power"),
    (5000, 5199, "industrials_distribution"),
    (5810, 5813, "consumer_discretionary_restaurants"),
    (5961, 5961, "retail_ecommerce"),
    (5331, 5331, "retail_consumer_staples"),
    (5399, 5399, "retail_consumer_staples"),
    (5400, 5499, "retail_consumer_staples"),
    (5912, 5912, "retail_consumer_staples"),
    (5200, 5999, "retail_general"),
    (7000, 7099, "consumer_goods_leisure"),
    (7900, 7999, "consumer_goods_leisure"),
    (7800, 7899, "entertainment_media"),
    (2700, 2799, "entertainment_media"),
    (7300, 7369, "industrials_services"),
    (8700, 8799, "industrials_services"),
]

SMALL_WORDS = {"a", "an", "and", "as", "at", "for", "in", "of", "on", "or", "the", "to"}
SUFFIXES = {"inc": "Inc.", "corp": "Corp.", "co": "Co.", "ltd": "Ltd.", "plc": "plc", "lp": "L.P.", "nv": "N.V.",
            "sa": "S.A.", "ag": "AG", "se": "SE", "llc": "LLC", "hldgs": "Holdings", "grp": "Group", "intl": "International"}


def sector_for_sic(sic: Any) -> str:
    """The sector name for an SEC industry code, or "other" when the code is missing or unknown."""
    try:
        code = int(str(sic).strip())
    except (TypeError, ValueError):
        return "other"
    for low, high, sector in SIC_SECTORS:
        if low <= code <= high:
            return sector
    return "other"


def tidy_name(name: str) -> str:
    """SEC names are often in capitals ("COCA COLA CO"). Make those readable; leave mixed case alone."""
    name = re.sub(r"\s+", " ", str(name or "")).strip().rstrip("/").strip()
    name = re.sub(r"\s*/[A-Z]{2}/?$", "", name)  # state suffixes like "/DE/"
    letters = [c for c in name if c.isalpha()]
    if not letters or sum(c.isupper() for c in letters) / len(letters) < 0.8:
        return name
    words = []
    for i, raw in enumerate(name.split(" ")):
        bare = raw.strip(".,").lower()
        if bare in SUFFIXES and i > 0:
            words.append(SUFFIXES[bare])
        elif "&" in raw or (len(bare) <= 3 and not re.search(r"[aeiouy]", bare)):
            words.append(raw.upper())  # AT&T, IBM, CSX
        elif bare in SMALL_WORDS and i > 0:
            words.append(bare)
        else:
            words.append("-".join(part.capitalize() for part in raw.lower().split("-")))
    return " ".join(words)


def ticker_index(tickers_json: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """company_tickers.json, keyed by ticker. The SEC writes BRK-B where others write BRK.B."""
    index = {}
    for row in (tickers_json or {}).values():
        ticker = str(row.get("ticker") or "").upper()
        if ticker and ticker not in index:
            index[ticker] = {"cik": str(row.get("cik_str") or "").zfill(10), "name": row.get("title") or ticker}
    return index


def find_ticker(index: Dict[str, Dict[str, Any]], symbol: str) -> Optional[str]:
    symbol = symbol.upper().strip()
    for candidate in (symbol, symbol.replace(".", "-"), symbol.replace("-", ".")):
        if candidate in index:
            return candidate
    return None


def build_entries(
    requests: List[Tuple[str, Optional[str]]],
    index: Dict[str, Dict[str, Any]],
    submissions: Callable[[str], Dict[str, Any]],
    existing: List[str],
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Watchlist entries for (ticker, optional name) pairs, and a note for each one skipped."""
    entries, notes = [], []
    have = {s.upper() for s in existing}
    for symbol, name in requests:
        found = find_ticker(index, symbol)
        if not found:
            notes.append(f"{symbol}: not on the SEC's list of listed companies, so skipped")
            continue
        if found in have:
            notes.append(f"{found}: already on the watchlist")
            continue
        info = index[found]
        try:
            details = submissions(info["cik"]) or {}
        except Exception as exc:  # one failed lookup shouldn't stop the rest
            logger.warning("Could not read SEC details for %s: %s", found, exc)
            details = {}
        entries.append({
            "symbol": found,
            "name": name or tidy_name(details.get("name") or info["name"]),
            "cik": info["cik"],
            "sector": sector_for_sic(details.get("sic")),
            "industry": details.get("sicDescription") or "",
        })
        have.add(found)
    return entries, notes


def entries_yaml(entries: List[Dict[str, Any]]) -> str:
    """The entries as text to append under tickers:, matching the watchlist's own layout."""
    out = []
    for e in entries:
        out += [
            "",
            f"  - symbol: {e['symbol']}",
            f"    name: {json.dumps(e['name'])}",
            f"    cik: \"{e['cik']}\"",
            f"    sector: {e['sector']}",
        ]
        if e.get("industry"):
            out.append(f"    notes: {json.dumps('SEC industry: ' + e['industry'].title())}")
    return "\n".join(out) + "\n"


def fetch_json(url: str, user_agent: str = DEFAULT_USER_AGENT, timeout: int = 20) -> Dict[str, Any]:
    req = urllib.request.Request(url, headers={"User-Agent": user_agent, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def sec_submissions(user_agent: str = DEFAULT_USER_AGENT, delay_seconds: float = 0.15) -> Callable[[str], Dict[str, Any]]:
    """A polite reader for the SEC's per-company file (the SEC asks for at most 10 requests a second)."""
    def read(cik: str) -> Dict[str, Any]:
        time.sleep(delay_seconds)
        return fetch_json(SUBMISSIONS_URL.format(cik=cik), user_agent)
    return read
