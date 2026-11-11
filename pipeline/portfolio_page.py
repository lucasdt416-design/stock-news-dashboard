"""The Your portfolio page (site/portfolio.html).

The page's own scripts are plain .js files next to this one, so Node can test the same source the
page runs (tests/node/portfolio_*.test.mjs). There is still no build step: at render time they are
put into the page as one inline script, which the page's Content-Security-Policy then hashes.
"""

import os
from typing import Any, Dict, List

_HERE = os.path.dirname(__file__)

# In the order they run. Each later file may use what the earlier ones define.
PORTFOLIO_SCRIPTS = ("portfolio_input.js", "portfolio_math.js", "portfolio_app.js", "portfolio_xray.js", "portfolio_whatif.js")


def _script(name: str) -> str:
    with open(os.path.join(_HERE, name), "r", encoding="utf-8") as f:
        source = f.read()
    # The files go into a Jinja template inside a raw block and then into a <script> block,
    # so neither of those may be ended from inside them.
    for banned in ("{% endraw %}", "</script", "<!--"):
        if banned in source:
            raise ValueError(f"{name} contains {banned!r}")
    return source


def portfolio_scripts() -> str:
    return "\n".join(_script(name) for name in PORTFOLIO_SCRIPTS)


def portfolio_data(companies: List[Dict[str, Any]], sectors: List[str]) -> Dict[str, Any]:
    """What the page needs to know about the watchlist that the shared script doesn't already carry."""
    known = {co["symbol"] for co in companies}
    other = {}
    for co in companies:
        for ticker in co.get("other_tickers") or []:
            ticker = str(ticker).upper().strip()
            if ticker and ticker not in known:
                other[ticker] = co["symbol"]
    def strings(co, field):
        return [str(v).strip() for v in (co.get(field) or []) if isinstance(v, str) and str(v).strip()]

    def entities(co, field):
        # A customer or supplier the site follows is named by its ticker, however the list spells it.
        return [v.upper() if v.upper() in known else v for v in strings(co, field)]

    details = {}
    for co in companies:
        entry = {
            "th": strings(co, "macro_sensitivities"),
            "ec": strings(co, "economic_sensitivities"),
            "cu": entities(co, "key_customers"),
            "su": entities(co, "key_suppliers"),
            "co": [v.upper() for v in strings(co, "competitors") if v.upper() in known],
        }
        # Every followed company has an entry, even an empty one: that is how the page tells
        # "nothing noted about it" from "not a company we follow".
        details[co["symbol"]] = {k: v for k, v in entry.items() if v}
    return {"sectors": list(sectors), "other": other, "companies": details}


