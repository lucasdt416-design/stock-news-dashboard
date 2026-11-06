"""Short story summaries: from Gemini when it works and can be checked, keyword templates otherwise.

See summarize_items for how the free quota is spent and how summaries are checked against the source.
"""

import json
import logging
import os
import re
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

from pipeline.normalize import clean_text, extract_headline_subject

logger = logging.getLogger(__name__)

# Used only if the model list can't be read. Google keeps this alias pointing at its current Flash.
FALLBACK_GEMINI_MODEL = "gemini-flash-latest"


def extract_headline_topic(headline: str, subject: str = "") -> str:
    """Extract a clean, concise topic phrase from a news headline for dynamic summaries."""
    import re
    h = clean_text(headline)
    # Strip common wire prefixes
    h = re.sub(r"^(Market Chatter|Report|Exclusive|Update|Breaking|Analysis|Opinion|Preview|Brief):\s*", "", h, flags=re.IGNORECASE)
    h = re.sub(r"^([A-Z]{1,5}|[A-Za-z\s]+)\s*[-—:]\s*", "", h)
    # Strip quotes
    h = h.strip("'\"“”")
    # If headline mentions subject, clean up phrasing
    if subject and subject.lower() in h.lower():
        # Keep as is or normalize
        pass
    if len(h) > 85:
        # Cut at word boundary
        cut = h[:85].rsplit(" ", 1)[0]
        h = f"{cut}..."
    return h.strip()


