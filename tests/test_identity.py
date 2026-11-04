"""The visual identity is a contract: one amber accent, readable text, no leftover pairings."""

import re

from pipeline.render import COMPANY_TEMPLATE, INDEX_TEMPLATE, SHARED_CSS


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


def test_dark_is_the_default_and_light_is_opt_in():
    assert "color-scheme: dark" in _block(":root")
    assert _tokens(":root")["bg-base"].lower() == "#0b0d12"
    assert "color-scheme: light" in _block(':root[data-theme="light"]')
    assert "prefers-color-scheme" not in SHARED_CSS


def test_text_and_accent_are_readable_in_both_themes():
    for selector in (":root", ':root[data-theme="light"]'):
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
    assert "Fredoka" in INDEX_TEMPLATE
