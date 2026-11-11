# Contributing

Thanks for helping. The most useful contributions are often the smallest: a number that looks
wrong, a company that's missing, or a page that's confusing.

## Reporting

- **Wrong or out-of-date data:** use the "Wrong number or data" issue form. Say where you saw it and
  link the source that shows the right value.
- **Bugs and ideas:** use the matching issue form.
- **Security problems:** report privately, as in [SECURITY.md](SECURITY.md).

## Changing the code

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
# The browser checks use your installed Google Chrome, through Playwright.

pytest                                  # all tests
node --test tests/node/*.test.mjs       # the site's functions and the portfolio page's scripts
python scripts/build_demo.py            # a demo site in .capture/site, no network or keys
python scripts/check_following.py       # walks through the site in a real browser
python scripts/check_portfolio.py       # the same for Your portfolio, and checks what it sends
python scripts/capture_site.py          # screenshots every page, light and dark, and flags layout problems
```

The project has a few rules, and pull requests are checked against them:

- **Real data only.** Every figure is read from its source. If a source can't be read, show the
  last real reading with its date, or nothing. Never a made-up or placeholder number.
- **No new paid services and no new required secrets.** Everything must run on free plans, and the
  site must still build with no keys at all.
- **No build step.** Pages are rendered by `pipeline/render.py` into plain HTML, CSS and JavaScript.
- **Plain words.** Write what a reader would say ("Press release", not "PRESS_RELEASE").
- **Tests stay green, and new behaviour comes with a test.** Don't loosen an existing test to make
  a change pass.
- **Privacy stays true.** Nothing about a visitor leaves their browser. If a change would load
  something from a new outside service, the About page has to say so (a test checks this).

To add companies, see "Add companies" in the [README](README.md).

## Pull requests

Keep each one to a single change, and say how you checked it. Screenshots help for anything visual.
