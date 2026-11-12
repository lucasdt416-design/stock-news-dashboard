# Your portfolio: plan

**Status: approved 2026-11-11; being built in the pull requests listed below.** Written 2026-11-11 against `main` at `776c1af`, after reading the
files the task names. Things I checked are marked "checked"; things I could not check are in
"Not verified".

## What I found that changes the task

1. **The watchlist's theme tags are thin.** Only 30 of the 100 companies have any
   `macro_sensitivities`, and of the 95 different tags only 6 are shared by two or more companies
   (`datacenter_capex` covers NVDA, AMD and INTC; five others cover two each). Only 11 companies list
   `key_customers` and 21 list `key_suppliers`. Every company has `competitors`, and 30 have
   `economic_sensitivities` (inflation 21, interest rates 15, unemployment 11, 10-year yield 5, oil 5).
   So "45% of your portfolio is tied to datacenter capex (NVDA, AVGO, MSFT)" can't be said today:
   AVGO and MSFT don't carry that tag. See "Hidden overlap" for what v1 can honestly show.
2. **Prices are not stored anywhere today.** `collect_comparative_performance` is called at render
   time and its result is passed straight to the templates. Nothing about prices is in SQLite, so a
   failed fetch today means no chart. The long history needs a new table to meet "keep the last real
   reading".
3. **Yahoo's monthly history is usable** (checked from this machine for NVDA, SPY, VOO, BRK-B and a
   made-up ticker). `range=max&interval=1mo` returns one point per month from the first month of
   trading, with `adjclose`, plus `meta.instrumentType` (`EQUITY`, `ETF`, `MUTUALFUND`),
   `meta.firstTradeDate`, `meta.longName`, `meta.currency` and the latest price with its time. A
   ticker that doesn't exist returns 404 "symbol may be delisted". The last point is the month in
   progress, not a month-end.
4. **Adjusted prices are rewritten after every dividend.** Yahoo rescales the whole past series each
   time a dividend is paid. Stored history must be replaced whole on each good fetch, never merged
   with older rows, or the series would mix two scales.
5. **The fund flag comes free.** `instrumentType` tells stocks from funds without Finnhub, so the
   "Funds" group works with no key.
6. **The design is blue, not amber.** `SHARED_CSS` uses neutral greys, one blue (`--accent`), the
   device's own font, no shadows, light by default. The plan follows the stylesheet, not the older
   wording in `docs/redesign-plan.md`.
7. **One test already fails on `main`** on this machine:
   `tests/test_calendar.py::test_build_forthcoming_calendar_integration` (expects two events, gets
   one; it looks date-dependent). It is not touched by this work. I'll report it in each PR rather
   than change it.

## The page

`portfolio.html`, rendered by `pipeline/render.py` from a new `PORTFOLIO_TEMPLATE`, title "Your
portfolio". One page, two parts, each with its own heading and anchor.

**Part 1, Your holdings** (top to bottom):

- Empty state: one sentence saying what the page does and that holdings stay in this browser, the
  add row, and "Paste a list" and "Import a file" as text buttons. No illustration.
- Add row: ticker field, a shares/dollars switch, the number, and optional "Bought" (month) and
  "Paid" (total dollars) behind "Add details".
- Preview (after paste or import): a table of what was read, with unreadable lines listed underneath
  in full and a count ("3 lines couldn't be read"). Nothing is saved until "Add these".
- Holdings: hairline rows, largest first. Ticker and name (linked to the company page when it has
  one), shares, price with its date, value, share of total, gain/loss if a cost was given. Five rows,
  then "Show all". Each row can be edited or removed.
- Total value, with the oldest price date used if they differ.
- X-ray, as four short sections: Sectors, Where it's concentrated, Shared bets, Funds.
- Gain/loss against the S&P 500, only when there is something to compare.
- "Follow these companies" and "Remove everything".
- One quiet line: "For information only, not advice. Holdings are kept in this browser."

**Part 2, What if** (`#what-if`): the calculator, its result sentence, a line chart and the SPY
comparison. A query string opens the page scrolled here with the fields filled in.

