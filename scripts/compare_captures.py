#!/usr/bin/env python3
"""Compare two capture_site.py reports and print text, DOM id, and chart differences as Markdown.

Usage:
    python scripts/compare_captures.py .capture/before .capture/current
"""

import argparse
import json
import os
import re
from collections import Counter

VOLATILE = [
    (re.compile(r"Updated: .*"), "Updated: <time>"),
    (re.compile(r"[A-Z][a-z]{2} \d{2}, \d{4} \d{2}:\d{2}:\d{2}"), "<timestamp>"),
]


def norm(line):
    for pattern, repl in VOLATILE:
        line = pattern.sub(repl, line)
    return line


def load(path):
    with open(os.path.join(path, "report.json"), encoding="utf-8") as f:
        return json.load(f)["pages"]


def stable_ids(page):
    """Sparkline gradient ids are random per render, so they are not comparable."""
    return {i for i in page["ids"] if not i.startswith("grad-")}


def compare(before, after):
    out = []
    for name in sorted(set(before) | set(after)):
        old, new = before.get(name), after.get(name)
        if not old or not new:
            out.append(f"### {name}\n\nPage only in {'after' if new else 'before'}.\n")
            continue
        old_text = Counter(norm(t) for t in old["text"])
        new_text = Counter(norm(t) for t in new["text"])
        removed = sorted((old_text - new_text).elements())
        added = sorted((new_text - old_text).elements())
        ids_gone = sorted(stable_ids(old) - stable_ids(new))
        ids_new = sorted(stable_ids(new) - stable_ids(old))
        chart_changes = []
        old_charts = {c["id"]: c for c in old["charts"]}
        new_charts = {c["id"]: c for c in new["charts"]}
        for cid in sorted(set(old_charts) | set(new_charts)):
            a, b = old_charts.get(cid), new_charts.get(cid)
            if a != b:
                chart_changes.append(f"- `{cid}`: {json.dumps(a)} -> {json.dumps(b)}")
        out.append(f"### {name}\n")
        out.append(f"Text lines: {len(old['text'])} -> {len(new['text'])}. "
                   f"Removed {len(removed)}, added {len(added)}.\n")
        if removed:
            out.append("<details><summary>Removed text</summary>\n\n```\n" + "\n".join(removed) + "\n```\n</details>\n")
        if added:
            out.append("<details><summary>Added text</summary>\n\n```\n" + "\n".join(added) + "\n```\n</details>\n")
        if ids_gone:
            out.append("**DOM ids removed:** " + ", ".join(f"`{i}`" for i in ids_gone) + "\n")
        if ids_new:
            out.append("DOM ids added: " + ", ".join(f"`{i}`" for i in ids_new) + "\n")
        if chart_changes:
            out.append("**Chart changes:**\n" + "\n".join(chart_changes) + "\n")
    return "\n".join(out)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("before")
    parser.add_argument("after")
    args = parser.parse_args()
    print(compare(load(args.before), load(args.after)))
