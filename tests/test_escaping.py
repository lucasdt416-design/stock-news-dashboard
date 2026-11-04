"""Dynamic text must not become markup when pages build HTML in JavaScript."""

import json
import re

from pipeline.render import COMPANY_TEMPLATE, INDEX_TEMPLATE, _script_json

SEARCH_FIELDS = ["it.clean_headline", "it.category", "ev.headline", "c.name", "ind.name", "h.headline"]


def test_search_results_escape_dynamic_text():
    for field in SEARCH_FIELDS:
        assert "${" + field + "}" not in INDEX_TEMPLATE, f"{field} is inserted without escaping"


def test_external_links_only_allow_http():
    assert 'href="${h.url}"' not in INDEX_TEMPLATE
    assert "safeHref(h.url)" in INDEX_TEMPLATE


def test_company_table_escapes_names():
    assert "${coData.name}" not in COMPANY_TEMPLATE


def test_script_json_cannot_close_script_tag():
    encoded = _script_json({"category": "</script><script>alert(1)</script>"})
    assert "</script" not in encoded
    assert json.loads(encoded)["category"].startswith("</script>")
    assert re.search(r"<\\/script", encoded)
