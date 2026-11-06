"""What a filing actually says, read from the SEC's own free data.

The submissions list only tells us that a filing exists. This module opens each recent filing and
writes one plain sentence from the numbers inside it:

- Form 4 (insider trades): who, their role, bought or sold, shares, price, value, plan or not.
- Form 144 (planned insider sales): who, shares, value, approximate date.
- 8-K: what the filing is about (its item codes) and the opening of its press release or body.
- 10-Q / 10-K: revenue, net income and diluted EPS for the period, and the change from a year earlier,
  from the XBRL figures the company itself tagged in that filing.

Every figure comes from the filing. Nothing is estimated except the value of an insider trade,
which is shares times the reported price.

Results are cached in SQLite by accession number, so each filing is fetched once. Requests are paced
well under the SEC's 10 per second limit, and capped per run.
"""

import gzip
import html
import json
import logging
import re
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from collectors.edgar import DEFAULT_USER_AGENT
from pipeline.db import get_db_connection, init_db

logger = logging.getLogger(__name__)

ARCHIVE_DIR = "https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc_clean}/"
CONCEPT_URL = "https://data.sec.gov/api/xbrl/companyconcept/CIK{cik_10}/us-gaap/{concept}.json"

# 8-K item codes, in plain English. 9.01 (exhibits) never says anything on its own.
EIGHT_K_ITEMS = {
    "1.01": "New material agreement",
    "1.02": "Material agreement ended",
    "1.03": "Bankruptcy or receivership",
    "1.04": "Mine safety",
    "1.05": "Cybersecurity incident",
    "2.01": "Acquisition or sale completed",
    "2.02": "Quarterly results",
    "2.03": "New debt or financial obligation",
    "2.04": "Debt repayment accelerated",
    "2.05": "Restructuring or exit costs",
    "2.06": "Asset impairment",
    "3.01": "Stock exchange listing notice",
    "3.02": "Unregistered share sale",
    "3.03": "Change to shareholder rights",
    "4.01": "Change of auditor",
    "4.02": "Earlier financial statements no longer reliable",
    "5.01": "Change in control",
    "5.02": "Director or executive change",
    "5.03": "Bylaw or fiscal year change",
    "5.04": "Pension plan trading halt",
    "5.05": "Code of ethics change",
    "5.07": "Shareholder vote results",
    "5.08": "Shareholder nominations",
    "7.01": "Investor disclosure",
    "8.01": "Other company event",
}

FORM4_PAST = {
    "S": "sold {n} shares",
    "P": "bought {n} shares",
    "A": "received {n} shares as a stock award",
    "M": "exercised options for {n} shares",
    "F": "had {n} shares withheld for tax",
    "G": "gave away {n} shares",
    "C": "converted {n} shares",
    "D": "returned {n} shares to the company",
}
FORM4_PRESENT = {
    "S": "sells {n} shares",
    "P": "buys {n} shares",
    "A": "receives {n} shares as a stock award",
    "M": "exercises options for {n} shares",
    "F": "has {n} shares withheld for tax",
    "G": "gives away {n} shares",
    "C": "converts {n} shares",
    "D": "returns {n} shares to the company",
}

REVENUE_CONCEPTS = (
    "Revenues",
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "RevenueFromContractWithCustomerIncludingAssessedTax",
    "RevenuesNetOfInterestExpense",
    "SalesRevenueNet",
)
NET_INCOME_CONCEPTS = ("NetIncomeLoss", "ProfitLoss")
EPS_CONCEPTS = ("EarningsPerShareDiluted", "EarningsPerShareBasicAndDiluted")

BOILERPLATE_PARAGRAPH = re.compile(
    r"forward-looking statement|safe harbor|pursuant to the requirements of the securities exchange act"
    r"|check the appropriate box|securities registered pursuant|emerging growth company"
    r"|commission file number|^exhibit\b|table of contents",
    re.IGNORECASE,
)
ENTITY_WORDS = re.compile(r"\b(inc|llc|lp|l\.p|ltd|trust|corp|corporation|fund|group|partners|holdings|co)\b\.?$", re.I)