PORTFOLIO_CSS = """
    .page-portfolio .app-main { max-width: 60rem; }
    .page-portfolio [hidden] { display: none !important; }
    .pf-banner { margin: 0 0 1.5rem; padding: 0.6rem 0.9rem; border-radius: var(--radius-md); background: var(--warn-soft); color: var(--warn); font-size: 0.9rem; }
    .pf-section { padding: 1.75rem 0; border-top: 1px solid var(--border-subtle); }
    .pf-section > .settings-heading { margin-bottom: 0.75rem; }
    .pf-note { margin: 0.5rem 0 0; font-size: 0.86rem; line-height: 1.45; color: var(--text-muted); max-width: 40rem; }
    .pf-note a { color: var(--accent); text-decoration: none; }
    .pf-note a:hover { text-decoration: underline; }
    .pf-add { display: flex; flex-wrap: wrap; align-items: center; gap: 0.6rem; }
    .pf-input { min-height: 40px; box-sizing: border-box; padding: 0.45rem 0.7rem; border: 1px solid var(--border-card); border-radius: var(--radius-md); background: var(--bg-base); color: var(--text-primary); font-size: 1rem; max-width: 100%; }
    .pf-input:focus-visible, .pf-link:focus-visible, .pf-seg button:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
    .pf-input::placeholder { color: var(--text-muted); }
    .pf-add #pfTicker { flex: 1 1 11rem; min-width: 0; }
    .pf-add #pfAmount { flex: 1 1 9rem; min-width: 0; }
    .pf-seg { display: inline-flex; border: 1px solid var(--border-card); border-radius: var(--radius-md); overflow: hidden; }
    .pf-seg button { min-height: 38px; padding: 0 0.8rem; border: none; background: none; color: var(--text-secondary); font: inherit; font-size: 0.9rem; cursor: pointer; }
    .pf-seg button[aria-pressed="true"] { background: var(--text-primary); color: var(--bg-base); }
    .pf-link { background: none; border: none; padding: 0.35rem 0; min-height: 36px; font: inherit; font-size: 0.9rem; color: var(--accent); cursor: pointer; }
    .pf-link:hover { text-decoration: underline; }
    .pf-danger { color: var(--neg); }
    .pf-more-ways { display: flex; flex-wrap: wrap; gap: 0.25rem 1.25rem; margin-top: 0.5rem; }
    .pf-details { display: flex; flex-wrap: wrap; gap: 0.75rem 1rem; margin-top: 0.85rem; }
    .pf-field { display: flex; flex-direction: column; gap: 0.25rem; font-size: 0.82rem; color: var(--text-muted); min-width: 0; }
    .pf-field .pf-input { width: 11rem; }
    .pf-paste { margin-top: 0.85rem; }
    .pf-paste textarea { display: block; width: 100%; min-height: 6.5rem; resize: vertical; font-family: inherit; }
    .pf-paste .setup-yes { margin-top: 0.6rem; }
    .pf-status { min-height: 1.3rem; margin: 0.75rem 0 0; font-size: 0.9rem; color: var(--text-secondary); }
    .pf-status-bad { color: var(--neg); }
    .pf-preview-rows, .pf-preview-unread, .pf-list { list-style: none; margin: 0; padding: 0; }
    .pf-preview-row { display: grid; grid-template-columns: 5rem minmax(0, 1fr); gap: 0.1rem 0.75rem; padding: 0.6rem 0; border-bottom: 1px solid var(--border-subtle); font-size: 0.95rem; }
    .pf-preview-name { color: var(--text-secondary); overflow-wrap: anywhere; }
    .pf-preview-what, .pf-preview-note { grid-column: 2; }
    .pf-preview-note { font-size: 0.84rem; color: var(--text-muted); }
    .pf-preview-bad .pf-preview-note { color: var(--neg); }
    .pf-preview-bad .pf-ticker, .pf-preview-bad .pf-preview-what { color: var(--text-muted); }
    .pf-preview-unread-head { margin: 1rem 0 0.35rem; font-size: 0.9rem; color: var(--text-secondary); }
    .pf-preview-unread li { display: flex; flex-wrap: wrap; gap: 0.15rem 0.75rem; padding: 0.3rem 0; font-size: 0.88rem; }
    .pf-unread-text { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 0.84rem; overflow-wrap: anywhere; min-width: 0; }
    .pf-unread-why { color: var(--text-muted); }
    .pf-preview-actions { display: flex; align-items: center; gap: 1rem; margin-top: 1rem; }
    .pf-ticker { font-weight: 600; color: var(--text-primary); text-decoration: none; }
    a.pf-ticker:hover { color: var(--accent); }
    .pf-row { display: grid; grid-template-columns: minmax(0, 1fr) auto 3.5rem auto; align-items: start; gap: 0.2rem 1rem; padding: 0.85rem 0; border-bottom: 1px solid var(--border-subtle); }
    .pf-row-title { display: flex; flex-wrap: wrap; align-items: baseline; gap: 0.1rem 0.6rem; }
    .pf-row-name { color: var(--text-secondary); font-size: 0.95rem; overflow-wrap: anywhere; min-width: 0; }
    .pf-row-meta { margin-top: 0.15rem; font-size: 0.84rem; color: var(--text-muted); }
    .pf-old { color: var(--warn); }
    .pf-row-value { text-align: right; font-variant-numeric: tabular-nums; }
    .pf-value { font-weight: 600; }
    .pf-gain { font-size: 0.84rem; color: var(--text-muted); }
    .pf-gain.pos { color: var(--pos); }
    .pf-gain.neg { color: var(--neg); }
    .pf-row-weight { text-align: right; color: var(--text-secondary); font-variant-numeric: tabular-nums; }
    .pf-row-out .pf-value { color: var(--text-muted); font-weight: 400; }
    .pf-row-edit { padding: 0.25rem 0 1rem; border-bottom: 1px solid var(--border-subtle); }
    .pf-edit { display: flex; flex-wrap: wrap; align-items: flex-end; gap: 0.75rem 1rem; }
    .pf-edit-actions { display: flex; flex-wrap: wrap; align-items: center; gap: 0.5rem 1rem; flex: 1 1 100%; }
    .pf-total { display: flex; align-items: baseline; justify-content: space-between; gap: 1rem; padding: 1rem 0 0.25rem; }
    .pf-total-label { color: var(--text-secondary); }
    .pf-total-value { font-size: 1.6rem; font-weight: 600; letter-spacing: -0.01em; font-variant-numeric: tabular-nums; }
    .pf-follow { display: flex; flex-wrap: wrap; align-items: baseline; gap: 0.25rem 1rem; margin-top: 0.75rem; }
    .pf-follow .pf-note { margin: 0; }
    .pf-foot { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 0.5rem 1.5rem; }
    .pf-lead { margin: 0 0 0.75rem; font-size: 1.02rem; line-height: 1.5; color: var(--text-primary); max-width: 42rem; }
    .pf-lead .pos { color: var(--pos); }
    .pf-lead .neg { color: var(--neg); }
    .pf-sectors, .pf-lines { list-style: none; margin: 0; padding: 0; }
    .pf-sector { display: grid; grid-template-columns: 13rem minmax(0, 1fr) 3.5rem; align-items: center; gap: 0.15rem 1rem; padding: 0.6rem 0; border-bottom: 1px solid var(--border-subtle); }
    .pf-sector-name { font-size: 0.95rem; }
    .pf-sector-pct { text-align: right; font-variant-numeric: tabular-nums; }
    .pf-sector-tickers { grid-column: 1 / -1; font-size: 0.84rem; color: var(--text-muted); overflow-wrap: anywhere; }
    .pf-bar { display: block; width: 100%; height: 6px; }
    .pf-bar-track { fill: var(--bg-surface-highlight); }
    .pf-bar-fill { fill: var(--text-primary); }
    .pf-stats { margin: 0; }
    .pf-stat { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 0.1rem 1rem; padding: 0.7rem 0; border-bottom: 1px solid var(--border-subtle); }
    .pf-stat-label { font-size: 0.95rem; }
    .pf-stat-value { margin: 0; text-align: right; font-size: 1.15rem; font-weight: 600; font-variant-numeric: tabular-nums; }
    .pf-stat-detail { grid-column: 1 / -1; margin: 0; font-size: 0.84rem; color: var(--text-muted); max-width: 38rem; }
    .pf-sectors > li:last-child, .pf-stats > .pf-stat:last-child, .pf-lines > li:last-child { border-bottom: none; }
    .pf-overlap-line { padding: 0.65rem 0; border-bottom: 1px solid var(--border-subtle); font-size: 0.97rem; line-height: 1.45; max-width: 44rem; }
    .wi-form { display: flex; flex-wrap: wrap; gap: 0.75rem 1rem; }
    .wi-picks { display: flex; flex-wrap: wrap; gap: 0.5rem; margin-top: 1rem; }
    .wi-picks .chip { min-height: 36px; padding: 0.3rem 0.85rem; font-size: 0.88rem; }
    .wi-actions { display: flex; flex-wrap: wrap; align-items: center; gap: 0.5rem 1.25rem; margin-top: 1rem; }
    .wi-result { margin-top: 0.5rem; }
    .wi-answer { margin: 0 0 0.6rem; font-size: 1.2rem; line-height: 1.4; max-width: 42rem; }
    .wi-value { font-weight: 600; font-variant-numeric: tabular-nums; }
    .wi-chart { display: block; width: 100%; max-width: 46rem; height: auto; margin-top: 1rem; }
    .wi-grid { stroke: var(--border-subtle); stroke-width: 1; }
    .wi-axis { fill: var(--text-muted); font-size: 11px; font-family: var(--font-sans); }
    .wi-line { fill: none; stroke-width: 2; stroke-linejoin: round; stroke-linecap: round; vector-effect: non-scaling-stroke; }
    .wi-line.wi-line-main { stroke: var(--series-1); }
    .wi-line.wi-line-spy { stroke: var(--series-other); }
    .wi-legend { display: flex; flex-wrap: wrap; gap: 0.25rem 1.25rem; margin: 0.4rem 0 0.25rem; font-size: 0.86rem; color: var(--text-secondary); }
    .wi-key::before { content: ""; display: inline-block; width: 1.1rem; height: 2px; margin-right: 0.45rem; vertical-align: middle; background: var(--series-other); }
    .wi-key.wi-line-main::before { background: var(--series-1); }
    .wi-table-wrap { max-height: 22rem; overflow: auto; margin-top: 0.5rem; max-width: 34rem; border-top: 1px solid var(--border-subtle); border-bottom: 1px solid var(--border-subtle); }
    .wi-table { width: 100%; border-collapse: collapse; font-size: 0.88rem; font-variant-numeric: tabular-nums; }
    .wi-table th, .wi-table td { padding: 0.35rem 0.5rem 0.35rem 0; text-align: right; border-bottom: 1px solid var(--border-subtle); white-space: nowrap; }
    .wi-table th:first-child, .wi-table td:first-child { text-align: left; }
    .wi-table th { position: sticky; top: 0; background: var(--bg-base); font-weight: 600; color: var(--text-secondary); }
    @media (max-width: 640px) {
      .pf-row { grid-template-columns: minmax(0, 1fr) auto; }
      .pf-row-weight { grid-column: 2; grid-row: 2; font-size: 0.84rem; }
      .pf-row > .pf-link { grid-column: 1; grid-row: 2; justify-self: start; }
      .pf-row-main { grid-column: 1; grid-row: 1; }
      .pf-row-value { grid-column: 2; grid-row: 1; }
      .pf-field .pf-input { width: 100%; }
      .pf-field { flex: 1 1 9rem; }
      .pf-preview-row { grid-template-columns: 4rem minmax(0, 1fr); }
      .pf-sector { grid-template-columns: minmax(0, 1fr) 3.5rem; }
      .pf-sector .pf-bar { grid-column: 1 / -1; grid-row: 2; }
    }
"""

