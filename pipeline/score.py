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


def is_named_in_headline(headline: str, ticker: str, company_name: str) -> bool:
    """Check if the ticker symbol or core company name is prominently in the headline."""
    if not headline:
        return False
    h = headline.upper()
    t = ticker.upper()
    # Check ticker symbol as word
    if re.search(r"\b" + re.escape(t) + r"\b", h):
        return True
    # Check first word of company name (e.g., "NVIDIA", "APPLE", "MICROSOFT")
    if company_name:
        core_name = company_name.split()[0].upper()
        if len(core_name) > 2 and re.search(r"\b" + re.escape(core_name) + r"\b", h):
            return True
    return False


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
    if is_named_in_headline(headline, ticker, company):
        headline_adj = 1.0
        breakdown_parts.append("Headline: +1 (Named)")

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


def score_items(items: list) -> list:
    """Score a collection of normalized items."""
    return [score_item(it) for it in items]
