"""The Your portfolio page (site/portfolio.html).

The page's own scripts are plain .js files next to this one, so Node can test the same source the
page runs (tests/node/portfolio_*.test.mjs). There is still no build step: at render time they are
put into the page as one inline script, which the page's Content-Security-Policy then hashes.
"""

import os
from datetime import date, timedelta
from typing import Any, Dict, Iterable, List, Optional

_HERE = os.path.dirname(__file__)

# In the order they run. Each later file may use what the earlier ones define.
PORTFOLIO_SCRIPTS = ("portfolio_input.js", "portfolio_math.js", "portfolio_brief_logic.js", "portfolio_app.js", "portfolio_xray.js",
                     "portfolio_summary.js", "portfolio_brief.js", "portfolio_whatif.js")

BRIEF_EVENT_DAYS = 45   # how far ahead "Coming up" looks
BRIEF_MOVE_DAYS = 14    # how far back a big price day still counts as news
BRIEF_TEXT = 240        # longest summary kept per story


def _script(name: str) -> str:
    with open(os.path.join(_HERE, name), "r", encoding="utf-8") as f:
        source = f.read()
    # The files go into a Jinja template inside a raw block and then into a <script> block,
    # so neither of those may be ended from inside them.
    for banned in ("{% endraw %}", "</script", "<!--"):
        if banned in source:
            raise ValueError(f"{name} contains {banned!r}")
    return source


def portfolio_scripts() -> str:
    return "\n".join(_script(name) for name in PORTFOLIO_SCRIPTS)


def portfolio_data(companies: List[Dict[str, Any]], sectors: List[str]) -> Dict[str, Any]:
    """What the page needs to know about the watchlist that the shared script doesn't already carry."""
    known = {co["symbol"] for co in companies}
    other = {}
    for co in companies:
        for ticker in co.get("other_tickers") or []:
            ticker = str(ticker).upper().strip()
            if ticker and ticker not in known:
                other[ticker] = co["symbol"]
    def strings(co, field):
        return [str(v).strip() for v in (co.get(field) or []) if isinstance(v, str) and str(v).strip()]

    def entities(co, field):
        # A customer or supplier the site follows is named by its ticker, however the list spells it.
        return [v.upper() if v.upper() in known else v for v in strings(co, field)]

    details = {}
    for co in companies:
        entry = {
            "th": strings(co, "themes"),
            "ec": strings(co, "economic_sensitivities"),
            "cu": entities(co, "key_customers"),
            "su": entities(co, "key_suppliers"),
            "co": [v.upper() for v in strings(co, "competitors") if v.upper() in known],
        }
        # Every followed company has an entry, even an empty one: that is how the page tells
        # "nothing noted about it" from "not a company we follow".
        details[co["symbol"]] = {k: v for k, v in entry.items() if v}
    return {"sectors": list(sectors), "other": other, "companies": details}


def _story_kind(item: Dict[str, Any]) -> str:
    source = item.get("source") or ""
    if source == "sec_edgar":
        return "results" if item.get("category") == "Earnings & Financials" else "filing"
    if source == "company_ir":
        return "release"
    return "news"


def _event_kind(event_type: str) -> str:
    if "Earnings" in event_type:
        return "results"
    if "Dividend" in event_type:
        return "dividend"
    if "SEC" in event_type or "Statutory" in event_type:
        return "filing"
    return "event"


def brief_data(
    feed_items: Iterable[Dict[str, Any]],
    calendar_events: Iterable[Dict[str, Any]],
    deck: Optional[Dict[str, Any]],
    generated: str,
    today: Optional[date] = None,
) -> Dict[str, Any]:
    """site/data/brief.json: what the Briefing tab ranks against the holdings, in the browser.

    It's the same for every visitor and carries no holdings: the page fetches it and does the
    matching itself, so what someone owns never leaves their browser."""
    today = today or date.today()
    stories = []
    for it in feed_items:
        ticker = it.get("ticker") or ""
        if not ticker:
            continue
        related = sorted({t for t in (it.get("related_tickers_list") or []) if t and t != ticker})
        refs = {r.get("related_ticker"): (r.get("impact_note") or "")[:160]
                for r in it.get("cross_references_list") or [] if r.get("related_ticker")}
        summary = str(it.get("ai_summary") or it.get("story_text") or "").strip()
        stories.append({
            "t": ticker,
            "rel": related,
            "why": {k: v for k, v in refs.items() if k in related and v},
            "d": str(it.get("published_date") or "")[:10],
            "h": it.get("clean_headline") or it.get("headline") or "",
            "u": it.get("url") or "",
            "k": _story_kind(it),
            "c": it.get("category") or "",
            "s": round(float(it.get("score") or 0), 1),
            "src": it.get("source_label") or "",
            "x": summary[:BRIEF_TEXT] + ("…" if len(summary) > BRIEF_TEXT else ""),
        })
    last = (today + timedelta(days=BRIEF_EVENT_DAYS)).isoformat()
    events = []
    for ev in calendar_events:
        when = str(ev.get("event_date") or "")[:10]
        if ev.get("ticker") and today.isoformat() <= when <= last:
            events.append({"t": ev["ticker"], "d": when, "k": _event_kind(str(ev.get("event_type") or "")),
                           "h": ev.get("headline") or "", "u": ev.get("source_url") or "",
                           "est": ev.get("source_type") == "ESTIMATED_RULE"})
    events.sort(key=lambda e: (e["d"], e["t"]))
    since = (today - timedelta(days=BRIEF_MOVE_DAYS)).isoformat()
    days = []
    for card in (deck or {}).get("cards") or []:
        for day in card.get("days") or []:
            if day.get("date", "") >= since:
                days.append({"t": card["symbol"], "d": day["date"], "m": day["move"], "mk": day.get("market"),
                             "v": day.get("verdict")})
    days.sort(key=lambda x: (x["d"], x["t"]), reverse=True)
    return {"v": 1, "generated": generated, "stories": stories, "events": events, "days": days}


