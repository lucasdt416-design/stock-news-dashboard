#!/usr/bin/env python3
"""Add companies to the watchlist by ticker. Names, SEC numbers and sectors are filled in for you.

Usage:
    python scripts/add_companies.py KO PEP NFLX
    python scripts/add_companies.py "KO=The Coca-Cola Company" BRK.B
    python scripts/add_companies.py --file tickers.txt          (one ticker per line)
    python scripts/add_companies.py KO PEP --dry-run            (show what would be added)

It reads the SEC's free public lists, so it needs no keys. Check the names it prints: the SEC
stores some in capitals, and those are tidied by rule, which is usually but not always right.
Edit data/watchlist.yaml afterwards to add a newsroom feed, customers, suppliers or competitors.
"""

import argparse
import os
import sys

import yaml

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

from collectors.sec_companies import (  # noqa: E402
    DEFAULT_USER_AGENT, TICKERS_URL, build_entries, entries_yaml, fetch_json, sec_submissions, ticker_index,
)


def parse_requests(args, file_path=None):
    raw = list(args)
    if file_path:
        with open(file_path, encoding="utf-8") as f:
            raw += [line.split("#")[0].strip() for line in f]
    requests = []
    for item in raw:
        if not item:
            continue
        symbol, _, name = item.partition("=")
        requests.append((symbol.strip().upper(), name.strip() or None))
    return requests


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("tickers", nargs="*", help="tickers, optionally TICKER=Name")
    parser.add_argument("--file", help="a text file with one ticker per line")
    parser.add_argument("--watchlist", default=os.path.join(ROOT, "data", "watchlist.yaml"))
    parser.add_argument("--dry-run", action="store_true", help="print the entries without saving them")
    args = parser.parse_args(argv)

    requests = parse_requests(args.tickers, args.file)
    if not requests:
        parser.error("name at least one ticker")

    with open(args.watchlist, encoding="utf-8") as f:
        existing = [str(t.get("symbol", "")) for t in (yaml.safe_load(f) or {}).get("tickers", [])]

    user_agent = os.environ.get("SEC_EDGAR_USER_AGENT") or DEFAULT_USER_AGENT
    index = ticker_index(fetch_json(TICKERS_URL, user_agent))
    entries, notes = build_entries(requests, index, sec_submissions(user_agent), existing)

    for note in notes:
        print(f"  skipped  {note}")
    for e in entries:
        print(f"  {'would add' if args.dry_run else 'added'}  {e['symbol']:<6} {e['name']}  ·  {e['sector']}")
    if entries and not args.dry_run:
        with open(args.watchlist, "a", encoding="utf-8") as f:
            f.write(entries_yaml(entries))
        with open(args.watchlist, encoding="utf-8") as f:
            yaml.safe_load(f)  # still valid YAML
        print(f"\n{len(entries)} added to {os.path.relpath(args.watchlist, ROOT)}. "
              f"The watchlist now has {len(existing) + len(entries)} companies.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
