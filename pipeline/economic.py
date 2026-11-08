"""The Economy page: five indicators from FRED and the dates of the releases that move them.

Every number comes from the source, with no key needed:
- FRED's public download files (fred.stlouisfed.org/graph/fredgraph.csv?id=...) for the figures.
- The Federal Reserve's meeting calendar, the BLS release calendar (an iCal file) and the EIA's
  weekly oil report schedule for the dates.

Nothing is typed in by hand. When a source can't be read, the last real reading or date stays (it
shows its own "as of" date), and when there has never been one the page says so instead of guessing.
"""

import csv
import datetime
import html as html_lib
import io
import json
import logging
import os
import re
import urllib.request
from contextlib import closing
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlparse

from pipeline.db import get_db_connection

logger = logging.getLogger(__name__)

USER_AGENT = "StockNewsDashboard/1.0 (contact: admin@stocknewsdashboard.local)"
FRED_CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}&cosd={start}"
FRED_SERIES_URL = "https://fred.stlouisfed.org/series/{series}"
FOMC_URL = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
BLS_ICS_URL = "https://www.bls.gov/schedule/news_release/bls.ics"
EIA_SCHEDULE_URL = "https://www.eia.gov/petroleum/supply/weekly/schedule.php"

HISTORY_DAYS = 800  # enough monthly readings for 13 points of a 12-month change
SPARK_MONTHS = 13

Fetch = Callable[[str], str]

# What each card shows. Figures, dates and changes are filled in from FRED.
INDICATORS: List[Dict[str, Any]] = [
    {
        "indicator_id": "interest_rates",
        "name": "Federal funds target range",
        "series_id": "DFEDTARU",
        "category": "Interest rates",
        "unit": "%",
        "context_note": "The range the Federal Reserve sets for overnight lending between banks. It feeds into "
                        "the cost of almost all borrowing, and into what banks earn on loans.",
    },
    {
        "indicator_id": "treasury_10y",
        "name": "10-year Treasury yield",
        "series_id": "DGS10",
        "category": "Interest rates",
        "unit": "%",
        "context_note": "What the US government pays to borrow for ten years. Mortgages and long-term company "
                        "debt are priced from it.",
    },
    {
        "indicator_id": "inflation",
        "name": "Inflation (consumer prices)",
        "series_id": "CPIAUCNS",
        "category": "Prices, change over 12 months",
        "unit": "%",
        "context_note": "How much more a typical basket of goods and services costs than a year earlier, from "
                        "the Consumer Price Index.",
    },
    {
        "indicator_id": "crude_oil",
        "name": "Crude oil (WTI)",
        "series_id": "DCOILWTICO",
        "category": "Energy",
        "unit": "$/bbl",
        "context_note": "The US benchmark price for a barrel of crude oil. It sets fuel costs for airlines, "
                        "shippers and manufacturers, and revenue for oil producers.",
    },
    {
        "indicator_id": "unemployment",
        "name": "Unemployment rate",
        "series_id": "UNRATE",
        "category": "Jobs",
        "unit": "%",
        "context_note": "The share of the labor force (people working or looking for work) who are out of "
                        "work and looking. It shapes how much households spend and borrow.",
    },
]

RELEASES: Dict[str, Dict[str, str]] = {
    "fomc": {"title": "Fed interest rate decision", "authority": "Federal Reserve",
             "about": "The Fed announces its target range for short-term interest rates.", "source_url": FOMC_URL},
    "jobs": {"title": "Jobs report", "authority": "Bureau of Labor Statistics",
             "about": "Hiring and the unemployment rate for the month before.",
             "source_url": "https://www.bls.gov/schedule/news_release/empsit.htm"},
    "cpi": {"title": "Consumer prices (CPI)", "authority": "Bureau of Labor Statistics",
            "about": "How fast prices rose over the month before, and over the year.",
            "source_url": "https://www.bls.gov/schedule/news_release/cpi.htm"},
    "eia": {"title": "Weekly oil inventories", "authority": "Energy Information Administration",
            "about": "US stocks of crude oil and fuel for the week before.", "source_url": EIA_SCHEDULE_URL},
}
BLS_SUMMARIES = {"Employment Situation": "jobs", "Consumer Price Index": "cpi"}
MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


# ---- Reading the sources ------------------------------------------------------------------------

