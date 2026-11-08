"""The category donut: six fixed colors, the rest folded into one "Other", neighbours told apart.

Separation is measured as OKLab distance x100, for normal vision and simulated protanopia,
deuteranopia and tritanopia (Machado et al. 2009). Below 15 for normal vision, two slices look
the same to anyone; below 6 for color-blind vision, they need more than a label to be told apart.
"""

import re

from pipeline.render import ANALYTICS_TEMPLATE, SHARED_CSS

MACHADO = {
    "protan": [[0.152286, 1.052583, -0.204868], [0.114503, 0.786281, 0.099216], [-0.003882, -0.048116, 1.051998]],
    "deutan": [[0.367322, 0.860646, -0.227968], [0.280085, 0.672501, 0.047413], [-0.011820, 0.042940, 0.968881]],
    "tritan": [[1.255528, -0.076749, -0.178779], [-0.078411, 0.930809, 0.147602], [0.004733, 0.691367, 0.303900]],
}
# The usual order of slices, largest first (live site, 2026-11-07); "Other" closes the ring.
USUAL_ORDER = ["Company Announcement", "Earnings & Financials", "Product Launches & Technology",
               "Guidance & Commentary", "Insider Transactions", "Capital Structure & Offerings", "Other"]


def _linear(h):
    out = []
    for i in (1, 3, 5):
        c = int(h[i:i + 2], 16) / 255
        out.append(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)
    return out


def _oklab(rgb):
    r, g, b = rgb
    lms = [0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b, 0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b,
           0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b]
    l, m, s = [max(x, 0) ** (1 / 3) for x in lms]
    return (0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s, 1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s,
            0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s)


def _distance(a, b, matrix=None):
    def view(h):
        rgb = _linear(h)
        if matrix:
            rgb = [max(0.0, min(1.0, sum(matrix[i][j] * rgb[j] for j in range(3)))) for i in range(3)]
        return _oklab(rgb)
    return 100 * sum((x - y) ** 2 for x, y in zip(view(a), view(b))) ** 0.5


def _themes():
    light = SHARED_CSS[:SHARED_CSS.index(':root[data-theme="dark"]')]
    dark = SHARED_CSS[SHARED_CSS.index(':root[data-theme="dark"]'):]
    return [{k: v for k, v in re.findall(r"--(series-[\w]+):\s*(#[0-9a-fA-F]{6})", block)} for block in (light, dark)]


def _assignments():
    block = ANALYTICS_TEMPLATE[ANALYTICS_TEMPLATE.index("const categoryColors = {"):]
    block = block[:block.index("};")]
    return dict(re.findall(r"'([^']+)':\s*'--([\w-]+)'", block))


def test_six_categories_have_their_own_color_and_the_rest_are_other():
    colors = _assignments()
    assert sorted(colors.values()) == [f"series-{i}" for i in range(1, 7)]
    assert colors["Earnings & Financials"] == "series-1", "earnings is blue everywhere on the site"
    assert "cssColor(categoryColors[label] || '--series-other')" in ANALYTICS_TEMPLATE
    assert "if (label === 'Other') folded.forEach" in ANALYTICS_TEMPLATE, "the list still names every category"


def test_neighbouring_slices_can_be_told_apart_in_both_themes():
    colors = _assignments()
    for palette in _themes():
        slots = [palette[colors.get(name, "series-other")] for name in USUAL_ORDER]
        for i, a in enumerate(slots):
            b = slots[(i + 1) % len(slots)]
            pair = (USUAL_ORDER[i], USUAL_ORDER[(i + 1) % len(slots)])
            assert _distance(a, b) >= 15, pair
            assert min(_distance(a, b, m) for m in MACHADO.values()) >= 6, pair
