"""Health monitoring, collector telemetry, and anomaly detection engine.

Implements build-plan.md Section 10:
- Tracks per-source item yield (SEC EDGAR, Company IR, total raw, unique).
- Evaluates moving averages across previous runs.
- Flags anomalies (e.g. source returning 0 items, total volume < 33% of 7-run average).
- Persists health reports to SQLite 'pipeline_runs' table.
"""

import logging
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

STATUS_HEALTHY = "HEALTHY"
STATUS_WARNING = "WARNING"
STATUS_CRITICAL = "CRITICAL"


def init_health_schema(conn: sqlite3.Connection) -> None:
    """Create pipeline_runs table if it does not exist."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS pipeline_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_timestamp TEXT NOT NULL,
            edgar_count INTEGER NOT NULL,
            company_ir_count INTEGER NOT NULL,
            total_raw INTEGER NOT NULL,
            total_unique INTEGER NOT NULL,
            high_impact_count INTEGER NOT NULL,
            status TEXT NOT NULL,
            health_message TEXT NOT NULL,
            moving_avg_raw REAL DEFAULT 0.0
        );
        """
    )
    conn.commit()


def calculate_historical_baseline(
    conn: sqlite3.Connection, window_size: int = 7
) -> Tuple[float, int]:
    """Calculate moving average of total_raw collected over previous N runs.

    Returns:
        (moving_average, number_of_past_runs)
    """
    cursor = conn.execute(
        """
        SELECT total_raw FROM pipeline_runs 
        ORDER BY id DESC LIMIT ?
        """,
        (window_size,),
    )
    rows = cursor.fetchall()
    if not rows:
        return (0.0, 0)

    counts = [r[0] for r in rows if r[0] is not None]
    if not counts:
        return (0.0, 0)

    avg = sum(counts) / float(len(counts))
    return (round(avg, 1), len(counts))


def evaluate_run_health(
    edgar_count: int,
    company_ir_count: int,
    total_raw: int,
    total_unique: int,
    moving_avg_raw: float,
    past_runs_count: int,
) -> Tuple[str, str]:
    """Evaluate health status and generate diagnostic message."""
    issues: List[str] = []
    is_critical = False
    is_warning = False

    # 1. Critical Checks: Primary source (EDGAR) completely empty or 0 total items
    if total_raw == 0:
        issues.append("Total items collected is 0 (all scrapers/APIs failed)")
        is_critical = True
    elif edgar_count == 0:
        issues.append("SEC EDGAR returned 0 filings (expected ~150-450)")
        is_critical = True

    # 2. Warning Checks: Company IR returned 0 items
    if company_ir_count == 0 and total_raw > 0:
        issues.append("Company IR feeds returned 0 announcements (expected ~50-150)")
        is_warning = True

    # 3. Volume Drop Check: If total volume is < 33% of moving average (requires >= 2 previous runs)
    if past_runs_count >= 2 and moving_avg_raw > 50:
        threshold = moving_avg_raw / 3.0
        if total_raw < threshold:
            drop_pct = round((1.0 - (total_raw / moving_avg_raw)) * 100, 1)
            issues.append(
                f"Collection volume ({total_raw}) fell below 33% threshold "
                f"of {past_runs_count}-run average ({moving_avg_raw:.0f}) — drop of {drop_pct}%"
            )
            is_warning = True

    # Determine overall status
    if is_critical:
        status = STATUS_CRITICAL
        message = "🚨 CRITICAL OUTAGE: " + "; ".join(issues)
    elif is_warning:
        status = STATUS_WARNING
        message = "⚠️ DEGRADED PERFORMANCE: " + "; ".join(issues)
    else:
        status = STATUS_HEALTHY
        message = "🟢 All collectors operating normally within historical volume bands."

    return status, message


def record_pipeline_run_health(
    collector_counts: Dict[str, int],
    total_raw: int,
    total_unique: int,
    high_impact_count: int,
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Record pipeline run telemetry and return the health evaluation report."""
    from pipeline.db import get_db_connection

    edgar_count = collector_counts.get("sec_edgar", 0)
    ir_count = collector_counts.get("company_ir", 0)
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")

    with get_db_connection(db_path) as conn:
        init_health_schema(conn)
        moving_avg, past_runs = calculate_historical_baseline(conn, window_size=7)

        status, message = evaluate_run_health(
            edgar_count=edgar_count,
            company_ir_count=ir_count,
            total_raw=total_raw,
            total_unique=total_unique,
            moving_avg_raw=moving_avg,
            past_runs_count=past_runs,
        )

        conn.execute(
            """
            INSERT INTO pipeline_runs (
                run_timestamp, edgar_count, company_ir_count,
                total_raw, total_unique, high_impact_count,
                status, health_message, moving_avg_raw
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                now_iso,
                edgar_count,
                ir_count,
                total_raw,
                total_unique,
                high_impact_count,
                status,
                message,
                moving_avg,
            ),
        )
        conn.commit()

    report = {
        "run_timestamp": now_iso,
        "edgar_count": edgar_count,
        "company_ir_count": ir_count,
        "total_raw": total_raw,
        "total_unique": total_unique,
        "high_impact_count": high_impact_count,
        "status": status,
        "health_message": message,
        "moving_avg_raw": moving_avg,
        "past_runs_count": past_runs,
    }

    if status == STATUS_CRITICAL:
        logger.error("Pipeline Health Alert [%s]: %s", status, message)
    elif status == STATUS_WARNING:
        logger.warning("Pipeline Health Notice [%s]: %s", status, message)
    else:
        logger.info("Pipeline Health Status [%s]: %s", status, message)

    return report