PORTFOLIO_CSS = """
    .page-portfolio .app-main { max-width: 60rem; }
    .page-portfolio [hidden] { display: none !important; }
    .pf-banner { margin: 0 0 1.5rem; padding: 0.6rem 0.9rem; border-radius: var(--radius-md); background: var(--warn-soft); color: var(--warn); font-size: 0.9rem; }
    .pf-section { padding: 1.75rem 0; border-top: 1px solid var(--border-subtle); }
    .pf-section > .settings-heading { margin-bottom: 0.75rem; }
    .pf-note { margin: 0.5rem 0 0; font-size: 0.86rem; line-height: 1.45; color: var(--text-muted); max-width: 40rem; }
    .pf-note a { color: var(--accent); text-decoration: none; }
    .pf-note a:hover { text-decoration: underline; }
    .pf-add { display: flex; flex-wrap: wrap; align-items: center; gap: 0.6rem; }
    .pf-input { min-height: 40px; box-sizing: border-box; padding: 0.45rem 0.7rem; border: 1px solid var(--border-card); border-radius: var(--radius-md); background: var(--bg-base); color: var(--text-primary); font-size: 1rem; max-width: 100%; }
    .pf-input:focus-visible, .pf-link:focus-visible, .pf-seg button:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
    .pf-input::placeholder { color: var(--text-muted); }
    .pf-add #pfTicker { flex: 1 1 11rem; min-width: 0; }
    .pf-add #pfAmount { flex: 1 1 9rem; min-width: 0; }
    .pf-seg { display: inline-flex; border: 1px solid var(--border-card); border-radius: var(--radius-md); overflow: hidden; }
    .pf-seg button { min-height: 38px; padding: 0 0.8rem; border: none; background: none; color: var(--text-secondary); font: inherit; font-size: 0.9rem; cursor: pointer; }
    .pf-seg button[aria-pressed="true"] { background: var(--text-primary); color: var(--bg-base); }
    .pf-link { background: none; border: none; padding: 0.35rem 0; min-height: 36px; font: inherit; font-size: 0.9rem; color: var(--accent); cursor: pointer; }
    .pf-link:hover { text-decoration: underline; }
    .pf-danger { color: var(--neg); }
    .pf-more-ways { display: flex; flex-wrap: wrap; gap: 0.25rem 1.25rem; margin-top: 0.5rem; }
    .pf-details { display: flex; flex-wrap: wrap; gap: 0.75rem 1rem; margin-top: 0.85rem; }
    .pf-field { display: flex; flex-direction: column; gap: 0.25rem; font-size: 0.82rem; color: var(--text-muted); min-width: 0; }
    .pf-field .pf-input { width: 11rem; }
    .pf-paste { margin-top: 0.85rem; }
    .pf-paste textarea { display: block; width: 100%; min-height: 6.5rem; resize: vertical; font-family: inherit; }
    .pf-paste .setup-yes { margin-top: 0.6rem; }
    .pf-status { min-height: 1.3rem; margin: 0.75rem 0 0; font-size: 0.9rem; color: var(--text-secondary); }
    .pf-status-bad { color: var(--neg); }
    .pf-preview-rows, .pf-preview-unread, .pf-list { list-style: none; margin: 0; padding: 0; }
    .pf-preview-row { display: grid; grid-template-columns: 5rem minmax(0, 1fr); gap: 0.1rem 0.75rem; padding: 0.6rem 0; border-bottom: 1px solid var(--border-subtle); font-size: 0.95rem; }
    .pf-preview-name { color: var(--text-secondary); overflow-wrap: anywhere; }
    .pf-preview-what, .pf-preview-note { grid-column: 2; }
    .pf-preview-note { font-size: 0.84rem; color: var(--text-muted); }
    .pf-preview-bad .pf-preview-note { color: var(--neg); }
    .pf-preview-bad .pf-ticker, .pf-preview-bad .pf-preview-what { color: var(--text-muted); }
    .pf-preview-unread-head { margin: 1rem 0 0.35rem; font-size: 0.9rem; color: var(--text-secondary); }
    .pf-preview-unread li { display: flex; flex-wrap: wrap; gap: 0.15rem 0.75rem; padding: 0.3rem 0; font-size: 0.88rem; }
    .pf-unread-text { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 0.84rem; overflow-wrap: anywhere; min-width: 0; }
    .pf-unread-why { color: var(--text-muted); }
    .pf-preview-actions { display: flex; align-items: center; gap: 1rem; margin-top: 1rem; }
    .pf-ticker { font-weight: 600; color: var(--text-primary); text-decoration: none; }
    a.pf-ticker:hover { color: var(--accent); }
    .pf-tabs { display: flex; gap: 1.5rem; margin: 0 0 1.5rem; border-bottom: 1px solid var(--border-subtle); overflow-x: auto; }
    .pf-tabs button { flex: none; min-height: 44px; padding: 0 0.1rem; border: none; border-bottom: 2px solid transparent; margin-bottom: -1px; background: none; color: var(--text-muted); font: inherit; font-size: 1rem; cursor: pointer; }
    .pf-tabs button:hover { color: var(--text-primary); }
    .pf-tabs button[aria-pressed="true"] { color: var(--text-primary); font-weight: 600; border-bottom-color: var(--accent); }
    .pf-tabs button:focus-visible { outline: 2px solid var(--accent); outline-offset: -2px; }
    .page-portfolio[data-view] [data-in] { display: none; }
    .page-portfolio[data-view="briefing"] [data-in="briefing"], .page-portfolio[data-view="overview"] [data-in="overview"], .page-portfolio[data-view="holdings"] [data-in="holdings"],
    .page-portfolio[data-view="exposure"] [data-in="exposure"], .page-portfolio[data-view="what-if"] [data-in="what-if"] { display: block; }
    .page-portfolio:not([data-view]) .pf-intro-held, .page-portfolio[data-view] .pf-intro-empty { display: none; }
    .page-portfolio[data-view] .pf-first { border-top: none; padding-top: 0.25rem; }
    .page-portfolio .pf-section > .settings-heading, .page-portfolio .pf-head > .settings-heading { margin: 0 0 0.9rem; padding-bottom: 0.6rem; border-bottom: 1px solid var(--text-primary); font-size: 0.78rem; font-weight: 650; letter-spacing: 0.06em; text-transform: uppercase; }
    .page-portfolio .pf-head { align-items: baseline; }
    .page-portfolio .pf-head > .settings-heading { flex: 1; }
    .page-portfolio .pf-section { border-top: none; padding: 1.25rem 0 1.5rem; }
    .page-portfolio .pf-lead { font-size: 1.15rem; line-height: 1.45; letter-spacing: -0.01em; }
    .page-portfolio .pf-hero-value { font-size: clamp(2.6rem, 8vw, 3.8rem); font-weight: 650; letter-spacing: -0.04em; }
    .pf-tab-count { display: inline-block; min-width: 1.35rem; margin-left: 0.3rem; padding: 0 0.35rem; border-radius: var(--radius-full); background: var(--accent); color: var(--on-accent); font-size: 0.72rem; font-weight: 600; line-height: 1.35rem; text-align: center; font-variant-numeric: tabular-nums; vertical-align: 0.1em; }
    .page-portfolio[data-view] [data-in] { animation: pf-in 0.28s cubic-bezier(0.2, 0.7, 0.2, 1) both; }
    @keyframes pf-in { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: none; } }
    @media (prefers-reduced-motion: reduce) { .page-portfolio[data-view] [data-in] { animation: none; } }

    /* ---- Briefing ---- */
    .br-top { display: flex; flex-wrap: wrap; align-items: baseline; justify-content: space-between; gap: 0.25rem 1.5rem; }
    .br-date { margin: 0; font-size: 0.9rem; font-weight: 600; color: var(--text-muted); }
    .br-actions { display: flex; gap: 1.25rem; }
    .br-lead { margin: 0.5rem 0 0; max-width: 40rem; font-size: clamp(1.6rem, 3.2vw, 2.15rem); font-weight: 650; line-height: 1.18; letter-spacing: -0.025em; color: var(--text-primary); text-wrap: balance; }
    .br-sub { margin: 0.75rem 0 0; max-width: 38rem; font-size: 1.05rem; line-height: 1.5; color: var(--text-secondary); }
    .br-sub:empty { display: none; }
    .br-block { margin-top: 2.5rem; }
    .br-label { margin: 0 0 0.25rem; padding-bottom: 0.6rem; border-bottom: 1px solid var(--text-primary); font-size: 0.78rem; font-weight: 650; letter-spacing: 0.06em; text-transform: uppercase; color: var(--text-primary); }
    .br-stories, .br-moves, .br-events { list-style: none; margin: 0; padding: 0; }
    .br-story { display: grid; grid-template-columns: minmax(0, 1fr); gap: 0 1.25rem; padding: 1rem 0; border-bottom: 1px solid var(--border-subtle); }
    .br-story-first { grid-template-columns: 2.25rem minmax(0, 1fr); }
    .br-n { font-size: 1.9rem; font-weight: 300; line-height: 1; color: var(--text-muted); font-variant-numeric: tabular-nums; padding-top: 0.1rem; }
    .br-meta { display: flex; flex-wrap: wrap; gap: 0.15rem 0.65rem; margin: 0 0 0.3rem; font-size: 0.8rem; color: var(--text-muted); }
    .br-meta > * + *::before { content: "·"; margin-right: 0.65rem; color: var(--border-card); }
    .br-ticker { font-weight: 650; color: var(--text-primary); text-decoration: none; letter-spacing: 0.01em; }
    .br-ticker:hover { color: var(--accent); }
    .br-headline { margin: 0; font-size: 1.08rem; font-weight: 600; line-height: 1.35; letter-spacing: -0.01em; }
    .br-story-first .br-headline { font-size: 1.2rem; }
    .br-headline a { color: var(--text-primary); text-decoration: none; }
    .br-headline a:hover { color: var(--accent); }
    .br-why { margin: 0.35rem 0 0; max-width: 40rem; font-size: 0.92rem; line-height: 1.5; color: var(--text-secondary); }
    .br-rest .br-headline { font-size: 0.98rem; font-weight: 500; }
    .br-rest .br-why { display: none; }
    .br-move { display: grid; grid-template-columns: 4rem 5rem minmax(0, 1fr) auto; align-items: baseline; gap: 0.25rem 1rem; padding: 0.85rem 0; border-bottom: 1px solid var(--border-subtle); }
    .br-move-pct { font-size: 1.15rem; font-weight: 650; font-variant-numeric: tabular-nums; }
    .br-move-pct.pos { color: var(--pos); }
    .br-move-pct.neg { color: var(--neg); }
    .br-move-words { font-size: 0.92rem; color: var(--text-secondary); }
    .br-share { font-size: 0.82rem; color: var(--text-muted); font-variant-numeric: tabular-nums; white-space: nowrap; text-align: right; }
    .br-event { display: grid; grid-template-columns: 5.5rem minmax(0, 1fr) auto; align-items: baseline; gap: 0.25rem 1rem; padding: 0.7rem 0; border-bottom: 1px solid var(--border-subtle); color: var(--text-muted); }
    .br-event-soon { color: var(--text-primary); }
    .br-event-when { font-size: 0.9rem; font-weight: 600; font-variant-numeric: tabular-nums; }
    .br-event-what { font-size: 0.95rem; }
    .br-event-what a:not(.br-ticker) { color: inherit; text-decoration: none; }
    .br-event-what a:not(.br-ticker):hover { color: var(--accent); }
    .br-est { color: var(--text-muted); font-size: 0.85rem; }
    .br-quiet .pf-note { font-size: 0.95rem; color: var(--text-secondary); }
    .br-foot { margin-top: 2rem; }
    @media (max-width: 640px) {
      .br-move { grid-template-columns: 3.5rem 4.5rem minmax(0, 1fr); }
      .br-move .br-move-words { grid-column: 1 / -1; }
      .br-move .br-share { grid-column: 3; grid-row: 1; }
      .br-story-first { grid-template-columns: 1.75rem minmax(0, 1fr); gap: 0 0.75rem; }
      .br-n { font-size: 1.5rem; }
      .br-event { grid-template-columns: 4.5rem minmax(0, 1fr) auto; gap: 0.2rem 0.75rem; }
    }
    .pf-head { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 0.5rem 1rem; margin-bottom: 0.5rem; }
    .pf-head .settings-heading { margin: 0; }
    .pf-sort { display: flex; align-items: center; gap: 0.5rem; font-size: 0.88rem; color: var(--text-muted); }
    .pf-sort .pf-input { min-height: 36px; padding: 0.25rem 0.5rem; font-size: 0.9rem; }
    .pf-hero-spy { margin: 0.15rem 0 0; font-size: 0.92rem; color: var(--text-muted); font-variant-numeric: tabular-nums; }
    .pf-hero-spy .pos { color: var(--pos); }
    .pf-hero-spy .neg { color: var(--neg); }
    .pf-line.pf-line-spy { stroke: var(--series-other); }
    .pf-hero { padding: 0.25rem 0 2rem; }
    .pf-hero-label { margin: 0; font-size: 0.92rem; color: var(--text-muted); }
    .pf-hero-value { margin: 0.1rem 0 0.15rem; font-size: clamp(2.2rem, 7vw, 3.1rem); line-height: 1.1; font-weight: 600; letter-spacing: -0.02em; font-variant-numeric: tabular-nums; }
    .pf-hero-change { margin: 0; min-height: 1.5rem; font-size: 1.02rem; color: var(--text-secondary); font-variant-numeric: tabular-nums; }
    .pf-hero-change .pos, .pf-tile-value.pos, .pf-move-amount.pos { color: var(--pos); }
    .pf-hero-change .neg, .pf-tile-value.neg, .pf-move-amount.neg { color: var(--neg); }
    .pf-ranges { margin: 1.1rem 0 0.6rem; }
    .pf-seg button:disabled { opacity: 0.35; cursor: default; }
    .pf-chart { min-height: 0; touch-action: pan-y; }
    .pf-chart-svg { display: block; width: 100%; height: auto; cursor: crosshair; }
    .pf-line { fill: none; stroke: var(--series-1); stroke-width: 2; stroke-linejoin: round; stroke-linecap: round; }
    .pf-cross { stroke: var(--text-muted); stroke-width: 1; }
    .pf-dot { fill: var(--series-1); stroke: var(--bg-base); stroke-width: 2; }
    .pf-tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(10.5rem, 1fr)); gap: 1.1rem 2rem; margin: 1.25rem 0 0.75rem; }
    .pf-tile-label { font-size: 0.84rem; color: var(--text-muted); }
    .pf-tile-value { margin: 0.1rem 0 0; font-size: 1.2rem; font-weight: 600; font-variant-numeric: tabular-nums; }
    .pf-tile-detail { margin: 0; font-size: 0.84rem; color: var(--text-muted); }
    .pf-add-section > .settings-heading { margin-bottom: 0.75rem; }
    .pf-move { display: grid; grid-template-columns: 4.5rem minmax(0, 1fr) 7.5rem; align-items: center; gap: 0.1rem 1rem; padding: 0.6rem 0; border-bottom: 1px solid var(--border-subtle); }
    .pf-movebar { display: block; width: 100%; height: 14px; }
    .pf-bar-pos { fill: var(--pos); }
    .pf-bar-neg { fill: var(--neg); }
    .pf-zero { stroke: var(--text-muted); stroke-width: 1; vector-effect: non-scaling-stroke; }
    .pf-move-amount { text-align: right; font-weight: 600; font-variant-numeric: tabular-nums; }
    .pf-money-bars { margin: 0.25rem 0 1rem; max-width: 42rem; }
    .pf-money-row { display: grid; grid-template-columns: 11rem minmax(0, 1fr) 7rem; align-items: center; gap: 0.15rem 1rem; padding: 0.45rem 0; }
    .pf-money-label { font-size: 0.92rem; color: var(--text-secondary); }
    .pf-money-amount { text-align: right; font-weight: 600; font-variant-numeric: tabular-nums; }
    .pf-bar-quiet { fill: var(--series-other); }
    .pf-bar-other { fill: var(--text-muted); }
    .pf-row { display: grid; grid-template-columns: minmax(0, 1fr) 96px 13rem auto; align-items: center; gap: 0.2rem 1.25rem; padding: 0.9rem 0; border-bottom: 1px solid var(--border-subtle); }
    .pf-row-spark { height: 30px; }
    .pf-spark { display: block; }
    .pf-spark path { fill: none; stroke-width: 1.5; stroke-linejoin: round; stroke-linecap: round; }
    .pf-spark-up path { stroke: var(--pos); }
    .pf-spark-down path { stroke: var(--neg); }
    .pf-row-title { display: flex; flex-wrap: wrap; align-items: baseline; gap: 0.1rem 0.6rem; }
    .pf-row-name { color: var(--text-secondary); font-size: 0.95rem; overflow-wrap: anywhere; min-width: 0; }
    .pf-row-meta { margin-top: 0.15rem; font-size: 0.84rem; color: var(--text-muted); }
    .pf-old { color: var(--warn); }
    .pf-row-value { text-align: right; font-variant-numeric: tabular-nums; }
    .pf-value { font-weight: 600; }
    .pf-gain { font-size: 0.84rem; color: var(--text-muted); }
    .pf-gain.pos { color: var(--pos); }
    .pf-gain.neg { color: var(--neg); }
    .pf-row-weight { font-variant-numeric: tabular-nums; }
    .pf-row-out .pf-value { color: var(--text-muted); font-weight: 400; }
    .pf-row-edit { padding: 0.25rem 0 1rem; border-bottom: 1px solid var(--border-subtle); }
    .pf-edit { display: flex; flex-wrap: wrap; align-items: flex-end; gap: 0.75rem 1rem; }
    .pf-edit-actions { display: flex; flex-wrap: wrap; align-items: center; gap: 0.5rem 1rem; flex: 1 1 100%; }
    .pf-total { display: flex; align-items: baseline; justify-content: space-between; gap: 1rem; padding: 1rem 0 0.25rem; }
    .pf-total-label { color: var(--text-secondary); }
    .pf-total-value { font-size: 1.6rem; font-weight: 600; letter-spacing: -0.01em; font-variant-numeric: tabular-nums; }
    .pf-follow { display: flex; flex-wrap: wrap; align-items: baseline; gap: 0.25rem 1rem; margin-top: 0.75rem; }
    .pf-follow .pf-note { margin: 0; }
    .pf-foot { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 0.5rem 1.5rem; }
    .pf-lead { margin: 0 0 0.75rem; font-size: 1.02rem; line-height: 1.5; color: var(--text-primary); max-width: 42rem; }
    .pf-lead .pos { color: var(--pos); }
    .pf-lead .neg { color: var(--neg); }
    .pf-sectors, .pf-lines { list-style: none; margin: 0; padding: 0; }
    .pf-sector { display: grid; grid-template-columns: 13rem minmax(0, 1fr) 6.5rem 3rem; align-items: center; gap: 0.15rem 1rem; padding: 0.6rem 0; border-bottom: 1px solid var(--border-subtle); }
    .pf-sector-name { font-size: 0.95rem; }
    .pf-sector-money { text-align: right; font-weight: 600; font-variant-numeric: tabular-nums; }
    .pf-sector-pct { text-align: right; font-size: 0.86rem; color: var(--text-muted); font-variant-numeric: tabular-nums; }
    .pf-sector-tickers { grid-column: 1 / -1; font-size: 0.84rem; color: var(--text-muted); overflow-wrap: anywhere; }
    .pf-bar { display: block; width: 100%; height: 6px; }
    .pf-bar-track { fill: var(--bg-surface-highlight); }
    .pf-bar-fill { fill: var(--series-1); }
    .pf-stats { margin: 0; }
    .pf-stat { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 0.1rem 1rem; padding: 0.7rem 0; border-bottom: 1px solid var(--border-subtle); }
    .pf-stat-label { font-size: 0.95rem; }
    .pf-stat-value { margin: 0; text-align: right; font-size: 1.15rem; font-weight: 600; font-variant-numeric: tabular-nums; }
    .pf-stat-detail { grid-column: 1 / -1; margin: 0; font-size: 0.84rem; color: var(--text-muted); max-width: 38rem; }
    .pf-sectors > li:last-child, .pf-stats > .pf-stat:last-child, .pf-lines > li:last-child { border-bottom: none; }
    .pf-overlap-line { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 0.25rem 1.5rem; align-items: baseline; padding: 0.65rem 0; border-bottom: 1px solid var(--border-subtle); font-size: 0.97rem; line-height: 1.45; }
    .pf-line-amount { font-variant-numeric: tabular-nums; white-space: nowrap; }
    .pf-gain-wrap { overflow-x: auto; margin: 0.5rem 0; }
    .pf-gain-table { max-width: 40rem; }
    .wi-form { display: flex; flex-wrap: wrap; gap: 0.75rem 1rem; }
    .wi-picks { display: flex; flex-wrap: wrap; gap: 0.5rem; margin-top: 1rem; }
    .wi-picks .chip { min-height: 36px; padding: 0.3rem 0.85rem; font-size: 0.88rem; }
    .wi-actions { display: flex; flex-wrap: wrap; align-items: center; gap: 0.5rem 1.25rem; margin-top: 1rem; }
    .wi-result { margin-top: 0.5rem; }
    .wi-answer { margin: 0 0 0.6rem; font-size: 1.2rem; line-height: 1.4; max-width: 42rem; }
    .wi-value { font-weight: 600; font-variant-numeric: tabular-nums; }
    .wi-chart { display: block; width: 100%; max-width: 46rem; height: auto; margin-top: 1rem; }
    .wi-grid { stroke: var(--border-subtle); stroke-width: 1; }
    .wi-axis { fill: var(--text-muted); font-size: 11px; font-family: var(--font-sans); }
    .wi-line { fill: none; stroke-width: 2; stroke-linejoin: round; stroke-linecap: round; vector-effect: non-scaling-stroke; }
    .wi-line.wi-line-main { stroke: var(--series-1); }
    .wi-line.wi-line-spy { stroke: var(--series-other); }
    .wi-legend { display: flex; flex-wrap: wrap; gap: 0.25rem 1.25rem; margin: 0.4rem 0 0.25rem; font-size: 0.86rem; color: var(--text-secondary); }
    .wi-key::before { content: ""; display: inline-block; width: 1.1rem; height: 2px; margin-right: 0.45rem; vertical-align: middle; background: var(--series-other); }
    .wi-key.wi-line-main::before { background: var(--series-1); }
    .wi-table-wrap { max-height: 22rem; overflow: auto; margin-top: 0.5rem; max-width: 34rem; border-top: 1px solid var(--border-subtle); border-bottom: 1px solid var(--border-subtle); }
    .wi-table { width: 100%; border-collapse: collapse; font-size: 0.88rem; font-variant-numeric: tabular-nums; }
    .wi-table th, .wi-table td { padding: 0.35rem 0.5rem 0.35rem 0; text-align: right; border-bottom: 1px solid var(--border-subtle); white-space: nowrap; }
    .wi-table th:first-child, .wi-table td:first-child { text-align: left; }
    .wi-table th { position: sticky; top: 0; background: var(--bg-base); font-weight: 600; color: var(--text-secondary); }
    @media (max-width: 640px) {
      .pf-row { grid-template-columns: minmax(0, 1fr) auto; align-items: start; }
      .pf-row-main { grid-column: 1; grid-row: 1; }
      .pf-row-spark { grid-column: 2; grid-row: 1; justify-self: end; }
      .pf-row-value { grid-column: 1 / -1; grid-row: 2; display: flex; flex-wrap: wrap; align-items: baseline; gap: 0.1rem 0.9rem; text-align: left; margin-top: 0.35rem; }
      .pf-row-value .pf-value { font-size: 1.1rem; }
      .pf-row > .pf-link { grid-column: 1 / -1; grid-row: 3; justify-self: start; }
      .pf-move { grid-template-columns: 3.75rem minmax(0, 1fr) 6.5rem; gap: 0.1rem 0.6rem; }
      .pf-money-row { grid-template-columns: minmax(0, 1fr) 6.5rem; }
      .pf-money-row .pf-bar { grid-column: 1 / -1; grid-row: 2; }
      .pf-field .pf-input { width: 100%; }
      .pf-field { flex: 1 1 9rem; }
      .pf-preview-row { grid-template-columns: 4rem minmax(0, 1fr); }
      .pf-sector { grid-template-columns: minmax(0, 1fr) 6rem 3rem; }
      .pf-sector .pf-bar { grid-column: 1 / -1; grid-row: 2; }
    }
"""

