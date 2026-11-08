"""Dates on the pages stay right between updates: the browser works out "Today", "In 3 days",
what is over and the local update time again from the reader's clock."""

import json
import re
import shutil
import sqlite3
import subprocess
from datetime import date, timedelta
from pathlib import Path

import pytest

from pipeline.render import CALENDAR_TEMPLATE, SHARED_MOBILE_JS, _relative_day, render_dashboard

DATES = SHARED_MOBILE_JS[SHARED_MOBILE_JS.index("// ---- Dates that stay right"):SHARED_MOBILE_JS.index("// ---- Learning from what you read")]


def test_updates_run_every_day():
    text = Path(".github/workflows/daily-run.yml").read_text(encoding="utf-8")
    assert "- cron: '0 11 * * *'" in text


@pytest.mark.skipif(not shutil.which("node"), reason="needs Node")
def test_browser_and_build_use_the_same_words():
    today = date.today()
    offsets = list(range(-20, 400))
    harness = (DATES.replace("\\\\", "\\") + (
        "\nconst t = new Date(); const out = {};\n"
        f"for (const n of {json.dumps(offsets)}) {{ const d = new Date(t.getFullYear(), t.getMonth(), t.getDate() + n);\n"
        "  const iso = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;\n"
        "  out[n] = relativeDay(iso); }\nout.bad = relativeDay('soon');\nconsole.log(JSON.stringify(out));\n"
    )).replace("document.addEventListener('DOMContentLoaded', refreshDates);", "")
    out = json.loads(subprocess.run(["node", "-e", harness], capture_output=True, text=True, check=True).stdout)
    for n in offsets:
        assert out[str(n)] == _relative_day(today + timedelta(days=n), today), n
    assert out["bad"] == ""
    assert _relative_day(today - timedelta(days=1), today) == "Yesterday"


def test_calendar_hides_what_is_over_and_relabels_weeks():
    assert "const ahead = (ev.dataset.date || '') >= today;" in CALENDAR_TEMPLATE
    assert "ev.hidden = !(typeOk && followOk && ahead);" in CALENDAR_TEMPLATE
    assert "heading.textContent = 'This week'" in CALENDAR_TEMPLATE
    assert 'id="calendarSummary"' in CALENDAR_TEMPLATE


def test_pages_carry_the_dates_the_browser_needs(tmp_path):
    db = str(tmp_path / "d.db")
    from pipeline.db import init_db
    from pipeline.calendar import init_calendar_schema
    from pipeline.economic import init_economic_schema
    init_db(db)
    soon = date.today() + timedelta(days=3)
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    init_calendar_schema(conn)
    init_economic_schema(conn)
    cols = [r[1] for r in conn.execute("PRAGMA table_info(calendar_events)")]
    row = {"event_id": "e1", "ticker": "NVDA", "company_name": "NVIDIA", "event_type": "Earnings Call",
           "event_date": soon.isoformat(), "display_date": "x", "relative_badge": "stored long ago",
           "headline": "NVIDIA to report", "source_url": "https://example.com", "source_type": "NEWS",
           "created_at": "2026-11-01"}
    use = [c for c in cols if c in row]
    conn.execute(f"INSERT INTO calendar_events ({','.join(use)}) VALUES ({','.join('?' * len(use))})", [row[c] for c in use])
    conn.execute("INSERT INTO economic_releases VALUES ('cpi', ?, '08:30', 'now')", (soon.isoformat(),))
    conn.execute("INSERT INTO economic_releases VALUES ('cpi', ?, '08:30', 'now')", ((soon + timedelta(days=30)).isoformat(),))
    conn.commit()
    conn.close()
    site = tmp_path / "site"
    render_dashboard(output_path=str(site / "index.html"), db_path=db, performance_data={})

    home = (site / "index.html").read_text(encoding="utf-8")
    assert re.search(r'Updated <time datetime="\d{4}-\d\d-\d\dT\d\d:\d\dZ" data-local-time>[^<]+ UTC</time>', home)

    cal = (site / "calendar.html").read_text(encoding="utf-8")
    assert f'data-date="{soon.isoformat()}" data-what="NVIDIA' in cal
    assert f'<span data-rel-date="{soon.isoformat()}">In 3 days</span>' in cal

    econ = (site / "economic.html").read_text(encoding="utf-8")
    assert re.search(r'data-kind="cpi" data-at="[\d-]+T08:30:00-0[45]:00">', econ), "the first CPI release is shown"
    assert re.search(r'data-kind="cpi" data-at="[\d-]+T08:30:00-0[45]:00" hidden>', econ), "the next one waits"
    assert 'id="econNoReleases" hidden' in econ

    company = (site / "company-nvda.html").read_text(encoding="utf-8")
    assert f'<li class="fp-event" data-until="{soon.isoformat()}">' in company
    assert f'<span data-until="{soon.isoformat()}"> · Next: ' in company, "the line at the top goes too once it is over"
    assert "stored long ago" not in company, "the label is worked out, not the one stored with the event"
