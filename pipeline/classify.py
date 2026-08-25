"""Rule-based classification engine for news items, journalism, and SEC filings."""

from typing import Any, Dict

# Category definitions
CAT_EARNINGS = "Earnings & Financials"
CAT_M_AND_A = "M&A & Strategic Deals"
CAT_REGULATORY = "Regulation & Policy / Litigation"
CAT_LEADERSHIP = "Leadership & Governance"
CAT_SUPPLY_CHAIN = "Supplier & Customer Intelligence"
CAT_PRODUCT_TECH = "Product Launches & Technology"
CAT_INSIDER = "Insider Transactions"
CAT_CAPITAL = "Capital Structure & Offerings"
CAT_INSTITUTIONAL = "Institutional Ownership"
CAT_GUIDANCE_COMMENTARY = "Guidance & Commentary"
CAT_GENERAL = "Company Announcement"


def classify_item(item: Dict[str, Any]) -> str:
    """Classify a single normalized item into a category based on source, form, and text."""
    form = (item.get("form_or_type") or "").upper().strip()
    headline = (item.get("headline") or "").lower()
    summary = (item.get("summary") or "").lower()
    full_text = f"{headline} {summary}"

    # 1. Earnings & Financial Results
    if form in ("10-K", "10-Q") or "10-k" in headline or "10-q" in headline:
        return CAT_EARNINGS
    if any(
        kw in full_text
        for kw in (
            "financial results",
            "quarterly results",
            "reports fiscal",
            "reports first quarter",
            "reports second quarter",
            "reports third quarter",
            "reports fourth quarter",
            "reports q1",
            "reports q2",
            "reports q3",
            "reports q4",
            "earnings release",
            "annual revenue",
            "eps beats",
            "revenue miss",
            "quarterly revenue",
            "profit surges",
            "earnings beat",
        )
    ):
        return CAT_EARNINGS

    # 2. Insider Transactions (Form 4, 144, 3, 5)
    if form in ("4", "144", "3", "5", "FORM 4", "FORM 144", "FORM 3"):
        return CAT_INSIDER
    if "beneficial ownership" in full_text or "proposed sale of securities" in full_text or "insider trade" in full_text:
        return CAT_INSIDER

    # 3. Institutional Ownership & Activist stakes (13F, 13G, 13D)
    if "13F" in form or "13G" in form or "13G/A" in form:
        return CAT_INSTITUTIONAL
    if "13D" in form or "activist stake" in full_text or "schedule 13d" in full_text or "activist investor" in full_text:
        return CAT_M_AND_A

    # 4. M&A & Strategic Deals
    if any(
        kw in full_text
        for kw in (
            "to acquire",
            "acquires",
            "acquisition of",
            "merger agreement",
            "definitive agreement to acquire",
            "strategic partnership with",
            "joint venture",
            "buyout",
            "takeover bid",
            "takeover target",
            "in talks to buy",
            "agrees to purchase",
        )
    ):
        return CAT_M_AND_A

    # 5. Leadership & Governance / Labour Actions
    if "DEF 14A" in form or "DEFA14A" in form or "PX14A6G" in form:
        return CAT_LEADERSHIP
    if any(
        kw in full_text
        for kw in (
            "appoints",
            "named ceo",
            "steps down as ceo",
            "chief executive",
            "board of directors",
            "resigns from",
            "named president",
            "leadership transition",
            "executive appointment",
            "ousted as",
            "union strike",
            "labor union",
            "worker walkout",
            "board seat",
            "proxy fight",
        )
    ):
        return CAT_LEADERSHIP

    # 6. Capital Structure & Offerings (424B, S-3, S-8, debt, dividends)
    if any(f in form for f in ("424B", "S-3", "S-8", "11-K", "FWP")):
        return CAT_CAPITAL
    if any(
        kw in full_text
        for kw in (
            "senior notes",
            "public offering of",
            "debt offering",
            "declares dividend",
            "share repurchase program",
            "stock buyback",
            "priced offering",
            "secondary offering",
        )
    ):
        return CAT_CAPITAL

    # 7. Regulatory & Policy / Litigation / External Safety Incidents (plane crash, recall, lawsuits)
    if any(
        kw in full_text
        for kw in (
            "european union",
            "european commission",
            "antitrust",
            "doj",
            "ftc",
            "cma",
            "investigation",
            "subpoena",
            "regulatory approval",
            "compliance",
            "lawsuit",
            "sued by",
            "sues",
            "patent infringement",
            "settlement agreement",
            "plane crash",
            "crash",
            "emergency landing",
            "faa audit",
            "faa probe",
            "grounding",
            "safety incident",
            "product recall",
            "recall",
            "recalls",
            "safety defect",
            "sec probe",
            "class action lawsuit",
            "judge rules",
            "court hearing",
            "cybersecurity breach",
            "ransomware",
        )
    ):
        return CAT_REGULATORY

    # 8. Product Launches & Technology
    if any(
        kw in full_text
        for kw in (
            "introduces",
            "unveils",
            "launches",
            "new ai",
            "geforce",
            "copilot",
            "blackwell",
            "supercomputer",
            "arcade",
            "chip",
            "processor",
            "architecture",
            "manufacturing center",
            "ai center",
            "open source",
            "fda approval",
            "clinical trial",
            "phase 3 study",
        )
    ):
        return CAT_PRODUCT_TECH

    # 9. Guidance, Analyst Actions & Commentary
    if any(
        kw in full_text
        for kw in (
            "guidance",
            "financial outlook",
            "annual meeting of shareholders",
            "fireside chat",
            "keynote address",
            "webcast",
            "presents at",
            "upgrade",
            "downgrade",
            "price target",
            "maintains buy",
            "initiates coverage",
            "overweight",
            "underweight",
            "outperform",
            "analyst says",
        )
    ):
        return CAT_GUIDANCE_COMMENTARY

    # 10. Fallback for SEC Form 8-K
    if "8-K" in form:
        return CAT_REGULATORY

    return CAT_GENERAL