PORTFOLIO_BODY = """
      <header class="page-header">
        <h1 class="page-title">Your portfolio</h1>
        <p class="page-standfirst pf-intro-empty">Put in the stocks you own to see what they’re worth, how that has changed and what you’re actually invested in. Your holdings stay in this browser.</p>
        <p class="page-standfirst pf-intro-held">What happened to what you own, and what it adds up to. Kept in this browser only.</p>
      </header>

      <p class="pf-banner" id="pfDemo" hidden>Demo prices, not real. This copy of the site was built from made-up data.</p>
      <p class="pf-banner" id="pfPricesFailed" hidden>Prices couldn’t be loaded just now. Your holdings are still here; try again in a little while.</p>

      <nav class="pf-tabs" id="pfTabs" aria-label="Parts of this page" hidden>
        <button type="button" data-click="pfView" data-view="briefing" aria-pressed="true">Briefing <span class="pf-tab-count" id="pfBriefCount" hidden></span></button>
        <button type="button" data-click="pfView" data-view="overview" aria-pressed="false">Overview</button>
        <button type="button" data-click="pfView" data-view="holdings" aria-pressed="false">Holdings</button>
        <button type="button" data-click="pfView" data-view="exposure" aria-pressed="false">Exposure</button>
        <button type="button" data-click="pfView" data-view="what-if" aria-pressed="false">What if</button>
      </nav>

      <section class="br" id="pfBrief" data-in="briefing" aria-labelledby="brLead" hidden>
        <div class="br-top">
          <p class="br-date" id="brDate"></p>
          <div class="br-actions">
            <button type="button" class="pf-link" data-click="brCopy">Copy as text</button>
            <button type="button" class="pf-link" id="brMarkRead" data-click="brMarkRead">Mark all as read</button>
          </div>
        </div>
        <h2 class="br-lead" id="brLead"></h2>
        <p class="br-sub" id="brSub"></p>

        <div class="br-block" id="brFirstWrap" hidden>
          <h3 class="br-label">Read these first</h3>
          <ol class="br-stories" id="brFirst"></ol>
        </div>

        <div class="br-block" id="brMovesWrap" hidden>
          <h3 class="br-label">Big days</h3>
          <ul class="br-moves" id="brMoves"></ul>
          <p class="pf-note">“On its own” means the S&amp;P 500 and the company’s peers didn’t move the same way that day. It doesn’t say why.</p>
        </div>

        <div class="br-block" id="brComingWrap" hidden>
          <h3 class="br-label">Coming up</h3>
          <ul class="br-events" id="brComing"></ul>
        </div>

        <div class="br-block" id="brRestWrap" hidden>
          <h3 class="br-label" id="brRestHeading">Also new</h3>
          <ul class="br-stories br-rest" id="brRest"></ul>
          <button type="button" class="pf-link" id="brRestAll" data-click="brRestAll" hidden>Show all</button>
        </div>

        <div class="br-block br-quiet" id="brQuietWrap" hidden>
          <h3 class="br-label">Quiet</h3>
          <div id="brQuiet"></div>
        </div>
        <p class="pf-note br-foot" id="brSeenNote"></p>
      </section>

      <section class="pf-hero" id="pfSummary" data-in="overview" aria-label="Your portfolio at a glance" hidden>
        <p class="pf-hero-label" id="pfHeroLabel">Your portfolio is worth</p>
        <p class="pf-hero-value" id="pfHeroValue"></p>
        <p class="pf-hero-change" id="pfHeroDay" hidden></p>
        <p class="pf-hero-change" id="pfHeroChange"></p>
        <p class="pf-hero-spy" id="pfHeroSpy" hidden></p>
        <div class="pf-seg pf-ranges" id="pfRanges" role="group" aria-label="How far back the chart goes" hidden>
          <button type="button" data-click="pfSetRange" data-months="12" aria-pressed="false">1Y</button>
          <button type="button" data-click="pfSetRange" data-months="36" aria-pressed="false">3Y</button>
          <button type="button" data-click="pfSetRange" data-months="60" aria-pressed="false">5Y</button>
          <button type="button" data-click="pfSetRange" data-months="0" aria-pressed="false">All</button>
        </div>
        <div class="pf-chart" id="pfValueChart"></div>
        <p class="wi-legend" id="pfValueKey" hidden><span class="wi-key wi-line-main">Your shares</span><span class="wi-key">Same money in the S&amp;P 500</span></p>
        <dl class="pf-tiles" id="pfTiles" hidden></dl>
        <button type="button" class="pf-link" id="pfValueNumbers" data-click="pfValueNumbers" aria-expanded="false" aria-controls="pfValueTable" hidden>Show the numbers</button>
        <div class="wi-table-wrap" id="pfValueTable" hidden></div>
        <p class="pf-note" id="pfValueNote"></p>
      </section>

      <p class="pf-note" id="pfEmpty">Nothing here yet. Add what you hold below: a ticker and either how many shares or what it’s worth today. A file exported from your broker works too; it’s read here, in your browser, and isn’t uploaded.</p>

      <section class="pf-section pf-first" id="pfHoldings" data-in="holdings" aria-labelledby="pfHoldingsHeading" hidden>
        <div class="pf-head">
          <h2 class="settings-heading" id="pfHoldingsHeading">Your holdings</h2>
          <label class="pf-sort" id="pfSortBox" hidden>Sort by
            <select class="pf-input" id="pfSort" data-change="pfSort">
              <option value="value">Value</option>
              <option value="change">Change</option>
              <option value="name">Name</option>
            </select>
          </label>
        </div>
        <ul class="pf-list" id="pfList"></ul>
        <button type="button" class="pf-link" id="pfShowAll" data-click="pfShowAll" hidden>Show all</button>
        <div class="pf-total"><span class="pf-total-label">Total</span><span class="pf-total-value" id="pfTotal"></span></div>
        <p class="pf-note" id="pfTotalNote"></p>
        <p class="pf-note" id="pfDropped" hidden></p>
        <div class="pf-follow" id="pfFollowBox" hidden>
          <button type="button" class="pf-link" id="pfFollow" data-click="pfFollowHeld">Follow these companies</button>
          <span class="pf-note" id="pfFollowNote"></span>
        </div>
      </section>

      <section class="pf-section pf-add-section" data-in="holdings" aria-labelledby="pfAddHeading">
        <h2 class="settings-heading" id="pfAddHeading">Add a holding</h2>
        <div class="pf-add" id="pfAddRow">
          <input class="pf-input" id="pfTicker" type="text" list="pfTickers" autocomplete="off" autocapitalize="characters" spellcheck="false" maxlength="60" placeholder="Ticker, e.g. NVDA" aria-label="Ticker or company name">
          <datalist id="pfTickers">
            {% for co in watchlist_companies %}<option value="{{ co.symbol }}">{{ co.name }}</option>
            {% endfor %}
          </datalist>
          <div class="pf-seg" role="group" aria-label="Enter shares or dollars">
            <button type="button" data-click="pfSetMode" data-pf-mode="shares" aria-pressed="true">Shares</button>
            <button type="button" data-click="pfSetMode" data-pf-mode="dollars" aria-pressed="false">Dollars</button>
          </div>
          <input class="pf-input" id="pfAmount" type="text" inputmode="decimal" autocomplete="off" maxlength="20" placeholder="Shares, e.g. 10" aria-label="Number of shares">
          <button type="button" class="setup-yes" data-click="pfAddOne">Add</button>
        </div>
        <div class="pf-details" id="pfDetails" hidden>
          <label class="pf-field"><span class="pf-field-label">Bought (month), optional</span><input class="pf-input" id="pfBought" type="month" max="{{ generated_iso[:7] }}"></label>
          <label class="pf-field"><span class="pf-field-label">Paid in total ($), optional</span><input class="pf-input" id="pfPaid" type="text" inputmode="decimal" autocomplete="off" maxlength="20"></label>
        </div>
        <div class="pf-more-ways">
          <button type="button" class="pf-link" data-click="pfToggleDetails" aria-expanded="false" aria-controls="pfDetails">Add when you bought and what you paid</button>
          <button type="button" class="pf-link" data-click="pfTogglePaste" aria-expanded="false" aria-controls="pfPasteBox">Paste a list</button>
          <button type="button" class="pf-link" data-click="pfPickFile">Import a file from your broker</button>
          <input type="file" id="pfFile" accept=".csv,.tsv,.txt,text/csv,text/plain" data-change="pfReadFile" hidden>
        </div>
        <p class="pf-note">Import reads the positions CSV from Fidelity, Schwab, Vanguard, E*Trade or Interactive Brokers, and Robinhood’s account activity report. The file stays in your browser.</p>
        <div class="pf-paste" id="pfPasteBox" hidden>
          <textarea class="pf-input" id="pfPasteText" maxlength="20000" spellcheck="false" aria-label="A list of holdings" placeholder="NVDA 10, AAPL 5 shares, VOO $2000"></textarea>
          <p class="pf-note">One holding per line or separated by commas. A plain number is shares; a dollar amount is what it’s worth today. “AAPL 5 @ 150” also records what you paid.</p>
          <button type="button" class="setup-yes" data-click="pfReadPaste">Read the list</button>
        </div>
        <p class="pf-status" id="pfStatus" role="status" aria-live="polite"></p>
        <div class="pf-preview" id="pfPreview" hidden></div>
      </section>

      <section class="pf-section" id="pfMovesSection" data-in="overview" aria-labelledby="pfMovesHeading" hidden>
        <h2 class="settings-heading" id="pfMovesHeading">What moved your money</h2>
        <p class="pf-lead" id="pfMovesLead"></p>
        <ul class="pf-lines" id="pfMoves"></ul>
        <button type="button" class="pf-link" id="pfMovesAll" data-click="pfMovesAll" hidden>Show all</button>
      </section>

      <section class="pf-section" id="pfIncomeSection" data-in="overview" aria-labelledby="pfIncomeHeading" hidden>
        <h2 class="settings-heading" id="pfIncomeHeading">Dividends</h2>
        <p class="pf-lead" id="pfIncomeLead"></p>
        <ul class="pf-lines pf-money-bars" id="pfIncomeBars"></ul>
        <button type="button" class="pf-link" id="pfIncomeAll" data-click="pfIncomeAll" hidden>Show all</button>
        <p class="pf-note" id="pfIncomeNote"></p>
      </section>
{{ portfolio_sections }}
      <section class="pf-section pf-foot">
        <p class="pf-note">For information only, not advice. Your holdings are kept in this browser and never sent to us. To price a stock we don’t list, its ticker (not how much you hold) is sent to our own server. <a href="about.html#aboutPrivacy">More on privacy</a></p>
        <button type="button" class="pf-link pf-danger" data-click="pfRemoveAll">Remove everything</button>
      </section>
"""