# --- Small formatting helpers ---------------------------------------------------------------

def money(value: float) -> str:
    """$478.8 billion, $912 million, $781,474, $2.10."""
    sign = "-" if value < 0 else ""
    v = abs(value)
    if v >= 1e9:
        return f"{sign}${v / 1e9:,.1f} billion"
    if v >= 1e6:
        return f"{sign}${v / 1e6:,.1f} million"
    if v >= 1000:
        return f"{sign}${v:,.0f}"
    return f"{sign}${v:,.2f}"


def change_phrase(current: float, prior: Optional[float], fmt=None) -> str:
    """', up 12%' against the year before, when both years are positive; otherwise nothing.

    From a very small base a percentage stops meaning much ("up 2168%"), so it says
    ', up from $189.0 million' instead.
    """
    if prior is None or prior <= 0 or current <= 0:
        return ""
    pct = round((current - prior) / prior * 100)
    if pct == 0:
        return ", flat"
    if pct >= 100:
        return f", up from {(fmt or money)(prior)}"
    return f", {'up' if pct > 0 else 'down'} {abs(pct)}%"


def short_date(iso: str) -> str:
    try:
        d = datetime.strptime(iso[:10], "%Y-%m-%d")
    except (ValueError, TypeError):
        return iso or ""
    return f"{d.strftime('%b')} {d.day}, {d.year}"


def person_name(raw: str, is_individual: bool = True) -> str:
    """SEC lists people as 'Newstead Jennifer'; show 'Jennifer Newstead'. Leave companies alone."""
    raw = re.sub(r"\s+", " ", (raw or "").strip())
    if not raw:
        return ""
    parts = raw.split(" ")
    if is_individual and len(parts) >= 2 and not ENTITY_WORDS.search(raw):
        parts = parts[1:] + parts[:1]
    name = " ".join(parts)
    if name.isupper() or name.islower():
        name = name.title()
    return name


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _find(node: ET.Element, *path: str) -> Optional[ET.Element]:
    """Find by local tag names, ignoring XML namespaces."""
    current = [node]
    for name in path:
        nxt = []
        for c in current:
            nxt.extend(el for el in c.iter() if _local(el.tag) == name and el is not c)
        if not nxt:
            return None
        current = nxt[:1]
    return current[0]


def _text(node: Optional[ET.Element], *path: str) -> str:
    if node is None:
        return ""
    el = _find(node, *path) if path else node
    if el is None:
        return ""
    value = _find(el, "value")
    return ((value.text if value is not None else el.text) or "").strip()


