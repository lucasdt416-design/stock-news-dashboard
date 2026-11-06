# StockPulse security review

Reviewed 2026-11-03. The repo is public. The site is static, plus one Cloudflare Pages Function and a
daily GitHub Actions pipeline, with no logins or accounts. So the real risks are leaked keys, abuse
of the lookup endpoint, injected content and unsafe deployment settings.

**Branches.** `security/01-hardening` is cut from `main` and merges on its own. `security/02-csp` sits
on top of the redesign stack, because it depends on the new render code.

**What was and wasn't tested.** Everything here ran locally, with mocks for the lookup function and a
real Chrome for the pages, and the Actions YAML was parsed by tests. Nothing has run on real Cloudflare or against the real Finnhub API. See "Not verified".

No secret values appear in this document, in the code, or in the pull requests.

## Summary

| ID | Severity | Finding | Status |
|----|----------|---------|--------|
| 1 | None | No committed secrets found | Nothing to rotate |
| 2 | High | Lookup endpoint open to any site, with no abuse protection | Fixed |
| 3 | Medium | Lookup errors could expose the API key | Fixed |
| 4 | Medium | Every workflow step could read every secret | Fixed |
| 5 | Medium | Deploy ran an unpinned `npx wrangler` holding the Cloudflare token | Fixed |
| 6 | Medium | Third-party actions pinned only to movable tags | Fixed |
| 7 | Medium | `main` has no branch protection | **Owner action** |
| 8 | Low | Workflow granted `id-token: write` it never used | Fixed |
| 9 | Low | Pipeline sends API keys in URLs, and Actions logs are public | **Open, recommended** |
| 10 | Low | No security headers on the site | Fixed (basic here, full CSP in 02) |
| 11 | Low | Lookup accepted any method and any input | Fixed |
| 12 | Low | Upstream text and links passed through unchecked | Fixed |
| 13 | Low | No tests ran on pull requests | Fixed |
| 14 | None | SQL is parameterized | Confirmed, now tested |
| 15 | None | Deployed files are as intended, no debug routes | Confirmed, now tested |
| 16 | None | No known vulnerable dependencies | Confirmed on 2026-11-03 |
| 17 | Medium | Calendar links accepted `javascript:` URLs from data | Fixed in `security/02-csp` |
| 18 | Medium | Stored XSS through `innerHTML` and inline handlers on `main` | Fixed in redesign PR #2, now blocked twice |
| 19 | Low | Weak `startswith('http')` link check | Fixed in `security/02-csp` |
| 20 | Low | Page data could break out of a script block with `<!--<script>` | Fixed in `security/02-csp` |
| 21 | Low | URL parameters and stored data trusted too readily | Fixed in the stack and `security/02-csp` |
| 22 | Low | No script or style restrictions, no integrity check on Chart.js | Fixed in `security/02-csp` |
| 23 | Low | Search crashed on first-run data | Fixed in `security/02-csp` |

## Findings

### 1. Secrets (None)
- **What:** scanned all 96 commits on all refs, including every line ever added, for Google, GitHub,
  AWS, OpenAI and Slack key formats, private keys, and any `key`, `token` or `secret` assignment with a
  long value, including Finnhub, Gemini, FRED and Cloudflare names. Also checked every filename ever
  added for `.env`, `.pem`, `.key`, `.log`, `.db` and backups.
- **Result:** three matches, none real: two function names, and the `your-gemini-api-key` placeholder in
  `README.md`. No sensitive files were ever committed. **Nothing needs rotating because of this scan.**
- **Limit:** this used custom patterns, because `gitleaks` and `trufflehog` were not installed. GitHub
  secret scanning is also on (confirmed through the API).

### 2. Lookup endpoint open to abuse (High)
- **What:** `Access-Control-Allow-Origin: *`, no rate limit, and no server-side cache. Any website or
  script could spend the Finnhub free-tier quota and take live lookup down for real visitors.
