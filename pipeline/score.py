"""Rule-based scoring engine with transparent arithmetic (Section 6 of build-plan)."""

from datetime import datetime, timezone
import re
from typing import Any, Dict, Tuple
from pipeline.classify import (
    CAT_EARNINGS,
    CAT_M_AND_A,
    CAT_REGULATORY,
    CAT_LEADERSHIP,
    CAT_SUPPLY_CHAIN,
    CAT_PRODUCT_TECH,
    CAT_INSIDER,
    CAT_CAPITAL,
    CAT_INSTITUTIONAL,
    CAT_GUIDANCE_COMMENTARY,
    CAT_GENERAL,
    classify_item,
)

# Base Category Scores (Section 6: Earnings/M&A=8, Regulatory=7, Leadership=6, Supplier/Customer=5, etc.)
CATEGORY_BASE_SCORES: Dict[str, float] = {
    CAT_EARNINGS: 8.0,
    CAT_M_AND_A: 8.0,
    CAT_REGULATORY: 7.0,
    CAT_LEADERSHIP: 6.0,
    CAT_SUPPLY_CHAIN: 5.0,
    CAT_PRODUCT_TECH: 5.0,
    CAT_CAPITAL: 4.0,
    CAT_INSIDER: 3.5,
    CAT_INSTITUTIONAL: 3.0,
    CAT_GUIDANCE_COMMENTARY: 3.0,
    CAT_GENERAL: 2.0,
}

# Categories where SEC EDGAR being the source genuinely signals material importance
MATERIAL_SEC_CATEGORIES = {
    CAT_EARNINGS,
    CAT_REGULATORY,
    CAT_M_AND_A,
    CAT_LEADERSHIP,
}

# Routine/procedural SEC forms where filing existence is not inherently high-impact
ROUTINE_SEC_FORMS_PREFIXES = (
    "4",
    "144",
    "3",
    "5",
    "FORM 4",
    "FORM 144",
    "424B",
    "FWP",
    "11-K",
    "S-8",
    "POS AM",
    "PX14A6G",
)


