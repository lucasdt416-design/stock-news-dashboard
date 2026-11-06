"""The visual identity is a contract: light by default, one blue accent, readable text, no clutter."""

import re

from pipeline.render import (
    ANALYTICS_TEMPLATE,
    CALENDAR_TEMPLATE,
    COMPANY_TEMPLATE,
    ECONOMIC_TEMPLATE,
    INDEX_TEMPLATE,
    NAVIGATION_LAYOUT_HTML,
    NEWS_TEMPLATE,
    SHARED_CSS,
    SHARED_MOBILE_JS,
)


def _block(selector):
    start = SHARED_CSS.index(selector + " {")
    return SHARED_CSS[start:SHARED_CSS.index("\n    }", start)]


def _tokens(selector):
    return dict(re.findall(r"--([a-z0-9-]+):\s*(#[0-9a-fA-F]{6})", _block(selector)))


def _luminance(hex_color):
    channels = [int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    r, g, b = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast(a, b):
    high, low = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def test_light_is_the_default_and_dark_is_opt_in():
    assert "color-scheme: light" in _block(":root")
    assert _tokens(":root")["bg-base"].lower() == "#ffffff"
    assert "color-scheme: dark" in _block(':root[data-theme="dark"]')
    assert _tokens(':root[data-theme="dark"]')["bg-base"].lower() == "#000000"
    assert "prefers-color-scheme" not in SHARED_CSS


def test_text_and_accent_are_readable_in_both_themes():
    for selector in (":root", ':root[data-theme="dark"]'):
        t = _tokens(selector)
        for surface in ("bg-base", "bg-surface"):
            for ink in ("text-primary", "text-secondary", "text-muted", "accent", "pos", "neg"):
                ratio = _contrast(t[ink], t[surface])
                assert ratio >= 4.5, f"{selector} {ink} on {surface}: {ratio:.2f}"
        assert _contrast(t["on-accent"], t["accent"]) >= 4.5


def test_serif_and_mono_pairing_is_gone():
    for template in (INDEX_TEMPLATE, COMPANY_TEMPLATE):
        assert "Newsreader" not in template
        assert "IBM+Plex" not in template
    assert "Fredoka" not in INDEX_TEMPLATE
    assert "@font-face" not in SHARED_CSS, "the device's own font needs no download"


def _last_rule(selector):
    """The final declaration block for a selector, which is the one that wins."""
    return SHARED_CSS[SHARED_CSS.rindex("\n    " + selector + " {"):].split("}", 1)[0]


def test_amber_and_the_bubble_font_are_gone():
    for leftover in ("#ffb020", "#f5a300", "--mark", "hero-wordmark", "Hanken"):
        assert leftover not in SHARED_CSS, leftover
    assert "hero-wordmark" not in INDEX_TEMPLATE
    assert _tokens(":root")["accent"].lower() == "#0066cc"


def test_ring_chips_and_section_rows_have_no_box():
    for selector in (".orbit-chip", ".door"):
        rule = _last_rule(selector)
        assert "background: none" in rule, selector
        assert "border: 0" in rule, selector


def test_only_floating_things_cast_a_shadow():
    shadows = {m.split("{")[-1] for m in re.findall(r"box-shadow:\s*(var\(--shadow-[a-z]+\))", SHARED_CSS)}
    assert shadows <= {"var(--shadow-dropdown)", "var(--shadow-modal)"}, shadows
    for token in ("shadow-sm", "shadow-card", "shadow-hover", "shadow-float"):
        assert f"--{token}: none" in SHARED_CSS


def test_scores_and_counts_do_not_clutter_home_feed_or_nav():
    assert "top-score" not in INDEX_TEMPLATE
    assert 'class="feed-score"' not in NEWS_TEMPLATE
    assert "How it scored: {{ item.score }}" in NEWS_TEMPLATE, "the score stays available on request"
    assert "nav-count" not in NAVIGATION_LAYOUT_HTML
    assert "Pipeline:" not in NAVIGATION_LAYOUT_HTML


def test_every_page_sticks_to_plain_words():
    pages = INDEX_TEMPLATE + NEWS_TEMPLATE + CALENDAR_TEMPLATE + ECONOMIC_TEMPLATE + COMPANY_TEMPLATE + ANALYTICS_TEMPLATE
    for phrase in ("Today's news", "On file", "deserve your time", "Switch to", "Peer Relative Alpha",
                   "Corporate Ecosystem", "Macroeconomic", "Forthcoming", "Pipeline Health", "Top Peers Avg",
                   "3M Return", "AI Macro", "read its file", "Deduplication"):
        assert phrase not in pages, phrase
    assert "Lagging Peer Group" in SHARED_MOBILE_JS, "the collector's label is translated, not shown"


def test_scores_are_gone_from_every_story_list():
    for template in (INDEX_TEMPLATE, NEWS_TEMPLATE, COMPANY_TEMPLATE):
        assert 'class="feed-score"' not in template


def test_stylesheet_has_no_control_characters():
    """A stray NUL changes what the browser hashes, so the CSP would block the whole stylesheet."""
    assert not re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", SHARED_CSS)


def test_hidden_feed_rows_stay_hidden():
    """Without this, display: grid beats the hidden attribute and filters appear to do nothing."""
    assert ".news-row[hidden] { display: none; }" in SHARED_CSS


def test_map_text_is_readable_on_every_step_in_both_themes():
    for selector in (":root", ':root[data-theme="dark"]'):
        t = _tokens(selector)
        for step in ("u1", "u2", "u3", "n", "d1", "d2", "d3"):
            ratio = _contrast(t[f"heat-{step}-ink"], t[f"heat-{step}"])
            assert ratio >= 4.5, f"{selector} {step}: {ratio:.2f}"
