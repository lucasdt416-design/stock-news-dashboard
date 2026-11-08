"""Moves: each company's price over three months, its biggest days, and what was published then.

Everything here is worked out from data the pipeline already has: daily closes for every company,
its peers and the S&P 500 (SPY), and the dated stories and filings. Nothing is guessed. A big day
is set against the S&P 500 and the company's peers on the same day, so the page can say whether
the company moved on its own or with everyone else; it never claims a story caused a move, only
that it was published then.
"""

from datetime import date
from statistics import median
from typing import Any, Dict, Iterable, List, Optional, Tuple

BIG_DAYS = 3
MIN_BIG_MOVE = 2.0       # percent; smaller days are ordinary noise for most large companies
MARKET_MOVE = 1.0        # percent; a smaller S&P 500 day isn't "the market moving"
STORIES_PER_DAY = 2
CHART_W, CHART_H, CHART_PAD = 320, 120, 6


def _closes(bundle: Optional[Dict[str, Any]]) -> List[Tuple[str, float]]:
    out = []
    for pt in (bundle or {}).get("series") or []:
        try:
            out.append((str(pt["date"])[:10], float(pt["close"])))
        except (KeyError, TypeError, ValueError):
            continue
    return out


def _returns(closes: List[Tuple[str, float]]) -> Dict[str, float]:
    """Percent change from the previous close, by date."""
    return {d: (c / p - 1) * 100 for (_, p), (d, c) in zip(closes, closes[1:]) if p}


def verdict(move: float, market: Optional[float], peers: Optional[float]) -> str:
    """"market", "peers" or "own": whether a day's move was shared, from the numbers alone."""
    def close_to(other: Optional[float]) -> bool:
        return other is not None and other * move > 0 and abs(move - other) <= max(1.0, abs(move) * 0.4)
    if market is not None and abs(market) >= MARKET_MOVE and close_to(market):
        return "market"
    if close_to(peers):
        return "peers"
    return "own"


def _story_kind(item: Dict[str, Any]) -> str:
    source = item.get("source") or ""
    if source == "sec_edgar":
        return "results" if item.get("category") == "Earnings & Financials" else "filing"
    if source == "company_ir":
        return "release"
    return "news"


def _around(items: List[Dict[str, Any]], start: str, end: str, limit: int) -> List[Dict[str, Any]]:
    """The highest-scoring stories dated from start to end (inclusive), best first."""
    picked = [it for it in items if start <= str(it.get("published_date") or "")[:10] <= end and (it.get("score") or 0) >= 4]
    picked.sort(key=lambda it: (it.get("score") or 0), reverse=True)
    return [{"headline": it.get("clean_headline") or it.get("headline") or "", "url": it.get("url") or "",
             "date": str(it.get("published_date"))[:10], "kind": _story_kind(it), "source": it.get("source_label") or ""}
            for it in picked[:limit]]


def _path(values: List[float], low: float, high: float) -> str:
    span = (high - low) or 1.0
    step = (CHART_W - 2 * CHART_PAD) / max(1, len(values) - 1)
    pts = [(CHART_PAD + i * step, CHART_PAD + (high - v) / span * (CHART_H - 2 * CHART_PAD)) for i, v in enumerate(values)]
    return "M" + " L".join(f"{x:.1f} {y:.1f}" for x, y in pts)


def _chart(closes: List[Tuple[str, float]], spy: Dict[str, float], marks: Dict[str, int]) -> Dict[str, Any]:
    """Both lines as percent change from the first close, so they share one scale."""
    dates = [d for d, _ in closes]
    base = closes[0][1]
    stock = [(c / base - 1) * 100 for _, c in closes]
    spy_dates = [d for d in dates if d in spy]
    spy_base = spy[spy_dates[0]] if spy_dates else None
    market = [((spy[d] / spy_base - 1) * 100) if spy_base and d in spy else None for d in dates]
    known = [v for v in market if v is not None]
    low, high = min(stock + known + [0.0]), max(stock + known + [0.0])
    span = (high - low) or 1.0
    step = (CHART_W - 2 * CHART_PAD) / max(1, len(dates) - 1)

    def y(v: float) -> float:
        return CHART_PAD + (high - v) / span * (CHART_H - 2 * CHART_PAD)
    market_path = _path([v for v in market if v is not None], low, high) if len(known) == len(dates) else ""
    return {
        "stock": _path(stock, low, high),
        "market": market_path,
        "zero": round(y(0.0), 1),
        "dots": [{"n": n, "x": round(CHART_PAD + dates.index(d) * step, 1), "y": round(y(stock[dates.index(d)]), 1)}
                 for d, n in marks.items() if d in dates],
        "first": dates[0], "last": dates[-1],
    }


