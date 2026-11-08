"""GitHub Actions stay pinned to exact, current versions, and the pipeline installs only what it runs."""

import re
from pathlib import Path

WORKFLOWS = {p.name: p.read_text(encoding="utf-8") for p in Path(".github/workflows").glob("*.yml")}


def test_every_action_is_pinned_to_a_commit_and_says_which_version():
    for name, text in WORKFLOWS.items():
        for line in re.findall(r"uses:\s*(\S+.*)", text):
            assert re.fullmatch(r"[\w./-]+@[0-9a-f]{40} # v\d+(\.\d+){0,2}", line.strip()), f"{name}: {line}"


def test_no_action_still_runs_on_node_20():
    """GitHub warned on 2026-11-07 that the v4/v5 actions run on the deprecated Node.js 20."""
    floors = {"actions/checkout": 5, "actions/setup-python": 6, "actions/setup-node": 5, "actions/cache": 5,
              "actions/upload-artifact": 6}
    for name, text in WORKFLOWS.items():
        for action, major in re.findall(r"uses:\s*([\w-]+/[\w-]+)(?:/[\w-]+)?@[0-9a-f]{40} # v(\d+)", text):
            assert int(major) >= floors.get(action, 0), f"{name}: {action} v{major}"


def test_the_database_cache_is_restored_and_saved_by_the_same_version():
    text = WORKFLOWS["daily-run.yml"]
    restore = re.search(r"actions/cache/restore@([0-9a-f]{40})", text).group(1)
    save = re.search(r"actions/cache/save@([0-9a-f]{40})", text).group(1)
    assert restore == save


def test_the_linter_is_a_dev_tool_not_a_runtime_dependency():
    runtime = Path("requirements.txt").read_text(encoding="utf-8")
    dev = Path("requirements-dev.txt").read_text(encoding="utf-8")
    for tool in ("flake8", "pyflakes", "pycodestyle", "mccabe"):
        assert tool not in runtime, tool
        assert re.search(rf"^{tool}==[\d.]+; python_version >= \"3.11\"$", dev, re.M), tool