PORTFOLIO_BODY = """
      <header class="page-header">
        <h1 class="page-title">Your portfolio</h1>
        <p class="page-standfirst">Put in the stocks you own and see what you’re actually invested in. Your holdings stay in this browser.</p>
      </header>

      <p class="pf-banner" id="pfDemo" hidden>Demo prices, not real. This copy of the site was built from made-up data.</p>
      <p class="pf-banner" id="pfPricesFailed" hidden>Prices couldn’t be loaded just now. Your holdings are still here; try again in a little while.</p>

      <section class="pf-section" aria-labelledby="pfAddHeading">
        <h2 class="settings-heading" id="pfAddHeading">Add a holding</h2>
        <div class="pf-add" id="pfAddRow">
          <input class="pf-input" id="pfTicker" type="text" list="pfTickers" autocomplete="off" autocapitalize="characters" spellcheck="false" maxlength="60" placeholder="Ticker, e.g. NVDA" aria-label="Ticker or company name">
          <datalist id="pfTickers">
            {% for co in watchlist_companies %}<option value="{{ co.symbol }}">{{ co.name }}</option>
            {% endfor %}
          </datalist>
          <div class="pf-seg" role="group" aria-label="Enter shares or dollars">
            <button type="button" data-click="pfSetMode" data-pf-mode="shares" aria-pressed="true">Shares</button>
            <button type="button" data-click="pfSetMode" data-pf-mode="dollars" aria-pressed="false">Dollars</button>
          </div>
          <input class="pf-input" id="pfAmount" type="text" inputmode="decimal" autocomplete="off" maxlength="20" placeholder="Shares, e.g. 10" aria-label="Number of shares">
          <button type="button" class="setup-yes" data-click="pfAddOne">Add</button>
        </div>
        <div class="pf-details" id="pfDetails" hidden>
          <label class="pf-field"><span class="pf-field-label">Bought (month), optional</span><input class="pf-input" id="pfBought" type="month" max="{{ generated_iso[:7] }}"></label>
          <label class="pf-field"><span class="pf-field-label">Paid in total ($), optional</span><input class="pf-input" id="pfPaid" type="text" inputmode="decimal" autocomplete="off" maxlength="20"></label>
        </div>
        <div class="pf-more-ways">
          <button type="button" class="pf-link" data-click="pfToggleDetails" aria-expanded="false" aria-controls="pfDetails">Add when you bought and what you paid</button>
          <button type="button" class="pf-link" data-click="pfTogglePaste" aria-expanded="false" aria-controls="pfPasteBox">Paste a list</button>
          <button type="button" class="pf-link" data-click="pfPickFile">Import a file from your broker</button>
          <input type="file" id="pfFile" accept=".csv,.tsv,.txt,text/csv,text/plain" data-change="pfReadFile" hidden>
        </div>
        <div class="pf-paste" id="pfPasteBox" hidden>
          <textarea class="pf-input" id="pfPasteText" maxlength="20000" spellcheck="false" aria-label="A list of holdings" placeholder="NVDA 10, AAPL 5 shares, VOO $2000"></textarea>
          <p class="pf-note">One holding per line or separated by commas. A plain number is shares; a dollar amount is what it’s worth today. “AAPL 5 @ 150” also records what you paid.</p>
          <button type="button" class="setup-yes" data-click="pfReadPaste">Read the list</button>
        </div>
        <p class="pf-status" id="pfStatus" role="status" aria-live="polite"></p>
        <div class="pf-preview" id="pfPreview" hidden></div>
      </section>

      <p class="pf-note" id="pfEmpty">Nothing here yet. Add what you hold above: a ticker and either how many shares or what it’s worth today. A file exported from your broker works too; it’s read here, in your browser, and isn’t uploaded.</p>

      <section class="pf-section" id="pfHoldings" aria-labelledby="pfHoldingsHeading" hidden>
        <h2 class="settings-heading" id="pfHoldingsHeading">What you hold</h2>
        <ul class="pf-list" id="pfList"></ul>
        <button type="button" class="pf-link" id="pfShowAll" data-click="pfShowAll" hidden>Show all</button>
        <div class="pf-total"><span class="pf-total-label">Total</span><span class="pf-total-value" id="pfTotal"></span></div>
        <p class="pf-note" id="pfTotalNote"></p>
        <p class="pf-note" id="pfDropped" hidden></p>
        <div class="pf-follow" id="pfFollowBox" hidden>
          <button type="button" class="pf-link" id="pfFollow" data-click="pfFollowHeld">Follow these companies</button>
          <span class="pf-note" id="pfFollowNote"></span>
        </div>
      </section>
{{ portfolio_sections }}
      <section class="pf-section pf-foot">
        <p class="pf-note">For information only, not advice. Your holdings are kept in this browser and never sent to us. To price a stock we don’t list, its ticker (not how much you hold) is sent to our own server. <a href="about.html#aboutPrivacy">More on privacy</a></p>
        <button type="button" class="pf-link pf-danger" data-click="pfRemoveAll">Remove everything</button>
      </section>
"""

