# StockPulse redesign plan

**Status: written by the implementing agent, not the owner.** The task named `docs/redesign-brief.md` as the source
of truth, but that file is not in this repo, its history, or anywhere else that could be searched. If the original
brief turns up, it overrides this document. It is deliberately named differently so it cannot overwrite the original.

## Goal

Calm, minimalist, editorial, and far less cluttered, keeping the existing pages and navigation. Presentation only:
no changes to pipeline logic, scoring, classification, collectors, summarization, the schema,
`functions/api/lookup.js`, workflows, or function signatures.

## The idea: read it like a morning paper

The data is already ranked, dated, and tied to companies. The current design ignores that and gives everything the
same card, pill, and shadow. The redesign lets each page's natural structure carry the organization:

| Page | Organized as | Why |
|---|---|---|
| Home | A front page: one lead story, the next event, and an index of the watchlist by sector | Answers "what do I need to know today?" in one screen |
| Feed | Three reading bands: *Read first*, *Worth knowing*, *On file*, as hairline rows | A score only matters as a reading decision. Replaces a 30,000 px wall |
| Calendar | A timeline of the coming weeks above an agenda grouped by week | Time is the natural axis of this data |
| Economic | A ledger: one row per indicator with its trend and the holdings it touches | Makes indicators comparable at a glance |
| Directory | A book-style index grouped by sector | Thirty names need scanning, not thirty cards |
| Company | A dossier: position, performance, then filings and relationships | One company, top to bottom |
| Analytics | Figures with captions, like charts in a report | Every chart states what it shows |

## Design principles

1. **Hairlines over boxes.** Structure comes from rules and whitespace. A card needs a reason to exist.
2. **One voice per job.** A serif for reading, a sans for interface labels, tabular numerals for data.
3. **One accent.** Green and red appear only when they mean up or down.
4. **Rank by type, not decoration.** Size, weight, and position show importance. Badges don't.
5. **Disclose on demand.** Score arithmetic and cross-references stay available, one interaction away.
6. **Say only what is true.** No status, score, or "live" label the data does not support.
7. **Same quality in dark mode and at 390 px.** These are not afterthoughts.

## The "less AI" list

Remove on sight: gradient meshes and glows, glassmorphism, floating 3D or orbiting cards, pulsing "live" dots,
oversized radii, soft shadows on everything, bento grids, pill badges on every noun, gradient icon tiles, Inter
everywhere, marketing words ("Intelligence", "360°", "Deep-dive", "Catalyst"), emoji as icons, centered hero plus
subhead, a coloured badge per ticker, and sentence-long uppercase labels.

## Guardrails

- Edit existing components. After each PR, compare rendered text, DOM ids, and chart contents with the previous branch
  (`scripts/compare_captures.py`) and explain every difference.
- Keep ids used by scripts and tests, and keep search behavior.
- Escape all dynamic text inserted through JavaScript.
- Each PR passes `python -m pytest tests/` and has zero console errors, zero failed requests, and no horizontal
  overflow at 1440, 768, and 390 px in light and dark.

## PR plan

| PR | Branch | Scope |
|---|---|---|
| 00 | `redesign/00-demo-and-capture-tooling` | Demo database, capture and comparison scripts, this plan. No visual change |
| 01 | `redesign/01-design-foundations` | Palette, type, dark mode, removal of global gradients and shadows, escaping of dynamic text, overflow fixes |
| 02 | `redesign/02-app-shell` | Sidebar, mobile navigation, truthful status |
| 03 | `redesign/03-home-front-page` | Home as a front page, fake scores removed |
| 04 | `redesign/04-feed-reading-bands` | Feed organized by reading bands |
| 05 | `redesign/05-calendar-timeline` | Timeline and agenda |
| 06 | `redesign/06-economic-ledger` | Indicator ledger |
| 07 | `redesign/07-company-dossier` | Directory index and company dossier |
| 08 | `redesign/08-analytics-and-finish` | Analytics figures, chart styling, final cleanup |

## Additions made along the way

- PR 01 also took on escaping and overflow fixes, so every later PR could pass with zero console errors.
- Charts read colors through `cssColor()`, because a canvas can't resolve CSS variables. They redraw after web fonts load and when the theme changes.
- Chart series colors are the `--series-*` tokens, checked for color-blind separation against both page surfaces.
- `scripts/capture_site.py` fails on any legend entry that drew no pixels, and on search results that aren't visible.

## Running it

```bash
pip install -r requirements-dev.txt
python scripts/build_demo.py                                   # data/demo.db and .capture/site
python scripts/capture_site.py --out .capture/current          # screenshots and report.json
python scripts/compare_captures.py .capture/before .capture/current
```

All demo content is synthetic: generic headlines, a "Demo Wire" source, example.com links, and random-walk prices.
Economic values come from the offline fallback in `pipeline/economic.py`. Nothing here describes live data.
Demo output never goes in `site/`, because the test suite renders there and would overwrite it.