- **Where:** `functions/api/lookup.js`.
- **Fix:** CORS only for the site's own origin (optional extras through an `ALLOWED_ORIGINS` setting),
  403 for other origins, a 60-second cache per query (in memory and at the edge), 30 requests a minute
  per visitor, and 15 upstream lookups a minute overall. Over the limit returns 429 with `Retry-After`.
- **Limit:** the limits are per Cloudflare isolate, so they are best effort, and `Origin` can be forged
  by a script outside a browser. The WAF rule under "Owner actions" is the hard limit.

### 3. Lookup errors could expose the key (Medium)
- **What:** errors returned `err.message` to the visitor while the key was in the request URL, so a
  network error containing that URL would have exposed it. Another error named `FINNHUB_API_KEY`.
- **Where:** `functions/api/lookup.js`.
- **Fix:** the key now goes in the `X-Finnhub-Token` header. Errors are fixed generic messages. A bad
  key and a network failure look the same from outside. A missing key is a plain 503.

### 4. Secrets visible to every step (Medium)
- **What:** all secrets, including the Cloudflare token, were job-level environment variables, so
  tests, `pip install` and every third-party action could read them.
- **Where:** `.github/workflows/daily-run.yml`.
- **Fix:** each secret is now only on the step that needs it. Pipeline keys are on the pipeline step.
  The Cloudflare token is on the deploy step, plus one step that only checks whether it is set.

### 5. Unpinned deploy tool (Medium)
- **What:** `npx wrangler` downloaded whatever was newest at deploy time, with the Cloudflare token in
  its environment. A bad release would have run with that token.
- **Fix:** pinned to `wrangler@4.151.2`, chosen because it had been public for two weeks. Node goes from
  20 to 22 because current wrangler declares `node >=22`.
- **Check on first deploy:** this is the one change I could not run. See "Not verified".

### 6. Actions pinned to movable tags (Medium)
- **What:** `@v4` tags can be moved to new code by whoever controls the action.
- **Fix:** every action is pinned to a full commit SHA, with the version in a comment. A new
  `.github/dependabot.yml` proposes updates, so the pins do not go stale.

### 7. `main` is unprotected (Medium)
- **What:** the API reports "Branch not protected", so a compromised account or a mistaken push goes
  straight to production, because a push to `main` deploys.
- **Fix:** repository setting, see "Owner actions".

### 8. Unused OIDC permission (Low)
- **What:** `id-token: write` was granted, though nothing uses it.
- **Fix:** removed. Both workflows now default to `permissions: {}`, and each job states what it needs.
  `actions/checkout` no longer leaves the token on disk (`persist-credentials: false`).

### 9. API keys in pipeline URLs (Low, open)
- **What:** these place keys in query strings, and logs from a public repo are public:
  `collectors/earnings_calendar.py:65`, `collectors/finnhub_news.py:44`, `pipeline/lookup.py:85,104,137`,
  `pipeline/economic.py:337` (FRED). Gemini no longer: since the Gemini fix, `pipeline/summarize.py` and
  `pipeline/economic.py` send the key only in the `x-goog-api-key` header.
- **Risk:** I found no line that logs these URLs, and normal `urllib` HTTP and network errors do not
  include them. Other exceptions can: `collectors/earnings_calendar.py:65` does not encode `symbol`, and
  an invalid URL error quotes the URL, which that file logs. Today the symbols come from your own
  watchlist. GitHub also masks registered secrets in logs. So the risk is small, not zero.
- **Why open:** the brief excludes collector and pipeline logic changes.
- **Recommended fix:** use `X-Finnhub-Token` for Finnhub and `x-goog-api-key` for Gemini. FRED only
  accepts the key in the URL, so log around it. Encode `symbol`.

### 10. Security headers (Low)
- **What:** no headers were set. The site could be framed by another page, and browsers could sniff
  content types.