PORTFOLIO_XRAY = """
      <div id="pfXray" hidden>
        <section class="pf-section" aria-labelledby="pfSectorHeading">
          <h2 class="settings-heading" id="pfSectorHeading">Sectors</h2>
          <p class="pf-lead" id="pfSectorLead"></p>
          <ul class="pf-sectors" id="pfSectors"></ul>
        </section>

        <section class="pf-section" aria-labelledby="pfConcentrationHeading">
          <h2 class="settings-heading" id="pfConcentrationHeading">Where it’s concentrated</h2>
          <p class="pf-lead" id="pfConcentrationLead"></p>
          <dl class="pf-stats" id="pfConcentration"></dl>
          <p class="pf-note" id="pfConcentrationNote"></p>
        </section>

        <section class="pf-section" aria-labelledby="pfOverlapHeading">
          <h2 class="settings-heading" id="pfOverlapHeading">Shared bets</h2>
          <p class="pf-lead" id="pfOverlapLead"></p>
          <ul class="pf-lines" id="pfOverlap"></ul>
          <button type="button" class="pf-link" id="pfOverlapAll" data-click="pfOverlapAll" hidden>Show all</button>
          <p class="pf-note" id="pfOverlapNote"></p>
        </section>

        <section class="pf-section" id="pfFundsSection" aria-labelledby="pfFundsHeading" hidden>
          <h2 class="settings-heading" id="pfFundsHeading">Funds</h2>
          <p class="pf-lead" id="pfFunds"></p>
        </section>

        <section class="pf-section" id="pfGainSection" aria-labelledby="pfGainHeading" hidden>
          <h2 class="settings-heading" id="pfGainHeading">Gain and loss</h2>
          <p class="pf-lead" id="pfGainLead"></p>
          <p class="pf-lead" id="pfGainSpy"></p>
          <ul class="pf-lines" id="pfGainRows"></ul>
          <button type="button" class="pf-link" id="pfGainAll" data-click="pfGainAll" hidden>Show all</button>
          <p class="pf-note" id="pfGainNote"></p>
        </section>
      </div>
"""

