"""Stock price performance collector for comparative market & peer analysis.

Fetches 3-month daily close prices for:
- All watchlist companies
- Top 3 competitors per watchlist company
- S&P 500 benchmark ETF (ticker SPY)

Computes normalized % change series (Day 0 = 0.0%) and peer relative alpha metrics.
"""

from datetime import datetime, timezone
import json
import logging
import time
from typing import Any, Dict, List, Optional
import urllib.request
import yaml

logger = logging.getLogger(__name__)

BENCHMARK_TICKER = "SPY"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)


def fetch_ticker_historical_closes(
    symbol: str,
    range_str: str = "3mo",
    interval: str = "1d",
    timeout: int = 10,
) -> Optional[Dict[str, Any]]:
    """Fetch historical daily close prices for a single ticker."""
    url = f"https://query2.finance.yahoo.com/v8/finance/chart/{symbol}?range={range_str}&interval={interval}&includePrePost=false"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://finance.yahoo.com/",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            result = data.get("chart", {}).get("result", [])
            if not result:
                return None

            chart = result[0]
            timestamps = chart.get("timestamp", [])
            indicators = chart.get("indicators", {}).get("quote", [{}])[0]
            raw_closes = indicators.get("close", [])

            # Filter valid (timestamp, close) pairs
            series = []
            for ts, cl in zip(timestamps, raw_closes):
                if cl is not None:
                    dt = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
                    series.append({"date": dt, "timestamp": ts, "close": round(float(cl), 2)})

            if len(series) < 5:
                return None

            base_price = series[0]["close"]
            for pt in series:
                pt["pct_change"] = round(((pt["close"] - base_price) / base_price) * 100.0, 2)

            total_pct_change = series[-1]["pct_change"]
            latest_price = series[-1]["close"]

            return {
                "symbol": symbol,
                "latest_price": latest_price,
                "base_price": base_price,
                "total_pct_change": total_pct_change,
                "series": series,
            }
    except Exception as e:
        logger.warning("Failed to fetch historical prices for %s: %s", symbol, e)
        return None


def collect_comparative_performance(
    watchlist_path: str = "data/watchlist.yaml",
) -> Dict[str, Any]:
    """Collect performance series for all watchlist stocks, competitors, and SPY."""
    with open(watchlist_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    watchlist_tickers = config.get("tickers", [])

    # Identify all symbols needed
    needed_symbols = set([BENCHMARK_TICKER])
    company_competitor_map = {}

    for co in watchlist_tickers:
        sym = co["symbol"]
        needed_symbols.add(sym)
        comps = [c for c in co.get("competitors", []) if isinstance(c, str) and c.isupper() and len(c) <= 5][:3]
        company_competitor_map[sym] = comps
        for c in comps:
            needed_symbols.add(c)

    logger.info("Collecting historical price data for %d symbols...", len(needed_symbols))

    raw_data: Dict[str, Any] = {}
    for sym in sorted(needed_symbols):
        hist = fetch_ticker_historical_closes(sym)
        if hist:
            raw_data[sym] = hist
        time.sleep(0.08)

    # Align benchmark SPY
    spy_data = raw_data.get(BENCHMARK_TICKER)
    spy_pct = spy_data["total_pct_change"] if spy_data else 0.0

    # Build company comparative bundles
    performance_bundles: Dict[str, Any] = {}
    for co in watchlist_tickers:
        sym = co["symbol"]
        co_hist = raw_data.get(sym)
        if not co_hist:
            continue

        comps = company_competitor_map.get(sym, [])
        comp_hist_list = []
        comp_returns = []

        for c in comps:
            c_data = raw_data.get(c)
            if c_data:
                comp_hist_list.append(c_data)
                comp_returns.append(c_data["total_pct_change"])

        avg_comp_pct = round(sum(comp_returns) / len(comp_returns), 2) if comp_returns else 0.0
        alpha_vs_peers = round(co_hist["total_pct_change"] - avg_comp_pct, 2)
        alpha_vs_spy = round(co_hist["total_pct_change"] - spy_pct, 2)

        # Context summary assessment
        if alpha_vs_peers >= 8.0:
            assessment = "Strong Outperformance vs Peers"
            assessment_type = "positive"
        elif alpha_vs_peers <= -8.0:
            assessment = "Lagging Peer Group"
            assessment_type = "negative"
        elif abs(alpha_vs_peers) < 4.0:
            assessment = "In-Line with Competitors"
            assessment_type = "neutral"
        elif alpha_vs_peers > 0:
            assessment = "Moderate Outperformance"
            assessment_type = "positive"
        else:
            assessment = "Moderate Underperformance"
            assessment_type = "negative"

        performance_bundles[sym] = {
            "symbol": sym,
            "name": co.get("name", sym),
            "sector": co.get("sector", ""),
            "target": co_hist,
            "competitors": comp_hist_list,
            "benchmark": spy_data,
            "avg_competitor_pct": avg_comp_pct,
            "alpha_vs_peers": alpha_vs_peers,
            "alpha_vs_spy": alpha_vs_spy,
            "assessment": assessment,
            "assessment_type": assessment_type,
        }

    return {
        "benchmark": spy_data,
        "companies": performance_bundles,
        "collected_at": datetime.now(timezone.utc).isoformat(),
    }