def http_get(url: str, timeout: int = 20) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def snapshot_fetch(directory: str) -> Fetch:
    """Read saved copies of the sources instead of the network (tests and the demo build)."""
    def fetch(url: str) -> str:
        if "fredgraph.csv" in url:
            name = "fred_%s.csv" % parse_qs(urlparse(url).query)["id"][0]
        else:
            name = {FOMC_URL: "fomc.html", BLS_ICS_URL: "bls.ics", EIA_SCHEDULE_URL: "eia.html"}[url]
        with open(os.path.join(directory, name), encoding="utf-8", newline="") as f:
            return f.read()
    return fetch


def parse_fred_csv(text: str, series_id: str) -> List[Tuple[datetime.date, float]]:
    """(date, value) pairs, oldest first. Blank or "." values (holidays) are skipped."""
    rows = list(csv.reader(io.StringIO(text)))
    if not rows or len(rows[0]) < 2 or rows[0][1].strip() != series_id:
        raise ValueError(f"FRED sent something other than {series_id}")
    points = []
    for row in rows[1:]:
        if len(row) < 2:
            continue
        try:
            points.append((datetime.date.fromisoformat(row[0].strip()), float(row[1])))
        except ValueError:
            continue
    points.sort()
    return points


def read_series(series_id: str, fetch: Fetch, today: datetime.date) -> List[Tuple[datetime.date, float]]:
    start = (today - datetime.timedelta(days=HISTORY_DAYS)).isoformat()
    points = parse_fred_csv(fetch(FRED_CSV_URL.format(series=series_id, start=start)), series_id)
    if not points:
        raise ValueError(f"FRED had no readings for {series_id}")
    return points


# ---- Working out what a card shows --------------------------------------------------------------

def _month_name(d: datetime.date) -> str:
    return d.strftime("%B %Y")


def _day_name(d: datetime.date) -> str:
    return f"{d.strftime('%b')} {d.day}, {d.year}"


def _monthly(points: List[Tuple[datetime.date, float]], months: int = SPARK_MONTHS, digits: int = 2) -> List[Dict[str, Any]]:
    """The last reading of each month, for the small chart."""
    last: Dict[Tuple[int, int], Tuple[datetime.date, float]] = {}
    for d, v in points:
        last[(d.year, d.month)] = (d, v)
    return [{"date": d.isoformat(), "value": round(v, digits)} for d, v in [last[k] for k in sorted(last)][-months:]]


def _month_before(points: List[Tuple[datetime.date, float]]) -> Optional[Tuple[datetime.date, float]]:
    """For a daily series, the last reading at least 28 days before the newest one."""
    newest = points[-1][0]
    earlier = [p for p in points if p[0] <= newest - datetime.timedelta(days=28)]
    return earlier[-1] if earlier else None


def _change(now: float, then: float, unit: str, when: str, digits: int) -> Dict[str, Any]:
    delta = round(now - then, digits)
    if delta == 0:
        return {"change_value": 0.0, "change_direction": "flat", "change_text": f"Unchanged since {when}"}
    sign = "+" if delta > 0 else "−"
    size = f"${abs(delta):.{digits}f}" if unit == "$" else f"{abs(delta):.{digits}f} pts"
    return {"change_value": delta, "change_direction": "up" if delta > 0 else "down",
            "change_text": f"{sign}{size} since {when}"}


