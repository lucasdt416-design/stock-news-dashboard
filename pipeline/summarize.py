"""LLM-based and heuristic 'Why It Matters' summarization engine using Gemini API."""

import json
import logging
import os
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"


def generate_fallback_summary(item: Dict[str, Any]) -> str:
    """Generate a contextual plain-English 'why it matters' summary based on category and form."""
    ticker = item.get("ticker", "")
    category = item.get("category", "")
    form = (item.get("form_or_type") or "").upper().strip()
    headline = item.get("headline", "")
    summary = (item.get("summary") or "").lower()

    if category == "Earnings & Financials":
        if "10-K" in form or "10-k" in headline.lower():
            return f"Annual financial report detailing {ticker}'s full-year audited revenue, margins, and operational risk factors."
        if "10-Q" in form or "10-q" in headline.lower():
            return f"Quarterly financial filing providing essential updates on {ticker}'s recent quarterly balance sheet, revenue, and cash flow."
        return f"Key financial results release providing quarterly revenue, earnings per share, and forward guidance for {ticker}."

    if category == "Insider Transactions":
        if "144" in form or "144" in headline:
            return "Notice of proposed securities sale by an insider or affiliate under Rule 144."
        if "4" in form or "beneficial ownership" in summary:
            return "Routine insider transaction disclosure documenting executive/director share acquisition, disposition, or scheduled 10b5-1 plan execution."
        return "Insider disclosure tracking changes in executive or director share ownership."

    if category == "Regulation & Policy / Litigation":
        if "8-K" in form:
            return "Material corporate event disclosure requiring immediate SEC disclosure outside routine reporting cycles."
        return f"Regulatory or legal development potentially affecting {ticker}'s operational compliance, antitrust posture, or market access."

    if category == "Leadership & Governance":
        return "Governance disclosure documenting executive leadership changes, board elections, or key management restructuring."

    if category == "Product Launches & Technology":
        return f"Commercial product announcement expanding {ticker}'s core technology roadmap, partner ecosystem, or market footprint."

    if category == "Capital Structure & Offerings":
        return "Capital markets disclosure regarding debt issuance, equity offerings, credit agreements, or share repurchase programs."

    if category == "Institutional Ownership":
        return "Institutional holding update disclosing major institutional fund positioning or passive ownership changes."

    if category == "M&A & Strategic Deals":
        return "Strategic transaction announcement covering acquisitions, joint ventures, or partnership agreements."

    if "8-K" in form:
        return "Material SEC Form 8-K disclosure reporting unscheduled corporate events or company announcements."

    return f"Official company announcement detailing current business updates and strategic initiatives for {ticker}."


def summarize_batch_with_gemini(
    batch: List[Dict[str, Any]], api_key: str, timeout: int = 25
) -> Dict[str, str]:
    """Call Gemini API to generate plain-English 'why it matters' summaries for a batch of items.

    Fails safely: Returns empty dict on any network, quota, or parsing error without breaking.
    """
    if not api_key:
        return {}

    items_payload = []
    for it in batch:
        items_payload.append({
            "id": it.get("item_uid"),
            "ticker": it.get("ticker"),
            "company": it.get("company_name"),
            "form": it.get("form_or_type"),
            "category": it.get("category"),
            "headline": it.get("headline"),
            "summary_snippet": (it.get("summary") or "")[:200],
        })

    prompt = (
        "You are an expert financial analyst. For each company news item or SEC filing below, "
        "write a concise, punchy ONE-SENTENCE plain-English explanation of why it matters to an investor "
        "(e.g. 'Routine insider transaction under a scheduled 10b5-1 plan, not a material signal.' or "
        "'Major quarterly report highlighting hyperscaler capex growth and margin resilience.').\n\n"
        "Return ONLY a valid JSON object mapping each 'id' to its one-sentence summary string.\n\n"
        f"Items to summarize:\n{json.dumps(items_payload, indent=2)}"
    )

    request_body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.2,
            "responseMimeType": "application/json",
        },
    }

    url = GEMINI_API_URL.format(api_key=api_key)
    req = urllib.request.Request(
        url,
        data=json.dumps(request_body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            candidates = data.get("candidates", [])
            if candidates:
                text_out = candidates[0]["content"]["parts"][0]["text"]
                return json.loads(text_out)
    except urllib.error.HTTPError as e:
        logger.warning("Gemini API returned HTTP %s (%s). Falling back safely to default views.", e.code, e.reason)
    except urllib.error.URLError as e:
        logger.warning("Gemini API connection error (%s). Falling back safely to default views.", e.reason)
    except json.JSONDecodeError as e:
        logger.warning("Gemini API returned non-JSON output (%s). Falling back safely.", e)
    except Exception as e:
        logger.warning("Gemini API batch summarization error: %s. Falling back safely.", e)

    return {}


def summarize_items(
    items: List[Dict[str, Any]],
    api_key: Optional[str] = None,
    batch_size: int = 20,
) -> List[Dict[str, Any]]:
    """Generate and attach a one-sentence 'why it matters' summary for each item.

    Guaranteed safety: Never throws an uncaught exception; falls back gracefully
    to category/heuristic summaries if the API key is missing or calls fail.
    """
    gemini_key = api_key or os.environ.get("GEMINI_API_KEY", "").strip()

    if gemini_key:
        logger.info("Using Gemini API for LLM 'Why It Matters' summarization (%d items)...", len(items))
        for i in range(0, len(items), batch_size):
            batch = items[i : i + batch_size]
            try:
                llm_results = summarize_batch_with_gemini(batch, gemini_key)
            except Exception as e:
                logger.warning("Batch exception caught: %s", e)
                llm_results = {}

            for item in batch:
                uid = item.get("item_uid")
                if uid in llm_results and llm_results[uid]:
                    item["llm_summary"] = str(llm_results[uid]).strip()
                else:
                    item["llm_summary"] = generate_fallback_summary(item)
    else:
        logger.info("No GEMINI_API_KEY detected; applying contextual 'Why It Matters' intelligence engine.")
        for item in items:
            item["llm_summary"] = generate_fallback_summary(item)

    return items