def _num(raw: str) -> Optional[float]:
    try:
        return float(str(raw).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def _shares(n: float) -> str:
    return f"{n:,.0f}" if n == int(n) else f"{n:,.2f}"


# --- Form 4 ---------------------------------------------------------------------------------

def describe_form4(xml_text: str) -> Tuple[str, str]:
    """(headline, sentence) for an insider trade, or ('', '') if there's nothing to say."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return "", ""

    owner = _find(root, "reportingOwner")
    rel = _find(owner, "reportingOwnerRelationship") if owner is not None else None
    is_dir = _text(rel, "isDirector").lower() in ("1", "true")
    is_off = _text(rel, "isOfficer").lower() in ("1", "true")
    is_ten = _text(rel, "isTenPercentOwner").lower() in ("1", "true")
    title = _text(rel, "officerTitle")
    name = person_name(_text(owner, "rptOwnerName"), is_individual=is_dir or is_off)
    role = title or ("Director" if is_dir else "") or ("10% owner" if is_ten else "")
    who = f"{name} ({role})" if name and role else name or "An insider"

    totals: Dict[str, Dict[str, float]] = {}
    order: List[str] = []
    after = None
    for tx in (el for el in root.iter() if _local(el.tag) == "nonDerivativeTransaction"):
        code = _text(tx, "transactionCode").upper()
        shares = _num(_text(tx, "transactionShares")) or 0.0
        price = _num(_text(tx, "transactionPricePerShare")) or 0.0
        if not code or shares <= 0:
            continue
        if code not in totals:
            totals[code] = {"shares": 0.0, "value": 0.0, "count": 0}
            order.append(code)
        totals[code]["count"] += 1
        totals[code]["shares"] += shares
        totals[code]["value"] += shares * price
        held = _num(_text(tx, "sharesOwnedFollowingTransaction"))
        if held is not None:
            after = held

    if not order:
        return _describe_grants(root, who, name)

    # Lead with the trade an investor cares about: open-market sales and purchases first.
    order.sort(key=lambda c: {"S": 0, "P": 1}.get(c, 2))

    def did(code: str) -> str:
        t = totals[code]
        clause = FORM4_PAST.get(code, "reported a transaction in {n} shares").format(n=_shares(t["shares"]))
        if t["value"] > 0 and code in ("S", "P"):
            avg = t["value"] / t["shares"]
            clause += f" at {'an average of ' if t['count'] > 1 else ''}{money(avg)}, about {money(t['value'])}"
        return clause

    lead = order[0]
    sentence = f"{who} {did(lead)}"
    planned = _text(root, "aff10b5One").lower() in ("1", "true") or "10b5-1" in xml_text
    if planned and lead in ("S", "P"):
        sentence += ", under a pre-arranged trading plan"
    sentence += "."
    rest = [did(c) for c in order[1:]]
    if rest:
        also = rest[0] if len(rest) == 1 else ", ".join(rest[:-1]) + " and " + rest[-1]
        sentence += f" Also {also}."
    if after is not None:
        sentence += f" Now holds {_shares(after)} shares."

    who_short = f"insider {name}" if name else "insider"
    t = totals[lead]
    if lead in ("S", "P") and t["value"]:
        headline = f"{who_short} {'sells' if lead == 'S' else 'buys'} {money(t['value'])} of stock"
    else:
        headline = f"{who_short} " + FORM4_PRESENT.get(lead, "reports a trade in {n} shares").format(n=_shares(t["shares"]))
    return headline, sentence


def _describe_grants(root: ET.Element, who: str, name: str) -> Tuple[str, str]:
    """Forms with only derivative rows: usually restricted stock units or options being granted."""
    grants: Dict[Tuple[str, str], float] = {}
    for tx in (el for el in root.iter() if _local(el.tag) == "derivativeTransaction"):
        code = _text(tx, "transactionCode").upper()
        shares = _num(_text(tx, "transactionShares")) or 0.0
        title = re.split(r"\s[-–(]", re.sub(r"\s+", " ", _text(tx, "securityTitle")).strip())[0]
        # Lower-case ordinary words, keep acronyms such as "SSPS" as they are.
        title = " ".join(w if w.isupper() and len(w) > 1 else w.lower() for w in title.split()) or "derivative securities"
        if code and shares > 0:
            grants[(code, title)] = grants.get((code, title), 0.0) + shares
    if not grants:
        return "", ""
    (code, title), n = max(grants.items(), key=lambda kv: kv[1])
    words = title.split()
    # Pluralize the last ordinary word: "stock option" -> "stock options", "units SSPS" stays.
    for i in range(len(words) - 1, -1, -1):
        if not words[i].isupper():
            if not words[i].endswith("s"):
                words[i] += "s"
            break
    plural = " ".join(words)
    if code == "A":
        did, does = f"was granted {_shares(n)} {plural}", f"is granted {_shares(n)} {plural}"
    elif code == "M":
        did, does = f"converted {_shares(n)} {plural} into shares", f"converts {_shares(n)} {plural} into shares"
    else:
        did, does = f"reported a change in {_shares(n)} {plural}", f"reports a change in {_shares(n)} {plural}"
    who_short = f"insider {name}" if name else "insider"
    return f"{who_short} {does}", f"{who} {did}."


# --- Form 144 -------------------------------------------------------------------------------

def describe_form144(xml_text: str) -> Tuple[str, str]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return "", ""
    name = person_name(_text(root, "nameOfPersonForWhoseAccountTheSecuritiesAreToBeSold"), is_individual=False)
    relation = _text(root, "relationshipToIssuer")
    units = _num(_text(root, "noOfUnitsSold"))
    value = _num(_text(root, "aggregateMarketValue"))
    when = _text(root, "approxSaleDate")
    plan = _text(root, "planAdoptionDate")
    if not units:
        return "", ""
    who = f"{name} ({relation})" if name and relation else name or "An insider"
    sentence = f"{who} plans to sell {_shares(units)} shares"
    if value:
        sentence += f", worth about {money(value)}"
    if when:
        sentence += f", around {_us_date(when)}"
    if plan:
        sentence += f", under a trading plan adopted {_us_date(plan)}"
    sentence += "."
    headline = f"insider {name} plans" if name else "insider plans"
    headline += f" {money(value)} share sale" if value else f" sale of {_shares(units)} shares"
    return headline, sentence


def _us_date(raw: str) -> str:
    try:
        return short_date(datetime.strptime(raw.strip(), "%m/%d/%Y").strftime("%Y-%m-%d"))
    except ValueError:
        return raw


# --- 8-K ------------------------------------------------------------------------------------

def item_labels(items: str) -> List[str]:
    codes = [c.strip() for c in (items or "").split(",") if c.strip()]
    return [EIGHT_K_ITEMS[c] for c in codes if c in EIGHT_K_ITEMS]


def html_paragraphs(raw_html: str) -> List[str]:
    """Readable paragraphs from a filing's HTML, in order."""
    text = re.sub(r"(?is)<(script|style|head|title)\b.*?</\1>", " ", raw_html)
    text = re.sub(r"(?is)<ix:header>.*?</ix:header>", " ", text)
    text = re.sub(r"(?i)<\s*(br|/p|/div|/tr|/li|/h\d|/table)\b[^>]*>", "\n", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = html.unescape(text).replace("\xa0", " ")
    out: List[str] = []
    for line in text.split("\n"):
        line = re.sub(r"\s+", " ", line).strip()
        if not line:
            continue
        # Some filings break every printed line; rejoin a sentence that carries on to the next line.
        if out and not re.search(r"[.!?:;][\"”’)]?$", out[-1]) and re.match(r"[a-z0-9€$£(%]", line):
            out[-1] += " " + line
        else:
            out.append(line)
    return out


def excerpt(paragraphs: List[str], limit: int = 900, skip_until: Optional[re.Pattern] = None) -> str:
    """The first real sentences: long paragraphs that aren't legal boilerplate, up to `limit` chars."""
    started = skip_until is None
    chosen: List[str] = []
    size = 0
    for p in paragraphs:
        p = re.sub(r"^\((?:[a-z]|[ivx]{1,4}|\d{1,2})\)\s+", "", p)  # "(b) On November 4, ..."
        if not started:
            if skip_until.search(p):
                started = True
            continue
        if len(p) < 100 or not re.search(r"[.!?][\"”’)]?$", p) or BOILERPLATE_PARAGRAPH.search(p):
            continue
        if p[0] in "\"“" and chosen:  # executives' quotes add words, rarely facts
            continue
        if re.match(r"^(\d{1,2}|\*+|\(\d{1,2}\))\s", p):
            if len(p) < 400:
                continue  # a footnote
            p = re.sub(r"^\d{1,2}\s+", "", p)  # a page number in front of a whole page of text
        if not (p[0].isupper() or p[0].isdigit() or p[0] in "\"“$"):
            continue  # a fragment split off the middle of a sentence
        words = [w for w in re.findall(r"[A-Za-z]{4,}", p)]
        if words and sum(w[0].isupper() for w in words) / len(words) > 0.6:
            continue  # a heading such as "Departure of Directors or Certain Officers; ..."
        if re.match(r"(?i)item\s+9\.01", p):
            break
        chosen.append(p)
        size += len(p) + 1
        if size >= limit:
            break
    text = " ".join(chosen)
    if len(text) > limit:
        cut = text[:limit]
        ends = [m.end() for m in re.finditer(r"[.!?][\"”’)]?\s", cut)]
        text = cut[: ends[-1]].strip() if ends and ends[-1] > 150 else cut.rsplit(" ", 1)[0] + "…"
    return text


def exhibit_documents(index_html: str) -> List[Tuple[str, str]]:
    """(type, href) for each document row of a filing index page."""
    docs = []
    for row in re.findall(r"(?is)<tr[^>]*>(.*?)</tr>", index_html):
        cells = re.findall(r"(?is)<td[^>]*>(.*?)</td>", row)
        if len(cells) < 4:
            continue
        href = re.search(r'(?i)href="([^"]+)"', cells[2])
        doc_type = re.sub(r"<[^>]+>", "", cells[3]).strip().upper()
        if href:
            # "/ix?doc=/Archives/..." is the interactive viewer, which needs JavaScript; open the document itself.
            docs.append((doc_type, re.sub(r"^/ix\?doc=", "", href.group(1))))
    return docs


# --- 10-Q / 10-K ----------------------------------------------------------------------------

def period_figures(concept_data: Optional[Dict[str, Any]], accession: str, annual: bool) -> Tuple[Optional[float], Optional[float], str]:
    """(this period, same period a year earlier, period end) for one concept in one filing."""
    if not concept_data:
        return None, None, ""
    facts = []
    for unit_facts in (concept_data.get("units") or {}).values():
        for f in unit_facts:
            if f.get("accn") != accession or not f.get("start") or not f.get("end"):
                continue
            try:
                start = date.fromisoformat(f["start"])
                end = date.fromisoformat(f["end"])
            except ValueError:
                continue
            days = (end - start).days
            if (annual and 330 <= days <= 380) or (not annual and 80 <= days <= 100):
                facts.append((end, f.get("val")))
    if not facts:
        return None, None, ""
    facts.sort(key=lambda x: x[0], reverse=True)
    end, current = facts[0]
    prior = next((v for e, v in facts[1:] if 330 <= (end - e).days <= 400), None)
    return _num(current), _num(prior), end.isoformat()


def describe_financials(concepts: Dict[str, Optional[Dict[str, Any]]], accession: str, form: str) -> Tuple[str, str]:
    """Revenue, net income and diluted EPS for the period the filing covers."""
    annual = form.upper().startswith("10-K")
    parts: List[str] = []
    period_end = ""
    picked: Dict[str, Tuple[float, Optional[float]]] = {}
    for label, names in (("revenue", REVENUE_CONCEPTS), ("net income", NET_INCOME_CONCEPTS), ("diluted earnings per share", EPS_CONCEPTS)):
        for name in names:
            cur, prior, end = period_figures(concepts.get(name), accession, annual)
            if cur is not None:
                picked[label] = (cur, prior)
                period_end = period_end or end
                break
    if not picked:
        return "", ""
    for label, (cur, prior) in picked.items():
        fmt = money if label != "diluted earnings per share" else (lambda v: f"{'-' if v < 0 else ''}${abs(v):.2f}")
        shown = fmt(cur)
        if label == "net income" and cur < 0:
            parts.append(f"net loss {money(abs(cur))}")
            continue
        parts.append(f"{label} {shown}{change_phrase(cur, prior, fmt)}")
    span = "Year" if annual else "Quarter"
    sentence = f"{span} ended {short_date(period_end)}: " + "; ".join(parts) + "."
    if any(prior is not None and prior > 0 and cur > 0 for cur, prior in picked.values()):
        sentence += " Changes are against the same period a year earlier."
    headline = ""
    if "revenue" in picked:
        cur, prior = picked["revenue"]
        headline = f"{'annual' if annual else 'quarterly'} report: revenue {money(cur)}{change_phrase(cur, prior)}"
    return headline, sentence


# --- Fetching and caching -------------------------------------------------------------------

class _Fetcher:
    def __init__(self, user_agent: str, delay: float, max_requests: int):
        self.user_agent = user_agent
        self.delay = delay
        self.left = max_requests
        self.last = 0.0

    def get(self, url: str, timeout: int = 20) -> Optional[str]:
        if self.left <= 0:
            return None
        self.left -= 1
        wait = self.delay - (time.monotonic() - self.last)
        if wait > 0:
            time.sleep(wait)
        self.last = time.monotonic()
        req = urllib.request.Request(url, headers={"User-Agent": self.user_agent, "Accept-Encoding": "gzip"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
                if resp.info().get("Content-Encoding") == "gzip":
                    raw = gzip.decompress(raw)
                return raw.decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return ""
            logger.debug("SEC fetch %s failed: HTTP %s", url, e.code)
        except Exception as e:  # network trouble: try again on a later run
            logger.debug("SEC fetch %s failed: %s", url, e)
        return None


def _load_cache(db_path: Optional[str]) -> Dict[str, Tuple[str, str]]:
    conn = get_db_connection(db_path)
    try:
        return {r["accession"]: (r["headline"] or "", r["detail"] or "") for r in conn.execute("SELECT accession, headline, detail FROM filing_details")}
    finally:
        conn.close()


def _save_cache(rows: List[Tuple[str, str, str]], db_path: Optional[str]) -> None:
    if not rows:
        return
    conn = get_db_connection(db_path)
    with conn:
        conn.executemany(
            "INSERT OR REPLACE INTO filing_details (accession, headline, detail, fetched_at) VALUES (?, ?, ?, CURRENT_TIMESTAMP)",
            rows,
        )
    conn.close()


def _raw_xml_doc(primary_doc: str) -> str:
    """'xslF345X06/form4.xml' is the styled view; the data is 'form4.xml'."""
    return re.sub(r"^xsl[^/]*/", "", primary_doc or "")


def _describe(filing: Dict[str, Any], fetch: _Fetcher, concept_cache: Dict[Tuple[str, str], Optional[Dict[str, Any]]]) -> Optional[Tuple[str, str]]:
    """(headline, detail) for one filing; None means try again on a later run."""
    form = (filing.get("form") or "").upper()
    cik_10 = filing.get("cik", "")
    cik_int = str(int(cik_10)) if str(cik_10).isdigit() else str(cik_10)
    acc = filing.get("accession_number", "")
    base = ARCHIVE_DIR.format(cik_int=cik_int, acc_clean=acc.replace("-", ""))

    if form in ("4", "4/A", "144", "144/A"):
        doc = _raw_xml_doc(filing.get("primary_doc_name", ""))
        if not doc.lower().endswith(".xml"):
            return "", ""
        body = fetch.get(base + doc)
        if body is None:
            return None
        return describe_form4(body) if form.startswith("4") else describe_form144(body)

    if form in ("8-K", "8-K/A"):
        labels = item_labels(filing.get("items", ""))
        headline = f"8-K: {', '.join(labels[:2])}" if labels else ""
        index = fetch.get(base + f"{acc}-index.htm")
        if index is None:
            return None
        docs = exhibit_documents(index)
        target = next((h for t, h in docs if t.startswith("EX-99")), None)
        skip = None
        if not target:
            target = filing.get("primary_doc_name") or next((h for t, h in docs if t.startswith("8-K")), None)
            skip = re.compile(r"(?i)^item\s+[1-8]\.\d\d")
        if not target:
            return headline, ""
        url = target if target.startswith("http") else ("https://www.sec.gov" + target if target.startswith("/") else base + target)
        body = fetch.get(url)
        if body is None:
            return None
        return headline, excerpt(html_paragraphs(body), skip_until=skip)

    if form in ("10-Q", "10-K", "10-Q/A", "10-K/A"):
        concepts: Dict[str, Optional[Dict[str, Any]]] = {}
        for group in (REVENUE_CONCEPTS, NET_INCOME_CONCEPTS, EPS_CONCEPTS):
            for name in group:
                key = (cik_10, name)
                if key not in concept_cache:
                    raw = fetch.get(CONCEPT_URL.format(cik_10=cik_10, concept=name))
                    if raw is None:
                        return None
                    try:
                        concept_cache[key] = json.loads(raw) if raw else None
                    except json.JSONDecodeError:
                        concept_cache[key] = None
                concepts[name] = concept_cache[key]
                if period_figures(concepts[name], acc, form.startswith("10-K"))[0] is not None:
                    break
        return describe_financials(concepts, acc, form)

    return "", ""


def _match_planned_sale_names(filings: List[Dict[str, Any]]) -> None:
    """Form 144 gives names in either order ('Cook Timothy D'); use the Form 4 spelling when it's the same person."""
    known: Dict[frozenset, str] = {}
    for f in filings:
        m = re.match(r"insider (.+?) (?:sells|buys|receives|exercises|has|gives|converts|returns|reports)\b", f.get("detail_headline", ""))
        if m:
            known[frozenset(m.group(1).lower().split())] = m.group(1)
    for f in filings:
        m = re.match(r"insider (.+?) plans\b", f.get("detail_headline", ""))
        if not m:
            continue
        raw = m.group(1)
        better = known.get(frozenset(raw.lower().split()))
        if better and better != raw:
            f["detail_headline"] = f["detail_headline"].replace(raw, better, 1)
            f["detail_text"] = f.get("detail_text", "").replace(raw, better, 1)


def enrich_filings(
    filings: List[Dict[str, Any]],
    db_path: Optional[str] = None,
    user_agent: Optional[str] = None,
    max_age_days: int = 100,
    max_requests: int = 900,
    delay_seconds: float = 0.12,
) -> List[Dict[str, Any]]:
    """Add 'detail_headline' and 'detail_text' to each raw filing record, in place.

    Filings already looked at are read from the cache. New ones are fetched, newest first, until the
    per-run request budget runs out; the rest wait for the next run.
    """
    if not filings:
        return filings
    init_db(db_path)
    cache = _load_cache(db_path)
    fetch = _Fetcher(user_agent or DEFAULT_USER_AGENT, delay_seconds, max_requests)
    concept_cache: Dict[Tuple[str, str], Optional[Dict[str, Any]]] = {}
    cutoff = (date.today() - timedelta(days=max_age_days)).isoformat()
    new_rows: List[Tuple[str, str, str]] = []
    looked_up = 0

    for filing in sorted(filings, key=lambda f: f.get("filing_date", ""), reverse=True):
        acc = filing.get("accession_number", "")
        if not acc:
            continue
        if acc in cache:
            headline, detail = cache[acc]
        elif filing.get("filing_date", "") >= cutoff and fetch.left > 0:
            try:
                found = _describe(filing, fetch, concept_cache)
            except Exception as e:  # one odd filing must not stop the run
                logger.debug("Could not read filing %s: %s", acc, e)
                found = None
            if found is None:
                continue
            headline, detail = found
            new_rows.append((acc, headline, detail))
            cache[acc] = found
            looked_up += 1
        else:
            continue
        if headline:
            filing["detail_headline"] = headline
        if detail:
            filing["detail_text"] = detail

    _save_cache(new_rows, db_path)
    _match_planned_sale_names(filings)
    described = sum(1 for f in filings if f.get("detail_text"))
    logger.info(
        "Read %d new SEC filings (%d requests); %d of %d filings now have their figures",
        looked_up, max_requests - fetch.left, described, len(filings),
    )
    return filings