- **Fix:** `deploy/_headers` is copied into `site/` at deploy time, with `nosniff`, `X-Frame-Options`,
  `Referrer-Policy`, `Permissions-Policy` and a CSP covering framing, `base-uri`, `object-src` and
  `form-action`. It leaves out `script-src` because `main` still relies on inline handlers.
  `security/02-csp` writes the full policy instead.

### 11. Lookup method and input checks (Low)
- **What:** any method was processed, and any string was forwarded upstream.
- **Fix:** GET and OPTIONS only (others get 405). Input must match an allow-list: a ticker of up to 10
  characters, or a company name of up to 60 with letters, digits, spaces and `. , & ' -`. Anything else
  gets 400 before any upstream call. Upstream parameters are URL-encoded. Company-name search still
  works through `?ticker=`, because the current page sends names that way.

### 12. Upstream content (Low)
- **What:** Finnhub text and links were forwarded as received.
- **Fix:** only `http` and `https` links are passed on, text is length-limited with control characters
  removed, and search results with odd-looking symbols are ignored. The page still escapes everything.

### 13. No tests on pull requests (Low)
- **Fix:** new `.github/workflows/ci.yml` runs Python and lookup tests on Python 3.11 and Node 22 for
  pull requests, with no secrets and read-only access. It uses `pull_request`, never
  `pull_request_target`, so fork code cannot reach secrets. This also gives branch protection a required
  check to point at.

### 14. SQL (None)
Every statement is parameterized. The three that use string building only add literals: `select_cols`
in `pipeline/persist.py:366,446`, and `query` plus `conditions`, whose values are bound separately.
`tests/test_security_hardening.py` now fails if data is ever interpolated, and stores a hostile
`'); DROP TABLE` string to confirm that it comes back as plain text.

### 15. Deployment exposure (None)
`site/` holds only the rendered pages, and `.db`, `.env`, source maps, logs and backups are not there.
`functions/` has only `api/lookup.js`, with no debug routes. Both are now tested. `.gitignore` also now
covers `*.log`, `*.bak`, `*.map` and `.env.*`.

### 16. Dependencies (None)
`pip-audit` on `requirements.txt`: no known vulnerabilities on 2026-11-03. Runtime dependencies were
already pinned, and `pytest` is now pinned in workflows. `requirements.txt` also lists `flake8` and its
helpers, which the pipeline does not need at run time; harmless, but they could move out.

### 17. `javascript:` links on the calendar (Medium)
- **What:** `{{ ev.source_url }}` went into an `href` unchecked, so a `javascript:` value in the data
  would run when clicked. Present on `main` and in the redesign stack.
- **Where:** the calendar template in `pipeline/render.py`.
- **Fix:** every template link now goes through `_safe_url`, which allows only absolute `http(s)` URLs.
  A test fails if any template adds an unchecked `href`.

### 18. Stored XSS on `main` (Medium)
- **What:** headlines and other scraped text reached `innerHTML` and inline `onclick` handlers.
- **Fix:** escaped in redesign PR #2. The CSP now blocks injected scripts as a second layer.
- **Until the stack merges, `main` is still exposed to this.**

### 19. Weak link check (Low)
`startswith('http')` also accepted `httpx://` and `http-evil:`. Replaced by `_safe_url` (finding 17).

### 20. Script block breakout (Low)
`_script_json` escaped `</` but not `<!--<script>`, which can stop a script block from closing and break
the page. Now escaped, along with U+2028 and U+2029.

### 21. URL parameters and localStorage (Low)
- `company.html?ticker=` must match a strict pattern and an existing watchlist profile. Anything else is
  treated as a ticker we don't cover.