PORTFOLIO_XRAY = """
      <div id="pfXray" hidden>
        <section class="pf-section" data-in="overview" aria-labelledby="pfSectorHeading">
          <h2 class="settings-heading" id="pfSectorHeading">Where the money is</h2>
          <p class="pf-lead" id="pfSectorLead"></p>
          <ul class="pf-sectors" id="pfSectors"></ul>
        </section>

        <section class="pf-section pf-first" data-in="exposure" aria-labelledby="pfConcentrationHeading">
          <h2 class="settings-heading" id="pfConcentrationHeading">Where it’s concentrated</h2>
          <p class="pf-lead" id="pfConcentrationLead"></p>
          <dl class="pf-stats" id="pfConcentration"></dl>
          <p class="pf-note" id="pfConcentrationNote"></p>
        </section>

        <section class="pf-section" data-in="exposure" aria-labelledby="pfOverlapHeading">
          <h2 class="settings-heading" id="pfOverlapHeading">Shared bets</h2>
          <p class="pf-lead" id="pfOverlapLead"></p>
          <ul class="pf-lines" id="pfOverlap"></ul>
          <button type="button" class="pf-link" id="pfOverlapAll" data-click="pfOverlapAll" hidden>Show all</button>
          <p class="pf-note" id="pfOverlapNote"></p>
        </section>

        <section class="pf-section" id="pfFundsSection" data-in="exposure" aria-labelledby="pfFundsHeading" hidden>
          <h2 class="settings-heading" id="pfFundsHeading">Funds</h2>
          <p class="pf-lead" id="pfFunds"></p>
        </section>

        <section class="pf-section" id="pfGainSection" data-in="overview" aria-labelledby="pfGainHeading" hidden>
          <h2 class="settings-heading" id="pfGainHeading">Gain and loss</h2>
          <p class="pf-lead" id="pfGainLead"></p>
          <ul class="pf-lines pf-money-bars" id="pfGainBars"></ul>
          <p class="pf-lead" id="pfGainSpy"></p>
          <div class="pf-gain-wrap" id="pfGainRows"></div>
          <button type="button" class="pf-link" id="pfGainAll" data-click="pfGainAll" hidden>Show all</button>
          <p class="pf-note" id="pfGainNote"></p>
        </section>
      </div>
"""

