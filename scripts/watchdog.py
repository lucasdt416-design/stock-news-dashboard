#!/usr/bin/env python3
"""
Pipeline Watchdog & Self-Healing Auto-Recovery
----------------------------------------------
Checks the latest completion time of a target GitHub Actions workflow (e.g. daily-run.yml).
If the last successful run was more than `max_hours` ago (and no run is currently queued/running),
automatically triggers a catch-up run via the GitHub Actions API.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request


def github_api_request(
    endpoint: str,
    token: str = None,
    method: str = "GET",
    payload: dict = None,
    timeout: int = 15,
) -> tuple[int, dict | list | None]:
    """
    Makes a request to the GitHub REST API using urllib.

    Args:
        endpoint: API path (e.g., '/repos/owner/repo/actions/workflows/daily-run.yml/runs')
                  or full URL.
        token: GitHub personal access token or GITHUB_TOKEN.
        method: HTTP method (GET, POST, etc.)
        payload: JSON serializable dict for POST request body.
        timeout: Network timeout in seconds.

    Returns:
        tuple of (status_code, parsed_json_response)
    """
    if endpoint.startswith("http://") or endpoint.startswith("https://"):
        url = endpoint
    else:
        url = f"https://api.github.com{endpoint}"

    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "StockNewsDashboard-Watchdog/1.0",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=data, headers=headers, method=method)

    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            status_code = response.status
            content = response.read().decode("utf-8")
            if content:
                try:
                    return status_code, json.loads(content)
                except json.JSONDecodeError:
                    return status_code, {"raw": content}
            return status_code, None
    except urllib.error.HTTPError as e:
        error_content = e.read().decode("utf-8")
        try:
            error_json = json.loads(error_content)
        except json.JSONDecodeError:
            error_json = {"error": error_content}
        return e.code, error_json
    except urllib.error.URLError as e:
        return 0, {"error": str(e.reason)}
    except Exception as e:
        return 0, {"error": str(e)}


def parse_iso_datetime(dt_str: str) -> datetime:
    """Parses an ISO 8601 UTC timestamp string from GitHub API into a timezone-aware datetime."""
    clean_str = dt_str.replace("Z", "+00:00")
    return datetime.fromisoformat(clean_str)


def get_latest_successful_run(repo: str, workflow: str, token: str = None) -> dict | None:
    """Fetches the most recent completed run with conclusion=success."""
    endpoint = f"/repos/{repo}/actions/workflows/{urllib.parse.quote(workflow)}/runs?status=success&per_page=1"
    status_code, data = github_api_request(endpoint, token=token)
    if status_code != 200 or not isinstance(data, dict):
        # Fallback to query all runs and find latest success
        fallback_endpoint = f"/repos/{repo}/actions/workflows/{urllib.parse.quote(workflow)}/runs?per_page=10"
        status_code, data = github_api_request(fallback_endpoint, token=token)
        if status_code != 200 or not isinstance(data, dict):
            return None

    runs = data.get("workflow_runs", [])
    for run in runs:
        if run.get("conclusion") == "success":
            return run
    return None


def get_active_runs(repo: str, workflow: str, token: str = None) -> list[dict]:
    """Fetches any runs that are currently in_progress or queued."""
    active_runs = []
    for status in ("in_progress", "queued"):
        endpoint = f"/repos/{repo}/actions/workflows/{urllib.parse.quote(workflow)}/runs?status={status}&per_page=5"
        status_code, data = github_api_request(endpoint, token=token)
        if status_code == 200 and isinstance(data, dict):
            active_runs.extend(data.get("workflow_runs", []))
    return active_runs


def trigger_workflow_dispatch(repo: str, workflow: str, ref: str, token: str = None) -> tuple[bool, str]:
    """Dispatches a workflow run via the GitHub Actions API."""
    endpoint = f"/repos/{repo}/actions/workflows/{urllib.parse.quote(workflow)}/dispatches"
    payload = {"ref": ref}
    status_code, response = github_api_request(endpoint, token=token, method="POST", payload=payload)
    if status_code in (204, 200, 201):
        return True, f"Successfully dispatched workflow '{workflow}' on ref '{ref}' (HTTP {status_code})."
    else:
        err_msg = response.get("message", json.dumps(response)) if isinstance(response, dict) else str(response)
        return False, f"Failed to dispatch workflow (HTTP {status_code}): {err_msg}"


def append_github_step_summary(markdown_text: str):
    """Appends Markdown content to $GITHUB_STEP_SUMMARY if available."""
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        try:
            with open(summary_path, "a", encoding="utf-8") as f:
                f.write(markdown_text + "\n")
        except Exception as e:
            print(f"Warning: Failed to write to GITHUB_STEP_SUMMARY: {e}", file=sys.stderr)


def evaluate_watchdog(
    repo: str,
    workflow: str = "daily-run.yml",
    max_hours: float = 20.0,
    ref: str = "main",
    token: str = None,
    dry_run: bool = False,
    now_utc: datetime = None,
) -> dict:
    """
    Evaluates workflow health and triggers a catch-up run if overdue.

    Returns:
        dict containing assessment details, status, and action taken.
    """
    if now_utc is None:
        now_utc = datetime.now(timezone.utc)

    result = {
        "repo": repo,
        "workflow": workflow,
        "max_hours": max_hours,
        "ref": ref,
        "checked_at": now_utc.isoformat(),
        "active_runs_count": 0,
        "last_success_at": None,
        "elapsed_hours": None,
        "action": "none",
        "reason": "",
        "triggered": False,
        "healthy": True,
    }

    if not repo:
        result["healthy"] = False
        result["reason"] = "Repository not specified (GITHUB_REPOSITORY not set)."
        result["action"] = "error"
        return result

    # 1. Check for active/queued runs
    active_runs = get_active_runs(repo, workflow, token=token)
    result["active_runs_count"] = len(active_runs)
    if active_runs:
        active_ids = [str(r.get("id")) for r in active_runs]
        result["healthy"] = True
        result["action"] = "skipped_active_run"
        result["reason"] = f"Pipeline is currently active (Run IDs: {', '.join(active_ids)}). No trigger needed."
        return result

    # 2. Check latest successful run
    latest_success = get_latest_successful_run(repo, workflow, token=token)
    if latest_success:
        # Use updated_at or created_at
        ts_str = latest_success.get("updated_at") or latest_success.get("created_at")
        last_success_dt = parse_iso_datetime(ts_str)
        result["last_success_at"] = last_success_dt.isoformat()
        elapsed_seconds = (now_utc - last_success_dt).total_seconds()
        elapsed_hours = max(0.0, elapsed_seconds / 3600.0)
        result["elapsed_hours"] = round(elapsed_hours, 2)
        result["last_run_url"] = latest_success.get("html_url", "")
        result["last_run_id"] = latest_success.get("id")

        if elapsed_hours <= max_hours:
            result["healthy"] = True
            result["action"] = "healthy"
            result["reason"] = (
                f"Last successful run was {elapsed_hours:.1f}h ago (within threshold of {max_hours:.1f}h). "
                f"Pipeline is healthy."
            )
            return result
        else:
            result["healthy"] = False
            result["reason"] = (
                f"Last successful run was {elapsed_hours:.1f}h ago (exceeds threshold of {max_hours:.1f}h). "
                f"Schedule may have been missed by GitHub cron."
            )
    else:
        result["healthy"] = False
        result["reason"] = "No previous successful runs found for this workflow. Triggering initial run."

    # 3. Overdue -> Trigger Auto-Recovery
    if dry_run:
        result["action"] = "dry_run_trigger"
        result["reason"] += " [DRY RUN: Trigger dispatch skipped]"
        result["triggered"] = False
    else:
        success, msg = trigger_workflow_dispatch(repo, workflow, ref, token=token)
        if success:
            result["action"] = "triggered_auto_recovery"
            result["triggered"] = True
            result["dispatch_message"] = msg
        else:
            result["action"] = "dispatch_failed"
            result["triggered"] = False
            result["error"] = msg

    return result


def main():
    parser = argparse.ArgumentParser(
        description="Watchdog safeguard to detect missed GitHub Actions scheduled runs and trigger auto-recovery."
    )
    parser.add_argument(
        "--repo",
        default=os.environ.get("GITHUB_REPOSITORY", ""),
        help="GitHub repository in 'owner/repo' format (defaults to $GITHUB_REPOSITORY)",
    )
    parser.add_argument(
        "--workflow",
        default="daily-run.yml",
        help="Target workflow file name or ID (default: daily-run.yml)",
    )
    parser.add_argument(
        "--max-hours",
        type=float,
        default=float(os.environ.get("WATCHDOG_MAX_HOURS", 20.0)),
        help="Maximum allowed hours since last successful run before triggering catch-up (default: 20.0)",
    )
    parser.add_argument(
        "--ref",
        default=os.environ.get("WATCHDOG_TARGET_REF", "main"),
        help="Git branch or ref to trigger (default: main)",
    )
    parser.add_argument(
        "--token",
        default=os.environ.get("GITHUB_TOKEN"),
        help="GitHub token with actions:write permission (defaults to $GITHUB_TOKEN)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate watchdog check without triggering workflow dispatch",
    )

    args = parser.parse_args()

    print("=" * 60)
    print("🛡️  PIPELINE WATCHDOG & SELF-HEALING AUTO-RECOVERY")
    print("=" * 60)
    print(f"Target Repo:        {args.repo or '(None)'}")
    print(f"Target Workflow:    {args.workflow}")
    print(f"Max Inactive Hours: {args.max_hours} hours")
    print(f"Target Ref / Branch:{args.ref}")
    print(f"Dry Run Mode:       {'ENABLED' if args.dry_run else 'DISABLED'}")
    print(f"Token Configured:   {'YES' if args.token else 'NO'}")
    print("=" * 60)

    res = evaluate_watchdog(
        repo=args.repo,
        workflow=args.workflow,
        max_hours=args.max_hours,
        ref=args.ref,
        token=args.token,
        dry_run=args.dry_run,
    )

    print("\n📊 WATCHDOG EVALUATION RESULT:")
    print(f"Status:             {res['action'].upper()}")
    print(f"Pipeline Healthy:   {res['healthy']}")
    print(f"Active Runs:        {res['active_runs_count']}")
    if res.get("elapsed_hours") is not None:
        print(f"Hours Since Success:{res['elapsed_hours']}h (Threshold: {args.max_hours}h)")
    if res.get("last_run_url"):
        print(f"Last Run URL:       {res['last_run_url']}")
    print(f"Reason / Details:   {res['reason']}")
    if res.get("dispatch_message"):
        print(f"Dispatch Status:    {res['dispatch_message']}")
    if res.get("error"):
        print(f"Error:              {res['error']}")
    print("=" * 60)

    # Build Markdown Summary for GitHub Actions
    summary_md = [
        "## 🛡️ Pipeline Watchdog Safeguard Summary",
        "",
        f"- **Target Workflow**: `{args.workflow}`",
        f"- **Target Repository**: `{args.repo}`",
        f"- **Evaluation Timestamp**: `{res['checked_at']}`",
        f"- **Active Runs Count**: `{res['active_runs_count']}`",
    ]
    if res.get("elapsed_hours") is not None:
        summary_md.append(f"- **Elapsed Time Since Last Success**: `{res['elapsed_hours']}h` (Max Threshold: `{args.max_hours}h`)")
    if res.get("last_success_at"):
        summary_md.append(f"- **Last Successful Run**: `{res['last_success_at']}` ([Run #{res.get('last_run_id')}]({res.get('last_run_url')}))")

    if res["action"] == "healthy":
        summary_md.append("\n> ✅ **Pipeline Status**: **HEALTHY**. Pipeline completed within normal operational window.")
    elif res["action"] == "skipped_active_run":
        summary_md.append("\n> ⏳ **Pipeline Status**: **ACTIVE RUN IN PROGRESS**. Catch-up trigger omitted.")
    elif res["action"] in ("triggered_auto_recovery", "dry_run_trigger"):
        summary_md.append(f"\n> 🚨 **Pipeline Status**: **OVERDUE & AUTO-RECOVERED**.")
        summary_md.append(f"> ⚡ **Action**: Dispatched workflow `{args.workflow}` on `{args.ref}` via GitHub Actions API.")
    elif res["action"] == "dispatch_failed":
        summary_md.append(f"\n> ⚠️ **Pipeline Status**: **OVERDUE BUT DISPATCH FAILED**.")
        summary_md.append(f"> Error details: `{res.get('error')}`")

    append_github_step_summary("\n".join(summary_md))

    if res["action"] == "error":
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