- `news.html?ticker=` only filters by a company in the picker. `?q=` only fills an input's value.
- Recently viewed entries are checked against the watchlist before use (redesign PR #4).
- Every external link has `rel="noopener noreferrer"`, tested in the rendered pages and the browser.
- Nothing sensitive is in URLs or storage: `localStorage` holds only the theme and recently viewed tickers.

### 22. Content-Security-Policy and integrity (Low)
- **Handlers:** all 47 inline handlers replaced by one delegated listener and a fixed allow-list of actions.
- **Styles:** all 56 `style=` attributes replaced by classes, or by data attributes applied through the
  stylesheet API. No `'unsafe-inline'` is used anywhere.
- **Hashes:** `pipeline/render.py` hashes each page's inline script and style blocks at render time and
  writes `site/_headers`, one policy per page. `default-src 'none'`, and only the two chart pages may load
  from the CDN.
- **Chart.js:** has Subresource Integrity and `crossorigin="anonymous"`.
- **Fonts:** the site uses each device's own font and downloads none, so no font is requested from Google or anyone else.
- **Dependency pins:** `requirements-dev.txt` now pins `pytest` and `playwright`.

### 23. Search crash on first-run data (Low)
`relevant_tickers` can be a list when indicators are freshly seeded, which threw an error on every search.
Not a security issue, found by the hostile-data run.

### How the frontend was tested
`scripts/check_security.py` builds a database of hostile text and URLs (`<img onerror>`, `"><script>`,
`</script>`, `<!--<script>`, `javascript:` in mixed case, `data:`, 20,000-character strings, control
characters), loads every page in Chrome under the generated headers, attacks search, a mocked hostile
lookup answer, URL parameters and `localStorage`, and fails on any executed script, CSP violation, unsafe
link or inline handler. Result: 0 problems. To confirm the check can fail, I disabled `_safe_url` once and
it reported 97 problems. `scripts/capture_site.py` also serves `_headers` locally, so every capture ran
under the real policy: 7 pages at 3 widths in both themes, 0 problems.

## Not verified
- **The CSP on real Cloudflare.** Tested with a local server that applies `_headers`. Anything that rewrites
  HTML at the edge would break the hashes. See owner action 10.
- **Deploy with `wrangler@4.151.2` on Node 22.** Not run. Watch the first deploy after merging. If it
  fails, the workflow's `WRANGLER` setting is the one line to change.
- **The edge cache on real Cloudflare.** Tested against a stand-in. Cloudflare's Cache API may not work on
  every hostname, so an in-memory cache is there as well.
- **CI on Python 3.11.** Local runs used 3.9.6. The first run of `ci.yml` on this pull request will be
  the first real check.

## Owner actions

Only you can do these, in GitHub or Cloudflare settings.

**GitHub**
1. **Protect `main`** (Settings, Branches): require a pull request and the `Tests` check. Currently off.
   Do this after `ci.yml` has run once, because the check only becomes selectable then.
2. **Turn on Dependabot alerts and security updates** (Settings, Code security). Security updates are
   currently off; I could not confirm the state of alerts.
3. **Secret scanning and push protection:** already on, confirmed through the API. Nothing to do.
4. **Enable 2FA** on your GitHub account, if it isn't already. I can't check this.
5. **Require approval for fork pull request workflows** (Settings, Actions, General): "Require approval
   for all outside collaborators".

**Cloudflare**
6. **Scope the API token** to Cloudflare Pages: Edit on this account only, with an expiry date.
7. **Add a rate-limiting rule** (Security, WAF) for `/api/lookup`, for example 30 requests a minute per
   IP. This is the hard limit behind finding 2. It requires a custom domain on the zone; a `pages.dev`
   address alone can't have one.
8. **Enable 2FA** on your Cloudflare account, if it isn't already.
9. **If the site uses more than one hostname** and lookups are called across them, set `ALLOWED_ORIGINS`
   as a comma-separated list. Same-origin use needs nothing.

10. **Keep Cloudflare from rewriting pages.** Leave Rocket Loader, Email Address Obfuscation, and automatic
    Web Analytics injection off for this site. They inject or change scripts, which the strict CSP will
    block. After the first deploy with `security/02-csp`, open the browser console on Home and check for
    "Content-Security-Policy" errors.

**Keys**
11. **Nothing needs rotating** based on this review. Rotate if you ever pasted a key somewhere else.