**Navigation.** Sidebar: "Portfolio" second, after Home. Home: one text link under the search bar.
The phone tab bar has five slots (Home, Moves, Companies, Feed, Calendar) and six won't fit at
390 px. **Proposal:** Portfolio takes Calendar's slot, and Calendar stays in the drawer. This is
your call; see "Decisions".

**Charts.** Sector bars and the what-if line are drawn as inline SVG built with DOM calls. No
Chart.js on this page, so it loads nothing from jsDelivr, and there are no `style=` attributes (the
CSP forbids them). Colours come from the existing `--series-*` and `--accent` tokens.

## Data

### Static files for watchlist companies and SPY

`site/data/prices/<SYMBOL>.json`, one per watchlist company plus `SPY.json`, written at render time
from the database:

```json
{
  "symbol": "NVDA",
  "name": "NVIDIA Corporation",
  "kind": "stock",
  "currency": "USD",
  "first_month": "1999-01",
  "months": [["1999-01", 0.041804], ["1999-02", 0.0457], "..."],
  "price": {"value": 173.94, "date": "2026-11-10"},
  "fetched": "2026-11-11"
}
```

- `months` holds **finished months only**: the adjusted close at the end of each month, six
  significant figures. The month in progress is left out, so a part-month is never shown as a
  month-end. A month Yahoo has no value for is simply absent; nothing is filled in.
- `price` is the latest real close and its date. The daily job runs at 11:00 UTC, before the US
  market opens, so this is the previous session's close.
- `kind` is `stock` or `fund`, from `instrumentType`.
- Size: about 6 KB for NVDA (334 months). About 600 KB for all 101 files, fetched one at a time and
  only for tickers the visitor holds or asks about.
- `site/data/prices/index.json` lists the symbols with a file, their `kind` and `price`, so the page
  values a portfolio of watchlist names with one request.

**Collection.** `collectors/stock_prices.py` gets one new function,
`fetch_ticker_monthly_history(symbol)`, built on the same request code as
`fetch_ticker_historical_closes` (the URL building and headers move into one shared helper so there
is one copy). `collect_price_history(watchlist_path)` loops over the watchlist and SPY with the same
pause between calls. That is 101 more Yahoo requests a day on top of today's roughly 200.

**Storage.** New table in `pipeline/db.py`:

```sql
CREATE TABLE IF NOT EXISTS price_history (
  symbol TEXT PRIMARY KEY,
  name TEXT, kind TEXT, currency TEXT,
  months_json TEXT NOT NULL,      -- [["1999-01", 0.041804], ...]
  price REAL, price_date TEXT,
  fetched_at TEXT NOT NULL
);
```

A good fetch replaces the row. A failed or odd-looking fetch (no points, a non-positive value, months
out of order, a currency other than USD) leaves the old row alone and logs a warning, so the file
keeps the last real series with its `fetched` date. The table rides in `data/dashboard.db`, which the
Actions cache already carries.

**Staleness on the page.** Every price shows its date. If `price.date` is more than four days old,
the row says "price from 3 Nov" in the muted colour and the total says which holdings are old.

### The function for other tickers: `functions/api/history.js`

A new file, not an extension of `lookup.js`: it has a different upstream, cache time and limits, and
`lookup.js` stays untouched. The shared hardening code (origin check, visitor limit, cache helpers,
`json()`) moves to `functions/_shared/guard.js`, which both import. Files under `functions/` whose
names start with `_` are not routed by Pages. **If you'd rather not touch `lookup.js` at all, I'll
copy the helpers instead and have a test assert the two copies match.**

`GET /api/history?ticker=VOO`

- Same checks as lookup, in the same order: cross-site refusal, GET and OPTIONS only, visitor limit
  (30 a minute), `TICKER_PATTERN` only (no company names here), cache, upstream limit (30 a minute),
  8-second timeout, fixed error messages with no upstream URL.
- Upstream 1: Yahoo `chart/<ticker>?range=max&interval=1mo`. No key.
- Upstream 2, only when `FINNHUB_API_KEY` is set and the ticker is a stock: Finnhub
  `stock/profile2` for `finnhubIndustry`. It shares Finnhub's 60 calls a minute with lookup, so it
  has its own cap of 10 a minute and a 7-day cache; when it is skipped or fails, the answer simply
  has `"sector": null`.
