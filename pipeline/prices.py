"""Long price history: kept in the database between runs and written out as small static files.

Each ticker also carries two optional extras: the close of the trading day before its price, and
the dividends per share of the past year. An extra that doesn't look right is dropped on its own;
it never costs the ticker its prices, and a missing one means "not known", never zero.

Yahoo rescales a ticker's whole adjusted series after every dividend, so a good fetch replaces the
stored series whole. A failed fetch changes nothing, which leaves the last real reading and the
date it was read.
"""

import glob
import json
import logging
import os
import re
from datetime import date
from typing import Any, Dict, Iterable, List, Optional

from pipeline.db import get_db_connection, init_db

logger = logging.getLogger(__name__)

SYMBOL_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9.\-]{0,9}$")
MONTH_PATTERN = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
KINDS = {"stock", "fund"}
SOURCES = {"yahoo", "demo"}


def _usable(record: Any) -> bool:
    """True if a record is safe to store: right shapes, positive numbers, months in order."""
    if not isinstance(record, dict):
        return False
    months, price = record.get("months"), record.get("price")
    if not SYMBOL_PATTERN.match(str(record.get("symbol") or "")) or record.get("kind") not in KINDS:
        return False
    if not isinstance(price, (int, float)) or isinstance(price, bool) or price <= 0:
        return False
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", str(record.get("price_date") or "")) or not isinstance(months, list):
        return False
    last = ""
    for pair in months:
        if not (isinstance(pair, (list, tuple)) and len(pair) == 2 and MONTH_PATTERN.match(str(pair[0]))):
            return False
        if not isinstance(pair[1], (int, float)) or isinstance(pair[1], bool) or pair[1] <= 0 or pair[0] <= last:
            return False
        last = pair[0]
    return True


DAY_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
MAX_DIVIDENDS = 60  # A year of weekly payers, with room to spare.


def _positive(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0


def _previous(record: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """The earlier close, if it is a real price from a day before the price date."""
    previous = record.get("previous")
    if not isinstance(previous, dict) or not _positive(previous.get("value")):
        return None
    day = str(previous.get("date") or "")
    if not DAY_PATTERN.match(day) or day >= record["price_date"]:
        return None
    return {"value": float(previous["value"]), "date": day}


def _dividends(record: Dict[str, Any]) -> Optional[List[List[Any]]]:
    """The year's dividends, oldest first. [] is a real "none paid"; None is "not known"."""
    dividends = record.get("dividends")
    if not isinstance(dividends, list) or len(dividends) > MAX_DIVIDENDS:
        return None
    out = []
    for pair in dividends:
        if not (isinstance(pair, (list, tuple)) and len(pair) == 2 and DAY_PATTERN.match(str(pair[0]))):
            return None
        if not _positive(pair[1]) or pair[0] > record["price_date"] or (out and pair[0] < out[-1][0]):
            return None
        out.append([pair[0], float(pair[1])])
    return out


def save_price_history(records: Iterable[Dict[str, Any]], db_path: Optional[str] = None,
                       source: str = "yahoo", today: Optional[date] = None) -> int:
    """Replace the stored history of each ticker that came back whole. Returns how many were stored."""
    if source not in SOURCES:
        raise ValueError(source)
    init_db(db_path)
    fetched = (today or date.today()).isoformat()
    stored = 0
    conn = get_db_connection(db_path)
    with conn:
        for record in records:
            if not _usable(record):
                logger.warning("Keeping the stored price history for %s: the new reading didn't look right",
                               (record or {}).get("symbol") if isinstance(record, dict) else record)
                continue
            previous, dividends = _previous(record), _dividends(record)
            conn.execute(
                """INSERT INTO price_history (symbol, name, kind, months_json, price, price_date, fetched_at, source,
                                              previous_close, previous_date, dividends_json)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(symbol) DO UPDATE SET name=excluded.name, kind=excluded.kind,
                     months_json=excluded.months_json, price=excluded.price, price_date=excluded.price_date,
                     fetched_at=excluded.fetched_at, source=excluded.source,
                     previous_close=excluded.previous_close, previous_date=excluded.previous_date,
                     dividends_json=excluded.dividends_json""",
                (record["symbol"], str(record.get("name") or record["symbol"]), record["kind"],
                 json.dumps([[m, v] for m, v in record["months"]], separators=(",", ":")),
                 float(record["price"]), record["price_date"], fetched, source,
                 previous["value"] if previous else None, previous["date"] if previous else None,
                 json.dumps(dividends, separators=(",", ":")) if dividends is not None else None),
            )
            stored += 1
    conn.close()
    return stored


def get_price_history(db_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """Every stored ticker, in the shape the static files use."""
    init_db(db_path)
    conn = get_db_connection(db_path)
    rows = conn.execute("SELECT * FROM price_history ORDER BY symbol").fetchall()
    conn.close()
    out = []
    for row in rows:
        months = json.loads(row["months_json"])
        record = {
            "symbol": row["symbol"],
            "name": row["name"],
            "kind": row["kind"],
            "currency": "USD",
            "first_month": months[0][0] if months else None,
            "months": months,
            "price": {"value": row["price"], "date": row["price_date"]},
            "fetched": row["fetched_at"],
        }
        if row["previous_close"] and row["previous_date"]:
            record["previous"] = {"value": row["previous_close"], "date": row["previous_date"]}
        if row["dividends_json"] is not None:
            record["dividends"] = json.loads(row["dividends_json"])
        if row["source"] == "demo":
            record["demo"] = True
        out.append(record)
    return out


def write_price_files(site_dir: str, db_path: Optional[str] = None) -> int:
    """site/data/prices/<SYMBOL>.json for each stored ticker, and index.json listing them."""
    folder = os.path.join(site_dir, "data", "prices")
    os.makedirs(folder, exist_ok=True)
    for stale in glob.glob(os.path.join(folder, "*.json")):
        os.remove(stale)
    records = get_price_history(db_path)
    index: Dict[str, Any] = {"symbols": {}}
    for record in records:
        with open(os.path.join(folder, f"{record['symbol']}.json"), "w", encoding="utf-8") as f:
            json.dump(record, f, separators=(",", ":"))
        index["symbols"][record["symbol"]] = {
            "name": record["name"], "kind": record["kind"], "price": record["price"],
            "first_month": record["first_month"],
        }
        for extra in ("previous", "dividends"):
            if extra in record:
                index["symbols"][record["symbol"]][extra] = record[extra]
    if any(r.get("demo") for r in records):
        index["demo"] = True
    with open(os.path.join(folder, "index.json"), "w", encoding="utf-8") as f:
        json.dump(index, f, separators=(",", ":"))
    return len(records)