def generate_fallback_summary(item: Dict[str, Any]) -> str:
    """Generate a specific, contextual plain-English 'why it matters' takeaway based on headline, category, and company details."""
    ticker = item.get("ticker", "").upper()
    company_name = item.get("company_name", ticker)
    category = item.get("category", "")
    form = (item.get("form_or_type") or "").upper().strip()
    headline = clean_text(item.get("headline", ""))
    summary = clean_text(item.get("summary", ""))
    full_lower = f"{headline} {summary}".lower()

    # Extract true focal subject (e.g. XPeng (XPEV) vs Tesla, or ABC News vs Disney)
    subject = item.get("subject_name")
    if not subject or subject == ticker:
        subject = extract_headline_subject(
            headline=headline,
            summary=summary,
            default_ticker=ticker,
            default_company=company_name,
        )

    # 1. Specifically surface legitimate subsidiary and press pool connection for DIS / media items
    if (ticker == "DIS" or "disney" in company_name.lower()) and any(
        kw in full_lower for kw in ("white house", "press pool", "cnn", "politico", "ms now", "msnbc", "press credentials")
    ):
        return "Involves Disney subsidiary ABC News and broadcast television pool operations amid White House credentialing disputes and media regulatory scrutiny."

    # 2. Energy / LNG / Gas Portfolio Expansion (e.g. Chevron in Argentina & Mediterranean)
    if any(kw in full_lower for kw in ("lng", "liquefied natural gas", "natural gas", "gas portfolio", "argentina", "mediterranean")):
        locs = []
        if "argentina" in full_lower:
            locs.append("Argentina")
        if "mediterranean" in full_lower:
            locs.append("the Mediterranean")
        if locs:
            loc_str = " and ".join(locs)
            return f"Strategic energy infrastructure initiative expanding {subject}'s natural gas and LNG assets across {loc_str}."
        return f"Strategic energy infrastructure initiative expanding {subject}'s global LNG export and gas portfolio footprint."

    # 3. Patent & Intellectual Property Litigation
    if any(kw in full_lower for kw in ("patent infringement", "patent fight", "patent dispute", "interdigital", "licensing dispute")):
        return f"Intellectual property litigation regarding patent licensing claims and potential financial liability for {subject}."

    # 4. Comparative investment articles (e.g., "A: A Better Bet Than B")
    if "better bet than" in headline.lower() or " vs " in headline.lower() or " vs. " in headline.lower() or "which media stock" in headline.lower():
        topic = extract_headline_topic(headline, subject)
        return f"Comparative investment analysis ({topic}) evaluating {subject}'s valuation, risk profile, and market outlook."

    # 5. Aerospace & Aviation Safety (e.g. Boeing, FAA)
    if any(kw in full_lower for kw in ("faa", "grounding", "aircraft delivery", "jetliner", "safety directive")):
        return f"Commercial aerospace regulatory review monitoring fleet safety compliance and delivery schedules for {subject}."

    # 6. Category-Specific Contextual Fallbacks with Headline Integration
    if category == "Regulation & Policy / Litigation":
        if "8-K" in form:
            return f"Material SEC Form 8-K disclosure detailing immediate legal or regulatory events for {subject} outside routine reporting cycles."
        if any(kw in full_lower for kw in ("antitrust", "ftc", "doj", "monopoly", "cma", "investigation")):
            return f"Antitrust regulatory scrutiny assessing market competition, platform compliance, and potential legal remedies for {subject}."
        if any(kw in full_lower for kw in ("lawsuit", "sued by", "sues", "court", "judge", "class action")):
            topic = extract_headline_topic(headline, subject)
            return f"Legal dispute and court proceedings regarding {topic}, impacting operational compliance for {subject}."
        topic = extract_headline_topic(headline, subject)
        return f"Regulatory or policy development regarding {topic}, affecting operational compliance and market posture for {subject}."

    if category == "Product Launches & Technology":
        if any(kw in full_lower for kw in ("ai", "artificial intelligence", "copilot", "supercomputer", "blackwell", "chip", "processor")):
            return f"Advanced computing and AI platform release advancing {subject}'s technology roadmap and competitive positioning."
        if any(kw in full_lower for kw in ("clinical trial", "phase 3", "fda approval", "drug", "therapy")):
            return f"Clinical biopharmaceutical milestone evaluating treatment efficacy and regulatory review for {subject}."
        topic = extract_headline_topic(headline, subject)
        return f"Commercial product milestone expanding {subject}'s market reach: {topic}."

    if category == "Capital Structure & Offerings":
        if any(kw in full_lower for kw in ("dividend", "yield")):
            return f"Capital return update announcing dividend payouts and shareholder distribution policy for {subject}."
        if any(kw in full_lower for kw in ("repurchase", "buyback")):
            return f"Share repurchase program signaling balance sheet liquidity and capital allocation priorities for {subject}."
        if any(kw in full_lower for kw in ("notes", "debt offering", "credit agreement", "senior notes")):
            return f"Capital markets financing providing debt structure optimization and balance sheet flexibility for {subject}."
        topic = extract_headline_topic(headline, subject)
        return f"Capital structure update detailing financing and securities issuance for {subject}: {topic}."

    if category == "Earnings & Financials":
        if "10-k" in form or "10-k" in headline.lower():
            return f"Annual SEC Form 10-K filing providing {subject}'s full-year audited financial statements, revenue mix, and risk factors."
        if "10-q" in form or "10-q" in headline.lower():
            return f"Quarterly SEC Form 10-Q filing detailing {subject}'s balance sheet strength, operating cash flow, and segment margins."
        if any(kw in full_lower for kw in ("beats", "beat", "surges", "profit jumps")):
            return f"Quarterly earnings release reporting stronger-than-expected revenue and earnings performance for {subject}."
        if any(kw in full_lower for kw in ("misses", "miss", "plunges", "slumps")):
            return f"Quarterly earnings report reflecting revenue or margin contraction relative to consensus expectations for {subject}."
        if "preview" in headline.lower() or "outlook" in headline.lower():
            return f"Financial outlook and analyst consensus preview assessing forward earnings expectations for {subject}."
        topic = extract_headline_topic(headline, subject)
        return f"Financial performance disclosure detailing quarterly operating results for {subject} ({topic})."

    if category == "Leadership & Governance":
        if any(kw in full_lower for kw in ("ceo", "chief executive")):
            return f"Executive leadership transition appointing chief executive leadership to guide strategic direction at {subject}."
        if any(kw in full_lower for kw in ("cfo", "chief financial")):
            return f"Executive management update appointing chief financial leadership to oversee capital allocation at {subject}."
        if any(kw in full_lower for kw in ("board", "director", "proxy", "def 14a")):
            return f"Corporate governance disclosure regarding board oversight, director elections, or shareholder proxy votes for {subject}."
        topic = extract_headline_topic(headline, subject)
        return f"Governance update detailing executive appointments or organizational restructuring for {subject}: {topic}."

    if category == "Insider Transactions":
        if "144" in form or "144" in headline:
            return f"Notice of proposed securities sale by an insider or affiliate of {subject} under SEC Rule 144."
        if "4" in form or "beneficial ownership" in summary:
            return f"Routine insider transaction disclosure documenting executive/director share positioning for {subject}."
        return f"Insider disclosure tracking changes in executive or director share ownership for {subject}."

    if category == "Institutional Ownership":
        return f"Institutional holding update disclosing major institutional fund positioning or ownership changes in {subject}."

    if category == "M&A & Strategic Deals":
        if any(kw in full_lower for kw in ("acquire", "acquisition", "buyout", "takeover")):
            return f"Strategic acquisition agreement expanding {subject}'s commercial footprint and operational scale."
        if any(kw in full_lower for kw in ("partner", "partnership", "joint venture")):
            return f"Commercial partnership agreement uniting technical and distribution capabilities to accelerate {subject}'s growth."
        topic = extract_headline_topic(headline, subject)
        return f"Strategic transaction disclosure regarding corporate deals or partnership agreements for {subject}: {topic}."

    if "8-K" in form:
        topic = extract_headline_topic(headline, subject)
        return f"Material SEC Form 8-K disclosure reporting unscheduled corporate developments for {subject}: {topic}."

    # General Press / News Media / Company IR fallback incorporating specific topic
    topic = extract_headline_topic(headline, subject)
    if topic:
        return f"Market coverage examining {topic}, analyzing operational implications and sector demand for {subject}."
    return f"Official company announcement detailing current business updates and strategic initiatives for {subject}."


