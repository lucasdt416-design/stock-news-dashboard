"""Normalization layer to reshape multi-source news and filings into a unified schema."""

import hashlib
from typing import Any, Dict, List
from urllib.parse import urlparse, urlunparse


def canonicalize_url(url: str) -> str:
    """Strip tracking query parameters and fragments for consistent URL matching."""
    if not url:
        return ""
    parsed = urlparse(url.strip())
    # Keep path, scheme, netloc, clear fragment
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", "", ""))


def generate_item_uid(source: str, raw_id: str, url: str) -> str:
    """Generate a consistent unique identifier for an item."""
    seed = f"{source}:{raw_id}:{canonicalize_url(url)}"
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]


def format_edgar_human_headline(
    company_name: str, ticker: str, form: str, primary_desc: str = ""
) -> str:
    """Generate a clean, human-readable executive title for an SEC filing."""
    company = company_name or ticker
    form_clean = (form or "").upper().strip()

    if form_clean == "8-K":
        return f"{company} Discloses Material Corporate Event"
    elif form_clean == "10-Q":
        return f"{company} Files Quarterly Financial Report (10-Q)"
    elif form_clean == "10-K":
        return f"{company} Files Annual Financial Report (10-K)"
    elif form_clean == "4":
        return f"{company} Reports Executive & Director Insider Transaction"
    elif form_clean == "144":
        return f"{company} Files Notice of Proposed Securities Sale"
    elif form_clean in ("DEF 14A", "DEFA14A"):
        return f"{company} Files Definitive Proxy Statement"
    elif form_clean in ("13F-HR", "13F"):
        return f"{company} Discloses Institutional Holdings (Form 13F)"
    elif form_clean in ("SC 13G", "SC 13G/A", "SC 13D"):
        return f"{company} Discloses Beneficial Ownership Stake"
    elif primary_desc and not primary_desc.lower().endswith((".htm", ".xml", ".txt")):
        return f"{company} Files SEC {form_clean} — {primary_desc}"
    else:
        return f"{company} Files Official Regulatory Disclosure ({form_clean})"


def normalize_edgar_item(item: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize a raw SEC EDGAR filing item with human-readable title."""
    ticker = item.get("ticker", "").upper()
    company_name = item.get("company_name", ticker)
    form = item.get("form", "FILING")
    acc_num = item.get("accession_number", "")
    url = item.get("url", "")
    primary_desc = item.get("primary_doc_description") or ""

    headline = format_edgar_human_headline(
        company_name=company_name,
        ticker=ticker,
        form=form,
        primary_desc=primary_desc,
    )

    # Summary details
    summary = f"Official SEC submission ({form}). Accession: {acc_num}"
    if item.get("report_date"):
        summary += f" | Report Period: {item.get('report_date')}"

    return {
        "item_uid": generate_item_uid("sec_edgar", acc_num, url),
        "ticker": ticker,
        "company_name": company_name,
        "source": "sec_edgar",
        "source_label": "SEC EDGAR",
        "source_type": "regulatory_filing",
        "headline": headline,
        "summary": summary,
        "url": url,
        "published_date": item.get("filing_date", ""),
        "published_time": item.get("acceptance_date_time", ""),
        "form_or_type": form,
        "raw_id": acc_num,
    }


def normalize_company_ir_item(item: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize a raw Company IR / Press Release item."""
    ticker = item.get("ticker", "").upper()
    url = item.get("link", "")
    guid = item.get("guid", url)
    title = item.get("title", "Company Announcement")
    summary = item.get("summary", "")

    return {
        "item_uid": generate_item_uid("company_ir", guid, url),
        "ticker": ticker,
        "company_name": item.get("company_name", ticker),
        "source": "company_ir",
        "source_label": "Company IR",
        "source_type": "company_announcement",
        "headline": title,
        "summary": summary[:300] + ("..." if len(summary) > 300 else ""),
        "url": url,
        "published_date": item.get("published_date", ""),
        "published_time": item.get("published_time", ""),
        "form_or_type": item.get("form_or_type", "PRESS_RELEASE"),
        "raw_id": guid,
    }


def normalize_items(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Normalize an arbitrary list of collected items from any source."""
    normalized: List[Dict[str, Any]] = []

    for item in items:
        source = item.get("source")
        if source == "sec_edgar" or "accession_number" in item:
            normalized.append(normalize_edgar_item(item))
        elif source == "company_ir" or "link" in item:
            normalized.append(normalize_company_ir_item(item))
        else:
            # General fallback
            ticker = item.get("ticker", "").upper()
            url = item.get("url") or item.get("link", "")
            raw_id = item.get("raw_id") or item.get("guid") or url
            normalized.append({
                "item_uid": generate_item_uid("generic", str(raw_id), url),
                "ticker": ticker,
                "company_name": item.get("company_name", ticker),
                "source": item.get("source", "unknown"),
                "source_label": item.get("source_label", "Unknown"),
                "source_type": item.get("source_type", "news"),
                "headline": item.get("headline") or item.get("title", "News Item"),
                "summary": item.get("summary", ""),
                "url": url,
                "published_date": item.get("published_date", ""),
                "published_time": item.get("published_time", ""),
                "form_or_type": item.get("form_or_type", "NEWS"),
                "raw_id": str(raw_id),
            })

    return normalized
