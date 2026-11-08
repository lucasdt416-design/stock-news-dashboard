"""The community files GitHub looks for exist, and the issue forms are valid."""

from pathlib import Path

import yaml


def test_community_files_exist():
    for name in ("README.md", "LICENSE", "SECURITY.md", "CONTRIBUTING.md", "CODE_OF_CONDUCT.md",
                 ".github/pull_request_template.md"):
        assert Path(name).is_file(), name


def test_issue_forms_are_valid():
    forms = sorted(Path(".github/ISSUE_TEMPLATE").glob("*.yml"))
    assert {f.name for f in forms} >= {"config.yml", "wrong-data.yml", "bug.yml", "idea.yml"}
    for form in forms:
        data = yaml.safe_load(form.read_text(encoding="utf-8"))
        if form.name == "config.yml":
            assert data["contact_links"][0]["url"].endswith("/security/advisories/new")
            continue
        assert data["name"] and data["description"] and data["body"], form.name
        assert all(field["type"] in ("input", "textarea", "dropdown", "markdown", "checkboxes") for field in data["body"])


def test_security_policy_points_to_private_reporting():
    text = Path("SECURITY.md").read_text(encoding="utf-8")
    assert "/security/advisories/new" in text and "not in a public issue" in text
