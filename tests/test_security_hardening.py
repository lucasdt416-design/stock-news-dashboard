"""Guards for the deployment, workflow and SQL hardening. See docs/security-review.md."""

import ast
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest
import yaml

from pipeline.db import get_db_connection, init_db
from pipeline.persist import get_all_news_items, save_news_items
from pipeline.render import render_dashboard

ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = sorted((ROOT / ".github" / "workflows").glob("*.yml"))
CODE_DIRS = ("pipeline", "collectors", "scripts")


def _load(path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("workflow", WORKFLOWS, ids=lambda p: p.name)
def test_workflow_is_least_privilege(workflow):
    data = _load(workflow)
    triggers = data.get("on", data.get(True))
    assert "pull_request_target" not in triggers
    assert data.get("permissions") == {}, "default must be no permissions"
    for job in data["jobs"].values():
        assert "permissions" in job, "each job states what it needs"
        assert "id-token" not in job["permissions"]
        assert job["permissions"].get("contents", "read") == "read"
        assert not any("secrets." in str(v) for v in (job.get("env") or {}).values()), "secrets go on steps"


@pytest.mark.parametrize("workflow", WORKFLOWS, ids=lambda p: p.name)
def test_actions_are_pinned_to_commit_shas(workflow):
    uses = re.findall(r"uses:\s*(\S+)", workflow.read_text(encoding="utf-8"))
    assert uses
    for action in uses:
        assert re.fullmatch(r"[\w./-]+@[0-9a-f]{40}", action), action


def test_checkout_does_not_keep_the_token():
    for workflow in WORKFLOWS:
        for job in _load(workflow)["jobs"].values():
            for step in job["steps"]:
                if "checkout" in step.get("uses", ""):
                    assert step["with"]["persist-credentials"] is False


def test_cloudflare_token_is_only_near_the_deploy():
    steps = _load(ROOT / ".github/workflows/daily-run.yml")["jobs"]["build-and-deploy"]["steps"]
    seen = [s["name"] for s in steps if "CLOUDFLARE_API_TOKEN" in str(s.get("env", ""))]
    assert len(seen) == 2 and "Deploy" in seen[1]
    tested = [s for s in steps if "pytest" in str(s.get("run", ""))]
    assert tested and not tested[0].get("env")


def test_no_workflow_echoes_a_secret():
    for workflow in WORKFLOWS:
        for line in workflow.read_text(encoding="utf-8").splitlines():
            # Piping a secret into a command is fine; printing one to the log is not.
            printed = re.search(r"\b(?:echo|printf)\b([^|;>]*)(?:$|[;>])", line)
            if printed:
                assert not re.search(r"\$\{?\w*(KEY|TOKEN|SECRET)", printed.group(1)), line
                assert "secrets." not in printed.group(1), line


def test_wrangler_version_is_pinned():
    text = (ROOT / ".github/workflows/daily-run.yml").read_text(encoding="utf-8")
    assert re.search(r"wrangler@\d+\.\d+\.\d+", text)
    assert "npx wrangler" not in text


def test_headers_file_has_the_required_headers():
    text = (ROOT / "deploy" / "_headers").read_text(encoding="utf-8")
    for needed in ("X-Content-Type-Options: nosniff", "X-Frame-Options: DENY",
                   "Referrer-Policy: strict-origin-when-cross-origin", "Permissions-Policy:",
                   "frame-ancestors 'none'"):
        assert needed in text


def test_only_the_lookup_route_is_deployed():
    routes = sorted(str(p.relative_to(ROOT / "functions")) for p in (ROOT / "functions").rglob("*") if p.is_file())
    assert routes == [os.path.join("api", "lookup.js")]


def test_rendered_site_contains_only_intended_files():
    with tempfile.TemporaryDirectory() as tmp:
        db = os.path.join(tmp, "t.db")
        init_db(db)
        site = os.path.join(tmp, "site")
        render_dashboard(output_path=os.path.join(site, "index.html"), db_path=db, performance_data={})
        files = [p for p in Path(site).rglob("*") if p.is_file()]
        assert files
        for path in files:
            assert path.suffix in {".html", ".woff2", ""}, path.name
            assert path.suffix or path.name == "_headers", path.name
            assert not re.search(r"\.(db|sqlite|env|map|log|bak)$", path.name)


def _sql_calls():
    for folder in CODE_DIRS:
        for path in (ROOT / folder).rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                        and node.func.attr in {"execute", "executemany", "executescript"} and node.args):
                    yield path.name, node.lineno, node.args[0]


def test_sql_is_never_built_from_data():
    # select_cols is assembled only from literal column names (see persist.py), and query only
    # ever has literal clauses appended, with values passed separately as parameters.
    allowed = {"select_cols"}
    for name, line, sql in _sql_calls():
        assert not isinstance(sql, ast.BinOp), f"{name}:{line} concatenates SQL"
        assert not (isinstance(sql, ast.Call) and getattr(sql.func, "attr", "") == "format"), f"{name}:{line}"
        if isinstance(sql, ast.JoinedStr):
            names = {n.id for v in sql.values if isinstance(v, ast.FormattedValue) for n in ast.walk(v) if isinstance(n, ast.Name)}
            assert names <= allowed, f"{name}:{line} interpolates {names}"


def test_query_variables_only_append_literals():
    tree = ast.parse((ROOT / "pipeline" / "persist.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.AugAssign) and getattr(node.target, "id", "") in {"query", "select_cols"}:
            joined_conditions = ast.unparse(node.value) == "' WHERE ' + ' AND '.join(conditions)"
            assert isinstance(node.value, ast.Constant) or joined_conditions, f"persist.py:{node.lineno}"
        if (isinstance(node, ast.Call) and ast.unparse(node.func) == "conditions.append"):
            clause = node.args[0]
            assert isinstance(clause, ast.Constant) and "?" in clause.value, f"persist.py:{node.lineno}"


HOSTILE = "'); DROP TABLE news_items; -- <img src=x onerror=alert(1)>"


def test_hostile_text_is_stored_as_plain_data():
    with tempfile.TemporaryDirectory() as tmp:
        db = os.path.join(tmp, "t.db")
        init_db(db)
        save_news_items([{
            "item_uid": "hostile-1", "ticker": "NVDA", "source": "news", "headline": HOSTILE, "url": "https://example.com/x", "source_type": "news",
            "source_label": HOSTILE, "published_date": "2026-01-01", "form_or_type": "NEWS",
            "category": HOSTILE, "score": 5.0,
        }], db_path=db)
        stored = get_all_news_items(limit=None, db_path=db)
        assert [i["headline"] for i in stored] == [HOSTILE]
        conn = get_db_connection(db)
        assert conn.execute("SELECT COUNT(*) FROM news_items").fetchone()[0] == 1
        conn.close()


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_lookup_function_node_suite():
    result = subprocess.run(["node", "--test", "tests/node/lookup.test.mjs"], cwd=ROOT,
                            capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stdout[-2000:]