def build_indicator(spec: Dict[str, Any], fetch: Fetch, today: datetime.date) -> Dict[str, Any]:
    """One card's figures, straight from FRED. Raises when the source can't be read."""
    ind_id = spec["indicator_id"]
    item = dict(spec, source_url=FRED_SERIES_URL.format(series=spec["series_id"]))

    if ind_id == "inflation":
        index = read_series("CPIAUCNS", fetch, today)
        by_month = {(d.year, d.month): v for d, v in index}
        yoy = []
        for d, v in index:
            base = by_month.get((d.year - 1, d.month))
            if base:
                yoy.append((d, (v / base - 1) * 100))
        if len(yoy) < 2:
            raise ValueError("not enough CPI readings for a 12-month change")
        (d0, v0), (d1, v1) = yoy[-2], yoy[-1]
        item.update(current_value=round(v1, 1), previous_value=round(v0, 1), formatted_value=f"{v1:.1f}%",
                    observation_date=d1.isoformat(), as_of=_month_name(d1), history=_monthly(yoy, digits=1),
                    **_change(round(v1, 1), round(v0, 1), "pts", d0.strftime("%B"), 1))
        return item

    if ind_id == "unemployment":
        points = read_series("UNRATE", fetch, today)
        if len(points) < 2:
            raise ValueError("not enough unemployment readings")
        (d0, v0), (d1, v1) = points[-2], points[-1]
        item.update(current_value=v1, previous_value=v0, formatted_value=f"{v1:.1f}%",
                    observation_date=d1.isoformat(), as_of=_month_name(d1), history=_monthly(points, digits=1),
                    **_change(v1, v0, "pts", d0.strftime("%B"), 1))
        return item

    if ind_id == "interest_rates":
        upper = read_series("DFEDTARU", fetch, today)
        lower = read_series("DFEDTARL", fetch, today)
        try:
            effective = read_series("DFF", fetch, today)[-1][1]
        except Exception as exc:  # the range alone is still right
            logger.warning("Could not read the effective federal funds rate: %s", exc)
            effective = None
        points, low = upper, lower[-1][1]
        d1, v1 = upper[-1]
        figure = f"{low:.2f}–{v1:.2f}%" + (f" (effective rate {effective:.2f}%)" if effective is not None else "")
        digits, unit = 2, "pts"
    elif ind_id == "treasury_10y":
        points = read_series("DGS10", fetch, today)
        d1, v1 = points[-1]
        figure, digits, unit = f"{v1:.2f}%", 2, "pts"
    elif ind_id == "crude_oil":
        points = read_series("DCOILWTICO", fetch, today)
        d1, v1 = points[-1]
        figure, digits, unit = f"${v1:.2f} (a barrel)", 2, "$"
    else:
        raise ValueError(f"unknown indicator {ind_id}")

    before = _month_before(points)
    item.update(current_value=v1, formatted_value=figure, observation_date=d1.isoformat(),
                as_of=_day_name(d1), history=_monthly(points))
    if before:
        when = f"{before[0].strftime('%b')} {before[0].day}"
        item.update(previous_value=before[1], **_change(v1, before[1], unit, when, digits))
    else:
        item.update(previous_value=None, change_value=0.0, change_direction="flat", change_text="")
    return item


def generate_economic_synthesis(
    indicator_id: str,
    name: str,
    formatted_val: str,
    change_dir: str,
    change_val: float,
    relevant_tickers: List[str],
    api_key: Optional[str] = None,
) -> str:
    """One plain sentence on why the reading matters. Gemini when a key is set, else a fixed line."""
    token = api_key or os.environ.get("GEMINI_API_KEY", "").strip()
    ticker_str = ", ".join(relevant_tickers[:5]) if relevant_tickers else "the companies below"

    if token:
        try:
            from pipeline.summarize import _gemini_request, _cached_model, grounded, GEMINI_BASE
            prompt = (
                f"In one plain sentence of under 25 words, say what the latest reading of '{name}' "
                f"({formatted_val}, moving {change_dir} by {change_val}) could mean for these companies: {ticker_str}. "
                f"Use only the numbers given here. No hype, no advice. Output only the sentence."
            )
            model = _cached_model(token)
            res_data = _gemini_request(
                f"{GEMINI_BASE}/models/{model}:generateContent", token,
                {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"temperature": 0.1}}, timeout=15,
            )
            text = res_data["candidates"][0]["content"]["parts"][0]["text"].strip()
            if text and grounded(text, prompt):
                return text
        except Exception as e:  # never let the economy page depend on Gemini
            logger.debug("Gemini economic synthesis fallback: %s", type(e).__name__)

    # Plain lines that hold whichever way the companies are exposed. Only the given figure is used.
    figure = formatted_val.split(" (")[0]
    moved = {"up": "rose to", "down": "fell to"}.get(change_dir, "held at")
    if indicator_id == "interest_rates":
        return (f"The Fed's target range {moved} {figure}. Banks' lending rates move with it, so it feeds "
                f"into borrowing costs for {ticker_str}.")
    if indicator_id == "treasury_10y":
        return (f"The 10-year yield {moved} {figure}. Long-term borrowing and the value investors put on "
                f"future profits both follow it, which matters for {ticker_str}.")
    if indicator_id == "inflation":
        return (f"Prices were {figure} higher than a year earlier. Inflation moves costs, what customers can "
                f"afford and where rates go, which matters for {ticker_str}.")
    if indicator_id == "crude_oil":
        return (f"Oil {moved} {figure}. That is revenue for producers and a cost for anyone who burns fuel, "
                f"which matters for {ticker_str}.")
    if indicator_id == "unemployment":
        return (f"Unemployment {moved} {figure}. More people in work usually means more spending and fewer "
                f"missed loan payments, which matters for {ticker_str}.")
    return f"{name} {moved} {figure}, which matters for {ticker_str}."