PORTFOLIO_WHAT_IF = """
      <section class="pf-section" id="what-if" aria-labelledby="wiHeading">
        <h2 class="settings-heading" id="wiHeading">What if I’d invested…</h2>
        <p class="pf-lead">Put an amount into any US stock or fund at some point in the past and see what it would be worth now, next to the same money in the S&amp;P 500.</p>
        <div class="wi-form" id="wiForm">
          <label class="pf-field"><span class="pf-field-label">Ticker or company</span><input class="pf-input" id="wiTicker" type="text" list="pfTickers" autocomplete="off" autocapitalize="characters" spellcheck="false" maxlength="60" placeholder="e.g. NVDA"></label>
          <label class="pf-field"><span class="pf-field-label">Amount ($)</span><input class="pf-input" id="wiAmount" type="text" inputmode="decimal" autocomplete="off" maxlength="20" value="1000"></label>
          <label class="pf-field"><span class="pf-field-label">Starting at the end of</span><input class="pf-input" id="wiFrom" type="month" data-input="wiClearPicks"></label>
          <label class="pf-field"><span class="pf-field-label">Plus every month ($), optional</span><input class="pf-input" id="wiMonthly" type="text" inputmode="decimal" autocomplete="off" maxlength="20"></label>
        </div>
        <div class="wi-picks" role="group" aria-label="Quick picks for the start">
          <button type="button" class="chip" data-click="wiPick" data-wi-years="1" aria-pressed="false">1 year ago</button>
          <button type="button" class="chip" data-click="wiPick" data-wi-years="3" aria-pressed="false">3 years ago</button>
          <button type="button" class="chip" data-click="wiPick" data-wi-years="5" aria-pressed="false">5 years ago</button>
          <button type="button" class="chip" data-click="wiPick" data-wi-years="10" aria-pressed="false">10 years ago</button>
          <button type="button" class="chip" data-click="wiPick" data-wi-years="first" aria-pressed="false">From its first month</button>
        </div>
        <div class="wi-actions">
          <button type="button" class="setup-yes" data-click="wiRun">Work it out</button>
          <button type="button" class="pf-link" id="wiPortfolio" data-click="wiRunPortfolio" hidden>Or use my whole portfolio</button>
        </div>
        <p class="pf-status" id="wiStatus" role="status" aria-live="polite"></p>
        <div class="wi-result" id="wiResult" hidden></div>
      </section>
"""

