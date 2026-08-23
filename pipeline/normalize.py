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


def normalize_edgar_item(item: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize a raw SEC EDGAR filing item."""
    ticker = item.get("ticker", "").upper()
    form = item.get("form", "FILING")
    acc_num = item.get("accession_number", "")
    url = item.get("url", "")
    primary_desc = item.get("primary_doc_description") or ""
    primary_name = item.get("primary_doc_name") or ""

    # Build clean headline
    headline = f"SEC Form {form}"
    if primary_desc and primary_desc != form:
        headline += f" — {primary_desc}"
    elif primary_name:
        headline += f" ({primary_name})"

    # Summary details
    summary = f"Official SEC submission. Accession: {acc_num}"
    if item.get("report_date"):
        summary += f" | Report Period: {item.get('report_date')}"

    return {
        "item_uid": generate_item_uid("sec_edgar", acc_num, url),
        "ticker": ticker,
        "company_name": item.get("company_name", ticker),
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
                "item_uid": generate_item_uid("general", raw_id, url),
                "ticker": ticker,
                "company_name": item.get("company_name", ticker),
                "source": item.get("source", "unknown"),
                "source_label": item.get("source_label", "News"),
                "source_type": item.get("source_type", "news"),
                "headline": item.get("headline") or item.get("title", "Untitled"),
                "summary": item.get("summary", ""),
                "url": url,
                "published_date": item.get("published_date") or item.get("filing_date", ""),
                "published_time": item.get("published_time") or item.get("acceptance_date_time", ""),
                "form_or_type": item.get("form_or_type") or item.get("form", "NEWS"),
                "raw_id": raw_id,
            })

    return normalized