- Answer: the same shape as the static files, plus `"sector"` (one of the site's sector names or
  `null`) and `"industry"` (Finnhub's own word, for display).
- Cache: 6 hours at the edge and in memory for a found ticker, 1 hour for "not found".
- Nothing is logged. The function has no `console.log`, and a test asserts that.
- Failure: `{found:false, error:"..."}` with 404, 429, 502 or 503. The page then shows "Couldn't get
  prices for VOO right now" and no number or chart for that ticker.

Node tests in `tests/node/history.test.mjs`, mirroring `lookup.test.mjs`: origin, method, input,
limits, cache hit, no leak of key or upstream host in any error, works with no key, part-month
dropped, non-USD refused, fund flagged, industry mapped, unknown industry left `null`.

### Sector for tickers outside the watchlist

Finnhub's `finnhubIndustry` words map to the site's sector names through one table in `history.js`
(mirrored in a Python test so the names can't drift from `SECTOR_METADATA`):

| Finnhub industry | Site sector |
|---|---|
| Semiconductors, Technology, Electrical Equipment (tech hardware names only: see note) | Technology |
| Banking, Financial Services, Insurance | Finance |
| Pharmaceuticals, Biotechnology, Health Care, Life Sciences Tools & Services | Healthcare |
| Energy | Energy |
| Machinery, Industrial Conglomerates, Building, Construction, Road & Rail, Airlines, Marine, Logistics & Transportation, Commercial Services & Supplies, Professional Services, Trading Companies & Distributors, Transportation Infrastructure | Industrials |
| Aerospace & Defense | Aerospace |
| Retail, Distributors | Retail |
| Beverages, Food Products, Tobacco, Consumer products | Consumer Staples |
| Telecommunication, Communications | Telecom |
| Utilities | Utilities |
| Chemicals, Metals & Mining, Packaging, Paper & Forest | Materials |
| Real Estate | Real Estate |
| Automobiles, Auto Components, Textiles, Apparel & Luxury Goods, Leisure Products, Hotels, Restaurants & Leisure, Diversified Consumer Services | Consumer Goods |
| Media | Sector unknown. Finnhub uses it for Meta and Alphabet (Technology here) as well as Disney and Netflix (Consumer Staples here), so it can't be mapped without guessing. |
| anything else, or "N/A" | Sector unknown |

Note: I wrote this list from memory of Finnhub's values and have no key on this machine. In PR (b)
I'll check it against real `profile2` answers for about 40 tickers and correct it. "Electrical
Equipment" goes to Industrials unless that check says otherwise. Anything not in the table shows
"Sector unknown" with a "Set sector" control; a sector set by hand is stored with the holding and
marked "set by you".

## Storage in the browser

Key `stockpulse_portfolio`:

```json
{"v": 1, "holdings": [
  {"t": "NVDA", "sh": 10, "paid": 1200, "bought": "2023-05", "sector": null, "usd": null, "at": null}
]}
```

- `sh` shares; `paid` total dollars paid or `null`; `bought` a month or `null`; `sector` only when
  set by hand; `usd` and `at` hold a dollar entry that couldn't be turned into shares yet.
- Read with the `FOLLOW_KEY` pattern: `try/catch`, then validate every field (ticker matches the
  pattern, numbers finite and positive and below 1e12, month looks like a month, sector is a known
  name). Bad rows are dropped on read and counted in a visible note. At most 200 holdings; one ticker
  appears once (adding it again adds the shares and keeps the earlier details, after asking).
- Key `stockpulse_prices`: cached answers from `/api/history`, at most 40 tickers, each with the time
  it was fetched; reused for 6 hours (history) and 7 days (sector). Watchlist tickers are never
  cached here because their files are static.
- "Remove everything" clears both keys after a confirm.
- `tests/test_about.py` lists the allowed keys and the words the About page must use; both get the
  two new keys and "the stocks you hold".
- Holdings never go into the setup link or `stockpulse_reading`. A browser check in
  `scripts/check_following.py` adds holdings, builds a setup link and asserts no ticker from the
  portfolio that isn't followed appears in it.

**What leaves the browser.** For a watchlist ticker: nothing but the request for a static file,
which Cloudflare sees like any page. For any other ticker: one request to `/api/history` with that
ticker, once per 6 hours. Shares, dollars, dates and costs are never sent. The page and About say:
"To price a stock we don't list, the ticker (not how much you hold) is sent to our own server, which
asks Yahoo Finance and, for its sector, Finnhub."

## Reading what people type

**Ticker normalising.** Upper case, trimmed, `$` dropped, `BRK.B` and `BRK/B` become `BRK-B`. Then
it must match `TICKER_PATTERN`.

**Same company, other ticker.** The watchlist has GOOGL but not GOOG. A new optional field on a
watchlist entry, `other_tickers: [GOOG]`, lets the page price GOOG as itself but give it GOOGL's
sector, links and overlap data, and count the two as one company in the concentration numbers. Only
GOOGL needs it today.

**Paste box.** Split on newlines, commas and semicolons. In each piece, find one ticker and one
number:

| Text | Read as |
|---|---|
| `NVDA 10`, `10 NVDA`, `NVDA 10 shares`, `NVDA x10` | 10 shares |
| `VOO $2000`, `VOO 2,000 USD`, `$2k VOO` | $2,000 at today's price |
| `AAPL 5 @ 150` | 5 shares, paid $750 |
| `NVDA`, `10`, `NVDA 10 20` | not read; shown in the preview with the reason |

A bare number is shares. A piece with two tickers or no number is not guessed at.

**CSV.** Parsed in the browser (quoted fields, commas inside quotes, a byte-order mark, CRLF). The
header row is found by looking in the first 15 lines for a ticker column; names are matched without
case or punctuation:

- ticker: Symbol, Ticker, Instrument, Security
- shares: Quantity, Qty, Shares, Units
- paid: Cost Basis, Cost Basis Total, Total Cost, Book Cost
- per-share cost (multiplied by shares): Average Cost, Avg Price, Cost Per Share, Purchase Price
- value (only if there is no shares column): Market Value, Current Value, Value

Rows without a usable ticker (cash, totals, footers, options with long symbols) are listed as not
read. Files over 1 MB or 2,000 lines are refused with a message. The file is read with `FileReader`
and never uploaded.

**Dollar entries.** A dollar amount means what the holding is worth today. It becomes shares once,
at the latest real close: `shares = dollars / price.value`, and the row says "about 3.6 shares at
the 10 Nov close". With no price yet, the row is kept as dollars (`usd`, `at`), counts toward the
total at that amount, is marked "not priced", and is converted the first time a price arrives.

## Calculations

All in one plain script block of pure functions (`PortfolioMath`), tested from Node against
hand-worked numbers by loading the same source the page uses.

**Value and weights.** `value_i = shares_i × price_i`; `total = Σ value_i`;
`w_i = value_i / total`. Holdings with no price are left out of weights and named.

**Sectors.** `sector_weight_s = Σ w_i` over holdings in sector `s`. Funds form their own bar, "Funds
(contents not broken out)". Unknown sectors form "Sector unknown".

**Concentration**, over individual stocks only, with weights rescaled to stocks
(`u_i = value_i / Σ stock values`), one entry per company (GOOG and GOOGL added together):

- largest holding: `max u_i`
- top three: sum of the three largest `u_i`
- largest sector: `max` sector weight among stocks
- effective number: `N = 1 / Σ u_i²`, shown to one decimal below 10 and whole above

  Hand check: weights 50%, 30%, 20% give `1 / (0.25 + 0.09 + 0.04) = 2.63`: "Your 3 stocks behave
  like about 2.6 equal-sized ones." Four equal holdings give exactly 4.

Beside them: "Funds are 40% of your portfolio and aren't counted here." All funds: the numbers are
replaced by "Everything here is a fund, so there's nothing to measure stock by stock."

**Gain and loss.** With `paid`: `gain = value − paid`, `gain% = gain / paid`. Overall: the same over
holdings that have `paid`, with a note of how many don't. With `paid` and `bought`: SPY's adjusted
close at the end of the last finished month on or before the purchase month, `S0`, and SPY's latest,
`S1`, give `same money in the S&P 500 = paid × S1 / S0`. Without `bought`, no SPY line. The SPY
figure includes dividends and the holding's own gain doesn't (it's price against cost), so the line
says so: "S&P 500 figure includes dividends; yours doesn't."

**What if, one lump.** Let `m0` be the last finished month on or before the chosen date, `A0` the
adjusted close for `m0`, and `A1` the latest price.

- `value = amount × A1 / A0`
- `total return = A1 / A0 − 1`
- `years = (date of A1 − last day of m0) / 365.25`
- `a year = (A1 / A0)^(1 / years) − 1`, shown only when `years ≥ 1`

The page states the date used: "From the end of October 2021". Quick picks count back whole months
from today. "At IPO" uses `first_month`. A start before `first_month` gives: "NVDA started trading
in January 1999. Use that?"

**What if, with a monthly amount.** A contribution `c` is bought at each finished month-end after
`m0`, up to the last finished month:

- `shares = amount / A0 + Σ c / A_m`
- `value = shares × A1`
- `put in = amount + c × (number of contributions)`
- `gain = value − put in`, `gain% = gain / put in`
- "a year" is the money-weighted rate: the monthly rate `r` that makes
  `amount × (1+r)^n + Σ c × (1+r)^(n−k) = value`, found by bisection, shown as `(1+r)^12 − 1`.

  Hand check: $1,000 at 100, then $100 a month at 110 and 121, latest 121: shares
  `10 + 0.9091 + 0.8264 = 11.7355`, value `$1,420.00`, put in `$1,200`, gain `18.3%`.

**Same money in SPY.** The same amounts on the same months, bought at SPY's adjusted closes.

**Chart.** One point per finished month, `shares_so_far × A_m`, plus the latest price as the last
point. Two lines: the ticker and SPY. A table of the same numbers sits behind "Show the numbers".

**Whole portfolio.** The amount is split by today's weights `w_i`; each part runs as a lump from
`m0`. A holding whose `first_month` is after `m0` is left out and named, and the others' weights are
rescaled to add to 100%. If any holding's history can't be loaded, the result isn't shown; the page
names the missing tickers and offers "Run it without them". The line under it: "Uses today's mix.
You may have held something different then." Not shareable by link.

**Link.** `?t=NVDA&a=1000&from=2020-11&m=100`. `t` must match the ticker pattern, `a` and `m` are
numbers within limits, `from` a month. Anything else is ignored. The link is written with
`history.replaceState` when a single-ticker result is shown, never for the portfolio run.

**The one line.** "Uses prices adjusted for splits and dividends, so it assumes dividends were
reinvested. Ignores taxes and fees. Monthly prices, so dates are to the month."

## Hidden overlap, with the data as it is

Each line is a count or a percentage the watchlist states, with the holdings named:

1. **Shared themes** (`themes`, a fixed list of 27 added after launch; the free-text
   `macro_sensitivities` are no longer used here): shown when two or more holdings carry the same tag.
   "38% of your portfolio is exposed to datacenter spending (NVDA, AMD)."
2. **Shared economy links** (`economic_sensitivities`): "5 of your holdings, 44% of your portfolio,
   are marked as sensitive to interest rates (…)". These link to the Economy page.
3. **Customer and supplier ties inside the portfolio:** "You hold NVDA and three of its key
   customers (MSFT, META, AMZN)", and "2 of your holdings count Microsoft as a key customer."
4. **Head-to-head competitors:** "NVDA, AMD and INTC list each other as competitors: 41% of your
   portfolio."

Rule for every percentage: the summed weights of the holdings named, each counted once in that line.
Lines are never added together. Top five lines by weight, then "Show all". Under them: "This covers
the 100 companies StockPulse follows. 3 of your holdings (22%) aren't among them, and not every
company has these details yet."

**What this means for the pitch.** For a tech-heavy portfolio it will say useful things. For many
others, section 1 will be empty and the page will say so rather than invent a link. Making it rich
needs more tags in `data/watchlist.yaml`, fact-checked like PR #34. That is a separate piece of work
and I have not planned it here.

## Edge cases

| Case | What happens |
|---|---|
| No holdings | Empty state; the what-if calculator still works |
| Ticker doesn't exist or is delisted | "We couldn't find ZZZZ." The row can be kept (unpriced, left out of the numbers) or removed |
| Splits | Shares are what the visitor holds today; history uses adjusted prices, so splits are already in it. A buy price typed from before a split will look wrong, and the "Paid" field asks for the total paid to avoid that |
| Fund | "Funds" group; valued and charted, not looked through, left out of concentration and overlap |
| Shares and dollars mixed | Dollars become shares at the latest close (above) |
| Paid but no buy date | Gain shown, no SPY comparison |
| Buy date before the first month | Treated as no buy date, with a note |
| Holding younger than the what-if start | Left out, named, weights rescaled |
| Watchlist company under another ticker | `other_tickers` (GOOG and GOOGL) |
| BRK.B, BRK/B | Become BRK-B |
| Non-USD or foreign listing | Refused: "StockPulse only prices US-listed stocks in dollars" |
| Only funds | Concentration replaced by one sentence |
| Old price | Dated and marked; total names the old ones |
| Storage blocked or full | Works for this visit, says it couldn't save |
| Hostile text in paste, CSV or the link | Everything goes in through `textContent`; `scripts/check_security.py` gets portfolio cases |
| Month missing in Yahoo's series | Not filled in; the nearest earlier real month is used and its name shown |
| Negative or zero shares, huge numbers | Rejected in the preview with the reason |

## Pull requests

Each one: both test suites, `build_demo.py`, `check_following.py`, `capture_site.py` at 1440, 768
and 390 in light and dark, how it was checked in the description. None merged by me.

| PR | Branch | What |
|---|---|---|
| 0 | `feature/portfolio-plan` | This file |
| a | `feature/portfolio-prices` | `fetch_ticker_monthly_history`, `price_history` table, `site/data/prices/*.json`, keep-last-reading behaviour, tests with saved responses, demo prices |
| b | `feature/portfolio-history-api` | `functions/api/history.js`, shared guard, node tests, sector table checked against real Finnhub answers, `docs/security-review.md` |
| c | `feature/portfolio-holdings` | The page, add row, paste, CSV, preview, storage, "Remove everything", About and its test |
| d | `feature/portfolio-xray` | `PortfolioMath`, weights, sectors, concentration, overlap, funds, gain and loss |
| e | `feature/portfolio-what-if` | Calculator, chart, portfolio run, link; hand checks for NVDA and AAPL over 5 years in the description |
| f | `feature/portfolio-nav` | Sidebar, phone tab bar, Home link, "Follow these companies", README |

The page is not linked from anywhere until (f), so (c) to (e) can merge without showing a
half-built page.

**Demo.** `build_demo.py` writes seeded random-walk monthly prices for the watchlist and SPY, each
file carrying `"demo": true`, and the page then shows "Demo prices, not real" at the top. The demo
portfolio uses watchlist tickers only, so the capture makes no `/api/history` call; one extra
capture step adds an outside ticker with the function answered by a canned response, as the lookup
capture already does.

## Not verified

- **Yahoo answering a Cloudflare function.** I can only test from this machine. The first real test
  is a deploy. Until that passes, the calculator and the page work for watchlist tickers and SPY
  from the static files, and any other ticker gets the plain failure message. If Yahoo does refuse
  Cloudflare, I know of no free source of dividend-adjusted history that needs no key, so v1 would
  stay watchlist-only for history, and other tickers could still be valued today through the
  existing Finnhub lookup.
- **Finnhub's industry words.** From memory; checked in PR (b).
- **Yahoo's terms.** The site already shows Yahoo prices. This adds 27 years of monthly values per
  ticker as downloadable files. That is your call to make, not mine.

## Decisions

The owner said to go with the suggestions, so:

1. **Phone tab bar:** Portfolio takes Calendar's slot; Calendar stays in the drawer.
2. **Hidden overlap:** ships with today's data and an honest coverage line.
3. **`lookup.js`:** the hardening code is shared through `functions/_shared/guard.js`.
4. **Other tickers:** the history function is built now, and Yahoo-from-Cloudflare is found out on
   the first deploy. Until then other tickers fail with a plain message.