# --- Gemini ---------------------------------------------------------------------------------
#
# Google retires model names (gemini-1.5-flash, then gemini-2.5-flash) and every request then fails
# with HTTP 404. So the model is chosen from the list Google says this key can use, once per run.

GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"
SOURCE_SNIPPET_CHARS = 1200
# Form 4 and Form 144 sentences are already exact; asking a model to restate them adds nothing.
SKIP_AI_FORMS = {"4", "4/A", "144", "144/A", "3", "5"}
NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")

PROMPT = (
    "You summarize company news for investors. For each item, write one or two plain sentences, "
    "at most 45 words in all: what happened, keeping the key figures (amounts, percentages, share "
    "counts, prices, dates) exactly as the text gives them, then, if it is clear from the text, why "
    "it matters to a shareholder.\n"
    "Rules: use only facts in that item's headline and text. Never add, round, convert or calculate "
    "a number. No hype words, no advice, no 'investors should'. If the text says nothing beyond the "
    "headline, return an empty string for that item.\n"
    "Return ONLY a JSON object mapping each item's id to its summary string.\n\n"
)


class GeminiStop(Exception):
    """A failure that will repeat for every batch (bad model, bad key, daily quota): stop asking."""


def _gemini_request(url: str, api_key: str, body: Optional[Dict[str, Any]] = None, timeout: int = 30) -> Dict[str, Any]:
    """The key goes in a header, so it never appears in a URL, a log line or an exception message."""
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8") if body is not None else None,
        headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
        method="POST" if body is not None else "GET",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _google_error(e: urllib.error.HTTPError) -> str:
    """Google's own explanation, e.g. 'models/gemini-2.5-flash is not found for API version v1beta'."""
    try:
        return json.loads(e.read().decode("utf-8")).get("error", {}).get("message", "")[:300]
    except Exception:
        return ""


def _model_rank(name: str) -> Optional[tuple]:
    """Stable Flash models, newest first; None for anything else (preview, image, audio, live...)."""
    short = name.split("/")[-1]
    if short == "gemini-flash-latest":
        return (3, 0.0)
    m = re.fullmatch(r"gemini-(\d+(?:\.\d+)?)-flash(-lite)?(?:-\d{3})?", short)
    if not m:
        return None
    return (1 if m.group(2) else 2, float(m.group(1)))