def build_deck(
    performance: Optional[Dict[str, Any]],
    items: Iterable[Dict[str, Any]],
    companies: Iterable[Dict[str, Any]],
    calendar_events: Iterable[Dict[str, Any]] = (),
    today: Optional[date] = None,
) -> Dict[str, Any]:
    """One card per company with prices, plus a lead card for the market that day."""
    today = today or date.today()
    performance = performance or {}
    spy_closes = _closes(performance.get("benchmark"))
    spy = dict(spy_closes)
    spy_ret = _returns(spy_closes)
    by_ticker: Dict[str, List[Dict[str, Any]]] = {}
    for it in items:
        by_ticker.setdefault(it.get("ticker") or "", []).append(it)
    next_event: Dict[str, Dict[str, Any]] = {}
    for ev in sorted(calendar_events, key=lambda e: str(e.get("event_date"))):
        sym, when = ev.get("ticker"), str(ev.get("event_date") or "")[:10]
        if sym and when >= today.isoformat() and sym not in next_event:
            next_event[sym] = ev
    names = {c["symbol"]: c.get("name") or c["symbol"] for c in companies}

    cards = []
    for sym, bundle in (performance.get("companies") or {}).items():
        if sym not in names:
            continue
        closes = _closes(bundle.get("target"))
        if len(closes) < 10:
            continue
        rets = _returns(closes)
        peer_rets = [(p.get("symbol"), _returns(_closes(p))) for p in bundle.get("competitors") or []]
        typical = median(abs(r) for r in rets.values()) if rets else 0.0
        threshold = max(MIN_BIG_MOVE, 2.5 * typical)
        dates = [d for d, _ in closes]
        big = sorted((d for d in rets if abs(rets[d]) >= threshold), key=lambda d: abs(rets[d]), reverse=True)[:BIG_DAYS]
        big.sort()
        stories = by_ticker.get(sym, [])
        days = []
        for n, d in enumerate(big, 1):
            prev = dates[dates.index(d) - 1]
            peers_today = [r[d] for _, r in peer_rets if d in r]
            peer_avg = sum(peers_today) / len(peers_today) if peers_today else None
            days.append({
                "n": n, "date": d, "move": round(rets[d], 1),
                "market": round(spy_ret[d], 1) if d in spy_ret else None,
                "peers": round(peer_avg, 1) if peer_avg is not None else None,
                "peer_names": [s for s, r in peer_rets if d in r],
                "verdict": verdict(rets[d], spy_ret.get(d), peer_avg),
                "stories": _around(stories, prev, d, STORIES_PER_DAY),
            })
        last_d, last_c = closes[-1]
        day = rets.get(last_d)
        three = (last_c / closes[0][1] - 1) * 100
        market_day = spy_ret.get(last_d)
        cards.append({
            "symbol": sym, "name": names[sym], "price": last_c, "date": last_d,
            "day": round(day, 1) if day is not None else None,
            "market_day": round(market_day, 1) if market_day is not None else None,
            "three_months": round(three, 1),
            "market_three_months": round((spy_closes[-1][1] / spy[dates[0]] - 1) * 100, 1) if spy_closes and dates[0] in spy else None,
            "chart": _chart(closes, spy, {d["date"]: d["n"] for d in days}),
            "days": days,
            "typical": round(typical, 1),
            "next": next_event.get(sym),
            # How far today's move stands out from the market, for ordering the deck.
            "standout": round(abs((day or 0) - (market_day or 0)), 2),
        })
    cards.sort(key=lambda c: (-c["standout"], c["symbol"]))

    lead = None
    if spy_closes and len(spy_closes) > 1 and cards:
        last_d = spy_closes[-1][0]
        today_cards = [c for c in cards if c["date"] == last_d and c["day"] is not None]
        lead = {
            "date": last_d,
            "market_day": round(spy_ret.get(last_d, 0.0), 1),
            "up": sum(1 for c in today_cards if c["day"] > 0),
            "down": sum(1 for c in today_cards if c["day"] < 0),
            "count": len(today_cards),
            "best": max(today_cards, key=lambda c: c["day"], default=None),
            "worst": min(today_cards, key=lambda c: c["day"], default=None),
        }
    return {"cards": cards, "lead": lead}
