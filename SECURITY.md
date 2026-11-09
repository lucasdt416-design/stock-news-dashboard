# Security

StockPulse is a static site with one small serverless function (the ticker lookup) and a daily
GitHub Actions job. It has no accounts and stores nothing about visitors, so the things that matter
most are leaked keys, abuse of the lookup, content that could inject script into a page, and the
deployment itself. The review in [docs/security-review.md](docs/security-review.md) covers each.

## Reporting a problem

Please report security problems privately, not in a public issue:
**[Report a vulnerability](https://github.com/lucasdt416-design/stock-news-dashboard/security/advisories/new)**
(the Security tab of this repository).

Include what you found, where (page, file or URL), and how to reproduce it. You'll get a reply
within a week. Once it's fixed, you'll be credited in the fix unless you'd rather not be.

## What's in scope

- The live site at https://stock-news-dashboard.pages.dev and its lookup endpoint (`/api/lookup`).
- The code in this repository, including the GitHub Actions workflows.

Out of scope: problems in the data providers themselves (SEC, Finnhub, Yahoo Finance, FRED), and
reports that need someone to already control your computer or browser.

## Please don't

Run load tests or scanners against the live site, or use the lookup endpoint to pull large amounts
of data. It runs on free plans and is rate-limited.