PORTFOLIO_WHAT_IF = """
      <section class="pf-section pf-first" id="what-if" data-in="what-if" aria-labelledby="wiHeading">
        <h2 class="settings-heading" id="wiHeading">What if I’d invested…</h2>
        <p class="pf-lead">Put an amount into any US stock or fund at some point in the past and see what it would be worth now, next to the same money in the S&amp;P 500.</p>
        <div class="wi-form" id="wiForm">
          <label class="pf-field"><span class="pf-field-label">Ticker or company</span><input class="pf-input" id="wiTicker" type="text" list="pfTickers" autocomplete="off" autocapitalize="characters" spellcheck="false" maxlength="60" placeholder="e.g. NVDA"></label>
          <label class="pf-field"><span class="pf-field-label">Amount ($)</span><input class="pf-input" id="wiAmount" type="text" inputmode="decimal" autocomplete="off" maxlength="20" value="1000"></label>
          <label class="pf-field"><span class="pf-field-label">Starting at the end of</span><input class="pf-input" id="wiFrom" type="month" data-input="wiClearPicks"></label>
          <label class="pf-field"><span class="pf-field-label">Plus every month ($), optional</span><input class="pf-input" id="wiMonthly" type="text" inputmode="decimal" autocomplete="off" maxlength="20"></label>
        </div>
        <div class="wi-picks" role="group" aria-label="Quick picks for the start">
          <button type="button" class="chip" data-click="wiPick" data-wi-years="1" aria-pressed="false">1 year ago</button>
          <button type="button" class="chip" data-click="wiPick" data-wi-years="3" aria-pressed="false">3 years ago</button>
          <button type="button" class="chip" data-click="wiPick" data-wi-years="5" aria-pressed="false">5 years ago</button>
          <button type="button" class="chip" data-click="wiPick" data-wi-years="10" aria-pressed="false">10 years ago</button>
          <button type="button" class="chip" data-click="wiPick" data-wi-years="first" aria-pressed="false">From its first month</button>
        </div>
        <div class="wi-actions">
          <button type="button" class="setup-yes" data-click="wiRun">Work it out</button>
          <button type="button" class="pf-link" id="wiPortfolio" data-click="wiRunPortfolio" hidden>Or use my whole portfolio</button>
        </div>
        <p class="pf-status" id="wiStatus" role="status" aria-live="polite"></p>
        <div class="wi-result" id="wiResult" hidden></div>
      </section>
"""

