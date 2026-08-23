"""Deduplication stage: Match by URL -> Headline Similarity."""

import difflib
import re
from typing import Any, Dict, List, Set, Tuple
from pipeline.normalize import canonicalize_url

# Stopwords & boilerplate phrases to strip for clean headline comparison
BOILERPLATE_PATTERNS = [
    r"^nvidia (reports|announces|introduces|delivers)\b",
    r"^apple (reports|announces|introduces|unveils|previews)\b",
    r"^microsoft (reports|announces|introduces|delivers)\b",
    r"\bsec form\b",
    r"\bpress release\b",
    r"\bcurrent report\b",
]


def clean_headline_for_comparison(text: str) -> str:
    """Normalize headline text for fuzzy similarity comparison."""
    if not text:
        return ""
    t = text.lower()
    for pat in BOILERPLATE_PATTERNS:
        t = re.sub(pat, "", t, flags=re.IGNORECASE).strip()
    # Remove punctuation
    t = re.sub(r"[^\w\s]", " ", t)
    # Collapse multiple whitespaces
    return " ".join(t.split())


def get_token_set(text: str) -> Set[str]:
    """Extract non-trivial token set."""
    words = clean_headline_for_comparison(text).split()
    # Filter short tokens
    return {w for w in words if len(w) > 2}


def compute_headline_similarity(h1: str, h2: str) -> float:
    """Compute combined Jaccard token overlap and SequenceMatcher ratio."""
    c1 = clean_headline_for_comparison(h1)
    c2 = clean_headline_for_comparison(h2)

    if not c1 or not c2:
        return 0.0

    if c1 == c2:
        return 1.0

    tokens1 = get_token_set(h1)
    tokens2 = get_token_set(h2)

    jaccard = 0.0
    if tokens1 and tokens2:
        intersection = len(tokens1 & tokens2)
        union = len(tokens1 | tokens2)
        jaccard = intersection / union if union > 0 else 0.0

    seq_ratio = difflib.SequenceMatcher(None, c1, c2).ratio()

    # Weight towards Jaccard if strong token overlap, otherwise average
    return max(jaccard, (jaccard * 0.5 + seq_ratio * 0.5))


def are_dates_close(d1: str, d2: str) -> bool:
    """Check if two YYYY-MM-DD dates are identical or adjacent (within 2 days)."""
    if not d1 or not d2:
        return True  # If date is missing, evaluate by headline
    if d1 == d2:
        return True
    try:
        from datetime import datetime
        dt1 = datetime.strptime(d1[:10], "%Y-%m-%d")
        dt2 = datetime.strptime(d2[:10], "%Y-%m-%d")
        return abs((dt1 - dt2).days) <= 2
    except Exception:
        return True


def deduplicate_items(
    items: List[Dict[str, Any]],
    similarity_threshold: float = 0.75,
) -> Tuple[List[Dict[str, Any]], int]:
    """Deduplicate a list of normalized items.

    Matching hierarchy:
    1. Exact Canonical URL match.
    2. Exact Item UID match.
    3. Fuzzy Headline similarity for the same ticker within adjacent dates.

    Returns:
        tuple (surviving_unique_items, num_duplicates_removed)
    """
    seen_urls: Set[str] = set()
    seen_uids: Set[str] = set()
    unique_items: List[Dict[str, Any]] = []
    duplicates_count = 0

    # Sort items so higher authority sources (e.g. SEC filings or full announcements) take precedence
    # Priority order: sec_edgar first, then company_ir
    def source_priority(it: Dict[str, Any]) -> int:
        src = it.get("source", "")
        if src == "sec_edgar":
            return 0
        if src == "company_ir":
            return 1
        return 2

    sorted_items = sorted(
        items,
        key=lambda x: (
            x.get("published_date", "") or "0000-00-00",
            source_priority(x),
        ),
        reverse=True,
    )

    for item in sorted_items:
        uid = item.get("item_uid")
        url = canonicalize_url(item.get("url", ""))

        # Stage 1: Exact UID match
        if uid and uid in seen_uids:
            duplicates_count += 1
            continue

        # Stage 2: Exact URL match
        if url and url in seen_urls:
            duplicates_count += 1
            continue

        # Stage 3: Headline similarity match against already-accepted items for the same ticker
        ticker = item.get("ticker", "")
        headline = item.get("headline", "")
        date = item.get("published_date", "")

        is_duplicate = False
        for accepted in unique_items:
            if accepted.get("ticker") != ticker:
                continue

            if not are_dates_close(date, accepted.get("published_date", "")):
                continue

            sim = compute_headline_similarity(headline, accepted.get("headline", ""))
            if sim >= similarity_threshold:
                is_duplicate = True
                break

        if is_duplicate:
            duplicates_count += 1
            continue

        # Item is unique
        if uid:
            seen_uids.add(uid)
        if url:
            seen_urls.add(url)
        unique_items.append(item)

    return unique_items, duplicates_count
