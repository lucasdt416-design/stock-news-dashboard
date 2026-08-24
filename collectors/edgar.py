"""SEC EDGAR Submissions API Collector.

Fetches recent company filings directly from the official SEC EDGAR system.
Adheres to SEC fair-access guidelines:
- Self-identifying User-Agent header.
- Rate-limited requests (<= 10 requests/second).
"""

import gzip
import json
import logging
import os
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# SEC EDGAR requires a User-Agent in the format: Sample Company Name AdminContact@<sample company domain>.com
DEFAULT_USER_AGENT = os.environ.get(
    "SEC_EDGAR_USER_AGENT",
    "StockNewsDashboard/1.0 (contact: admin@stocknewsdashboard.local)"
)
SEC_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik_10}.json"
SEC_ARCHIVE_URL = "https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc_clean}/{primary_doc}"
SEC_INDEX_URL = "https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc_clean}/{acc_num}-index.htm"


def format_cik(cik: str) -> str:
    """Pad CIK with leading zeros to 10 digits as required by SEC API."""
    cleaned = "".join(c for c in str(cik) if c.isdigit())
    return cleaned.zfill(10)


def fetch_company_submissions(
    cik: str,
    user_agent: Optional[str] = None,
    timeout: int = 15,
) -> Optional[Dict[str, Any]]:
    """Fetch raw submissions JSON for a single CIK from SEC EDGAR."""
    cik_10 = format_cik(cik)
    url = SEC_SUBMISSIONS_URL.format(cik_10=cik_10)
    ua = user_agent or DEFAULT_USER_AGENT

    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": ua,
            "Accept-Encoding": "gzip, deflate",
            "Host": "data.sec.gov",
            "Accept": "application/json, text/plain, */*",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            raw_data = response.read()
            if response.info().get("Content-Encoding") == "gzip":
                raw_data = gzip.decompress(raw_data)
            return json.loads(raw_data.decode("utf-8"))
    except urllib.error.HTTPError as e:
        logger.error("HTTP error fetching EDGAR CIK %s: %s %s", cik_10, e.code, e.reason)
        return None
    except Exception as e:
        logger.error("Error fetching EDGAR submissions for CIK %s: %s", cik_10, e)
        return None


def parse_submissions(
    data: Dict[str, Any],
    ticker: str,
    max_items: int = 40,
) -> List[Dict[str, Any]]:
    """Transform SEC submissions JSON into a list of normalized filing records."""
    if not data or "filings" not in data or "recent" not in data["filings"]:
        return []

    company_name = data.get("name", "")
    cik_raw = str(data.get("cik", ""))
    cik_int = str(int(cik_raw)) if cik_raw.isdigit() else cik_raw

    recent = data["filings"]["recent"]
    accession_numbers = recent.get("accessionNumber", [])
    filing_dates = recent.get("filingDate", [])
    report_dates = recent.get("reportDate", [])
    acceptance_date_times = recent.get("acceptanceDateTime", [])
    forms = recent.get("form", [])
    primary_documents = recent.get("primaryDocument", [])
    primary_doc_descriptions = recent.get("primaryDocDescription", [])

    total_available = len(accession_numbers)
    items_to_take = min(total_available, max_items)

    filings = []
    for i in range(items_to_take):
        acc_num = accession_numbers[i]
        acc_clean = acc_num.replace("-", "")
        form = forms[i] if i < len(forms) else "UNKNOWN"
        filing_date = filing_dates[i] if i < len(filing_dates) else ""
        report_date = report_dates[i] if i < len(report_dates) else ""
        acceptance_dt = acceptance_date_times[i] if i < len(acceptance_date_times) else ""
        primary_doc = primary_documents[i] if i < len(primary_documents) else ""
        primary_desc = primary_doc_descriptions[i] if i < len(primary_doc_descriptions) else ""

        if primary_doc:
            doc_url = SEC_ARCHIVE_URL.format(
                cik_int=cik_int, acc_clean=acc_clean, primary_doc=primary_doc
            )
        else:
            doc_url = SEC_INDEX_URL.format(
                cik_int=cik_int, acc_clean=acc_clean, acc_num=acc_num
            )

        filing_item = {
            "ticker": ticker.upper(),
            "company_name": company_name,
            "cik": format_cik(cik_raw),
            "form": form,
            "filing_date": filing_date,
            "report_date": report_date,
            "acceptance_date_time": acceptance_dt,
            "accession_number": acc_num,
            "primary_doc_name": primary_doc,
            "primary_doc_description": primary_desc,
            "url": doc_url,
        }
        filings.append(filing_item)

    return filings


def collect_edgar_filings(
    watchlist: List[Dict[str, Any]],
    max_items_per_ticker: int = 40,
    delay_seconds: float = 0.25,
) -> List[Dict[str, Any]]:
    """Collect filings for all tickers in the watchlist."""
    all_filings: List[Dict[str, Any]] = []

    for entry in watchlist:
        symbol = entry.get("symbol", "")
        cik = str(entry.get("cik", ""))

        if not cik:
            logger.warning("No CIK provided for %s, skipping", symbol)
            continue

        logger.info("Fetching SEC EDGAR filings for %s (CIK: %s)...", symbol, cik)
        data = fetch_company_submissions(cik)
        if data:
            filings = parse_submissions(data, ticker=symbol, max_items=max_items_per_ticker)
            logger.info("Retrieved %d filings for %s", len(filings), symbol)
            all_filings.extend(filings)
        else:
            logger.warning("Could not fetch filings for %s (CIK: %s)", symbol, cik)

        # Rate limit compliance
        time.sleep(delay_seconds)

    return all_filings


# Alias for consistency
collect_sec_edgar = collect_edgar_filings
