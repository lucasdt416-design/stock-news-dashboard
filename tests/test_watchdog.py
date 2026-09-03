"""Unit tests for the Pipeline Watchdog & Self-Healing Auto-Recovery system."""

from datetime import datetime, timezone, timedelta
import io
import json
import os
import tempfile
import unittest
from unittest.mock import patch, MagicMock
import urllib.error

from scripts.watchdog import (
    parse_iso_datetime,
    github_api_request,
    get_latest_successful_run,
    get_active_runs,
    trigger_workflow_dispatch,
    evaluate_watchdog,
    append_github_step_summary,
)


class TestWatchdog(unittest.TestCase):

    def test_parse_iso_datetime(self):
        dt1 = parse_iso_datetime("2026-08-30T11:00:00Z")
        self.assertEqual(dt1.year, 2026)
        self.assertEqual(dt1.month, 8)
        self.assertEqual(dt1.day, 30)
        self.assertEqual(dt1.hour, 11)
        self.assertEqual(dt1.tzinfo, timezone.utc)

        dt2 = parse_iso_datetime("2026-08-30T11:00:00+00:00")
        self.assertEqual(dt1, dt2)

    @patch("scripts.watchdog.urllib.request.urlopen")
    def test_github_api_request_success(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = b'{"workflow_runs": [{"id": 12345, "status": "completed"}]}'
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        status, data = github_api_request("/repos/test/repo/actions/runs", token="fake_token")
        self.assertEqual(status, 200)
        self.assertEqual(data["workflow_runs"][0]["id"], 12345)

    @patch("scripts.watchdog.urllib.request.urlopen")
    def test_github_api_request_http_error(self, mock_urlopen):
        fp = io.BytesIO(b'{"message": "Not Found"}')
        error = urllib.error.HTTPError(
            url="https://api.github.com/test",
            code=404,
            msg="Not Found",
            hdrs={},
            fp=fp,
        )
        mock_urlopen.side_effect = error

        status, data = github_api_request("/repos/test/repo/actions/runs")
        self.assertEqual(status, 404)
        self.assertEqual(data.get("message"), "Not Found")

    @patch("scripts.watchdog.github_api_request")
    def test_get_latest_successful_run(self, mock_api):
        mock_api.return_value = (
            200,
            {
                "workflow_runs": [
                    {
                        "id": 9991,
                        "status": "completed",
                        "conclusion": "success",
                        "created_at": "2026-08-30T11:00:00Z",
                    }
                ]
            },
        )
        run = get_latest_successful_run("owner/repo", "daily-run.yml")
        self.assertIsNotNone(run)
        self.assertEqual(run["id"], 9991)

    @patch("scripts.watchdog.github_api_request")
    def test_get_active_runs(self, mock_api):
        def side_effect(endpoint, **kwargs):
            if "status=in_progress" in endpoint:
                return 200, {"workflow_runs": [{"id": 8881, "status": "in_progress"}]}
            return 200, {"workflow_runs": []}

        mock_api.side_effect = side_effect
        active = get_active_runs("owner/repo", "daily-run.yml")
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0]["id"], 8881)

    @patch("scripts.watchdog.github_api_request")
    def test_trigger_workflow_dispatch_success(self, mock_api):
        mock_api.return_value = (204, None)
        success, msg = trigger_workflow_dispatch("owner/repo", "daily-run.yml", "main", token="tok")
        self.assertTrue(success)
        self.assertIn("Successfully dispatched", msg)

    @patch("scripts.watchdog.trigger_workflow_dispatch")
    @patch("scripts.watchdog.get_latest_successful_run")
    @patch("scripts.watchdog.get_active_runs")
    def test_evaluate_watchdog_healthy(self, mock_active, mock_success, mock_dispatch):
        now = datetime(2026, 8, 30, 16, 0, 0, tzinfo=timezone.utc)
        mock_active.return_value = []
        # Last run was 5 hours ago (11:00 UTC)
        mock_success.return_value = {
            "id": 101,
            "conclusion": "success",
            "created_at": "2026-08-30T11:00:00Z",
            "html_url": "https://github.com/owner/repo/actions/runs/101",
        }

        res = evaluate_watchdog(
            repo="owner/repo",
            workflow="daily-run.yml",
            max_hours=20.0,
            now_utc=now,
        )
        self.assertTrue(res["healthy"])
        self.assertEqual(res["action"], "healthy")
        self.assertEqual(res["elapsed_hours"], 5.0)
        self.assertFalse(res["triggered"])
        mock_dispatch.assert_not_called()

    @patch("scripts.watchdog.trigger_workflow_dispatch")
    @patch("scripts.watchdog.get_latest_successful_run")
    @patch("scripts.watchdog.get_active_runs")
    def test_evaluate_watchdog_overdue_triggers_dispatch(self, mock_active, mock_success, mock_dispatch):
        now = datetime(2026, 8, 30, 14, 0, 0, tzinfo=timezone.utc)
        mock_active.return_value = []
        # Last run was 27 hours ago (yesterday at 11:00 UTC)
        mock_success.return_value = {
            "id": 102,
            "conclusion": "success",
            "created_at": "2026-08-29T11:00:00Z",
            "html_url": "https://github.com/owner/repo/actions/runs/102",
        }
        mock_dispatch.return_value = (True, "Dispatched successfully")

        res = evaluate_watchdog(
            repo="owner/repo",
            workflow="daily-run.yml",
            max_hours=20.0,
            now_utc=now,
        )
        self.assertFalse(res["healthy"])
        self.assertEqual(res["action"], "triggered_auto_recovery")
        self.assertEqual(res["elapsed_hours"], 27.0)
        self.assertTrue(res["triggered"])
        mock_dispatch.assert_called_once_with("owner/repo", "daily-run.yml", "main", token=None)

    @patch("scripts.watchdog.trigger_workflow_dispatch")
    @patch("scripts.watchdog.get_latest_successful_run")
    @patch("scripts.watchdog.get_active_runs")
    def test_evaluate_watchdog_overdue_with_active_run_skips(self, mock_active, mock_success, mock_dispatch):
        now = datetime(2026, 8, 30, 14, 0, 0, tzinfo=timezone.utc)
        # Active run in flight
        mock_active.return_value = [{"id": 103, "status": "in_progress"}]
        mock_success.return_value = {
            "id": 100,
            "conclusion": "success",
            "created_at": "2026-08-29T11:00:00Z",
        }

        res = evaluate_watchdog(
            repo="owner/repo",
            workflow="daily-run.yml",
            max_hours=20.0,
            now_utc=now,
        )
        self.assertTrue(res["healthy"])
        self.assertEqual(res["action"], "skipped_active_run")
        self.assertFalse(res["triggered"])
        mock_dispatch.assert_not_called()

    @patch("scripts.watchdog.trigger_workflow_dispatch")
    @patch("scripts.watchdog.get_latest_successful_run")
    @patch("scripts.watchdog.get_active_runs")
    def test_evaluate_watchdog_dry_run(self, mock_active, mock_success, mock_dispatch):
        now = datetime(2026, 8, 30, 14, 0, 0, tzinfo=timezone.utc)
        mock_active.return_value = []
        mock_success.return_value = {
            "id": 104,
            "conclusion": "success",
            "created_at": "2026-08-29T11:00:00Z",
        }

        res = evaluate_watchdog(
            repo="owner/repo",
            workflow="daily-run.yml",
            max_hours=20.0,
            dry_run=True,
            now_utc=now,
        )
        self.assertFalse(res["healthy"])
        self.assertEqual(res["action"], "dry_run_trigger")
        self.assertFalse(res["triggered"])
        mock_dispatch.assert_not_called()

    @patch("scripts.watchdog.trigger_workflow_dispatch")
    @patch("scripts.watchdog.get_latest_successful_run")
    @patch("scripts.watchdog.get_active_runs")
    def test_evaluate_watchdog_no_previous_runs(self, mock_active, mock_success, mock_dispatch):
        now = datetime(2026, 8, 30, 14, 0, 0, tzinfo=timezone.utc)
        mock_active.return_value = []
        mock_success.return_value = None
        mock_dispatch.return_value = (True, "Dispatched initial run")

        res = evaluate_watchdog(
            repo="owner/repo",
            workflow="daily-run.yml",
            max_hours=20.0,
            now_utc=now,
        )
        self.assertEqual(res["action"], "triggered_auto_recovery")
        self.assertTrue(res["triggered"])

    def test_append_github_step_summary(self):
        with tempfile.NamedTemporaryFile(mode="w+", delete=False) as tf:
            summary_file = tf.name

        try:
            with patch.dict(os.environ, {"GITHUB_STEP_SUMMARY": summary_file}):
                append_github_step_summary("### Test Summary Line")

            with open(summary_file, "r", encoding="utf-8") as f:
                content = f.read()
            self.assertIn("### Test Summary Line", content)
        finally:
            if os.path.exists(summary_file):
                os.remove(summary_file)


if __name__ == "__main__":
    unittest.main()