# Sections added by later parts of the page (the X-ray, the what-if calculator), in page order.
PORTFOLIO_SECTIONS = PORTFOLIO_XRAY + PORTFOLIO_WHAT_IF


def build_portfolio_template(shared_css: str, navigation_html: str, shared_js: str, theme_boot_js: str) -> str:
    """The whole page as one Jinja template, built from the site's shared pieces."""
    body = PORTFOLIO_BODY.replace("{{ portfolio_sections }}", PORTFOLIO_SECTIONS)
    return (
        """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=5.0">
  <meta name="description" content="Put in the stocks you own and see what you're invested in. Your holdings stay in your browser.">
  <title>StockPulse — Your portfolio</title>
  <link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' rx='8' fill='%231d1d1f'/%3E%3Cpath d='M6 19h6l3-9 3 13 2-4h6' fill='none' stroke='%23ffffff' stroke-width='2'/%3E%3C/svg%3E">
  <script>""" + theme_boot_js + """</script>
  <style>
""" + shared_css + PORTFOLIO_CSS + """
  </style>
</head>
<body class="page-portfolio">
  <div class="app-layout">
    """ + navigation_html + """

    <main class="app-main">
""" + body + """
    </main>
  </div>

  <script>
    """ + shared_js + """
    const PF_DATA = {{ portfolio_json|safe }};
{% raw %}
""" + portfolio_scripts() + """
{% endraw %}
  </script>
</body>
</html>
"""
    )
