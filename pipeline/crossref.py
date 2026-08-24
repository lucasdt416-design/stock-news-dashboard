"""Supplier / Customer Cross-Reference Intelligence Engine (Category #12).

Cross-references disclosures and news items across watchlist supply chains:
- Identifies when a disclosure about Company A (or third-party supplier/customer)
  materially impacts Company B based on key_customers and key_suppliers in watchlist.yaml.
- Tags items with related_tickers, structured relationship metadata, and UI badge summaries.
- Allows filtering by a ticker to surface both direct disclosures and critical supply-chain intelligence.
"""

import logging
import re
from typing import Any, Dict, List, Set

logger = logging.getLogger(__name__)

# Common non-company stopwords to avoid false-positive supply chain matches
GENERIC_STOPWORDS = {
    "retail", "enterprise", "government", "governments", "consumers",
    "corporations", "utilities", "industrial", "hospitals", "hospital",
    "commercial", "creators", "advertisers", "developers", "fleet",
    "global", "prime", "moviegoers", "visitors", "borrowers", "depositors"
}


def build_supply_chain_index(watchlist: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Build fast lookup indexes for customers, suppliers, and ticker/name aliases."""
    customers_by_ticker: Dict[str, List[str]] = {}
    suppliers_by_ticker: Dict[str, List[str]] = {}
    ticker_to_name: Dict[str, str] = {}
    name_to_ticker: Dict[str, str] = {}

    for co in watchlist:
        sym = co.get("symbol", "")
        name = co.get("name", "")
        ticker_to_name[sym] = name

        # Map common clean company names
        clean_name = re.sub(r"\b(Inc\.|Corporation|Corp\.|Co\.|Company|Platforms|Holdings|The|Group)\b", "", name, flags=re.IGNORECASE).strip()
        if clean_name:
            name_to_ticker[clean_name.lower()] = sym
        name_to_ticker[sym.lower()] = sym

        customers_by_ticker[sym] = [
            str(c).strip() for c in co.get("key_customers", [])
            if str(c).strip().lower() not in GENERIC_STOPWORDS and len(str(c).strip()) >= 2
        ]
        suppliers_by_ticker[sym] = [
            str(s).strip() for s in co.get("key_suppliers", [])
            if str(s).strip().lower() not in GENERIC_STOPWORDS and len(str(s).strip()) >= 2
        ]

    return {
        "customers_by_ticker": customers_by_ticker,
        "suppliers_by_ticker": suppliers_by_ticker,
        "ticker_to_name": ticker_to_name,
        "name_to_ticker": name_to_ticker,
        "watchlist": watchlist,
    }


def find_supply_chain_matches_for_item(
    item: Dict[str, Any],
    sc_index: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Scan a news item's headline and summary for customer/supplier connections across the watchlist."""
    item_ticker = item.get("ticker", "")
    headline = item.get("headline", "")
    summary = item.get("summary", "") or ""
    llm_summary = item.get("llm_summary", "") or ""
    full_text = f"{headline} {summary} {llm_summary}"

    matches: List[Dict[str, Any]] = []
    seen_links: Set[str] = set()

    customers_by_ticker = sc_index["customers_by_ticker"]
    suppliers_by_ticker = sc_index["suppliers_by_ticker"]
    ticker_to_name = sc_index["ticker_to_name"]

    for target_co in sc_index["watchlist"]:
        target_sym = target_co.get("symbol")
        if target_sym == item_ticker:
            continue

        target_name = ticker_to_name.get(target_sym, target_sym)

        # 1. Check if item_ticker is a key customer of target_sym
        # (e.g. Item is about MSFT, MSFT is a customer of NVDA => Cross-ref NVDA)
        for cust_entity in customers_by_ticker.get(target_sym, []):
            pattern = rf"\b{re.escape(cust_entity)}\b"
            # Match either exact ticker or entity name in full text
            if cust_entity.upper() == item_ticker or re.search(pattern, full_text, re.IGNORECASE):
                link_key = f"{target_sym}|Customer"
                if link_key not in seen_links:
                    seen_links.add(link_key)
                    matches.append({
                        "related_ticker": target_sym,
                        "related_company": target_name,
                        "relation_type": "Customer",
                        "matched_entity": cust_entity,
                        "impact_note": f"{cust_entity} is a key customer of {target_sym}",
                    })

        # 2. Check if item_ticker is a key supplier to target_sym
        # (e.g. Item is about KO, KO is a supplier to WMT => Cross-ref WMT)
        for supp_entity in suppliers_by_ticker.get(target_sym, []):
            pattern = rf"\b{re.escape(supp_entity)}\b"
            if supp_entity.upper() == item_ticker or re.search(pattern, full_text, re.IGNORECASE):
                link_key = f"{target_sym}|Supplier"
                if link_key not in seen_links:
                    seen_links.add(link_key)
                    matches.append({
                        "related_ticker": target_sym,
                        "related_company": target_name,
                        "relation_type": "Supplier",
                        "matched_entity": supp_entity,
                        "impact_note": f"{supp_entity} is a key supplier to {target_sym}",
                    })

    return matches


def apply_supply_chain_cross_references(
    items: List[Dict[str, Any]],
    watchlist: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Process news items, tagging each with relevant supply-chain cross-references."""
    if not items or not watchlist:
        return items

    sc_index = build_supply_chain_index(watchlist)
    cross_ref_count = 0

    for it in items:
        matches = find_supply_chain_matches_for_item(it, sc_index)
        if matches:
            cross_ref_count += len(matches)
            related_tickers = sorted(list(set(m["related_ticker"] for m in matches)))
            it["related_tickers"] = related_tickers
            it["cross_references"] = matches

            # Create clean human-readable summary badges
            badge_parts = []
            for m in matches:
                badge_parts.append(f"🔗 {m['related_ticker']} ({m['relation_type']}: {m['matched_entity']})")
            it["cross_ref_summary"] = " · ".join(badge_parts)

            # If item is general company announcement or press release, tag category relevance
            if it.get("category") in ("Company Announcement", "Relevant World News"):
                it["category"] = "Supplier/Customer News"
        else:
            it["related_tickers"] = []
            it["cross_references"] = []
            it["cross_ref_summary"] = ""

    logger.info(
        "Cross-reference engine complete: %d supply-chain connections identified across %d items",
        cross_ref_count,
        len(items),
    )
    return items