def calculate_recency_adjustment(pub_date_str: str, pub_time_str: str) -> Tuple[float, str]:
    """Calculate recency adjustment based on age of publication."""
    if not pub_date_str:
        return (0.0, "Date unknown")

    try:
        now = datetime.now(timezone.utc)
        dt = None

        if pub_time_str:
            # Try parsing ISO timestamp
            clean_time = pub_time_str.replace("Z", "+00:00")
            try:
                dt = datetime.fromisoformat(clean_time)
            except Exception:
                pass

        if dt is None:
            # Fallback to YYYY-MM-DD
            dt = datetime.strptime(pub_date_str[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)

        age_hours = (now - dt).total_seconds() / 3600.0

        if age_hours < 6:
            return (2.0, "under 6h old (+2)")
        elif age_hours < 24:
            return (1.0, "under 24h old (+1)")
        elif age_hours > 72:
            return (-1.0, "over 72h old (-1)")
        else:
            return (0.0, "24-72h old (0)")
    except Exception:
        return (0.0, "Recency neutral")


# Words that start many company names, so on their own they don't identify one.
GENERIC_FIRST_WORDS = {"THE", "U.S.", "US", "GENERAL", "AMERICAN", "UNITED", "INTERNATIONAL", "BANK", "NATIONAL",
                       "FIRST", "TEXAS", "SOUTHERN", "UNION", "CAPITAL", "LAM", "ELI"}
NAME_WORDS = re.compile(
    r"(?<![\w.])(?:Inc|Incorporated|Corporation|Corp|Co|Company|Companies|Platforms|Holdings|Group|plc|Ltd|LLC|"
    r"N\.V|S\.A|L\.P)\.?(?!\w)|^The\s+", re.IGNORECASE)

# Stock-picking lists and market roundups: they name many companies and are opinion, not news.
STOCK_PICKING = re.compile(
    r"(?:^|\b(?:these|top|and|are|the)\s+)(?:\d+|two|three|four|five|seven|ten)\s+(?:[\w()'’&.-]+\s+){0,4}(?:stocks?|shares)\b"
    r"|\bstocks?\s+to\s+(?:buy|sell|watch|own|hold)\b|\bshould you buy\b|\bbuy (?:hand over fist|now)\b"
    r"|\btoo late to buy\b|\bbetter (?:buy|stock)\b|^prediction:|\bmillionaire\b|\bbillionaire\b"
    r"|\bjim cramer\b|\bstock market today\b|\bmost[- ]active stocks\b|\bif you invested\b|\$[\d,]+ investment\b"
    r"|\bis it a buy\b",
    re.IGNORECASE)


def company_spellings(company_name: str) -> list:
    """How news text names a company: "The Goldman Sachs Group, Inc." -> ["Goldman Sachs", "Goldman"]."""
    short = re.sub(r"\s*,\s*(?=,|$)", "", NAME_WORDS.sub("", company_name or ""))
    short = re.sub(r"\.com\b", "", short)
    short = re.sub(r"\s+(?:and|&)$", "", re.sub(r"\s{2,}", " ", short).strip(" ,&"))
    if short.upper() in GENERIC_FIRST_WORDS:  # "The Southern Company": "Southern" alone is just a word
        short = re.sub(r"^The\s+|[\s,]*Inc\.?$", "", company_name or "").strip(" ,")
    return [short] if len(short) >= 2 else []


# How headlines usually write the companies whose formal name they rarely use.
SHORT_NAMES = {
    "GOOGL": ["Google"], "META": ["Facebook"], "JPM": ["JPMorgan"], "XOM": ["Exxon", "ExxonMobil"], "DIS": ["Disney"],
    "AMD": ["AMD"], "GS": ["Goldman"], "PG": ["P&G", "Procter"], "COST": ["Costco"], "VZ": ["Verizon"],
    "NEE": ["NextEra"], "ABT": ["Abbott"], "BKNG": ["Booking.com"], "BMY": ["Bristol Myers", "Bristol-Myers"],
    "BNY": ["BNY Mellon"], "BRK-B": ["Berkshire"], "C": ["Citi"], "COF": ["Capital One"], "CSCO": ["Cisco"],
    "CVS": ["CVS"], "DELL": ["Dell"], "EMR": ["Emerson"], "GE": ["GE"], "GILD": ["Gilead"], "IBM": ["IBM"],
    "JNJ": ["J&J"], "LLY": ["Lilly"], "LMT": ["Lockheed"], "MDLZ": ["Mondelez"], "MMM": ["3M"], "MU": ["Micron"],
    "PANW": ["Palo Alto Networks"], "PLTR": ["Palantir"], "PM": ["Philip Morris"], "SCHW": ["Schwab"],
    "TMO": ["Thermo Fisher"], "TMUS": ["T-Mobile"], "UBER": ["Uber"], "UNH": ["UnitedHealth"], "UPS": ["UPS"],
    "DUK": ["Duke Energy"], "WMT": ["Walmart"], "AAPL": ["Apple"], "NVDA": ["Nvidia"],
}


def is_named(text: str, ticker: str, company_name: str) -> bool:
    """Whether text names the company. Tickers count only in capitals ("LOW", not "low")."""
    if not text:
        return False
    if ticker and re.search(rf"(?<![A-Za-z0-9]){re.escape(ticker.upper())}(?![A-Za-z0-9])", text):
        return True
    names = company_spellings(company_name) + SHORT_NAMES.get((ticker or "").upper(), [])
    return any(re.search(rf"(?<![\w&]){re.escape(name)}(?![\w&])", text, re.IGNORECASE) for name in names)


def is_named_in_headline(headline: str, ticker: str, company_name: str) -> bool:
    """Check if the ticker symbol or the company's name is in the headline."""
    return is_named(headline, ticker, company_name)


def score_item(item: Dict[str, Any]) -> Dict[str, Any]:
    """Compute transparent importance score (0.0 to 10.0) and attach breakdown."""
    # 1. Classification
    category = item.get("category") or classify_item(item)
    base_score = CATEGORY_BASE_SCORES.get(category, 2.0)
    breakdown_parts = [f"Base: {base_score:g} ({category})"]

    # 2. Selective Source Authority Adjustment (Section 6 fix)
    source = item.get("source", "")
    source_type = item.get("source_type", "")
    form = (item.get("form_or_type") or "").upper().strip()
    source_adj = 0.0

    if source == "sec_edgar" or source_type == "regulatory_filing":
        is_routine_sec = any(
            form == rf or form.startswith(rf) for rf in ROUTINE_SEC_FORMS_PREFIXES
        )
        if is_routine_sec or category == CAT_INSIDER:
            # Routine procedural paperwork (Form 4, 144, 424B2, 424B5, FWP, 11-K) gets no source bonus
            source_adj = 0.0
            breakdown_parts.append("Source: +0 (Routine SEC Filing)")
        elif category in MATERIAL_SEC_CATEGORIES:
            # Material official filings (10-K, 10-Q, 8-K material events, M&A, proxy leadership)
            source_adj = 3.0
            breakdown_parts.append("Source: +3 (Material SEC Filing)")
        elif category == CAT_CAPITAL:
            # Non-routine material capital restructurings
            source_adj = 1.0
            breakdown_parts.append("Source: +1 (Capital SEC Filing)")
        else:
            source_adj = 0.0
            breakdown_parts.append("Source: +0 (SEC Filing)")
    elif source == "company_ir" or source_type == "company_announcement":
        if category in MATERIAL_SEC_CATEGORIES:
            source_adj = 2.0
            breakdown_parts.append("Source: +2 (Material Company Announcement)")
        else:
            source_adj = 1.0
            breakdown_parts.append("Source: +1 (Company Announcement)")
    elif source in ("news_media", "finnhub") or source_type in ("press", "third_party_journalism"):
        if category in MATERIAL_SEC_CATEGORIES:
            source_adj = 1.0
            breakdown_parts.append("Source: +1 (News Media / Press)")
        else:
            source_adj = 0.5
            breakdown_parts.append("Source: +0.5 (News Media)")
    else:
        source_adj = 0.5
        breakdown_parts.append("Source: +0.5 (Press)")

    # 3. Recency Adjustment
    recency_adj, recency_label = calculate_recency_adjustment(
        item.get("published_date", ""), item.get("published_time", "")
    )
    if recency_adj != 0:
        sign = "+" if recency_adj > 0 else ""
        breakdown_parts.append(f"Recency: {sign}{recency_adj:g} ({recency_label})")

    # 4. Named in Headline Adjustment
    headline = item.get("headline", "")
    ticker = item.get("ticker", "")
    company = item.get("company_name", "")
    headline_adj = 0.0
    is_news = source in ("news_media", "finnhub") or source_type in ("press", "third_party_journalism")
    if is_named_in_headline(headline, ticker, company):
        headline_adj = 1.0
        breakdown_parts.append("Headline: +1 (Named)")
    elif is_news and company and not is_named(item.get("summary") or "", ticker, company):
        # News services tag articles to companies they barely touch; these come last.
        headline_adj = -4.0
        breakdown_parts.append("Not about the company: -4 (Not named)")

    # 4b. Stock-picking lists and market roundups are opinion, not news about the company
    if is_news and STOCK_PICKING.search(headline):
        headline_adj -= 3.0
        breakdown_parts.append("Stock picks: -3 (List or roundup)")

    # 5. Duplicate Penalty
    dup_adj = 0.0
    if item.get("is_duplicate"):
        dup_adj = -4.0
        breakdown_parts.append("Duplicate: -4")

    # 6. Final Score Calculation (Clamped 0.0 - 10.0)
    raw_score = base_score + source_adj + recency_adj + headline_adj + dup_adj
    final_score = round(max(0.0, min(10.0, float(raw_score))), 1)

    breakdown_str = " | ".join(breakdown_parts) + f" => Score: {final_score}"

    item["category"] = category
    item["score"] = final_score
    item["score_breakdown"] = breakdown_str
    return item


def score_items(items: list, **kwargs) -> list:
    """Score a collection of normalized items."""
    return [score_item(it) for it in items]