def choose_gemini_model(api_key: str) -> str:
    """GEMINI_MODEL if set; otherwise the newest stable Flash model this key can call."""
    configured = os.environ.get("GEMINI_MODEL", "").strip()
    if configured:
        return configured
    try:
        data = _gemini_request(f"{GEMINI_BASE}/models?pageSize=1000", api_key, timeout=20)
    except urllib.error.HTTPError as e:
        raise GeminiStop(f"listing models failed: HTTP {e.code} {_google_error(e)}".strip())
    except Exception as e:
        logger.warning("Could not list Gemini models (%s); trying %s.", e, FALLBACK_GEMINI_MODEL)
        return FALLBACK_GEMINI_MODEL
    usable = []
    for m in data.get("models", []):
        rank = _model_rank(m.get("name", ""))
        if rank and "generateContent" in m.get("supportedGenerationMethods", []):
            usable.append((rank, m["name"].split("/")[-1]))
    if not usable:
        raise GeminiStop("this key can't use any Gemini Flash model")
    return max(usable)[1]


_MODEL_BY_KEY: Dict[tuple, str] = {}


def _cached_model(api_key: str) -> str:
    """choose_gemini_model, asked once per run however many callers need it."""
    key = (api_key, os.environ.get("GEMINI_MODEL", "").strip())
    if key not in _MODEL_BY_KEY:
        _MODEL_BY_KEY[key] = choose_gemini_model(api_key)
    return _MODEL_BY_KEY[key]


def numbers_in(text: str) -> set:
    return {n.replace(",", "").rstrip(".") for n in NUMBER.findall(text or "")}


def grounded(summary: str, source: str) -> bool:
    """True when every number in the summary also appears in what the model was given."""
    return numbers_in(summary) <= numbers_in(source)


def _source_text(it: Dict[str, Any]) -> str:
    return " ".join(str(it.get(k) or "") for k in ("company_name", "form_or_type", "published_date", "headline")) + " " + (it.get("summary") or "")[:SOURCE_SNIPPET_CHARS]


def summarize_batch_with_gemini(
    batch: List[Dict[str, Any]],
    api_key: str,
    timeout: int = 60,
    max_retries: int = 3,
    model: Optional[str] = None,
) -> Dict[str, str]:
    """One request for a batch. Returns {item_uid: summary} for the summaries that pass the number check.

    Raises GeminiStop when retrying can't help (unknown model, rejected key, quota used up).
    """
    if not api_key or not batch:
        return {}
    model = model or os.environ.get("GEMINI_MODEL", "").strip() or FALLBACK_GEMINI_MODEL

    by_id = {}
    payload = []
    for it in batch:
        uid = it.get("item_uid")
        by_id[uid] = it
        payload.append({
            "id": uid,
            "company": it.get("company_name"),
            "form": it.get("form_or_type"),
            "date": it.get("published_date"),
            "headline": it.get("headline"),
            "text": (it.get("summary") or "")[:SOURCE_SNIPPET_CHARS],
        })
    body = {
        "contents": [{"parts": [{"text": PROMPT + json.dumps(payload, ensure_ascii=False)}]}],
        "generationConfig": {"temperature": 0.1, "responseMimeType": "application/json"},
    }
    url = f"{GEMINI_BASE}/models/{model}:generateContent"

    for attempt in range(max_retries):
        try:
            data = _gemini_request(url, api_key, body, timeout=timeout)
            break
        except urllib.error.HTTPError as e:
            detail = _google_error(e)
            if e.code in (429, 500, 502, 503, 504) and attempt < max_retries - 1:
                wait = 8.0 * (attempt + 1)
                logger.warning("Gemini returned HTTP %s; retrying in %.0fs (%d/%d). %s", e.code, wait, attempt + 1, max_retries, detail)
                time.sleep(wait)
                continue
            if e.code in (400, 401, 403, 404, 429):
                raise GeminiStop(f"HTTP {e.code} from {model}: {detail}".strip())
            logger.warning("Gemini returned HTTP %s for this batch. %s", e.code, detail)
            return {}
        except (urllib.error.URLError, TimeoutError) as e:
            if attempt < max_retries - 1:
                time.sleep(4.0 * (attempt + 1))
                continue
            logger.warning("Could not reach Gemini (%s).", getattr(e, "reason", e))
            return {}
    else:
        return {}

    try:
        text_out = data["candidates"][0]["content"]["parts"][0]["text"].strip()
        text_out = re.sub(r"^```(?:json)?\s*|\s*```$", "", text_out)
        results = json.loads(text_out)
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as e:
        logger.warning("Gemini answer wasn't the JSON asked for (%s).", e)
        return {}
    if not isinstance(results, dict):
        return {}

    kept, dropped = {}, 0
    for uid, summary in results.items():
        if uid not in by_id or not isinstance(summary, str):
            continue
        summary = clean_text(summary)
        if not summary:
            continue
        if grounded(summary, _source_text(by_id[uid])):
            kept[uid] = summary
        else:
            dropped += 1
    if dropped:
        logger.info("Dropped %d Gemini summaries with a number that isn't in the source.", dropped)
    return kept