# ---- Release dates ------------------------------------------------------------------------------

FOMC_STATEMENT_TIME = datetime.time(14, 0)  # "For release at 2:00 p.m." on each statement
EIA_STANDARD_TIME = datetime.time(10, 30)   # "10:30 a.m. eastern time on Wednesday"
EASTERN = "America/New_York"


def parse_fomc_dates(page: str) -> List[datetime.datetime]:
    """The last day of each scheduled meeting, when the decision comes out at 2:00 p.m. Eastern."""
    dates = []
    sections = re.split(r"(\d{4}) FOMC Meetings", page)
    for year_text, body in zip(sections[1::2], sections[2::2]):
        year = int(year_text)
        pairs = re.findall(r'fomc-meeting__month[^>]*>\s*<strong>([^<]+)</strong>.*?fomc-meeting__date[^>]*>([^<]+)<',
                           body, re.S)
        for month_text, day_text in pairs:
            days = re.fullmatch(r"\s*(\d{1,2})(?:-(\d{1,2}))?\*?\s*", day_text)
            months = [MONTHS.get(m.strip()[:3].lower()) for m in month_text.split("/")]
            if not days or not all(months):
                continue  # notation votes and unscheduled meetings have other wording
            first, last = int(days.group(1)), int(days.group(2) or days.group(1))
            month = months[-1] if (len(months) > 1 and last < first) else months[0]
            try:
                dates.append(datetime.datetime.combine(datetime.date(year, month, last), FOMC_STATEMENT_TIME))
            except ValueError:
                continue
    return sorted(set(dates))


def parse_bls_dates(ics: str) -> Dict[str, List[datetime.datetime]]:
    """Release times (Eastern) for the jobs report and CPI from the BLS calendar file."""
    found: Dict[str, List[datetime.datetime]] = {kind: [] for kind in BLS_SUMMARIES.values()}
    for event in re.findall(r"BEGIN:VEVENT(.*?)END:VEVENT", ics, re.S):
        summary = re.search(r"^SUMMARY:(.*?)\r?$", event, re.M)
        start = re.search(r"^DTSTART[^:\r\n]*:(\d{8})T(\d{4})", event, re.M)
        kind = BLS_SUMMARIES.get(summary.group(1).strip()) if summary else None
        if kind and start:
            found[kind].append(datetime.datetime.strptime(start.group(1) + start.group(2), "%Y%m%d%H%M"))
    return {kind: sorted(set(days)) for kind, days in found.items()}


def _long_date(text: str) -> Optional[datetime.date]:
    try:
        return datetime.datetime.strptime(re.sub(r"\s+", " ", text).strip(), "%B %d, %Y").date()
    except ValueError:
        return None


def _clock(text: str) -> Optional[datetime.time]:
    m = re.fullmatch(r"\s*(\d{1,2}):(\d{2})\s*([ap])\.?m\.?\s*", text.lower())
    if not m:
        return None
    hour = int(m.group(1)) % 12 + (12 if m.group(3) == "p" else 0)
    return datetime.time(hour, int(m.group(2)))


def parse_eia_dates(page: str, today: datetime.date, weeks: int = 8) -> List[datetime.datetime]:
    """The weekly report comes out on the Wednesday after the week it covers, except on the dates
    the EIA lists. Only weeks in years the EIA's table covers are given, so a holiday it hasn't
    listed yet can't produce a wrong date."""
    moved: Dict[datetime.date, datetime.datetime] = {}
    for row in re.findall(r"<tr.*?</tr>", page, re.S):
        cells = [html_lib.unescape(re.sub(r"<[^>]+>", " ", c)) for c in re.findall(r"<t[hd][\s>].*?</t[hd]>", row, re.S)]
        if len(cells) >= 2:
            week, release = _long_date(cells[0]), _long_date(cells[1])
            clock = _clock(cells[3]) if len(cells) >= 4 else None
            if week and release and clock:
                moved[week] = datetime.datetime.combine(release, clock)
    if not moved:
        raise ValueError("the EIA schedule table wasn't found")
    last_year = max(d.year for d in moved.values())
    friday = today - datetime.timedelta(days=(today.weekday() - 4) % 7 + 7)
    dates = []
    for _ in range(weeks):
        release = moved.get(friday) or datetime.datetime.combine(friday + datetime.timedelta(days=5), EIA_STANDARD_TIME)
        if release.year <= last_year:
            dates.append(release)
        friday += datetime.timedelta(days=7)
    return dates