# Sections added by later parts of the page (the X-ray, the what-if calculator), in page order.
PORTFOLIO_SECTIONS = PORTFOLIO_XRAY + PORTFOLIO_WHAT_IF


def build_portfolio_template(shared_css: str, navigation_html: str, shared_js: str, theme_boot_js: str) -> str:
    """The whole page as one Jinja template, built from the site's shared pieces."""
    body = PORTFOLIO_BODY.replace("{{ portfolio_sections }}", PORTFOLIO_SECTIONS)
    return (
        """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=5.0">
  <meta name="description" content="Put in the stocks you own and see what you're invested in. Your holdings stay in your browser.">
  <title>StockPulse — Your portfolio</title>
  <link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' rx='8' fill='%231d1d1f'/%3E%3Cpath d='M6 19h6l3-9 3 13 2-4h6' fill='none' stroke='%23ffffff' stroke-width='2'/%3E%3C/svg%3E">
  <script>""" + theme_boot_js + """</script>
  <style>
""" + shared_css + PORTFOLIO_CSS + """
  </style>
</head>
<body class="page-portfolio">
  <div class="app-layout">
    """ + navigation_html + """

    <main class="app-main">
""" + body + """
    </main>
  </div>

  <script>
    """ + shared_js + """
    const PF_DATA = {{ portfolio_json|safe }};
{% raw %}
""" + portfolio_scripts() + """
{% endraw %}
  </script>
</body>
</html>
"""
    )