def _cached_ai_summaries(db_path: Optional[str]) -> Dict[str, tuple]:
    """Summaries Gemini already wrote on earlier runs, so each story is only ever sent once."""
    try:
        from pipeline.db import get_db_connection, init_db
        init_db(db_path)
        conn = get_db_connection(db_path)
        try:
            rows = conn.execute(
                "SELECT item_uid, llm_summary, summary_origin FROM news_items WHERE summary_origin LIKE 'ai:%'"
            ).fetchall()
        finally:
            conn.close()
        return {r["item_uid"]: (r["llm_summary"], r["summary_origin"]) for r in rows}
    except Exception as e:
        logger.debug("No cached summaries: %s", e)
        return {}


def summarize_items(
    items: List[Dict[str, Any]],
    api_key: Optional[str] = None,
    batch_size: int = 25,
    inter_batch_delay: float = 6.5,
    **kwargs,
) -> List[Dict[str, Any]]:
    """Attach a short summary to each item, from Gemini where it can be trusted.

    - Stories Gemini summarized on an earlier run keep that summary (read from the database when
      `db_path` is passed), so the free daily quota goes on new stories only.
    - New stories go highest score first, at most GEMINI_MAX_BATCHES requests per run (default 12),
      paced under the free tier's per-minute limit. The rest wait for the next run.
    - A summary is only kept if every number in it appears in the source text.
    - Anything without one gets the keyword fallback, marked "template" so the site doesn't show it.
    """
    gemini_key = (api_key or os.environ.get("GEMINI_API_KEY", "")).strip()
    cached = _cached_ai_summaries(kwargs.get("db_path")) if kwargs.get("db_path") else {}
    for it in items:
        hit = cached.get(it.get("item_uid"))
        if hit and not it.get("llm_summary"):
            it["llm_summary"], it["summary_origin"] = hit
        elif it.get("llm_summary") and not it.get("summary_origin"):
            it["summary_origin"] = "given"

    todo = [
        it for it in items
        if not it.get("llm_summary")
        and (it.get("form_or_type") or "").upper() not in SKIP_AI_FORMS
        and len((it.get("summary") or "").strip()) >= 40
        and not (it.get("summary") or "").startswith("Official SEC submission")
    ]
    todo.sort(key=lambda it: (float(it.get("score") or 0), it.get("published_date") or ""), reverse=True)

    if gemini_key and todo:
        try:
            max_batches = int(os.environ.get("GEMINI_MAX_BATCHES", "12"))
        except ValueError:
            max_batches = 12
        todo = todo[: max_batches * batch_size]
        written = 0
        try:
            model = _cached_model(gemini_key)
            batches = [todo[i : i + batch_size] for i in range(0, len(todo), batch_size)]
            logger.info("Summarizing %d new stories with %s in %d requests.", len(todo), model, len(batches))
            for n, batch in enumerate(batches, 1):
                try:
                    results = summarize_batch_with_gemini(batch, gemini_key, model=model)
                except GeminiStop:
                    raise
                except Exception as e:
                    logger.warning("Gemini batch %d failed: %s", n, e)
                    results = {}
                for it in batch:
                    if results.get(it.get("item_uid")):
                        it["llm_summary"] = results[it["item_uid"]]
                        it["summary_origin"] = f"ai:{model}"
                        written += 1
                if n < len(batches):
                    time.sleep(inter_batch_delay)
        except GeminiStop as e:
            logger.warning("Stopped asking Gemini: %s", e)
        logger.info("Gemini wrote %d checked summaries this run.", written)
    elif not gemini_key:
        logger.info("No GEMINI_API_KEY set; using keyword summaries, which the site doesn't display.")

    for it in items:
        if not it.get("llm_summary"):
            it["llm_summary"] = generate_fallback_summary(it)
            it["summary_origin"] = "template"
    return items