def init_economic_schema(conn) -> None:
    """Tables for the indicator cards and release dates. Rows without a source are removed: they
    were typed-in placeholders from before the figures were read from FRED."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS economic_indicators (
            indicator_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            series_id TEXT NOT NULL,
            category TEXT NOT NULL,
            current_value REAL NOT NULL,
            formatted_value TEXT NOT NULL,
            unit TEXT NOT NULL,
            previous_value REAL,
            change_value REAL,
            change_direction TEXT,
            observation_date TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            context_note TEXT,
            relevant_tickers TEXT NOT NULL,
            history_json TEXT,
            ai_synthesis TEXT
        );
        """
    )
    columns = [col[1] for col in conn.execute("PRAGMA table_info(economic_indicators)").fetchall()]
    added = {
        "history_json": "ALTER TABLE economic_indicators ADD COLUMN history_json TEXT",
        "ai_synthesis": "ALTER TABLE economic_indicators ADD COLUMN ai_synthesis TEXT",
        "source_url": "ALTER TABLE economic_indicators ADD COLUMN source_url TEXT",
        "as_of": "ALTER TABLE economic_indicators ADD COLUMN as_of TEXT",
        "change_text": "ALTER TABLE economic_indicators ADD COLUMN change_text TEXT",
    }
    for column, statement in added.items():
        if column not in columns:
            conn.execute(statement)
    conn.execute("DELETE FROM economic_indicators WHERE source_url IS NULL OR source_url = ''")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS economic_releases (
            kind TEXT NOT NULL,
            release_date TEXT NOT NULL,
            release_time TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (kind, release_date)
        );
        """
    )
    conn.commit()


def _sensitive_tickers(watchlist: Optional[List[Dict[str, Any]]]) -> Dict[str, List[str]]:
    if watchlist is None:
        path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "watchlist.yaml")
        watchlist = []
        if os.path.exists(path):
            import yaml
            with open(path, "r", encoding="utf-8") as f:
                watchlist = (yaml.safe_load(f) or {}).get("tickers", [])
    found: Dict[str, List[str]] = {spec["indicator_id"]: [] for spec in INDICATORS}
    for co in watchlist or []:
        for s in co.get("economic_sensitivities") or []:
            if s in found and co.get("symbol") not in found[s]:
                found[s].append(co.get("symbol"))
    return found


def collect_economic_indicators(
    watchlist: Optional[List[Dict[str, Any]]] = None,
    db_path: Optional[str] = None,
    fetch: Fetch = http_get,
    today: Optional[datetime.date] = None,
) -> List[Dict[str, Any]]:
    """Read the five indicators from FRED and store them. One that can't be read keeps its last
    stored reading, if there is one. Returns the cards that were read this time."""
    today = today or datetime.date.today()
    tickers = _sensitive_tickers(watchlist)
    now_iso = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
    read: List[Dict[str, Any]] = []
    for spec in INDICATORS:
        try:
            item = build_indicator(spec, fetch, today)
        except Exception as exc:
            logger.warning("Could not read %s from FRED, keeping the last reading: %s", spec["name"], exc)
            continue
        item["relevant_tickers"] = item["tickers_list"] = tickers.get(spec["indicator_id"], [])
        item["ai_synthesis"] = generate_economic_synthesis(
            spec["indicator_id"], item["name"], item["formatted_value"], item["change_direction"],
            item["change_value"], item["relevant_tickers"],
        )
        item["history_json"] = json.dumps(item["history"])
        read.append(item)

    with closing(get_db_connection(db_path)) as conn:
        init_economic_schema(conn)
        for it in read:
            conn.execute(
                """
                INSERT OR REPLACE INTO economic_indicators (
                    indicator_id, name, series_id, category, current_value, formatted_value, unit,
                    previous_value, change_value, change_direction, observation_date, updated_at,
                    context_note, relevant_tickers, history_json, ai_synthesis, source_url, as_of, change_text
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    it["indicator_id"], it["name"], it["series_id"], it["category"], it["current_value"],
                    it["formatted_value"], it["unit"], it.get("previous_value"), it.get("change_value"),
                    it.get("change_direction"), it["observation_date"], now_iso, it.get("context_note"),
                    ",".join(it["relevant_tickers"]), it["history_json"], it["ai_synthesis"],
                    it["source_url"], it["as_of"], it.get("change_text", ""),
                ),
            )
        conn.commit()
    logger.info("Economic indicators read from FRED: %d of %d", len(read), len(INDICATORS))
    return read


def collect_economic_releases(
    db_path: Optional[str] = None,
    fetch: Fetch = http_get,
    today: Optional[datetime.date] = None,
) -> Dict[str, int]:
    """Read release dates from the official calendars and store them. A calendar that can't be
    read keeps the dates it gave last time. Returns how many dates each calendar gave."""
    today = today or datetime.date.today()
    found: Dict[str, List[datetime.datetime]] = {}
    try:
        found["fomc"] = parse_fomc_dates(fetch(FOMC_URL))
    except Exception as exc:
        logger.warning("Could not read the Fed's meeting calendar: %s", exc)
    try:
        found.update(parse_bls_dates(fetch(BLS_ICS_URL)))
    except Exception as exc:
        logger.warning("Could not read the BLS release calendar: %s", exc)
    try:
        found["eia"] = parse_eia_dates(fetch(EIA_SCHEDULE_URL), today)
    except Exception as exc:
        logger.warning("Could not read the EIA's weekly report schedule: %s", exc)

    now_iso = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
    counts = {}
    with closing(get_db_connection(db_path)) as conn:
        init_economic_schema(conn)
        for kind, days in found.items():
            if not days:
                logger.warning("The %s calendar had no dates; keeping the last ones", kind)
                continue
            conn.execute("DELETE FROM economic_releases WHERE kind = ?", (kind,))
            conn.executemany(
                "INSERT INTO economic_releases (kind, release_date, release_time, updated_at) VALUES (?, ?, ?, ?)",
                [(kind, d.date().isoformat(), d.strftime("%H:%M"), now_iso) for d in days],
            )
            counts[kind] = len(days)
        conn.commit()
    logger.info("Economic release dates read: %s", counts or "none")
    return counts


def _time_text(clock: str) -> str:
    t = datetime.datetime.strptime(clock, "%H:%M")
    return f"{t.hour % 12 or 12}:{t.minute:02d} {'a.m.' if t.hour < 12 else 'p.m.'} ET"


def get_upcoming_economic_events(
    db_path: Optional[str] = None, now: Optional[datetime.datetime] = None, per_kind: int = 2
) -> List[Dict[str, Any]]:
    """The next releases of each kind that haven't come out yet (times are US Eastern).

    The first of each kind is shown; the rest are marked "later" so the page can move on to them
    itself when it is read after the first one is out.
    """
    from zoneinfo import ZoneInfo
    eastern = ZoneInfo(EASTERN)
    if now is None:
        now = datetime.datetime.now(eastern).replace(tzinfo=None)
    with closing(get_db_connection(db_path)) as conn:
        if not conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='economic_releases'").fetchone():
            return []
        rows = conn.execute(
            "SELECT kind, release_date, release_time FROM economic_releases WHERE release_date >= ? "
            "ORDER BY release_date, release_time", (now.date().isoformat(),)
        ).fetchall()
    events: List[Dict[str, Any]] = []
    taken: Dict[str, int] = {}
    for row in rows:
        meta = RELEASES.get(row["kind"])
        when = datetime.datetime.fromisoformat(f"{row['release_date']}T{row['release_time']}")
        if not meta or when <= now or taken.get(row["kind"], 0) >= per_kind:
            continue
        events.append(dict(meta, event_id=row["kind"], date=row["release_date"],
                           time_text=_time_text(row["release_time"]), later=row["kind"] in taken,
                           at=when.replace(tzinfo=eastern).isoformat()))
        taken[row["kind"]] = taken.get(row["kind"], 0) + 1
    return events
