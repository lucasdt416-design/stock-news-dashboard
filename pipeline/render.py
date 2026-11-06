"""Static HTML generator for the StockPulse site.

Renders one page per view from the database: index (front page), news (feed), calendar,
economic, company, and analytics. Pages share SHARED_CSS, NAVIGATION_LAYOUT_HTML, and
SHARED_MOBILE_JS. Design rules are in docs/redesign-plan.md.
"""

import base64
import hashlib
import json
import logging
import os
import re
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional
import yaml
from jinja2 import Template
from markupsafe import Markup, escape
from pipeline.calendar import calculate_relative_badge
from pipeline.normalize import clean_text
from pipeline.persist import (
    get_all_news_items,
    get_chart_data,
    get_economic_indicators,
    get_forthcoming_calendar,
    get_news_stats,
    get_recent_pipeline_runs,
    get_top_priority_items,
)

logger = logging.getLogger(__name__)

CHART_JS_URL = "https://cdn.jsdelivr.net/npm/chart.js@4.4.7/dist/chart.umd.min.js"
SAFE_URL_PATTERN = re.compile(r"https?://[^\s\x00-\x1f\x7f\"'<>`]+", re.IGNORECASE)
INLINE_SCRIPT_PATTERN = re.compile(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", re.DOTALL)
INLINE_STYLE_PATTERN = re.compile(r"<style[^>]*>(.*?)</style>", re.DOTALL)


def format_human_headline(item: Dict[str, Any]) -> str:
    """Produce a clean human-readable executive title for any news or filing item."""
    raw = clean_text(item.get("headline", "") or "")
    co_name = item.get("company_name") or item.get("ticker", "")
    form = (item.get("form_or_type") or "").upper().strip()
    category = item.get("category", "")
    llm = item.get("llm_summary", "") or ""

    is_raw_edgar = (
        raw.startswith("SEC Form")
        or raw.startswith("FORM ")
        or ".htm" in raw.lower()
        or ".xml" in raw.lower()
        or "STATEMENT OF CHANGES" in raw
        or "xsl144" in raw.lower()
        or "primary_doc" in raw.lower()
    )

    if not is_raw_edgar:
        return raw

    if form == "8-K":
        if "financial results" in llm.lower() or "earnings" in llm.lower():
            return f"{co_name} Discloses Quarterly Financial Results"
        return f"{co_name} Discloses Material Corporate Event"
    elif form == "10-Q":
        return f"{co_name} Files Quarterly Financial Report (10-Q)"
    elif form == "10-K":
        return f"{co_name} Files Annual Financial Report (10-K)"
    elif form == "4":
        return f"{co_name} Reports Executive & Director Insider Transaction"
    elif form == "144":
        return f"{co_name} Files Notice of Proposed Securities Sale (Rule 144)"
    elif form in ("DEF 14A", "DEFA14A"):
        return f"{co_name} Files Definitive Proxy Statement"
    elif form in ("13F-HR", "13F"):
        return f"{co_name} Discloses Institutional Investment Holdings (13F)"
    elif form in ("SC 13G", "SC 13G/A", "SC 13D"):
        return f"{co_name} Discloses Beneficial Ownership Stake"
    elif category == "Earnings & Financials":
        return f"{co_name} Files Periodic Financial Disclosure"
    elif category == "Insider Transactions":
        return f"{co_name} Reports Insider Securities Transaction"
    elif category == "Regulation & Policy / Litigation":
        return f"{co_name} Discloses Regulatory & Governance Filing"
    else:
        return f"{co_name} Files Official Regulatory Filing ({form})"


# ==============================================================================
# SECTOR DIRECTORY & CATEGORIZATION SYSTEM (10 MACRO SECTORS)
# ==============================================================================
SECTOR_METADATA = {
    "Technology": {
        "icon": "",
        "description": "Semiconductors, Cloud Software, AI & Consumer Tech",
        "symbols": ["NVDA", "AMD", "INTC", "AAPL", "MSFT", "GOOGL", "META", "TSLA"],
    },
    "Finance": {
        "icon": "",
        "description": "Global Banking & Investment Management",
        "symbols": ["JPM", "BAC", "GS"],
    },
    "Healthcare": {
        "icon": "",
        "description": "Pharmaceuticals, Biotechnology & Managed Care",
        "symbols": ["JNJ", "PFE", "ABBV", "UNH"],
    },
    "Energy": {
        "icon": "",
        "description": "Integrated Oil, Natural Gas & Energy Infrastructure",
        "symbols": ["XOM", "CVX"],
    },
    "Industrials": {
        "icon": "",
        "description": "Heavy Machinery & Industrial Equipment",
        "symbols": ["CAT"],
    },
    "Aerospace": {
        "icon": "",
        "description": "Commercial Aviation & Defense Propulsion",
        "symbols": ["BA", "GE"],
    },
    "Retail": {
        "icon": "",
        "description": "Retail Chains, Wholesale & E-Commerce",
        "symbols": ["WMT", "COST", "HD", "AMZN"],
    },
    "Consumer Staples": {
        "icon": "",
        "description": "Household Products, Beverages, Dining & Media",
        "symbols": ["PG", "KO", "MCD", "DIS"],
    },
    "Telecom": {
        "icon": "",
        "description": "Broadband, 5G Wireless & Telecom Infrastructure",
        "symbols": ["VZ"],
    },
    "Utilities": {
        "icon": "",
        "description": "Clean Power Generation & Electric Grid Utilities",
        "symbols": ["NEE"],
    },
}


def get_company_macro_sector(symbol: str, sector_str: str = "") -> str:
    """Classify any stock symbol or sector string into one of the 10 macro sectors."""
    sym = (symbol or "").upper().strip()
    for sec_name, meta in SECTOR_METADATA.items():
        if sym in meta["symbols"]:
            return sec_name
    sec = (sector_str or "").lower()
    if any(k in sec for k in ["semi", "software", "search", "social", "cloud", "tech"]):
        return "Technology"
    if any(k in sec for k in ["bank", "financ"]):
        return "Finance"
    if any(k in sec for k in ["health", "pharma", "managed_care"]):
        return "Healthcare"
    if any(k in sec for k in ["oil", "gas", "energy"]):
        return "Energy"
    if any(k in sec for k in ["industr", "machin"]):
        return "Industrials"
    if any(k in sec for k in ["aero", "defen"]):
        return "Aerospace"
    if any(k in sec for k in ["retail", "ecom", "home_improvement"]):
        return "Retail"
    if any(k in sec for k in ["staple", "bever", "restaur", "entertain"]):
        return "Consumer Staples"
    if any(k in sec for k in ["tele"]):
        return "Telecom"
    if any(k in sec for k in ["util"]):
        return "Utilities"
    return "Technology"


# ==============================================================================
# SHARED BASE CSS & ORGANIC RESPONSIVE DESIGN SYSTEM
# ==============================================================================
SHARED_CSS = """
    /* Neutral greys with one blue for links and focus. White by default, black when asked.
       Green and red only ever mean up and down. */
    :root {
      color-scheme: light;
      --bg-base: #ffffff;
      --bg-surface: #ffffff;
      --bg-surface-elevated: #f5f5f7;
      --bg-surface-glass: var(--bg-surface);
      --bg-surface-highlight: #e8e8ed;
      --bg-hover: #f5f5f7;
      --border-subtle: #e8e8ed;
      --border-card: #d2d2d7;
      --text-primary: #1d1d1f;
      --text-secondary: #424245;
      --text-muted: #6e6e73;
      --accent: #0066cc;
      --accent-soft: #e8f1fb;
      --on-accent: #ffffff;
      --pos: #1a7f37;
      --pos-soft: #e3f3e7;
      --neg: #d70015;
      --neg-soft: #fbe6e7;
      --warn: #8a5a00;
      --warn-soft: #f7efdc;
      --scrim: rgba(18, 20, 26, 0.45);
      /* Chart series, validated for colour-blind separation on this surface. No greens or reds. */
      --series-1: #1f6fb2;
      --series-2: #be4a86;
      --series-3: #8f7312;
      --series-4: #00899f;
      --series-5: #bc5a1e;
      --series-6: #7a4fbf;
      /* The watchlist map: three strengths each way, with a grey middle. Ink is chosen per step. */
      --heat-u1: #d9f2e0; --heat-u1-ink: #0d3b1c;
      --heat-u2: #8fd6a4; --heat-u2-ink: #0d3b1c;
      --heat-u3: #1a7f37; --heat-u3-ink: #ffffff;
      --heat-n: #e8e8ed; --heat-n-ink: #1d1d1f;
      --heat-d1: #fce0de; --heat-d1-ink: #5c0f0a;
      --heat-d2: #f4a19b; --heat-d2-ink: #4a0b07;
      --heat-d3: #c81e1e; --heat-d3-ink: #ffffff;
      --shadow-dropdown: 0 12px 32px rgba(18, 20, 26, 0.14);
      --shadow-modal: 0 12px 32px rgba(18, 20, 26, 0.2);

      /* Older names kept so existing components inherit the new palette. */
      --border-glass: var(--border-card);
      --border-accent: var(--accent);
      --accent-blue: var(--accent);
      --accent-blue-soft: var(--accent-soft);
      --accent-indigo: var(--accent);
      --accent-purple: var(--accent);
      --accent-cyan: var(--accent);
      --accent-emerald: var(--pos);
      --accent-rose: var(--neg);
      --accent-amber: var(--warn);
      --accent-orange-dark: var(--warn);
      --accent-orange-main: var(--warn);

      /* The device's own font: San Francisco on Apple, Segoe UI on Windows, Roboto on Android. */
      --font-display: var(--font-sans);
      --font-sans: -apple-system, BlinkMacSystemFont, 'SF Pro Text', 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
      --font-serif: var(--font-sans);
      --font-mono: var(--font-sans);

      --radius-xs: 4px;
      --radius-sm: 6px;
      --radius-md: 8px;
      --radius-lg: 10px;
      --radius-xl: 12px;
      --radius-2xl: 14px;
      --radius-full: 999px;

      --shadow-sm: none;
      --shadow-card: none;
      --shadow-hover: none;
      --shadow-float: none;

      --transition-fast: 0.12s ease-out;
      --transition-normal: 0.18s ease-out;
    }

    :root[data-theme="dark"] {
      color-scheme: dark;
      --bg-base: #000000;
      --bg-surface: #000000;
      --bg-surface-elevated: #1c1c1e;
      --bg-surface-highlight: #2c2c2e;
      --bg-hover: #1c1c1e;
      --border-subtle: #2c2c2e;
      --border-card: #3a3a3c;
      --text-primary: #f5f5f7;
      --text-secondary: #c7c7cc;
      --text-muted: #98989d;
      --accent: #2997ff;
      --accent-soft: #0f2740;
      --on-accent: #000000;
      --pos: #30d158;
      --pos-soft: #0d2a16;
      --neg: #ff453a;
      --neg-soft: #331210;
      --warn: #ffd60a;
      --warn-soft: #2e2806;
      --scrim: rgba(0, 0, 0, 0.6);
      --series-1: #3f92d0;
      --series-2: #d05f94;
      --series-3: #b28b28;
      --series-4: #16a2ae;
      --series-5: #d9642b;
      --series-6: #9b78d0;
      --heat-u1: #10331c; --heat-u1-ink: #d9f2e0;
      --heat-u2: #17572b; --heat-u2-ink: #ffffff;
      --heat-u3: #1e7f38; --heat-u3-ink: #ffffff;
      --heat-n: #2c2c2e; --heat-n-ink: #f5f5f7;
      --heat-d1: #3a1614; --heat-d1-ink: #fce0de;
      --heat-d2: #7a1f19; --heat-d2-ink: #ffffff;
      --heat-d3: #c9302a; --heat-d3-ink: #ffffff;
      --shadow-dropdown: 0 12px 32px rgba(0, 0, 0, 0.55);
      --shadow-modal: 0 12px 32px rgba(0, 0, 0, 0.65);
    }

    button, input, select, textarea {
      font: inherit;
    }

    h1, h2, h3 {
      font-family: var(--font-sans);
      font-weight: 600;
      letter-spacing: -0.015em;
    }

    * {
      box-sizing: border-box;
      margin: 0;
      padding: 0;
    }

    html {
      scroll-behavior: smooth;
      -webkit-text-size-adjust: 100%;
    }

    body {
      background-color: var(--bg-base);
      background-attachment: fixed;
      color: var(--text-primary);
      font-family: var(--font-sans);
      font-feature-settings: 'tnum' 1;
      min-height: 100vh;
      line-height: 1.55;
      overflow-x: hidden;
      width: 100%;
    }

    /* Core Shared Layout: Sticky Sidebar on Desktop, Zero Leftover Margin on Main */
    .app-layout {
      display: flex;
      min-height: 100vh;
      width: 100%;
      position: relative;
    }

    .app-sidebar {
      width: 216px;
      min-width: 216px;
      max-width: 216px;
      flex-shrink: 0;
      background: var(--bg-base);
      border-right: 1px solid var(--border-subtle);
      display: flex;
      flex-direction: column;
      position: sticky;
      top: 0;
      height: 100vh;
      overflow-y: auto;
      padding: 2rem 1.5rem 1.5rem;
      z-index: 100;
      transition: transform var(--transition-normal);
    }

    .app-main {
      flex: 1 1 0%;
      min-width: 0;
      width: 100%;
      max-width: 1180px;
      padding: 3rem 4rem 6rem;
      margin: 0;
      box-sizing: border-box;
    }

    :focus-visible {
      outline: 2px solid var(--accent);
      outline-offset: 2px;
    }

    /* Mobile Sticky Header & Bottom Navigation Bar */
    .mobile-top-header {
      display: none;
      position: sticky;
      top: 0;
      left: 0;
      right: 0;
      z-index: 950;
      background: var(--bg-base);
      border-bottom: 1px solid var(--border-subtle);
      padding: 0.5rem 0.5rem 0.5rem 1rem;
      align-items: center;
      justify-content: space-between;
    }

    .mobile-header-right {
      display: flex;
      align-items: center;
      gap: 0.5rem;
    }

    .mobile-action-btn, .mobile-hamburger-btn {
      width: 44px;
      height: 44px;
      min-width: 44px;
      background: transparent;
      border: none;
      color: var(--text-primary);
      display: inline-flex;
      align-items: center;
      justify-content: center;
      cursor: pointer;
      padding: 0;
      touch-action: manipulation;
    }

    .mobile-action-btn:hover, .mobile-hamburger-btn:hover {
      color: var(--accent);
    }

    .mobile-drawer-backdrop {
      display: none;
      position: fixed;
      top: 0;
      left: 0;
      right: 0;
      bottom: 0;
      background: var(--scrim);
      z-index: 1050;
      opacity: 0;
      transition: opacity var(--transition-normal);
    }

    .mobile-drawer-backdrop.active {
      display: block;
      opacity: 1;
    }

    /* Native Phone Bottom Navigation Dock (5 Tabs) */
    .mobile-bottom-nav {
      display: none;
      position: fixed;
      bottom: 0;
      left: 0;
      right: 0;
      z-index: 1000;
      background: var(--bg-base);
      border-top: 1px solid var(--border-card);
      padding: 0 0.25rem env(safe-area-inset-bottom);
      justify-content: space-around;
      align-items: stretch;
    }

    .mobile-tab-link {
      display: flex;
      align-items: center;
      justify-content: center;
      color: var(--text-muted);
      text-decoration: none;
      font-size: 0.8rem;
      font-weight: 500;
      flex: 1;
      text-align: center;
      min-height: 48px;
      touch-action: manipulation;
      border-top: 2px solid transparent;
      margin-top: -1px;
    }

    .mobile-tab-link.active {
      color: var(--text-primary);
      border-top-color: var(--text-primary);
    }

    .sidebar-close-btn {
      display: none;
      background: transparent;
      border: none;
      font-size: 1.4rem;
      color: var(--text-muted);
      cursor: pointer;
      padding: 0.25rem 0.5rem;
      line-height: 1;
    }
    /* Responsive Viewports */
    @media (max-width: 1024px) {
      .app-layout {
        display: block !important;
        width: 100% !important;
      }

      .mobile-top-header {
        display: flex !important;
      }

      .mobile-bottom-nav {
        display: flex !important;
      }

      .sidebar-close-btn {
        display: block !important;
      }

      .app-sidebar {
        position: fixed !important;
        top: 0 !important;
        bottom: 0 !important;
        left: 0 !important;
        height: 100vh !important;
        width: 280px !important;
        max-width: 280px !important;
        z-index: 1100 !important;
        transform: translateX(-100%) !important;
      }

      .app-sidebar.mobile-open {
        transform: translateX(0) !important;
        background: var(--bg-surface) !important;
        box-shadow: var(--shadow-modal) !important;
      }

      .app-main {
        margin: 0 !important;
        width: 100% !important;
        max-width: 100% !important;
        padding: 1.75rem 1rem calc(5.5rem + env(safe-area-inset-bottom)) 1rem !important;
        box-sizing: border-box !important;
      }

    }

    /* Dedicated Phone Viewports (<= 640px and <= 480px / 375px - 414px) */
    @media (max-width: 640px) {
      .app-main {
        padding: 0.85rem 0.85rem calc(5.5rem + env(safe-area-inset-bottom)) 0.85rem !important;
      }

    }

    /* Sidebar Brand (Logo and Title Only - No Tagline) */
    .sidebar-brand {
      display: block;
      text-decoration: none;
      color: inherit;
    }

    .brand-title {
      font-family: var(--font-display);
      font-size: 1.5rem;
      font-weight: 700;
      letter-spacing: -0.01em;
      color: var(--text-primary);
      line-height: 1;
    }

    .sidebar-nav {
      display: flex;
      flex-direction: column;
      gap: 0.1rem;
      flex: 1;
    }

    .nav-link {
      display: flex;
      align-items: baseline;
      justify-content: space-between;
      padding: 0.42rem 0;
      color: var(--text-secondary);
      text-decoration: none;
      font-size: 0.92rem;
      font-weight: 400;
    }

    .nav-link:hover {
      color: var(--text-primary);
    }

    .nav-link.active {
      color: var(--text-primary);
      font-weight: 600;
    }

    .sidebar-footer {
      margin-top: auto;
      padding-top: 1.5rem;
      font-size: 0.74rem;
      line-height: 1.55;
      color: var(--text-muted);
    }

    .sidebar-status-alert { color: var(--neg); font-weight: 600; }

    .theme-toggle {
      background: none;
      border: none;
      padding: 0;
      margin-top: 0.5rem;
      min-height: 24px;
      font: inherit;
      color: var(--text-muted);
      cursor: pointer;
      text-decoration: underline;
      text-decoration-color: var(--border-card);
      text-underline-offset: 3px;
    }

    .theme-toggle:hover { color: var(--text-primary); }

    .catalyst-ticker, .ticker-badge {
      white-space: nowrap !important;
      word-break: keep-all !important;
      overflow-wrap: normal !important;
      display: inline-block;
    }

    /* Global Search & Command Bar (⌘K) with Bulletproof Overflow Containment */
    .search-wrapper {
      position: relative;
      width: 100%;
      margin: 0 0 3rem;
      z-index: 50;
    }

    .search-wrapper:has(.search-dropdown.active) { z-index: 300; }

    .search-box {
      display: flex;
      align-items: center;
      gap: 0.85rem;
      height: 66px;
      padding: 0 1.35rem;
      background: var(--bg-surface);
      border: 2px solid var(--border-card);
      border-radius: 18px;
      cursor: text;
    }

    .search-box:hover { border-color: var(--text-muted); }
    .search-box:focus-within { border-color: var(--accent); }

    .search-icon-wrap { display: flex; color: var(--text-muted); flex-shrink: 0; }
    .search-box:focus-within .search-icon-wrap { color: var(--accent); }

    .search-input {
      flex: 1;
      min-width: 0;
      border: none;
      outline: none;
      background: transparent;
      font-size: 1.15rem;
      font-weight: 500;
      color: var(--text-primary);
    }

    .search-input::placeholder { color: var(--text-muted); font-weight: 400; }

    .search-shortcut {
      font-size: 0.74rem;
      font-weight: 600;
      color: var(--text-muted);
      border: 1px solid var(--border-card);
      border-radius: 6px;
      padding: 0.15rem 0.4rem;
      flex-shrink: 0;
    }

    .search-dropdown {
      position: absolute;
      top: calc(100% + 6px);
      left: 0;
      right: 0;
      background: var(--bg-surface);
      border: 1px solid var(--border-card);
      box-shadow: var(--shadow-dropdown);
      padding: 0.5rem 1rem 1rem;
      z-index: 100;
      display: none;
      max-height: 440px;
      overflow-x: hidden;
      overflow-y: auto;
    }

    .search-dropdown.active { display: block; }

    .dropdown-section-title {
      font-size: 0.74rem;
      color: var(--text-muted);
      margin: 0.85rem 0 0.15rem;
    }

    .dropdown-tabs-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      column-gap: 2rem;
    }

    .dropdown-tab-card {
      display: flex;
      justify-content: space-between;
      align-items: baseline;
      gap: 0.75rem;
      padding: 0.65rem 0;
      border-bottom: 1px solid var(--border-subtle);
      color: inherit;
      text-decoration: none;
    }

    .dropdown-tab-card:hover .dropdown-tab-title { color: var(--accent); }
    .dropdown-tab-title { font-size: 0.92rem; }
    .dropdown-tab-sub { font-size: 0.76rem; color: var(--text-muted); white-space: nowrap; }

    .search-result-item {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 1rem;
      padding: 0.6rem 0;
      border-bottom: 1px solid var(--border-subtle);
      color: inherit;
      text-decoration: none;
    }

    .search-result-item:hover .search-result-title { color: var(--accent); }
    .search-result-left { display: flex; align-items: baseline; gap: 0.75rem; min-width: 0; flex: 1; }
    .search-result-icon { display: none; }
    .search-result-info { min-width: 0; }
    .search-result-title { font-size: 0.92rem; overflow-wrap: anywhere; }
    .search-result-sub { font-size: 0.76rem; color: var(--text-muted); overflow-wrap: anywhere; }
    .search-result-item .action-link { color: var(--text-muted); white-space: nowrap; }

    .search-no-results { padding: 1.25rem 0 0.5rem; }
    .no-results-icon { display: none; }
    .no-results-title { font-size: 0.95rem; margin-bottom: 0.3rem; }
    .no-results-sub { font-size: 0.82rem; color: var(--text-muted); }

    .quick-lookup-card { padding: 0.75rem 0; border-bottom: 1px solid var(--border-card); }
    .quick-lookup-header { display: flex; justify-content: space-between; align-items: baseline; flex-wrap: wrap; gap: 0.5rem; margin-bottom: 0.4rem; }
    .quick-lookup-title-group { display: flex; align-items: baseline; flex-wrap: wrap; gap: 0.5rem; min-width: 0; }
    .quick-lookup-badge, .quick-lookup-meta, .quick-lookup-range { font-size: 0.76rem; color: var(--text-muted); }
    .quick-lookup-price-strip { display: flex; align-items: baseline; flex-wrap: wrap; gap: 0.75rem; margin: 0.35rem 0; }
    .quick-lookup-price-val { font-family: var(--font-mono); font-size: 1.1rem; }
    .quick-lookup-change { font-family: var(--font-mono); font-size: 0.85rem; }
    .quick-lookup-change.pos { color: var(--pos); }
    .quick-lookup-change.neg { color: var(--neg); }
    .quick-lookup-change.neu { color: var(--text-muted); }
    .quick-lookup-headlines-title { font-size: 0.76rem; color: var(--text-muted); margin-top: 0.6rem; }
    .quick-lookup-news-item { display: block; padding: 0.45rem 0; border-bottom: 1px solid var(--border-subtle); color: inherit; text-decoration: none; }
    .quick-lookup-news-item:hover .quick-lookup-news-headline { color: var(--accent); }
    .quick-lookup-news-headline { font-size: 0.9rem; overflow-wrap: anywhere; }
    .quick-lookup-news-meta { display: flex; gap: 0.4rem; font-size: 0.74rem; color: var(--text-muted); }
    .quick-lookup-action-bar { display: flex; justify-content: space-between; flex-wrap: wrap; gap: 0.5rem; font-size: 0.76rem; padding-top: 0.6rem; }

    .table-container { width: 100%; overflow-x: auto; }

    /* Shared page header */
    .page-header { margin-bottom: 2.25rem; max-width: 46rem; }
    .page-title { font-size: clamp(2.1rem, 4.5vw, 3rem); line-height: 1.08; letter-spacing: -0.02em; margin-bottom: 0.6rem; }
    .page-standfirst { font-family: var(--font-serif); font-size: 1.15rem; line-height: 1.45; color: var(--text-secondary); }

    /* Feed */
    .feed-toolbar { margin-bottom: 0.25rem; }
    .feed-search { width: 100%; border: none; border-bottom: 1px solid var(--text-primary); background: transparent; color: var(--text-primary); font-size: 1rem; padding: 0.7rem 0; outline: none; }
    .feed-search::placeholder { color: var(--text-muted); }
    .feed-toolbar-row { display: flex; flex-wrap: wrap; align-items: center; gap: 0.25rem 1.25rem; padding-top: 0.5rem; }
    .feed-sort { display: flex; gap: 1rem; }
    .feed-sort-btn, .feed-clear, .feed-group-toggle { background: none; border: none; padding: 0; min-height: 36px; font-size: 0.84rem; color: var(--text-muted); cursor: pointer; }
    .feed-sort-btn:hover, .feed-clear:hover, .feed-group-toggle:hover { color: var(--text-primary); }
    .feed-sort-btn.active { color: var(--text-primary); font-weight: 600; }
    .feed-count { font-size: 0.84rem; color: var(--text-muted); }
    .feed-clear, .feed-group-toggle { color: var(--accent); }

    .controls-panel { background: none; border: none; padding: 0; margin: 0 0 1.75rem; box-shadow: none; }
    details > summary { list-style: none; }
    details > summary::-webkit-details-marker { display: none; }
    .feed-filters-toggle::after, .feed-details summary .feed-meta::after { content: ' +'; color: var(--text-muted); }
    details[open] > .feed-filters-toggle::after, .feed-details[open] summary .feed-meta::after { content: ' \\2212'; }
    .feed-filters-toggle { display: inline-flex; white-space: pre; align-items: center; min-height: 36px; font-size: 0.84rem; color: var(--text-secondary); cursor: pointer; }
    .feed-filters-toggle:hover { color: var(--text-primary); }
    .controls-panel[open] { padding-bottom: 0.75rem; border-bottom: 1px solid var(--border-subtle); }

    .filter-row { display: grid; grid-template-columns: 6rem minmax(0, 1fr); gap: 0.75rem; align-items: baseline; padding: 0.4rem 0; margin: 0; }
    .filter-label { font-size: 0.8rem; color: var(--text-muted); text-transform: none; letter-spacing: 0; font-weight: 400; margin: 0; }
    .filter-options, .feed-sector-bar { display: flex; flex-wrap: wrap; gap: 0 1rem; overflow: visible; padding: 0; margin: 0; }
    .filter-btn { background: none; border: none; padding: 0; min-height: 32px; font-size: 0.84rem; font-weight: 400; color: var(--text-secondary); cursor: pointer; border-radius: 0; display: inline-flex; align-items: baseline; gap: 0.3rem; }
    .filter-btn:hover { color: var(--text-primary); background: none; }
    .filter-btn.active { color: var(--text-primary); font-weight: 600; background: none; text-decoration: underline; text-underline-offset: 4px; text-decoration-thickness: 1px; }
    .pill-count { font-family: var(--font-mono); font-size: 0.7rem; color: var(--text-muted); background: none; padding: 0; font-weight: 400; }

    .feed-ticker-picker-wrap { position: relative; display: inline-block; max-width: 100%; }
    .feed-ticker-picker-btn { background: none; border: none; padding: 0; min-height: 32px; font-size: 0.84rem; color: var(--text-primary); cursor: pointer; }
    .feed-ticker-dropdown-menu { display: none; position: absolute; top: 100%; left: 0; width: 22rem; max-width: calc(100vw - 8.5rem); background: var(--bg-surface); border: 1px solid var(--border-card); box-shadow: var(--shadow-dropdown); z-index: 200; }
    .feed-ticker-dropdown-menu.active { display: block; }
    .feed-ticker-dropdown-search input { width: 100%; border: none; border-bottom: 1px solid var(--border-card); background: transparent; color: var(--text-primary); padding: 0.6rem 0.75rem; font-size: 0.86rem; outline: none; }
    .feed-ticker-dropdown-list { max-height: 300px; overflow-y: auto; }
    .feed-ticker-item { display: flex; justify-content: space-between; align-items: baseline; gap: 0.75rem; padding: 0.45rem 0.75rem; font-size: 0.84rem; cursor: pointer; }
    .feed-ticker-item:hover, .feed-ticker-item.active { background: var(--bg-hover); }
    .feed-dropdown-sec-header { padding: 0.6rem 0.75rem 0.15rem; font-size: 0.74rem; color: var(--text-muted); }

    .feed-group { display: flex; flex-wrap: wrap; align-items: baseline; gap: 0.25rem 0.75rem; padding: 2.25rem 0 0.5rem; border-bottom: 1px solid var(--text-primary); }
    .feed-group:first-child { padding-top: 0.5rem; }
    .feed-group-title { font-size: 1.3rem; }
    .feed-group-note { font-size: 0.8rem; color: var(--text-muted); }
    .feed-group-toggle { margin-left: auto; }

    .news-row { display: grid; grid-template-columns: 2.5rem 3.75rem minmax(0, 1fr) 3.5rem; gap: 0.75rem; align-items: baseline; padding: 0.8rem 0; border-bottom: 1px solid var(--border-subtle); }
    .feed-score { font-family: var(--font-mono); font-size: 0.8rem; color: var(--text-muted); cursor: help; }
    .news-row.is-high .feed-score { color: var(--text-primary); }
    .feed-headline { font-family: var(--font-serif); font-size: 1.08rem; font-weight: 400; line-height: 1.3; letter-spacing: 0; overflow-wrap: anywhere; }
    .news-row.is-high .feed-headline { font-weight: 500; }
    .feed-headline a { color: inherit; text-decoration: none; }
    .feed-headline a:hover { color: var(--accent); }
    .feed-takeaway { font-size: 0.9rem; line-height: 1.5; color: var(--text-secondary); margin-top: 0.25rem; max-width: 40rem; overflow-wrap: anywhere; }
    .feed-details summary { cursor: pointer; margin-top: 0.15rem; min-height: 24px; }
    .feed-details summary:hover .feed-meta { color: var(--text-primary); }
    .feed-meta { font-size: 0.76rem; color: var(--text-muted); overflow-wrap: anywhere; }
    .feed-details-body { padding: 0.35rem 0 0.5rem; font-size: 0.86rem; line-height: 1.5; color: var(--text-secondary); max-width: 40rem; overflow-wrap: anywhere; }
    .feed-details-body > .feed-takeaway { margin-top: 0; margin-bottom: 0.35rem; }
    .feed-detail-label { font-size: 0.76rem; color: var(--text-muted); margin-top: 0.6rem; }
    .feed-refs { list-style: none; }
    .feed-refs li { padding: 0.1rem 0; }
    .feed-breakdown { font-family: var(--font-mono); font-size: 0.74rem; }
    .date-cell { font-family: var(--font-mono); font-size: 0.74rem; color: var(--text-muted); text-align: right; white-space: nowrap; }

    @media (max-width: 620px) {
      .news-row { grid-template-columns: 2.25rem minmax(0, 1fr) auto; gap: 0.15rem 0.5rem; }
      .news-row .feed-body { grid-column: 1 / -1; grid-row: 2; }
      .filter-row { grid-template-columns: minmax(0, 1fr); gap: 0.1rem; padding: 0.55rem 0; }
      .filter-options, .feed-sector-bar { gap: 0 1.1rem; }
      .filter-btn, .feed-ticker-picker-btn { min-height: 40px; }
      .feed-ticker-dropdown-menu { max-width: calc(100vw - 2rem); }
      .feed-details summary { min-height: 32px; }
    }

    /* Calendar */
    .cal-timeline { margin: 0 0 2rem; }
    .cal-track { position: relative; height: 72px; margin: 0 0.5rem; border-bottom: 1px solid var(--text-primary); }
    .cal-month { position: absolute; top: 0; bottom: 0; padding-left: 0.35rem; border-left: 1px solid var(--border-card); font-size: 0.74rem; color: var(--text-muted); }
    .cal-mark { position: absolute; width: 7px; height: 10px; margin-left: -3px; background: var(--text-primary); }
    .cal-mark::before { content: ''; position: absolute; inset: -6px -3px; }
    .cal-mark:hover { background: var(--accent); }
    .cal-mark.is-estimated { background: var(--bg-base); box-shadow: inset 0 0 0 1px var(--text-primary); }
    .cal-mark.is-estimated:hover { box-shadow: inset 0 0 0 1px var(--accent); }
    .cal-mark.is-dimmed { opacity: 0.15; }
    .cal-legend { display: flex; flex-wrap: wrap; gap: 0.25rem 1.25rem; margin-top: 0.6rem; font-size: 0.76rem; color: var(--text-muted); }
    .cal-key { display: inline-block; width: 7px; height: 10px; margin-right: 0.45rem; background: var(--text-primary); }
    .cal-key.is-estimated { background: transparent; box-shadow: inset 0 0 0 1px var(--text-primary); }
    .cal-today { color: var(--text-primary); border-left-color: var(--text-primary); }
    .cal-filters { margin-bottom: 0.75rem; }

    .cal-week { padding-top: 1.5rem; }
    .cal-week-title { font-size: 1.3rem; padding-bottom: 0.5rem; border-bottom: 1px solid var(--text-primary); }
    .calendar-card { display: grid; grid-template-columns: 6rem 3.75rem minmax(0, 1fr) auto; gap: 0.75rem; align-items: baseline; padding: 0.8rem 0; border-bottom: 1px solid var(--border-subtle); scroll-margin-top: 5rem; }
    .calendar-card:target { background: var(--accent-soft); }
    .cal-when { display: flex; flex-direction: column; }
    .cal-date { font-family: var(--font-mono); font-size: 0.82rem; }
    .cal-relative { font-size: 0.74rem; color: var(--text-muted); }
    .cal-headline { font-size: 1.08rem; font-weight: 400; line-height: 1.3; letter-spacing: 0; overflow-wrap: anywhere; }
    .cal-details { font-size: 0.82rem; line-height: 1.45; color: var(--text-muted); margin-top: 0.15rem; overflow-wrap: anywhere; }
    .cal-estimated { color: var(--warn); }
    .cal-source { font-size: 0.8rem; color: var(--accent); text-decoration: none; white-space: nowrap; }
    .cal-source:hover { text-decoration: underline; text-underline-offset: 3px; }

    @media (max-width: 620px) {
      .cal-mark { width: 4px; margin-left: -2px; }
      .calendar-card { grid-template-columns: minmax(0, 1fr) auto; gap: 0.1rem 0.75rem; }
      .cal-when { flex-direction: row; gap: 0.5rem; align-items: baseline; grid-column: 1; }
      .calendar-card > .ticker-badge { grid-column: 2; grid-row: 1; justify-self: end; }
      .cal-body { grid-column: 1 / -1; }
      .cal-source { grid-column: 1 / -1; padding: 0.35rem 0 0.1rem; }
    }

    /* Economy */
    .econ-ledger { border-top: 1px solid var(--text-primary); margin-bottom: 3.5rem; }
    .economic-card { display: grid; grid-template-columns: minmax(0, 1fr) 11rem 9rem; gap: 0.25rem 2rem; align-items: center; padding: 1.1rem 0; border-bottom: 1px solid var(--border-subtle); }
    .economic-series-name { font-size: 1.2rem; line-height: 1.25; }
    .econ-sub { font-size: 0.76rem; color: var(--text-muted); margin-top: 0.15rem; overflow-wrap: anywhere; }
    .sparkline-wrapper { position: relative; cursor: crosshair; }
    .sparkline-svg { display: block; width: 100%; height: auto; overflow: visible; }
    .sparkline-labels { display: flex; justify-content: space-between; gap: 0.5rem; white-space: nowrap; margin-top: 0.25rem; font-family: var(--font-mono); font-size: 0.66rem; color: var(--text-muted); }
    .sparkline-tooltip { display: none; position: absolute; transform: translate(-50%, -130%); padding: 0.15rem 0.4rem; background: var(--text-primary); color: var(--bg-base); font-family: var(--font-mono); font-size: 0.68rem; white-space: nowrap; pointer-events: none; z-index: 5; }
    .econ-figure { text-align: right; }
    .economic-val { font-family: var(--font-mono); font-size: 1.3rem; font-weight: 500; letter-spacing: -0.02em; white-space: nowrap; }
    .econ-change { font-family: var(--font-mono); font-size: 0.74rem; color: var(--text-secondary); margin-top: 0.15rem; }
    .econ-details { grid-column: 1 / -1; }
    .econ-holdings { display: flex; flex-wrap: wrap; gap: 0.1rem 0.8rem; }

    .econ-select { max-width: 100%; min-height: 32px; background: transparent; color: var(--text-primary); border: none; border-bottom: 1px solid var(--border-card); font-size: 0.84rem; padding: 0.2rem 0; }
    .econ-section { margin-bottom: 3.5rem; }
    .econ-note { font-size: 0.82rem; color: var(--text-muted); padding: 0.6rem 0 0.25rem; }
    .econ-stale { color: var(--warn); }

    table.econ-matrix { width: 100%; min-width: 0; border-collapse: collapse; font-size: 0.84rem; }
    .econ-matrix th, .econ-matrix td { padding: 0.42rem 0.5rem 0.42rem 0; border-bottom: 1px solid var(--border-subtle); text-align: left; font-size: inherit; font-weight: 400; text-transform: none; letter-spacing: 0; color: inherit; vertical-align: baseline; white-space: normal; background: none; }
    .econ-matrix thead th { font-size: 0.76rem; color: var(--text-muted); border-bottom: 1px solid var(--border-card); }
    .econ-matrix .mx-col { width: 3.25rem; padding-right: 0; text-align: center; }
    .econ-matrix .matrix-sector th { padding-top: 1.1rem; font-size: 0.76rem; color: var(--text-muted); border-bottom: 1px solid var(--border-card); }
    .mx-name { color: var(--text-secondary); margin-left: 0.5rem; }
    .econ-matrix .mx-factors { font-size: 0.78rem; color: var(--text-muted); padding-left: 1rem; }
    .mx-dot { display: inline-block; width: 8px; height: 8px; background: var(--text-primary); vertical-align: baseline; }

    .econ-schedule { list-style: none; }
    .econ-release { display: grid; grid-template-columns: 6rem minmax(0, 1fr); gap: 0.75rem; align-items: baseline; padding: 0.8rem 0; border-bottom: 1px solid var(--border-subtle); }
    .econ-release .cal-when { flex-direction: column; gap: 0; }
    .econ-release.is-passed .cal-headline, .econ-release.is-passed .cal-date { color: var(--text-muted); }

    @media (max-width: 860px) {
      .economic-card { grid-template-columns: minmax(0, 1fr) 9.5rem 9.5rem; gap: 0.25rem 1.25rem; }
      .econ-matrix .mx-factors { display: none; }
      .econ-matrix .mx-col { width: 2.6rem; }
    }

    @media (max-width: 620px) {
      .economic-card { grid-template-columns: minmax(0, 1fr) auto; }
      .economic-card .sparkline-wrapper { grid-column: 1 / -1; grid-row: 2; margin: 0.5rem 0 0.25rem; }
      .mx-name { display: none; }
    }

    /* Companies */
    .company-directory-browser { margin-bottom: 3rem; }
    .company-directory-browser .econ-note { padding-bottom: 0; }
    .company-browser-grid { columns: 2; column-gap: 3rem; margin-top: 0.75rem; }
    .company-browser-sector { break-inside: avoid; padding-bottom: 1.25rem; }
    .company-browser-sector-name { font-size: 0.98rem; padding-bottom: 0.35rem; border-bottom: 1px solid var(--text-primary); }
    .company-browser-card { display: flex; justify-content: space-between; align-items: baseline; gap: 0.75rem; width: 100%; background: none; border: none; border-bottom: 1px solid var(--border-subtle); padding: 0.5rem 0; text-align: left; color: inherit; cursor: pointer; }
    .company-browser-card:hover .company-browser-card-name { color: var(--accent); }
    .company-browser-card.active .company-browser-card-name { font-weight: 600; }
    .company-browser-card-left { display: grid; grid-template-columns: 3.5rem minmax(0, 1fr); gap: 0.5rem; align-items: baseline; min-width: 0; }
    .company-browser-card-info { display: flex; flex-direction: column; min-width: 0; }
    .company-browser-card-name { font-size: 0.88rem; overflow-wrap: anywhere; }
    .company-browser-card-sec { font-size: 0.74rem; color: var(--text-muted); }
    .company-browser-card-stats { display: flex; flex-direction: column; align-items: flex-end; flex-shrink: 0; }
    .company-browser-card-alpha { font-family: var(--font-mono); font-size: 0.8rem; }
    .company-browser-card-stories { font-size: 0.72rem; color: var(--text-muted); white-space: nowrap; }

    .company-profile-container { border-top: 1px solid var(--text-primary); padding-top: 2rem; }
    .company-hero-symbol { font-family: var(--font-mono); font-size: 0.8rem; color: var(--text-muted); margin-bottom: 0.4rem; }
    .company-hero-name { font-size: clamp(1.9rem, 4vw, 2.6rem); line-height: 1.1; letter-spacing: -0.02em; margin-bottom: 0.6rem; }
    .company-notes-card { font-family: var(--font-serif); font-size: 1.1rem; line-height: 1.45; color: var(--text-secondary); max-width: 44rem; margin-bottom: 0.75rem; }
    .company-links { display: flex; flex-wrap: wrap; gap: 0.2rem 1.25rem; font-size: 0.8rem; color: var(--text-muted); }
    .company-links a { color: var(--accent); text-decoration: none; }
    .company-links a:hover { text-decoration: underline; text-underline-offset: 3px; }

    .company-kpi-ribbon { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 1.5rem; margin: 1.75rem 0 3rem; padding-top: 0.75rem; border-top: 1px solid var(--border-card); }
    .company-kpi-title { font-size: 0.76rem; color: var(--text-muted); }
    .company-kpi-val { font-family: var(--font-mono); font-size: 1.35rem; letter-spacing: -0.02em; margin: 0.1rem 0; }
    .company-kpi-sub { font-size: 0.74rem; line-height: 1.4; color: var(--text-muted); }

    .comparative-perf-card { margin-bottom: 3rem; }
    .perf-kpi-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 1.5rem; margin: 1rem 0 1.5rem; }
    .perf-kpi-box { min-width: 0; }
    .perf-kpi-label { font-size: 0.76rem; color: var(--text-muted); }
    .perf-kpi-val { font-family: var(--font-mono); font-size: 1.2rem; letter-spacing: -0.02em; }
    .perf-kpi-sub { font-size: 0.74rem; line-height: 1.4; color: var(--text-muted); overflow-wrap: anywhere; }
    .perf-chart-box { position: relative; height: 280px; width: 100%; }
    .perf-table-wrap { margin-top: 1.25rem; overflow-x: auto; }
    table.perf-table { width: 100%; min-width: 0; border-collapse: collapse; font-size: 0.84rem; }
    table.perf-table th, table.perf-table td { padding: 0.5rem 0.75rem 0.5rem 0; border-bottom: 1px solid var(--border-subtle); text-align: left; font-size: inherit; font-weight: 400; text-transform: none; letter-spacing: 0; white-space: nowrap; background: none; vertical-align: baseline; }
    table.perf-table th { font-size: 0.76rem; color: var(--text-muted); border-bottom-color: var(--border-card); }
    table.perf-table td:nth-child(n+3), table.perf-table th:nth-child(n+3) { text-align: right; padding-right: 0; padding-left: 0.75rem; }
    .perf-row-target td { font-weight: 600; }
    .perf-num { font-family: var(--font-mono); }

    .company-grid-layout { display: grid; grid-template-columns: minmax(0, 2fr) minmax(0, 1fr); gap: 3.5rem; align-items: start; }
    .company-feed-tools { padding: 0.5rem 0 0.25rem; }
    .company-feed-tools .feed-search { border-bottom-color: var(--border-card); font-size: 0.9rem; padding: 0.45rem 0; }
    .company-news-item { display: grid; grid-template-columns: 2.5rem minmax(0, 1fr) 3.25rem; gap: 0.75rem; align-items: baseline; padding: 0.8rem 0; border-bottom: 1px solid var(--border-subtle); }
    .company-news-item.is-high .feed-score { color: var(--text-primary); }
    .company-news-item.is-high .feed-headline { font-weight: 500; }
    .company-side-deck { display: flex; flex-direction: column; gap: 2.5rem; }
    .company-side-sub { display: block; font-size: 0.74rem; color: var(--text-muted); }
    .company-side-note { font-size: 0.8rem; line-height: 1.5; color: var(--text-muted); padding-top: 0.6rem; overflow-wrap: anywhere; }
    .company-names { font-size: 0.86rem; line-height: 1.6; overflow-wrap: anywhere; }
    .company-outside { color: var(--text-secondary); }
    .company-sep { color: var(--text-muted); }

    @media (max-width: 860px) {
      .company-browser-grid { columns: 1; }
      .company-grid-layout { grid-template-columns: minmax(0, 1fr); gap: 2.75rem; }
      .company-kpi-ribbon, .perf-kpi-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 1.25rem; }
      .perf-chart-box { height: 240px; }
      table.perf-table { font-size: 0.78rem; }
      table.perf-table td, table.perf-table th { white-space: normal; }
      table.perf-table td:nth-child(2), table.perf-table th:nth-child(2), table.perf-table td:nth-child(3), table.perf-table th:nth-child(3) { display: none; }
    }

    /* Analytics */
    .analytics-stat-row { margin-top: 0; }
    .analytics-grid { display: grid; grid-template-columns: minmax(0, 1fr); gap: 3rem; margin-bottom: 3.5rem; }
    .analytics-donut-layout { display: grid; grid-template-columns: minmax(0, 2fr) minmax(0, 3fr); gap: 2.5rem; align-items: center; }
    .analytics-card { margin: 0; min-width: 0; background: none; border: none; padding: 0; }
    .chart-canvas-container { position: relative; height: 300px; width: 100%; margin-top: 0.75rem; }
    .chart-canvas-donut { height: 300px; margin-top: 0; }
    .category-legend-list { margin-top: 0.75rem; }
    .category-stat-row { display: flex; justify-content: space-between; align-items: baseline; gap: 0.75rem; padding: 0.4rem 0; border-bottom: 1px solid var(--border-subtle); font-size: 0.84rem; }
    .cat-stat-left { display: flex; align-items: baseline; gap: 0.5rem; min-width: 0; }
    .category-legend-dot { width: 8px; height: 8px; flex-shrink: 0; }
    .cat-stat-name { overflow-wrap: anywhere; }
    .cat-stat-right { display: flex; gap: 0.75rem; flex-shrink: 0; font-family: var(--font-mono); font-size: 0.78rem; }
    .cat-stat-pct { width: 2.5rem; text-align: right; color: var(--text-muted); }
    .analytics-perf-tools { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: baseline; gap: 0.25rem 2rem; }
    .analytics-perf-picker { display: flex; align-items: baseline; gap: 0.6rem; min-width: 0; max-width: 100%; }
    .health-section { margin: 3.5rem 0 0; background: none; border: none; padding: 0; box-shadow: none; }
    .health-status { font-family: var(--font-serif); font-size: 1.1rem; line-height: 1.45; padding-top: 0.75rem; overflow-wrap: anywhere; }
    .health-status.is-alert { color: var(--neg); }
    .health-grid { grid-template-columns: repeat(5, minmax(0, 1fr)); margin-bottom: 0; }

    @media (max-width: 860px) {
      .analytics-grid { gap: 2.75rem; }
      .analytics-donut-layout { grid-template-columns: minmax(0, 1fr); gap: 0.75rem; }
      .chart-canvas-container { height: 260px; }
      .chart-canvas-donut { height: 220px; }
      .health-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    }

    /* Home: front page */
    .fp-masthead { margin-bottom: 2rem; max-width: 46rem; }
    .fp-dateline { font-size: 0.8rem; color: var(--text-muted); margin-bottom: 0.9rem; }
    .fp-title { font-size: clamp(2.3rem, 5vw, 3.5rem); line-height: 1.05; letter-spacing: -0.022em; margin-bottom: 0.9rem; }
    .fp-standfirst { font-family: var(--font-serif); font-size: 1.2rem; line-height: 1.45; color: var(--text-secondary); }

    .fp-grid { display: grid; grid-template-columns: minmax(0, 2fr) minmax(0, 1fr); gap: 4rem; margin-bottom: 4rem; }
    .fp-kicker { font-size: 0.8rem; color: var(--accent); font-weight: 500; margin-bottom: 0.5rem; }
    .fp-lead-title { font-size: clamp(1.6rem, 3vw, 2.15rem); line-height: 1.15; margin-bottom: 0.7rem; }
    .fp-lead-title a { color: inherit; text-decoration: none; }
    .fp-lead-title a:hover, .fp-row-title:hover { color: var(--accent); }
    .fp-lead-summary { font-size: 1.02rem; line-height: 1.6; color: var(--text-secondary); margin-bottom: 0.8rem; max-width: 38rem; }
    .fp-meta { display: flex; flex-wrap: wrap; align-items: baseline; gap: 0.3rem 1rem; font-size: 0.78rem; color: var(--text-muted); padding-bottom: 1.5rem; }

    .fp-list { list-style: none; border-top: 1px solid var(--text-primary); }
    .fp-row { display: grid; grid-template-columns: 3.75rem minmax(0, 1fr) auto; gap: 0.75rem; align-items: baseline; padding: 0.8rem 0; border-bottom: 1px solid var(--border-subtle); }
    .fp-row-title { font-family: var(--font-serif); font-size: 1.1rem; line-height: 1.3; color: inherit; text-decoration: none; }
    .fp-score { font-family: var(--font-mono); font-size: 0.8rem; color: var(--text-muted); cursor: help; }
    /* Replaces inline styles, which the Content-Security-Policy forbids. */
    .sidebar-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 2.25rem; }
    .action-small { font-size: 0.75rem; }
    .dropdown-section-title.is-spaced { margin-top: 0.6rem; }
    .tone-up { color: var(--pos); }
    .tone-down { color: var(--neg); }
    .tone-flat { color: var(--text-muted); }
    .tone-strong { font-weight: 700; }
    .lookup-note { font-size: 0.8rem; line-height: 1.4; color: var(--text-muted); }
    .lookup-body { padding: 0.25rem 0; }
    .lookup-gap { margin-top: 0.25rem; }
    .lookup-hint { margin-top: 0.35rem; font-size: 0.72rem; }
    .lookup-small { font-size: 0.72rem; }
    .lookup-name { margin-left: 0.4rem; font-size: 0.88rem; font-weight: 700; color: var(--text-primary); }
    .lookup-from { margin-left: 0.3rem; font-size: 0.72rem; color: var(--text-muted); }
    .lookup-badge-gap { margin-left: 0.35rem; }
    .lookup-source { font-weight: 600; color: var(--text-secondary); }
    .lookup-read { margin-left: auto; font-weight: 700; color: var(--accent); }

    /* Small list styles shared by the economy and company pages. */
    .fp-more { display: inline-block; margin-top: 0.9rem; font-size: 0.88rem; font-weight: 600; color: var(--accent); text-decoration: none; }
    .fp-more:hover { text-decoration: underline; text-underline-offset: 3px; }
    .fp-empty { color: var(--text-muted); font-size: 0.92rem; padding: 0.5rem 0; }
    .fp-heading { font-size: 1.15rem; padding-bottom: 0.5rem; border-bottom: 1px solid var(--border-card); }
    .fp-side-list { list-style: none; }
    .fp-event, .fp-indicator { padding: 0.6rem 0; border-bottom: 1px solid var(--border-subtle); font-size: 0.86rem; }
    .fp-event { display: grid; grid-template-columns: 3.5rem minmax(0, 1fr); gap: 0.5rem; align-items: baseline; }
    .fp-event-date { font-size: 0.76rem; color: var(--text-muted); }
    .fp-indicator { display: flex; justify-content: space-between; align-items: baseline; gap: 1rem; color: var(--text-secondary); }
    .fp-indicator-value { font-size: 0.82rem; color: var(--text-primary); white-space: nowrap; }

    /* Home: search bar orbited by the watchlist. The sidebar becomes a top bar here only. */
    .page-home .app-layout { display: block; }
    .page-home .app-main { max-width: none; padding: 0 !important; }

    @media (min-width: 1025px) {
      .page-home .app-sidebar {
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        width: auto;
        min-width: 0;
        max-width: none;
        height: auto;
        flex-direction: row;
        align-items: center;
        gap: 2rem;
        padding: 1.1rem 2rem;
        background: transparent;
        border: 0;
        overflow: visible;
      }
      .page-home .sidebar-head { margin: 0; }
      .page-home .sidebar-nav { flex-direction: row; gap: 1.5rem; flex: 1; }
      .page-home .nav-link { gap: 0.4rem; }
      .page-home .sidebar-footer { display: flex; align-items: center; gap: 1.25rem; margin: 0; padding: 0; }
      .page-home .theme-toggle { margin: 0; }
    }

    @media (max-width: 1024px) {
      .page-home .mobile-top-header { background: transparent; border: 0; position: absolute; width: 100%; }
    }

    .orbit-hero {
      position: relative;
      display: flex;
      flex-direction: column;
      align-items: center;
      min-height: 100vh;
      min-height: 100svh;
      overflow-x: clip;
    }

    .orbit-dust {
      position: absolute;
      inset: 0;
      width: 100%;
      height: 100%;
      pointer-events: none;
      z-index: 0;
    }

    .hero-copy {
      position: relative;
      z-index: 60;
      text-align: center;
      padding: clamp(4.25rem, 10vh, 6.5rem) 1rem 0;
      pointer-events: none;
    }

    .hero-headline {
      font-family: var(--font-display);
      font-weight: 700;
      font-size: clamp(1.25rem, 2.5vw, 2.1rem);
      line-height: 1.15;
      letter-spacing: 0;
      margin-top: 0.55rem;
    }

    .hero-orbit-stage {
      position: relative;
      flex: 1;
      width: 100%;
      min-height: 480px;
      cursor: grab;
      touch-action: pan-y;
    }

    .hero-orbit-stage.is-dragging { cursor: grabbing; }

    .hero-orbit-stage .search-wrapper {
      position: absolute;
      top: 36%;
      left: 50%;
      width: min(620px, calc(100% - 2rem));
      margin: 0;
      transform: translate(-50%, calc(-50% - var(--bar-lift, 0px)));
      transition: transform 0.28s ease-out;
      cursor: auto;
    }

    .hero-orbit-stage .search-dropdown { max-height: min(40vh, 340px); }

    .orbit-ring {
      list-style: none;
      position: absolute;
      inset: 0;
      pointer-events: none;
    }

    .orbit-slot {
      position: absolute;
      top: 0;
      left: 0;
      pointer-events: auto;
      will-change: transform, opacity;
    }

    .orbit-slot[hidden] { display: none; }

    .orbit-chip {
      display: block;
      width: 156px;
      padding: 0.6rem 0.8rem 0.65rem;
      color: var(--text-primary);
      text-decoration: none;
      background: var(--bg-surface-elevated);
      border: 1px solid var(--border-card);
      border-radius: 14px;
      user-select: none;
      -webkit-user-drag: none;
    }

    .orbit-chip:hover { border-color: var(--accent); }
    .orbit-chip:focus-visible { outline-offset: 3px; border-color: var(--accent); }

    .orbit-ticker { display: block; font-size: 1.45rem; font-weight: 700; line-height: 1.1; letter-spacing: -0.01em; }
    .orbit-name { display: block; font-size: 0.74rem; color: var(--text-secondary); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .orbit-fact { display: flex; align-items: center; gap: 0.35rem; margin-top: 0.3rem; font-size: 0.74rem; color: var(--text-muted); white-space: nowrap; }
    .orbit-dot { width: 7px; height: 7px; border-radius: 50%; background: var(--text-muted); flex-shrink: 0; }
    .orbit-dot.is-high { background: var(--accent); }

    .orbit-browse {
      position: absolute;
      left: 50%;
      bottom: 1.1rem;
      transform: translateX(-50%);
      z-index: 70;
      color: var(--accent);
      font-weight: 600;
      font-size: 0.95rem;
      white-space: nowrap;
      text-underline-offset: 3px;
      padding: 0.4rem 0.6rem;
    }

    /* The default until the script proves motion is welcome: a plain grid of the same links. */
    .orbit-static.hero-orbit-stage { flex: none; min-height: 0; cursor: auto; touch-action: auto; padding: 1.75rem 1rem 0; }
    .orbit-static .search-wrapper { position: relative; top: auto; left: auto; transform: none; width: 100%; max-width: 620px; margin: 0 auto 1.75rem; }
    .orbit-static .orbit-ring {
      position: static;
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
      gap: 0.75rem;
      max-width: 1000px;
      margin: 0 auto;
      pointer-events: auto;
    }
    .orbit-static .orbit-slot { position: static; will-change: auto; }
    .orbit-static .orbit-slot.is-dim { opacity: 0.3; }
    .orbit-static .orbit-chip { width: auto; }
    .orbit-hero:has(.orbit-static) { min-height: 0; }
    .orbit-hero:has(.orbit-static) .orbit-browse { position: static; transform: none; display: block; text-align: center; margin: 1.25rem 0 0; }
    .orbit-hero:has(.orbit-static) .orbit-dust { display: none; }

    @media (max-width: 640px) {
      .hero-copy { padding-top: 3.75rem; }
      .search-box { height: 58px; padding: 0 1rem; }
      .search-shortcut { display: none; }
      .dropdown-tabs-grid { grid-template-columns: minmax(0, 1fr); }
      .orbit-chip { width: 110px; padding: 0.4rem 0.55rem 0.45rem; border-radius: 12px; }
      .orbit-ticker { font-size: 1.1rem; }
      .orbit-name, .orbit-fact { font-size: 0.66rem; }
      .orbit-browse { bottom: calc(3.6rem + env(safe-area-inset-bottom)); }
    }

    .home-below {
      max-width: 1180px;
      margin: 0 auto;
      padding: 3rem 2rem 4rem;
    }

    .home-doors {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 1rem;
      margin-bottom: 3.5rem;
    }

    .door {
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      gap: 1.5rem;
      min-height: 164px;
      padding: 1.35rem 1.4rem;
      background: var(--bg-surface);
      border: 1px solid var(--border-card);
      border-radius: 16px;
      color: inherit;
      text-decoration: none;
    }

    .door:hover { border-color: var(--accent); }
    .door:hover .door-title { color: var(--accent); }
    .door-title { font-size: 1.55rem; font-weight: 700; letter-spacing: -0.015em; line-height: 1.1; }
    .door-line { font-size: 0.95rem; line-height: 1.4; color: var(--text-secondary); overflow-wrap: anywhere; }

    .home-heading { font-size: 1.3rem; font-weight: 700; margin-bottom: 0.75rem; }
    .home-heading-row { display: flex; justify-content: space-between; align-items: baseline; gap: 1rem; }

    .home-stories { margin-bottom: 3.5rem; }
    .top-list { list-style: none; border-top: 1px solid var(--border-card); }

    .top-row {
      display: grid;
      grid-template-columns: 3rem 4.5rem minmax(0, 1fr) auto;
      gap: 0.75rem;
      align-items: baseline;
      padding: 0.95rem 0;
      border-bottom: 1px solid var(--border-subtle);
    }

    .top-ticker { font-weight: 700; color: var(--text-primary); text-decoration: none; }
    .top-ticker:hover, .top-title:hover { color: var(--accent); }
    .top-title { font-size: 1.05rem; font-weight: 500; color: var(--text-primary); text-decoration: none; overflow-wrap: anywhere; }
    .top-date { font-size: 0.82rem; color: var(--text-muted); white-space: nowrap; }
    .home-more { display: inline-block; margin-top: 0.9rem; color: var(--accent); font-weight: 600; text-underline-offset: 3px; }
    .home-empty { color: var(--text-muted); padding: 1rem 0; }

    .recent-list { list-style: none; display: flex; flex-wrap: wrap; gap: 0.6rem; }
    .recent-list a { display: flex; align-items: baseline; gap: 0.55rem; padding: 0.55rem 0.8rem; background: var(--bg-surface); border: 1px solid var(--border-card); border-radius: 12px; color: inherit; text-decoration: none; }
    .recent-list a:hover { border-color: var(--accent); }
    .recent-ticker { font-weight: 700; }
    .recent-name, .recent-when { font-size: 0.8rem; color: var(--text-muted); }
    .home-clear { background: none; border: 0; color: var(--text-muted); text-decoration: underline; text-underline-offset: 3px; cursor: pointer; font-size: 0.85rem; min-height: 24px; }

    @media (max-width: 1024px) {
      .home-doors { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    }

    @media (max-width: 640px) {
      .home-below { padding: 2rem 1rem calc(5rem + env(safe-area-inset-bottom)); }
      .home-doors { gap: 0.65rem; }
      .door { min-height: 128px; padding: 1rem; gap: 0.9rem; }
      .door-title { font-size: 1.2rem; }
      .door-line { font-size: 0.85rem; }
      .top-row { grid-template-columns: 2.4rem 3.6rem minmax(0, 1fr); }
      .top-date { display: none; }
    }

    /* Recently Viewed Companies Quick Access Deck */
    .recently-viewed-section {
      margin-bottom: 2.75rem;
      width: 100%;
      position: relative;
      z-index: 1;
    }

    /* Ticker & Form Badges */
    .ticker-badge {
      font-family: var(--font-mono);
      font-weight: 500;
      font-size: 0.8rem;
      color: var(--text-primary);
      text-decoration: none;
      letter-spacing: 0.01em;
    }

    a.ticker-badge:hover { color: var(--accent); }

    /* Action Link */
    .action-link {
      color: var(--accent-blue);
      text-decoration: none;
      font-weight: 600;
      font-size: 0.85rem;
      display: inline-flex;
      align-items: center;
      gap: 0.25rem;
      transition: all var(--transition-fast);
      white-space: nowrap;
    }

    .action-link:hover {
      color: var(--accent);
      transform: translateX(2px);
    }

    /* Table Styles */



    tr.news-row:hover td {
      background: var(--bg-surface);
    }

    /* Restraint: type, spacing and rules do the structuring. No boxes around content, no shadows
       on anything that isn't floating, no decoration. Later rules here deliberately win. */
    @media (prefers-reduced-motion: no-preference) {
      @view-transition { navigation: auto; }
      a, button { transition: opacity 0.16s ease-out; }
    }

    body { font-size: 1rem; -webkit-font-smoothing: antialiased; }
    main a:hover { opacity: 0.62; }
    main a:active, .nav-link:active, .mobile-tab-link:active, button:active { opacity: 0.45; }

    .app-sidebar { padding: 1.75rem 1.5rem; }
    .nav-link { padding: 0.4rem 0; font-size: 0.95rem; color: var(--text-muted); }
    .nav-link:hover { color: var(--text-primary); }
    .nav-link.active { color: var(--text-primary); font-weight: 600; }
    .brand-title { font-size: 1.15rem; font-weight: 600; letter-spacing: -0.015em; }
    .orbit-dust { display: none; }
    .hero-headline { font-size: clamp(3.25rem, 8vw, 6.5rem); font-weight: 600; line-height: 1; letter-spacing: -0.03em; margin-top: 0; }
    .hero-sub { margin-top: 0.9rem; font-size: clamp(1.1rem, 2vw, 1.6rem); line-height: 1.35; letter-spacing: -0.01em; color: var(--text-muted); }
    .sidebar-footer { font-size: 0.78rem; }
    .theme-toggle { text-decoration: none; color: var(--text-muted); font-size: 0.78rem; }
    .mobile-tab-link { font-size: 0.76rem; border-top: 0; margin-top: 0; }
    .mobile-tab-link.active { font-weight: 600; }
    .mobile-bottom-nav { border-top-color: var(--border-subtle); }

    /* Search */
    .search-box { height: 60px; background: var(--bg-surface-elevated); border: 1px solid transparent; border-radius: 16px; }
    .search-box:hover { border-color: transparent; }
    .search-box:focus-within { background: var(--bg-base); border-color: var(--text-primary); }
    .search-input { font-size: 1.08rem; font-weight: 400; }
    .search-shortcut { border: 0; font-weight: 500; padding: 0; }
    .search-dropdown { border-radius: 16px; border-color: var(--border-subtle); padding: 0.5rem 1.25rem 1rem; }

    /* Home: the ring is type floating in space, not a set of cards */
    .hero-orbit-stage .search-wrapper { width: min(560px, calc(100% - 2rem)); }
    .orbit-chip { background: none; border: 0; border-radius: 10px; padding: 0.35rem 0.5rem; text-align: center; }
    .orbit-ticker { font-size: 1.7rem; font-weight: 600; letter-spacing: -0.02em; }
    .orbit-name { font-size: 0.76rem; color: var(--text-muted); }
    .orbit-fact { justify-content: center; font-size: 0.76rem; margin-top: 0.15rem; }
    .orbit-dot { width: 6px; height: 6px; background: var(--border-card); }
    .orbit-dot.is-high { background: var(--accent); }
    .orbit-browse, .home-more, .fp-more { color: var(--accent); font-weight: 400; font-size: 1rem; text-decoration: none; }
    .orbit-spark { display: block; width: 66%; height: 20px; margin: 0.2rem auto 0.05rem; overflow: visible; }
    .orbit-spark polyline { fill: none; stroke-width: 1.75; stroke-linejoin: round; stroke-linecap: round; vector-effect: non-scaling-stroke; }
    .orbit-spark.is-up polyline { stroke: var(--pos); }
    .orbit-spark.is-down polyline { stroke: var(--neg); }
    .orbit-move { display: block; font-size: 0.86rem; font-weight: 600; white-space: nowrap; }
    .orbit-note { position: absolute; left: 0; right: 0; bottom: 3.4rem; z-index: 70; text-align: center; font-size: 0.8rem; color: var(--text-muted); pointer-events: none; }
    .orbit-static .orbit-spark { margin-left: 0; }
    .orbit-hero:has(.orbit-static) .orbit-note { position: static; margin-top: 1.5rem; }
    .orbit-static .orbit-ring { gap: 1.25rem 0.5rem; }
    .orbit-static .orbit-chip { text-align: left; }
    .orbit-static .orbit-fact { justify-content: flex-start; }

    .home-heat { max-width: 1180px; margin: 0 auto; padding: 5rem 1.5rem 0; }
    .heat-heading { font-size: clamp(2rem, 4.5vw, 3.25rem); font-weight: 600; line-height: 1.08; letter-spacing: -0.025em; }
    .heat-sub { margin-top: 0.5rem; font-size: 1.1rem; color: var(--text-muted); }
    .heat-grid { display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); gap: 2px; margin-top: 1.75rem; list-style: none; border-radius: 16px; overflow: hidden; }
    .heat-tile { display: flex; flex-direction: column; justify-content: space-between; gap: 1.25rem; height: 100%; padding: 0.9rem 1rem; text-decoration: none; }
    .heat-ticker { font-size: 1.2rem; font-weight: 600; letter-spacing: -0.015em; }
    .heat-move { font-size: 0.95rem; font-weight: 500; }
    .heat-u1 { background: var(--heat-u1); color: var(--heat-u1-ink); }
    .heat-u2 { background: var(--heat-u2); color: var(--heat-u2-ink); }
    .heat-u3 { background: var(--heat-u3); color: var(--heat-u3-ink); }
    .heat-n { background: var(--heat-n); color: var(--heat-n-ink); }
    .heat-d1 { background: var(--heat-d1); color: var(--heat-d1-ink); }
    .heat-d2 { background: var(--heat-d2); color: var(--heat-d2-ink); }
    .heat-d3 { background: var(--heat-d3); color: var(--heat-d3-ink); }

    .home-below { max-width: 52rem; padding: 5rem 1.5rem 7rem; }
    .home-heading { font-size: 0.95rem; font-weight: 600; color: var(--text-muted); letter-spacing: 0; margin-bottom: 0.25rem; }
    .home-stories { margin-bottom: 5rem; }
    .top-list { border-top: 0; }
    .top-row { grid-template-columns: 4.5rem minmax(0, 1fr) auto; gap: 0.5rem; padding: 0.85rem 0; }
    .top-row:last-child { border-bottom: 0; }
    .top-ticker { font-size: 0.86rem; font-weight: 600; color: var(--text-muted); }
    .top-title { font-size: 1.1rem; font-weight: 500; line-height: 1.35; letter-spacing: -0.005em; }
    .top-date { font-size: 0.84rem; }
    .top-row.is-lead { grid-template-columns: minmax(0, 1fr) auto; padding: 1rem 0 2rem; }
    .top-row.is-lead .top-body { grid-column: 1 / -1; grid-row: 2; }
    .top-row.is-lead .top-title { font-size: clamp(1.75rem, 4vw, 2.6rem); font-weight: 600; line-height: 1.1; letter-spacing: -0.024em; }
    .top-summary { margin-top: 0.25rem; max-width: 38rem; font-size: 0.95rem; line-height: 1.5; color: var(--text-secondary); }
    .top-row.is-lead .top-summary { margin-top: 0.8rem; font-size: 1.1rem; }

    .home-doors { display: block; margin-bottom: 4rem; border-top: 1px solid var(--border-card); }
    .door { flex-direction: row; align-items: baseline; gap: 1.5rem; min-height: 0; padding: 1.15rem 0; background: none; border: 0; border-bottom: 1px solid var(--border-subtle); border-radius: 0; }
    .door:hover .door-title { color: inherit; }
    .door-title { font-size: 1.3rem; font-weight: 600; flex: none; width: 10rem; }
    .door-line { font-size: 1rem; color: var(--text-muted); }

    .recent-list { gap: 0.4rem 1.75rem; }
    .recent-list a { padding: 0.25rem 0; background: none; border: 0; border-radius: 0; }
    .home-clear { text-decoration: none; }

    /* Feed: edited like a front page, dense below the fold */
    .page-feed .app-main { max-width: 60rem; }
    .page-feed .page-header { margin-bottom: 1.75rem; }
    .feed-search { background: var(--bg-surface-elevated); border: 1px solid transparent; border-radius: 12px; padding: 0.7rem 1rem; }
    .feed-search:focus { background: var(--bg-base); border-color: var(--text-primary); }
    .company-feed-tools .feed-search { border: 1px solid transparent; padding: 0.55rem 0.9rem; }
    .feed-sort-btn.active { color: var(--text-primary); }
    .feed-group { padding: 3rem 0 0.4rem; border-bottom: 1px solid var(--border-card); justify-content: space-between; }
    .feed-group-title { font-size: 0.95rem; font-weight: 600; letter-spacing: 0; }
    .feed-group-note { font-size: 0.84rem; }
    .news-row { grid-template-columns: 4rem minmax(0, 1fr) 3.5rem; gap: 0.5rem; padding: 0.7rem 0; }
    .ticker-badge { font-weight: 600; color: var(--text-muted); }
    .feed-headline, .news-row.is-high .feed-headline { font-size: 1.04rem; font-weight: 500; line-height: 1.35; letter-spacing: -0.005em; }
    .news-row[hidden] { display: none; }
    .feed-summary { margin-top: 0.3rem; max-width: 44rem; font-size: 0.95rem; line-height: 1.5; color: var(--text-secondary); overflow-wrap: anywhere; }
    .fig { font-weight: 600; color: var(--text-primary); }
    .feed-meta { font-size: 0.78rem; }
    .feed-details summary .feed-meta::after { content: ' · More'; }
    .feed-details[open] summary .feed-meta::after { content: ' · Less'; }
    .date-cell { font-size: 0.8rem; }
    .news-row.is-lead { grid-template-columns: minmax(0, 1fr) auto; padding: 1.25rem 0 1.75rem; }
    .news-row.is-lead .feed-body { grid-column: 1 / -1; grid-row: 2; }
    .news-row.is-lead .feed-headline { font-size: clamp(1.45rem, 3vw, 2rem); font-weight: 600; line-height: 1.14; letter-spacing: -0.02em; }
    .news-row.is-lead .feed-summary { margin-top: 0.6rem; font-size: 1.06rem; }
    .news-row.is-lead .feed-details { margin-top: 0.35rem; }
    .feed-more { display: block; margin-top: 0.9rem; min-height: 36px; background: none; border: 0; color: var(--accent); font-size: 0.95rem; cursor: pointer; }

    /* Companies */
    .company-news-item { grid-template-columns: minmax(0, 1fr) 3.25rem; }
    .company-profile-container, .company-browser-sector-name, .econ-ledger, .fp-list { border-color: var(--border-card); }
    .company-hero-symbol { font-weight: 500; }
    .company-hero-name { font-size: clamp(2.2rem, 5vw, 3.5rem); font-weight: 600; letter-spacing: -0.028em; }
    .company-price { display: flex; flex-wrap: wrap; align-items: baseline; gap: 0.2rem 0.7rem; margin-bottom: 1rem; }
    .company-price-val { font-size: clamp(1.75rem, 3.5vw, 2.5rem); font-weight: 500; letter-spacing: -0.02em; }
    .company-price-move { font-size: 1.25rem; font-weight: 600; }
    .company-price-span { font-size: 0.95rem; color: var(--text-muted); }
    .company-links a { color: var(--accent); }
    .company-kpi-val, .perf-kpi-val { font-weight: 500; }
    .fp-heading { font-weight: 600; font-size: 1.25rem; border-bottom-color: var(--border-subtle); }

    /* Calendar: colour says what kind of event it is, a hollow mark says it's estimated */
    .cal-track { height: 84px; border-bottom-color: var(--border-card); }
    .cal-mark, .cal-key { width: 9px; height: 9px; margin-left: -4px; border-radius: 50%; background: var(--text-muted); }
    .cal-key { display: inline-block; margin: 0 0.4rem 0 0; }
    .cal-mark[data-event-type*="Earnings"], .cal-key.is-earnings { background: var(--series-1); }
    .cal-mark[data-event-type*="Dividend"], .cal-key.is-dividend { background: var(--series-4); }
    .cal-mark[data-event-type*="SEC"], .cal-key.is-sec { background: var(--series-5); }
    .cal-mark[data-event-type*="Conference"], .cal-key.is-conference { background: var(--series-6); }
    .cal-mark:hover { background: var(--text-primary); }
    .cal-mark.is-estimated, .cal-mark.is-estimated:hover { background: var(--bg-base); box-shadow: inset 0 0 0 2px var(--series-5); }
    .cal-key.is-estimated { background: transparent; box-shadow: inset 0 0 0 2px var(--text-muted); }
    .cal-today { font-weight: 600; border-left-color: var(--accent); color: var(--accent); }
    .cal-week-title { border-bottom-color: var(--border-card); font-size: 1.25rem; font-weight: 600; }
    .calendar-card[data-event-type*="Earnings"] .cal-details::before,
    .calendar-card[data-event-type*="Dividend"] .cal-details::before,
    .calendar-card[data-event-type*="SEC"] .cal-details::before,
    .calendar-card[data-event-type*="Conference"] .cal-details::before { content: ''; display: inline-block; width: 7px; height: 7px; margin-right: 0.4rem; border-radius: 50%; vertical-align: 0.06em; }
    .calendar-card[data-event-type*="Earnings"] .cal-details::before { background: var(--series-1); }
    .calendar-card[data-event-type*="Dividend"] .cal-details::before { background: var(--series-4); }
    .calendar-card[data-event-type*="SEC"] .cal-details::before { background: var(--series-5); }
    .calendar-card[data-event-type*="Conference"] .cal-details::before { background: var(--series-6); }
    .cal-source { color: var(--accent); }

    /* Economy */
    .economic-series-name { font-weight: 600; letter-spacing: -0.015em; }
    .economic-val { font-size: 1.6rem; font-weight: 500; }
    .mx-dot { width: 9px; height: 9px; border-radius: 50%; background: var(--accent); }
    .econ-select { background: var(--bg-surface-elevated); border: 0; border-radius: 8px; padding: 0.35rem 0.6rem; }
    .sparkline-tooltip { border-radius: 6px; padding: 0.2rem 0.5rem; }

    @media (min-width: 641px) and (max-width: 1024px) {
      .heat-grid { grid-template-columns: repeat(5, minmax(0, 1fr)); }
    }

    @media (max-width: 640px) {
      .home-below { padding: 3.5rem 1.15rem calc(6rem + env(safe-area-inset-bottom)); }
      .orbit-chip { width: 112px; padding: 0.2rem 0.25rem; }
      .orbit-ticker { font-size: 1.3rem; }
      .orbit-name { display: none; }
      .orbit-spark { display: none; }
      .orbit-static .orbit-spark { display: block; height: 20px; }
      .orbit-move { font-size: 0.74rem; }
      .orbit-note { bottom: calc(5.4rem + env(safe-area-inset-bottom)); font-size: 0.72rem; }
      .home-heat { padding: 3.5rem 1.15rem 0; }
      .heat-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); border-radius: 12px; }
      .heat-tile { padding: 0.65rem 0.7rem; gap: 0.75rem; }
      .heat-ticker { font-size: 1.02rem; }
      .heat-move { font-size: 0.82rem; }
      .orbit-fact { font-size: 0.68rem; margin-top: 0; }
      .orbit-static .orbit-name { display: block; }
      .search-box { height: 54px; }
      .top-row { grid-template-columns: 3.6rem minmax(0, 1fr); }
      .door { flex-direction: column; gap: 0.15rem; padding: 0.95rem 0; }
      .door-title { width: auto; font-size: 1.15rem; }
      .door-line { font-size: 0.92rem; }
      .news-row { grid-template-columns: minmax(0, 1fr) auto; gap: 0.1rem 0.5rem; }
      .news-row .feed-body { grid-column: 1 / -1; grid-row: 2; }
    }

    /* ---- Following ---- */
    .view-tabs { display: flex; justify-content: center; gap: 1.75rem; margin: 0.5rem 0 1.75rem; border-bottom: 1px solid var(--border-subtle); }
    .view-tabs-left { justify-content: flex-start; margin: 0 0 1rem; }
    .view-tab { background: none; border: none; border-bottom: 2px solid transparent; margin-bottom: -1px; padding: 0.55rem 0; min-height: 44px; font: inherit; font-size: 0.98rem; color: var(--text-muted); cursor: pointer; }
    .view-tab:hover { color: var(--text-primary); }
    .view-tab.active { color: var(--text-primary); font-weight: 600; border-bottom-color: var(--text-primary); }
    .view-tab:focus-visible, .follow-btn:focus-visible, .link-btn:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
    .follow-btn { flex: none; border: none; border-radius: var(--radius-full); padding: 0.4rem 1rem; min-height: 32px; font: inherit; font-size: 0.86rem; font-weight: 600; background: var(--accent); color: var(--on-accent); cursor: pointer; transition: background var(--transition-fast), color var(--transition-fast); }
    .follow-btn[aria-pressed="true"] { background: var(--bg-hover); color: var(--text-primary); }
    .company-hero-title-row { display: flex; align-items: center; gap: 1rem; flex-wrap: wrap; }
    .follow-footer { margin-top: 0.75rem; font-size: 0.84rem; color: var(--text-muted); }
    .follow-footer a { color: var(--text-secondary); }
    .link-btn { background: none; border: none; padding: 0; font: inherit; color: var(--text-secondary); text-decoration: underline; text-underline-offset: 2px; cursor: pointer; }
    .link-btn:hover, .follow-footer a:hover { color: var(--text-primary); }
    .follow-reason { margin-top: 0.3rem; font-size: 0.78rem; color: var(--text-muted); }
    .follow-suggest { list-style: none; margin: 0.75rem 0 1rem; padding: 0; }
    .follow-suggest-title { margin-top: 2rem; font-size: 0.95rem; font-weight: 600; color: var(--text-primary); }
    .follow-suggest li { display: flex; align-items: center; justify-content: space-between; gap: 1rem; padding: 0.6rem 0; border-bottom: 1px solid var(--border-subtle); }
    .follow-suggest-name { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--text-primary); }
    .company-browser-card.is-followed .company-browser-card-sec::after { content: " · Following"; color: var(--accent); }
    .setup-banner { position: fixed; z-index: 400; left: 50%; bottom: 1.25rem; transform: translateX(-50%); width: min(36rem, calc(100% - 2rem)); display: flex; align-items: center; flex-wrap: wrap; gap: 0.6rem 1rem; padding: 0.9rem 1rem; border-radius: var(--radius-lg); background: var(--bg-surface-elevated); border: 1px solid var(--border-subtle); box-shadow: var(--shadow-dropdown); color: var(--text-primary); font-size: 0.92rem; }
    .setup-banner p { flex: 1 1 100%; margin: 0; }
    @media (max-width: 1024px) { .setup-banner { bottom: calc(4.5rem + env(safe-area-inset-bottom, 0px)); } }
    .picker { max-width: 46rem; margin: 0 auto 2.5rem; padding: 0 1rem; text-align: center; }
    .picker-title { font-size: 1.6rem; font-weight: 600; letter-spacing: -0.01em; color: var(--text-primary); }
    .picker-sub { margin: 0.4rem 0 1.25rem; color: var(--text-secondary); }
    .picker-chips { display: flex; flex-wrap: wrap; gap: 0.5rem; }
    .picker .picker-chips { justify-content: center; }
    .chip { border: 1px solid var(--border-subtle); border-radius: var(--radius-full); padding: 0.45rem 0.95rem; min-height: 40px; font: inherit; font-size: 0.92rem; background: none; color: var(--text-primary); cursor: pointer; transition: background var(--transition-fast), color var(--transition-fast), border-color var(--transition-fast); }
    .chip:hover { border-color: var(--text-muted); }
    .chip[aria-pressed="true"] { background: var(--text-primary); border-color: var(--text-primary); color: var(--bg-base); }
    .chip-count { margin-left: 0.25rem; opacity: 0.6; font-size: 0.82rem; }
    .chip:focus-visible, .type-toggle:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
    .picker-actions { display: flex; flex-wrap: wrap; align-items: center; justify-content: center; gap: 0.5rem 1.25rem; margin-top: 1.5rem; }
    .picker-more { font-size: 0.9rem; color: var(--text-secondary); }
    .setup-yes:disabled { opacity: 0.4; cursor: default; }
    .settings-section { max-width: 44rem; padding: 1.75rem 0; border-top: 1px solid var(--border-subtle); }
    .settings-heading { font-size: 1.15rem; font-weight: 600; color: var(--text-primary); margin-bottom: 0.4rem; }
    .settings-note { margin: 0 0 1rem; font-size: 0.9rem; color: var(--text-secondary); max-width: 36rem; }
    .settings-subheading { margin: 1.5rem 0 0.1rem; font-size: 0.82rem; font-weight: 600; color: var(--text-muted); }
    .settings-group[hidden], .settings-group li[hidden] { display: none; }
    .settings-group { border-bottom: 1px solid var(--border-subtle); }
    .settings-group-head { display: flex; align-items: baseline; justify-content: space-between; gap: 1rem; padding: 0.9rem 0; min-height: 44px; cursor: pointer; list-style: none; }
    .settings-group-head::-webkit-details-marker { display: none; }
    .settings-group-name { font-weight: 600; color: var(--text-primary); }
    .settings-group-name::after { content: " +"; color: var(--text-muted); font-weight: 400; }
    .settings-group[open] .settings-group-name::after { content: " –"; }
    .settings-group-meta { font-size: 0.84rem; color: var(--text-muted); }
    .settings-group .follow-suggest { margin: 0 0 0.75rem; }
    .settings-group .follow-suggest li:last-child { border-bottom: none; }
    .settings-co { display: flex; align-items: baseline; gap: 0.6rem; text-decoration: none; color: var(--text-primary); }
    .settings-co:hover .settings-co-name { text-decoration: underline; text-underline-offset: 2px; }
    .settings-co-ticker { flex: none; width: 3.4rem; font-size: 0.78rem; font-weight: 600; letter-spacing: 0.02em; color: var(--text-muted); }
    .settings-co-name { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .settings-via { margin-left: auto; font-size: 0.8rem; color: var(--text-muted); }
    .settings-via[hidden] { display: none; }
    .settings-toggles { list-style: none; margin: 0; padding: 0; }
    .type-toggle { display: flex; width: 100%; align-items: center; justify-content: space-between; gap: 1rem; padding: 0.8rem 0; border: none; border-bottom: 1px solid var(--border-subtle); background: none; font: inherit; text-align: left; color: var(--text-primary); cursor: pointer; }
    .type-toggle-text { display: flex; flex-direction: column; }
    .type-toggle-count { font-size: 0.8rem; color: var(--text-muted); }
    .switch { position: relative; flex: none; width: 2.6rem; height: 1.55rem; border-radius: var(--radius-full); background: var(--bg-hover); transition: background var(--transition-fast); }
    .switch::after { content: ""; position: absolute; top: 0.18rem; left: 0.18rem; width: 1.19rem; height: 1.19rem; border-radius: 50%; background: var(--bg-base); border: 1px solid var(--border-subtle); transition: transform var(--transition-fast); }
    .type-toggle[aria-pressed="true"] .switch { background: var(--accent); }
    .type-toggle[aria-pressed="true"] .switch::after { transform: translateX(1.05rem); border-color: transparent; }
    .settings-actions { display: flex; flex-wrap: wrap; gap: 0.5rem 1.25rem; align-items: center; }
    .setup-yes { border: none; border-radius: var(--radius-full); padding: 0.45rem 1.1rem; min-height: 36px; font: inherit; font-weight: 600; background: var(--accent); color: var(--on-accent); cursor: pointer; }
    .setup-no { background: none; border: none; min-height: 36px; font: inherit; color: var(--text-secondary); cursor: pointer; }
"""

# ==============================================================================
# RESPONSIVE NAVIGATION MACROS (SIDEBAR + MOBILE HEADER + MOBILE BOTTOM NAV)
# ==============================================================================
NAVIGATION_LAYOUT_HTML = """
<div class="mobile-top-header">
  <a href="index.html" class="sidebar-brand"><span class="brand-title">StockPulse</span></a>
  <div class="mobile-header-right">
    <button class="mobile-action-btn" data-click="focusMobileSearch" aria-label="Search">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></svg>
    </button>
    <button class="mobile-hamburger-btn" data-click="toggleMobileNav" aria-label="Toggle navigation drawer">
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><line x1="3" y1="8" x2="21" y2="8"/><line x1="3" y1="16" x2="21" y2="16"/></svg>
    </button>
  </div>
</div>

<div class="mobile-drawer-backdrop" id="mobileBackdrop" data-click="closeMobileNav"></div>

<aside class="app-sidebar" id="appSidebar">
  <div class="sidebar-head">
    <a href="index.html" class="sidebar-brand"><span class="brand-title">StockPulse</span></a>
    <button class="sidebar-close-btn" data-click="closeMobileNav" aria-label="Close navigation">&times;</button>
  </div>

  <nav class="sidebar-nav" aria-label="Pages">
    <a href="index.html" class="nav-link {% if active_page == 'home' %}active{% endif %}" data-click="closeMobileNav"><span class="nav-text">Home</span></a>
    <a href="company.html" class="nav-link {% if active_page == 'company' %}active{% endif %}" data-click="closeMobileNav"><span class="nav-text">Companies</span></a>
    <a href="news.html" class="nav-link {% if active_page == 'news' %}active{% endif %}" data-click="closeMobileNav"><span class="nav-text">Feed</span></a>
    <a href="calendar.html" class="nav-link {% if active_page == 'calendar' %}active{% endif %}" data-click="closeMobileNav"><span class="nav-text">Calendar</span></a>
    <a href="economic.html" class="nav-link {% if active_page == 'economic' %}active{% endif %}" data-click="closeMobileNav"><span class="nav-text">Economy</span></a>
    <a href="analytics.html" class="nav-link {% if active_page == 'analytics' %}active{% endif %}" data-click="closeMobileNav"><span class="nav-text">Analytics</span></a>
    <a href="settings.html" class="nav-link nav-link-feed {% if active_page == 'settings' %}active{% endif %}" data-click="closeMobileNav"><span class="nav-text">Your feed</span></a>
  </nav>

  <div class="sidebar-footer">
    {% if not latest_run %}
    <div>No updates yet</div>
    {% elif latest_run.status != 'HEALTHY' %}
    <div class="sidebar-status-alert">Last update had problems</div>
    {% endif %}
    <div>Updated {{ generated_at.rsplit(':', 1)[0] }}</div>
    <button class="theme-toggle" id="themeToggle" type="button" data-click="cycleTheme">Dark mode</button>
  </div>
</aside>

<nav class="mobile-bottom-nav" aria-label="Pages">
  <a href="index.html" class="mobile-tab-link {% if active_page == 'home' %}active{% endif %}">Home</a>
  <a href="company.html" class="mobile-tab-link {% if active_page == 'company' %}active{% endif %}">Companies</a>
  <a href="news.html" class="mobile-tab-link {% if active_page == 'news' %}active{% endif %}">Feed</a>
  <a href="calendar.html" class="mobile-tab-link {% if active_page == 'calendar' %}active{% endif %}">Calendar</a>
  <a href="economic.html" class="mobile-tab-link {% if active_page == 'economic' %}active{% endif %}">Economy</a>
</nav>
"""

THEME_BOOT_JS = "try{var t=localStorage.getItem('stockpulse_theme');if(t==='light'||t==='dark')document.documentElement.dataset.theme=t;}catch(e){}"

# JavaScript for Mobile Drawer, Unified Search & Header Actions
SHARED_MOBILE_JS = """
// The Content-Security-Policy bans inline handlers, so elements name an action and this table
// runs it. Only what's listed here can be triggered from markup.
const PAGE_ACTIONS = {
  click: {
    clearFeedFilters: () => clearFeedFilters(),
    clearRecentlyViewed: () => clearRecentlyViewed(),
    copySetupLink: el => copySetupLink(el),
    acceptSetupLink: () => acceptSetupLink(),
    dismissSetupLink: () => dismissSetupLink(),
    closeMobileNav: () => closeMobileNav(),
    cycleTheme: () => cycleTheme(),
    filterCalendar: el => filterCalendar(el.dataset.val, el),
    filterCompanyNews: el => filterCompanyNews(el.dataset.ticker, el.dataset.source, el),
    filterEconomicBySector: el => filterEconomicBySector(el.dataset.sector, el),
    focusMobileSearch: () => focusMobileSearch(),
    openCompany: (el, event) => { event.preventDefault(); switchCompany(el.dataset.ticker); },
    selectFeedTicker: el => selectFeedTicker(el.dataset.ticker),
    setCategoryFilter: el => setCategoryFilter(el.dataset.val, el),
    setFeedSectorFilter: el => setFeedSectorFilter(el.dataset.sector, el),
    setSourceFilter: el => setSourceFilter(el.dataset.val, el),
    sortRows: el => sortRows(el.dataset.sort),
    switchCompany: el => switchCompany(el.dataset.ticker),
    toggleFeedTickerDropdown: () => toggleFeedTickerDropdown(),
    toggleFollow: el => toggleFollow(el.dataset.ticker),
    toggleSector: el => toggleSector(el.dataset.sectorToggle),
    toggleStoryType: el => toggleStoryType(el.dataset.typeToggle),
    resetFeed: () => resetFeed(),
    pickSector: el => pickSector(el),
    finishPicker: () => finishPicker(),
    skipPicker: () => skipPicker(),
    setView: el => setView(el.dataset.view),
    toggleMobileNav: () => toggleMobileNav(),
  },
  input: {
    filterCompanyStrip: el => filterCompanyStrip(el.value),
    filterFeedTickerDropdown: el => filterFeedTickerDropdown(el.value),
    filterItems: () => filterItems(),
    filterSettingsCompanies: el => filterSettingsCompanies(el.value),
    searchCompanyFeed: el => searchCompanyFeed(el.dataset.ticker, el.value),
  },
  change: {
    filterEconomicByTicker: el => filterEconomicByTicker(el.value),
    renderComparativePerformanceChart: el => renderComparativePerformanceChart(el.value),
  },
};

Object.keys(PAGE_ACTIONS).forEach(type => {
  document.addEventListener(type, event => {
    const el = event.target.closest && event.target.closest(`[data-${type}]`);
    if (!el) return;
    const action = PAGE_ACTIONS[type][el.dataset[type]];
    if (typeof action === 'function') action(el, event);
  });
});

// Everything inserted through innerHTML goes through these two.
function escapeHtml(value) {
  return String(value === null || value === undefined ? '' : value).replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[c]));
}

function safeHref(value) {
  const url = String(value || '');
  return /^https?:\\/\\//i.test(url) ? escapeHtml(url) : '#';
}

// Canvas charts can't read CSS variables, so resolve them to real colors first.
function cssColor(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

// Canvas charts can't inherit the page font either.
const CHART_FONT = "-apple-system, BlinkMacSystemFont, 'SF Pro Text', 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif";

// The collector's labels are written for analysts; these say the same thing plainly.
const ASSESSMENT_WORDS = {
  'Strong Outperformance vs Peers': 'Well ahead of peers',
  'Moderate Outperformance': 'Slightly ahead of peers',
  'In-Line with Competitors': 'In line with peers',
  'Moderate Underperformance': 'Slightly behind peers',
  'Lagging Peer Group': 'Well behind peers',
};

function plainAssessment(label) {
  return ASSESSMENT_WORDS[label] || label;
}

// "2026-09-01" or "09-01" becomes "Sep 1".
function shortDay(value) {
  const m = /(\\d{2})-(\\d{2})$/.exec(String(value || ''));
  if (!m) return String(value || '');
  return new Date(2000, Number(m[1]) - 1, Number(m[2])).toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

function currentTheme() {
  return document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light';
}

function labelThemeToggle() {
  const btn = document.getElementById('themeToggle');
  if (btn) btn.textContent = currentTheme() === 'light' ? 'Dark mode' : 'Light mode';
}

function cycleTheme() {
  const next = currentTheme() === 'light' ? 'dark' : 'light';
  if (next === 'light') delete document.documentElement.dataset.theme;
  else document.documentElement.dataset.theme = next;
  try {
    localStorage.setItem('stockpulse_theme', next);
  } catch (e) { /* storage may be blocked; the choice just won't persist */ }
  labelThemeToggle();
  document.dispatchEvent(new Event('themechange'));
}

document.addEventListener('DOMContentLoaded', labelThemeToggle);

function toggleMobileNav() {
  const sidebar = document.getElementById('appSidebar');
  const backdrop = document.getElementById('mobileBackdrop');
  if (sidebar && backdrop) {
    const isOpen = sidebar.classList.contains('mobile-open');
    if (isOpen) {
      closeMobileNav();
    } else {
      sidebar.classList.add('mobile-open');
      backdrop.classList.add('active');
      document.body.style.overflow = 'hidden';
    }
  }
}

function closeMobileNav() {
  const sidebar = document.getElementById('appSidebar');
  const backdrop = document.getElementById('mobileBackdrop');
  if (sidebar) sidebar.classList.remove('mobile-open');
  if (backdrop) backdrop.classList.remove('active');
  document.body.style.overflow = '';
}

function focusMobileSearch() {
  document.getElementById('companyDirectory')?.setAttribute('open', '');
  const input = document.getElementById('globalSearchInput') || document.getElementById('companyStripFilter') || document.getElementById('searchInput');
  if (input) {
    input.scrollIntoView({ behavior: 'smooth', block: 'center' });
    setTimeout(() => {
      input.focus();
      if (typeof openSearchDropdown === 'function') openSearchDropdown();
    }, 200);
  } else {
    window.location.href = 'index.html#globalSearchBox';
  }
}

// Single Universal ⌘K / Ctrl+K Search Keybinding
document.addEventListener('keydown', (e) => {
  if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
    e.preventDefault();
    const globalSearch = document.getElementById('globalSearchInput');
    const companySearch = document.getElementById('companyStripFilter');
    const feedSearch = document.getElementById('searchInput');
    if (globalSearch) {
      globalSearch.focus();
      if (typeof openSearchDropdown === 'function') openSearchDropdown();
    } else if (companySearch) {
      document.getElementById('companyDirectory')?.setAttribute('open', '');
      companySearch.focus();
    } else if (feedSearch) {
      feedSearch.focus();
    } else {
      window.location.href = 'index.html#globalSearchBox';
    }
  } else if (e.key === 'Escape') {
    closeMobileNav();
    if (typeof closeSearchDropdown === 'function') closeSearchDropdown();
  }
});

// ---- Following ------------------------------------------------------------------------------
// What someone follows (companies and whole sectors), which story types they hide from For you,
// and the view they last chose live in this browser only (localStorage). Nothing is sent anywhere.
// A setup link carries them to another device.
const KNOWN_SYMBOLS = new Set({{ watchlist_companies|map(attribute='symbol')|list|tojson }});
const COMPANY_SECTOR = {{ company_sectors|tojson }};
const KNOWN_SECTORS = new Set(Object.values(COMPANY_SECTOR));
const STORY_TYPES = {{ story_type_labels|tojson }};
const FOLLOW_KEY = 'stockpulse_follow';

// Which of the five kinds a story is, from where it came from and what it's about.
function storyType(source, category) {
  if (category === 'Insider Transactions') return 'insider';
  if (category === 'Earnings & Financials') return 'results';
  if (source === 'sec_edgar') return 'filings';
  if (source === 'company_ir') return 'releases';
  return 'news';
}

function cleanList(value, allowed, upper) {
  if (!Array.isArray(value)) return [];
  return [...new Set(value.map(v => (upper ? String(v).toUpperCase() : String(v))).filter(v => allowed(v)))];
}

let storedAnything = false;
function readFollowState() {
  let raw = {};
  storedAnything = false;
  try {
    const text = localStorage.getItem(FOLLOW_KEY);
    storedAnything = text !== null;
    raw = JSON.parse(text || '{}') || {};
  } catch (e) { raw = {}; }
  return {
    symbols: cleanList(raw.symbols, v => KNOWN_SYMBOLS.has(v), true),
    sectors: cleanList(raw.sectors, v => KNOWN_SECTORS.has(v), false),
    hide: cleanList(raw.hide, v => Object.prototype.hasOwnProperty.call(STORY_TYPES, v), false),
    view: raw.view === 'foryou' || raw.view === 'all' ? raw.view : '',
    onboarded: raw.onboarded === true,
  };
}

function writeFollowState(state) {
  const clean = { symbols: state.symbols, sectors: state.sectors, hide: state.hide, view: state.view, onboarded: state.onboarded };
  try {
    localStorage.setItem(FOLLOW_KEY, JSON.stringify(clean));
    storedAnything = true;
  } catch (e) { /* storage may be blocked; the choices then last for this page only */ }
  followMemory = clean;
  document.dispatchEvent(new Event('followchange'));
}

let followMemory = null;
function followState() {
  if (!followMemory) followMemory = readFollowState();
  return followMemory;
}

function followsAnything() {
  const state = followState();
  return state.symbols.length > 0 || state.sectors.length > 0;
}

// Companies followed directly, plus every company in a followed sector.
function followedSet() {
  const state = followState();
  const set = new Set(state.symbols);
  Object.keys(COMPANY_SECTOR).forEach(sym => { if (state.sectors.includes(COMPANY_SECTOR[sym])) set.add(sym); });
  return set;
}

function hiddenTypes() {
  return new Set(followState().hide);
}

// In words, why a story is in For you; '' if it doesn't belong there.
function followReason(ticker, related) {
  const state = followState();
  if (state.symbols.includes(ticker)) return `You follow ${ticker}`;
  if (state.sectors.includes(COMPANY_SECTOR[ticker])) return `In ${COMPANY_SECTOR[ticker]}, which you follow`;
  const follows = followedSet();
  const linked = (related || []).filter(t => t !== ticker && follows.has(t));
  return linked.length ? `Mentions ${linked.slice(0, 2).join(' and ')}, which you follow` : '';
}

// With nothing followed there is nothing "for you" yet, so everything shows.
function currentView() {
  const state = followState();
  if (state.view) return state.view;
  return followsAnything() ? 'foryou' : 'all';
}

function updateFollowState(change) {
  writeFollowState({ ...followState(), onboarded: true, ...change });
}

function setView(view) {
  if (view === 'foryou' || view === 'all') updateFollowState({ view });
}

function toggleIn(list, value) {
  return list.includes(value) ? list.filter(v => v !== value) : [...list, value];
}

function toggleFollow(symbol) {
  const sym = String(symbol || '').toUpperCase();
  if (KNOWN_SYMBOLS.has(sym)) updateFollowState({ symbols: toggleIn(followState().symbols, sym) });
}

function toggleSector(sector) {
  if (KNOWN_SECTORS.has(sector)) updateFollowState({ sectors: toggleIn(followState().sectors, sector) });
}

function toggleStoryType(type) {
  if (Object.prototype.hasOwnProperty.call(STORY_TYPES, type)) updateFollowState({ hide: toggleIn(followState().hide, type) });
}

function resetFeed() {
  if (!window.confirm('Unfollow everything and reset your feed settings?')) return;
  try { localStorage.removeItem(FOLLOW_KEY); } catch (e) { /* nothing stored */ }
  followMemory = null;
  document.dispatchEvent(new Event('followchange'));
}

function plural(n, one, many) {
  return `${n} ${n === 1 ? one : many}`;
}

function followSummary() {
  const state = followState();
  const parts = [];
  if (state.symbols.length) parts.push(plural(state.symbols.length, 'company', 'companies'));
  if (state.sectors.length) parts.push(plural(state.sectors.length, 'sector', 'sectors'));
  return parts.length ? `Following ${parts.join(' and ')}` : 'Not following anything yet';
}

function syncFollowUi() {
  const state = followState();
  const direct = new Set(state.symbols);
  document.querySelectorAll('.follow-btn[data-ticker]').forEach(btn => {
    const on = direct.has(btn.dataset.ticker);
    btn.setAttribute('aria-pressed', String(on));
    btn.textContent = on ? 'Following' : 'Follow';
  });
  const follows = followedSet();
  document.querySelectorAll('[data-follow-mark]').forEach(el => {
    el.classList.toggle('is-followed', follows.has(el.dataset.followMark));
  });
  document.querySelectorAll('[data-sector-toggle]').forEach(btn => {
    btn.setAttribute('aria-pressed', String(state.sectors.includes(btn.dataset.sectorToggle)));
  });
  document.querySelectorAll('[data-type-toggle]').forEach(btn => {
    btn.setAttribute('aria-pressed', String(!state.hide.includes(btn.dataset.typeToggle)));
  });
  const view = currentView();
  document.querySelectorAll('.view-tab[data-view]').forEach(tab => {
    const on = tab.dataset.view === view;
    tab.classList.toggle('active', on);
    tab.setAttribute('aria-selected', String(on));
  });
  document.querySelectorAll('[data-follow-count]').forEach(el => { el.textContent = followSummary(); });
}

function setupLinkUrl() {
  const state = followState();
  const base = new URL('index.html', window.location.href);
  const parts = ['follow=' + state.symbols.map(encodeURIComponent).join(',')];
  if (state.sectors.length) parts.push('sectors=' + state.sectors.map(encodeURIComponent).join(','));
  if (state.hide.length) parts.push('hide=' + state.hide.join(','));
  base.hash = parts.join('&');
  return base.href;
}

function copySetupLink(btn) {
  const url = setupLinkUrl();
  const done = text => {
    if (!btn) return;
    const before = btn.dataset.label || btn.textContent;
    btn.dataset.label = before;
    btn.textContent = text;
    setTimeout(() => { btn.textContent = before; }, 2400);
  };
  if (navigator.clipboard && window.isSecureContext) {
    navigator.clipboard.writeText(url).then(() => done('Link copied'), () => window.prompt('Copy this link:', url));
  } else {
    window.prompt('Copy this link:', url);
  }
}

// A setup link (index.html#follow=NVDA,AAPL&sectors=Energy&hide=insider) asks before it replaces anything.
let pendingSetup = null;
function readSetupLink() {
  const hash = window.location.hash || '';
  if (!/^#follow=[A-Za-z0-9.,%&=-]*$/.test(hash)) return null;
  const fields = {};
  hash.slice(1).split('&').forEach(pair => {
    const at = pair.indexOf('=');
    if (at > 0) {
      try { fields[pair.slice(0, at)] = decodeURIComponent(pair.slice(at + 1)).split(','); } catch (e) { /* bad escape */ }
    }
  });
  return {
    symbols: cleanList((fields.follow || []).map(v => v.trim()), v => KNOWN_SYMBOLS.has(v), true),
    sectors: cleanList(fields.sectors || [], v => KNOWN_SECTORS.has(v), false),
    hide: cleanList(fields.hide || [], v => Object.prototype.hasOwnProperty.call(STORY_TYPES, v), false),
  };
}

function clearSetupHash() {
  try {
    history.replaceState(null, '', window.location.pathname + window.location.search);
  } catch (e) { window.location.hash = ''; }
}

function acceptSetupLink() {
  if (pendingSetup) {
    const any = pendingSetup.symbols.length || pendingSetup.sectors.length;
    writeFollowState({ ...pendingSetup, view: any ? 'foryou' : 'all', onboarded: true });
  }
  dismissSetupLink();
}

function dismissSetupLink() {
  pendingSetup = null;
  document.getElementById('setupLinkBanner')?.remove();
  clearSetupHash();
}

function sameList(a, b) {
  return a.length === b.length && a.every(v => b.includes(v));
}

function offerSetupLink() {
  const setup = readSetupLink();
  if (!setup) return;
  const current = followState();
  if (sameList(setup.symbols, current.symbols) && sameList(setup.sectors, current.sectors) && sameList(setup.hide, current.hide)) {
    clearSetupHash();
    return;
  }
  pendingSetup = setup;
  const main = document.querySelector('.app-main');
  if (!main) return;
  const what = [];
  if (setup.symbols.length) what.push(setup.symbols.join(', '));
  if (setup.sectors.length) what.push(`the ${setup.sectors.join(', ')} ${setup.sectors.length === 1 ? 'sector' : 'sectors'}`);
  const bar = document.createElement('div');
  bar.className = 'setup-banner';
  bar.id = 'setupLinkBanner';
  bar.setAttribute('role', 'region');
  bar.setAttribute('aria-label', 'Use a setup link');
  const text = document.createElement('p');
  text.textContent = what.length
    ? `Use this setup? It follows ${what.join(' and ')}${followsAnything() ? ', and replaces what you follow now' : ''}.`
    : 'This setup link follows nothing.';
  const yes = document.createElement('button');
  yes.type = 'button';
  yes.className = 'setup-yes';
  yes.dataset.click = 'acceptSetupLink';
  yes.textContent = 'Use it';
  const no = document.createElement('button');
  no.type = 'button';
  no.className = 'setup-no';
  no.dataset.click = 'dismissSetupLink';
  no.textContent = 'No thanks';
  bar.append(text, yes, no);
  main.prepend(bar);
}

document.addEventListener('followchange', syncFollowUi);
document.addEventListener('DOMContentLoaded', () => { syncFollowUi(); offerSetupLink(); });
// Another tab changed the follows: pick that up here too.
window.addEventListener('storage', e => {
  if (e.key !== FOLLOW_KEY) return;
  followMemory = null;
  document.dispatchEvent(new Event('followchange'));
});
"""


# ==============================================================================
# 1. HOME / OVERVIEW TEMPLATE (site/index.html)
# ==============================================================================
INDEX_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=5.0">
  <meta name="description" content="Search your watchlist and see the top stories, upcoming events and the economy.">
  <title>StockPulse: keeping you informed</title>
  <link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' rx='8' fill='%231d1d1f'/%3E%3Cpath d='M6 19h6l3-9 3 13 2-4h6' fill='none' stroke='%23ffffff' stroke-width='2'/%3E%3C/svg%3E">
  <script>""" + THEME_BOOT_JS + """</script>
  <style>
""" + SHARED_CSS + """
  </style>
</head>
<body class="page-home">
  <div class="app-layout">
    """ + NAVIGATION_LAYOUT_HTML + """

    <main class="app-main">
      <section class="orbit-hero" id="orbitHero" aria-label="Search your watchlist">
        <canvas class="orbit-dust" id="orbitDust" aria-hidden="true"></canvas>

        <div class="hero-copy">
          <h1 class="hero-headline">Welcome!</h1>
          <p class="hero-sub">We keep you informed about the stocks you follow.</p>
        </div>

        <div class="hero-orbit-stage orbit-static" id="heroOrbitStage">
          <div class="search-wrapper" id="heroSearchWrapper">
            <div class="search-box" id="globalSearchBox">
              <span class="search-icon-wrap">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></svg>
              </span>
              <input type="text" id="globalSearchInput" class="search-input" aria-label="Search companies, stories and tickers" placeholder="Search a company or ticker" autocomplete="off" spellcheck="false">
              <span class="search-shortcut">⌘K</span>
            </div>

            <div class="search-dropdown" id="searchDropdown">
              <div id="defaultDropdownContent">
                <div class="dropdown-tabs-grid">
                  <a href="news.html" class="dropdown-tab-card"><span class="dropdown-tab-title">Feed</span><span class="dropdown-tab-sub">{{ stats.total }} stories</span></a>
                  <a href="calendar.html" class="dropdown-tab-card"><span class="dropdown-tab-title">Calendar</span><span class="dropdown-tab-sub">{{ calendar_events|length }} events</span></a>
                  <a href="economic.html" class="dropdown-tab-card"><span class="dropdown-tab-title">Economy</span><span class="dropdown-tab-sub">{{ economic_indicators|length }} indicators</span></a>
                  <a href="company.html" class="dropdown-tab-card"><span class="dropdown-tab-title">Companies</span><span class="dropdown-tab-sub">{{ watchlist_companies|length }} on the watchlist</span></a>
                </div>
              </div>
              <div id="liveSearchResults" hidden></div>
            </div>
          </div>

          <ul class="orbit-ring" id="orbitRing" aria-label="Companies with the biggest stories">
            {% for co in orbit_companies %}
            <li class="orbit-slot" data-symbol="{{ co.symbol }}" data-name="{{ co.name }}"{% if loop.index > 12 %} hidden{% endif %}>
              <a class="orbit-chip" href="company.html?ticker={{ co.symbol|urlencode }}" draggable="false">
                <span class="orbit-ticker">{{ co.symbol }}</span>
                <span class="orbit-name">{{ co.name }}</span>
                {% if co.move_pct is not none %}
                <svg class="orbit-spark {{ 'is-up' if co.move_pct >= 0 else 'is-down' }}" viewBox="0 0 100 28" preserveAspectRatio="none" aria-hidden="true"><polyline points="{{ co.spark }}"/></svg>
                <span class="orbit-move {{ 'tone-up' if co.move_pct >= 0 else 'tone-down' }}">{{ "%+.1f"|format(co.move_pct) }}%</span>
                {% else %}
                <span class="orbit-fact">{% if co.top_score is not none %}<span class="orbit-dot{% if co.top_score >= 7 %} is-high{% endif %}" title="Top story score {{ co.top_score }}"></span>{% if co.new_count %}{{ co.new_count }} new {{ 'story' if co.new_count == 1 else 'stories' }}{% else %}Top story {{ co.top_score }}{% endif %}{% else %}No stories yet{% endif %}</span>
                {% endif %}
              </a>
            </li>
            {% endfor %}
          </ul>
        </div>

        {% if watchlist_moves %}<p class="orbit-note">Price change over the last 3 months</p>{% endif %}
        <a class="orbit-browse" href="company.html">Browse all {{ watchlist_companies|length }} companies</a>
      </section>

      <section class="picker" id="welcomePicker" aria-labelledby="pickerTitle" hidden>
        <h2 class="picker-title" id="pickerTitle">What do you care about?</h2>
        <p class="picker-sub">Pick a few sectors and their stories gather under For you. You can change this any time.</p>
        <div class="picker-chips">
          {% for sec in sector_directory %}
          <button class="chip" type="button" data-click="pickSector" data-sector="{{ sec.name }}" aria-pressed="false">{{ sec.name }} <span class="chip-count">{{ sec.count }}</span></button>
          {% endfor %}
        </div>
        <div class="picker-actions">
          <button class="setup-yes" type="button" id="pickerDone" data-click="finishPicker" disabled>Show my stories</button>
          <button class="setup-no" type="button" data-click="skipPicker">Show me everything</button>
          <a class="picker-more" href="settings.html">Pick companies instead</a>
        </div>
      </section>

      <div class="view-tabs" role="tablist" aria-label="Which stories to show">
        <button class="view-tab" id="viewTabForYou" role="tab" type="button" data-view="foryou" data-click="setView" aria-selected="false">For you</button>
        <button class="view-tab active" id="viewTabAll" role="tab" type="button" data-view="all" data-click="setView" aria-selected="true">Everything</button>
      </div>

      {% if watchlist_moves %}
      {% set risers = watchlist_moves|selectattr('move_pct', 'gt', 0)|list|length %}
      {% set fallers = watchlist_moves|selectattr('move_pct', 'lt', 0)|list|length %}
      <section class="home-heat" aria-labelledby="homeHeatHeading">
        <h2 class="heat-heading" id="homeHeatHeading">{{ risers }} up, {{ fallers }} down</h2>
        <p class="heat-sub">Your watchlist over the last 3 months, best to worst.</p>
        <ul class="heat-grid">
          {% for co in watchlist_moves %}
          <li data-symbol="{{ co.symbol }}" data-move="{{ co.move_pct }}"><a class="heat-tile {{ heat_class(co.move_pct) }}" href="company.html?ticker={{ co.symbol|urlencode }}" title="{{ co.name }}"><span class="heat-ticker">{{ co.symbol }}</span><span class="heat-move">{{ "%+.1f"|format(co.move_pct) }}%</span></a></li>
          {% endfor %}
        </ul>
      </section>
      {% endif %}

      <div class="home-below">
        <section class="home-stories" aria-labelledby="homeStoriesHeading">
          <h2 class="home-heading" id="homeStoriesHeading">Top stories</h2>
          <div id="topForYou" hidden></div>
          <div id="topEverything">
          {% if priority_items %}
          <ol class="top-list">
            {% for it in priority_items[:5] %}
            <li class="top-row{% if loop.first %} is-lead{% endif %}">
              <a class="top-ticker" href="company.html?ticker={{ it.ticker|urlencode }}">{{ it.ticker }}</a>
              <div class="top-body">
                <a class="top-title" href="{{ safe_url(it.url, 'news.html') }}" target="_blank" rel="noopener noreferrer">{{ it.clean_headline }}</a>
                {% if it.story_text %}<p class="top-summary">{{ figures(it.story_text) }}</p>{% endif %}{% if it.ai_summary %}<p class="feed-takeaway">{{ figures(it.ai_summary) }}</p>{% endif %}
              </div>
              <span class="top-date">{{ short_date(it.published_date) }}</span>
            </li>
            {% endfor %}
          </ol>
          {% else %}
          <p class="home-empty">No stories yet. They appear here after the next pipeline run.</p>
          {% endif %}
          </div>
          <a class="home-more" id="homeMoreLink" href="news.html">All {{ stats.total }} stories</a>
          <p class="follow-footer"><span data-follow-count></span> · <a href="settings.html">Edit</a> · <button class="link-btn" type="button" data-click="copySetupLink">Copy setup link</button></p>
        </section>

        <nav class="home-doors" aria-label="Sections">
          <a class="door" href="news.html">
            <span class="door-title">News</span>
            <span class="door-line">{{ stats.high_priority_count }} to read first, out of {{ stats.total }} stories</span>
          </a>
          <a class="door" href="calendar.html">
            <span class="door-title">Calendar</span>
            <span class="door-line">{% if next_earnings %}Next earnings: {{ next_earnings.ticker }}, {{ short_date(next_earnings.event_date) }}{% elif calendar_events %}Next: {{ calendar_events[0].ticker }}, {{ short_date(calendar_events[0].event_date) }}{% else %}Nothing scheduled{% endif %}</span>
          </a>
          <a class="door" href="economic.html">
            <span class="door-title">Economy</span>
            <span class="door-line">{% if economic_indicators %}{{ economic_indicators[0].name }}: {{ economic_indicators[0].formatted_value.split(' (')[0] }}{% else %}No indicators available{% endif %}</span>
          </a>
          <a class="door" href="company.html">
            <span class="door-title">All companies</span>
            <span class="door-line">{{ watchlist_companies|length }} on the watchlist, {{ orbit_companies|selectattr('top_score', 'ne', none)|list|length }} with stories</span>
          </a>
        </nav>


        <section id="recentlyViewedSection" aria-labelledby="homeRecentHeading" hidden>
          <div class="home-heading-row">
            <h2 class="home-heading" id="homeRecentHeading">Recently viewed</h2>
            <button class="home-clear" id="clearRecentlyViewedBtn" type="button" data-click="clearRecentlyViewed">Clear</button>
          </div>
          <ul class="recent-list" id="recentlyViewedGrid"></ul>
        </section>
      </div>
    </main>
  </div>

  <script>
    """ + SHARED_MOBILE_JS + """

    const allItems = {{ items|tojson|safe }};
    const calendarEvents = {{ calendar_events|tojson|safe }};
    const econIndicators = {{ economic_indicators|tojson|safe }};
    const watchlistCompanies = {{ watchlist_companies|tojson|safe }};

    // Recently viewed comes from localStorage, so anything not on the watchlist is thrown away.
    function readRecentlyViewed() {
      let stored = [];
      try {
        stored = JSON.parse(localStorage.getItem('stockpulse_recently_viewed') || '[]');
      } catch (e) {
        return [];
      }
      if (!Array.isArray(stored)) return [];
      const known = new Set((watchlistCompanies || []).map(c => c.symbol));
      const seen = new Set();
      const clean = [];
      stored.forEach(item => {
        const symbol = String(item && typeof item === 'object' ? item.symbol : item).toUpperCase();
        if (!known.has(symbol) || seen.has(symbol)) return;
        seen.add(symbol);
        const visitedAt = item && Number.isFinite(item.visitedAt) ? item.visitedAt : null;
        clean.push({ symbol, visitedAt });
      });
      return clean;
    }

    function renderRecentlyViewed() {
      const section = document.getElementById('recentlyViewedSection');
      const grid = document.getElementById('recentlyViewedGrid');
      if (!grid || !section) return;

      const stored = readRecentlyViewed();
      if (stored.length === 0) {
        section.hidden = true;
        grid.innerHTML = '';
        return;
      }

      const companies = {};
      (watchlistCompanies || []).forEach(c => { companies[c.symbol] = c; });

      section.hidden = false;
      grid.innerHTML = stored.slice(0, 8).map(item => {
        let when = '';
        if (item.visitedAt) {
          const diffSec = Math.floor((Date.now() - item.visitedAt) / 1000);
          if (diffSec < 60) when = 'Just now';
          else if (diffSec < 3600) when = `${Math.floor(diffSec / 60)}m ago`;
          else if (diffSec < 86400) when = `${Math.floor(diffSec / 3600)}h ago`;
          else when = `${Math.floor(diffSec / 86400)}d ago`;
        }
        return `
          <li>
            <a href="company.html?ticker=${encodeURIComponent(item.symbol)}">
              <span class="recent-ticker">${escapeHtml(item.symbol)}</span>
              <span class="recent-name">${escapeHtml(companies[item.symbol].name)}</span>
              <span class="recent-when">${escapeHtml(when)}</span>
            </a>
          </li>`;
      }).join('');
    }

    function clearRecentlyViewed() {
      try {
        localStorage.removeItem('stockpulse_recently_viewed');
      } catch (e) { /* storage may be blocked */ }
      renderRecentlyViewed();
      orbit.refresh();
    }

    // ---- For you / Everything on the home page ----
    // Same rule as figures() on the server: money and percentages in bold, after escaping.
    const FIGURES = /(?:US)?[$€£]\\s?\\d(?:[\\d,.]*\\d)?(?:\\s?(?:million|billion|trillion|bn)\\b)?|[+\\-−]?\\d[\\d,.]*\\s?(?:%|percent\\b)|\\b\\d[\\d,.]*\\s(?:million|billion|trillion)\\b/gi;
    function figuresHtml(text) {
      return escapeHtml(text).replace(FIGURES, m => `<strong class="fig">${m}</strong>`);
    }

    function storiesFor(follows, limit) {
      const hidden = hiddenTypes();
      return (allItems || [])
        .filter(it => follows.has(it.ticker) || (it.related_tickers_list || []).some(t => follows.has(t)))
        .filter(it => !hidden.has(storyType(it.source, it.category)))
        .sort((a, b) => (b.score - a.score) || String(b.published_date).localeCompare(String(a.published_date)))
        .slice(0, limit);
    }

    function topRowHtml(it, i, follows) {
      const reason = followReason(it.ticker, it.related_tickers_list);
      return `
        <li class="top-row${i === 0 ? ' is-lead' : ''}">
          <a class="top-ticker" href="company.html?ticker=${encodeURIComponent(it.ticker)}">${escapeHtml(it.ticker)}</a>
          <div class="top-body">
            <a class="top-title" href="${safeHref(it.url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(it.clean_headline || it.headline)}</a>
            ${it.story_text ? `<p class="top-summary">${figuresHtml(it.story_text)}</p>` : ''}
            ${it.ai_summary ? `<p class="feed-takeaway">${figuresHtml(it.ai_summary)}</p>` : ''}
            ${reason ? `<p class="follow-reason">${escapeHtml(reason)}</p>` : ''}
          </div>
          <span class="top-date">${escapeHtml(shortDay(it.published_date))}</span>
        </li>`;
    }

    // Companies with the most going on, one tap each. Shown until a few are followed.
    function suggestionsHtml(follows) {
      const counts = {};
      (allItems || []).forEach(it => { counts[it.ticker] = (counts[it.ticker] || 0) + 1; });
      const names = {};
      (watchlistCompanies || []).forEach(c => { names[c.symbol] = c.name; });
      const picks = Object.keys(counts)
        .filter(s => names[s] && !follows.has(s))
        .sort((a, b) => counts[b] - counts[a])
        .slice(0, followsAnything() ? 4 : 8);
      const intro = followsAnything()
        ? '<h3 class="follow-suggest-title">More companies to follow</h3>'
        : '<p class="home-empty">Follow a few companies and their stories gather here, most important first.</p>';
      return `
        ${intro}
        <ul class="follow-suggest">
          ${picks.map(s => `<li><span class="follow-suggest-name"><span class="ticker-badge">${escapeHtml(s)}</span> ${escapeHtml(names[s])}</span><button class="follow-btn" type="button" data-click="toggleFollow" data-ticker="${escapeHtml(s)}" aria-pressed="false">Follow</button></li>`).join('')}
        </ul>
        <a class="home-more" href="company.html">See all ${(watchlistCompanies || []).length} companies</a>`;
    }

    function renderHomeView() {
      const view = currentView();
      const follows = followedSet();
      const forYou = view === 'foryou';
      const mine = document.getElementById('topForYou');
      const everything = document.getElementById('topEverything');
      const heading = document.getElementById('homeStoriesHeading');
      const more = document.getElementById('homeMoreLink');
      if (!mine || !everything) return;

      everything.hidden = forYou;
      mine.hidden = !forYou;
      if (heading) heading.textContent = forYou ? 'Top stories for you' : 'Top stories';
      if (more) more.hidden = forYou && !followsAnything();
      if (forYou) {
        if (!followsAnything()) {
          mine.innerHTML = suggestionsHtml(follows);
        } else {
          const rows = storiesFor(follows, 5);
          mine.innerHTML = (rows.length
            ? `<ol class="top-list">${rows.map((it, i) => topRowHtml(it, i, follows)).join('')}</ol>`
            : '<p class="home-empty">No stories yet about the companies you follow.</p>')
            + (follows.size < 3 ? suggestionsHtml(follows) : '');
          if (!rows.length && hiddenTypes().size) {
            mine.insertAdjacentHTML('afterbegin', '<p class="follow-reason">Some story types are hidden in <a href="settings.html">Your feed</a>.</p>');
          }
        }
      }

      // The 3-month grid narrows to followed companies too.
      const tiles = [...document.querySelectorAll('.heat-grid li[data-symbol]')];
      const narrow = forYou && follows.size > 0;
      let up = 0;
      let down = 0;
      tiles.forEach(li => {
        const show = !narrow || follows.has(li.dataset.symbol);
        li.hidden = !show;
        const move = parseFloat(li.dataset.move);
        if (show && move > 0) up += 1;
        if (show && move < 0) down += 1;
      });
      const heatHeading = document.getElementById('homeHeatHeading');
      if (heatHeading && tiles.length) heatHeading.textContent = `${up} up, ${down} down`;
      const heatSub = document.querySelector('.heat-sub');
      if (heatSub) heatSub.textContent = narrow ? 'The companies you follow over the last 3 months, best to worst.' : 'Your watchlist over the last 3 months, best to worst.';
      syncFollowUi();
    }

    // ---- First visit: a short, skippable "what do you care about?" ----
    const pickedSectors = new Set();

    function pickSector(btn) {
      const sector = btn.dataset.sector;
      if (!KNOWN_SECTORS.has(sector)) return;
      if (pickedSectors.has(sector)) pickedSectors.delete(sector);
      else pickedSectors.add(sector);
      btn.setAttribute('aria-pressed', String(pickedSectors.has(sector)));
      const done = document.getElementById('pickerDone');
      if (done) {
        done.disabled = pickedSectors.size === 0;
        done.textContent = pickedSectors.size ? `Show my stories (${plural(pickedSectors.size, 'sector', 'sectors')})` : 'Show my stories';
      }
    }

    function closePicker() {
      const picker = document.getElementById('welcomePicker');
      if (picker) picker.hidden = true;
    }

    function finishPicker() {
      const sectors = [...new Set([...followState().sectors, ...pickedSectors])];
      updateFollowState({ sectors, view: 'foryou' });
      closePicker();
      document.getElementById('homeStoriesHeading')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }

    function skipPicker() {
      updateFollowState({ view: 'all' });
      closePicker();
    }

    // Only for someone who has never chosen anything, and only if their browser can remember the answer.
    function offerPicker() {
      const picker = document.getElementById('welcomePicker');
      if (!picker) return;
      let canStore = false;
      try {
        localStorage.setItem('stockpulse_probe', '1');
        localStorage.removeItem('stockpulse_probe');
        canStore = true;
      } catch (e) { canStore = false; }
      followState();
      picker.hidden = !(canStore && !storedAnything && !readSetupLink());
    }

    document.addEventListener('followchange', () => { renderHomeView(); if (typeof orbit !== 'undefined') orbit.refresh(); });
    document.addEventListener('DOMContentLoaded', () => { offerPicker(); renderHomeView(); });

    // A ring of real company links orbiting the search bar. The chips are ordinary links in an
    // ordinary list: this script only positions them, and without it they stay a static grid.
    const orbit = (function createOrbit() {
      const stage = document.getElementById('heroOrbitStage');
      const hero = document.getElementById('orbitHero');
      const ring = document.getElementById('orbitRing');
      const canvas = document.getElementById('orbitDust');
      const dropdown = document.getElementById('searchDropdown');
      const bar = document.getElementById('globalSearchBox');
      const input = document.getElementById('globalSearchInput');
      const TWO_PI = Math.PI * 2;
      const AUTO_SPEED = 0.11;
      const all = [...ring.querySelectorAll('.orbit-slot')].map(el => ({
        el,
        symbol: el.dataset.symbol,
        name: (el.dataset.name || '').toLowerCase(),
        angle: 0,
        target: 0,
        dim: 0,
        blur: -1,
      }));
      const bySymbol = new Map(all.map(c => [c.symbol, c]));

      let visible = [];
      let matches = [];
      let query = '';
      let live = false;
      let running = false;
      let rotation = 0;
      let rotationTarget = null;
      let velocity = 0;
      let lastFrame = 0;
      let hovered = false;
      let ringFocused = false;
      let searchFocused = false;
      let onScreen = true;
      let ringShift = 0;
      let drag = null;
      let suppressClick = false;
      let barLifted = false;
      const geo = { width: 0, cx: 0, cy: 0, radius: 0, sinTilt: 0, cosTilt: 1, focal: 1, barW: 0, barH: 0, chipW: 0, chipH: 0 };
      const dust = { ctx: null, list: [], w: 0, h: 0, px: 0, py: 0, tx: 0, ty: 0, color: '', strength: 1 };

      function slotCount() {
        return stage.clientWidth < 640 ? 6 : (stage.clientWidth < 1025 ? 10 : 12);
      }

      // Followed companies join the ring first, then recently viewed ones, then the biggest stories.
      function chooseVisible() {
        const count = slotCount();
        const chosen = [];
        const add = c => { if (c && !chosen.includes(c) && chosen.length < count) chosen.push(c); };
        matches.forEach(add);
        followState().symbols.forEach(sym => add(bySymbol.get(sym)));
        followedSet().forEach(sym => add(bySymbol.get(sym)));
        readRecentlyViewed().slice(0, 4).forEach(item => add(bySymbol.get(item.symbol)));
        all.forEach(add);
        all.forEach(c => { c.el.hidden = !chosen.includes(c); });
        return chosen;
      }

      // Matches take the front slots, spreading out left and right from the centre.
      function assignSlots() {
        const previous = visible;
        visible = chooseVisible();
        const n = visible.length;
        if (!n) return;
        const ordered = [...visible];
        const order = [];
        for (let i = 0; i < n; i += 1) order.push(i % 2 ? (i + 1) / 2 : (n - i / 2) % n);
        const slots = new Array(n);
        ordered.forEach((chip, i) => { slots[i] = order[i]; });
        ordered.forEach((chip, i) => {
          chip.target = (slots[i] * TWO_PI) / n;
          if (!previous.includes(chip)) chip.angle = chip.target + Math.PI;
          chip.dim = query && !matches.includes(chip) ? 1 : 0;
          chip.el.classList.toggle('is-dim', chip.dim === 1);
        });
      }

      function measure() {
        const stageBox = stage.getBoundingClientRect();
        const barBox = bar.getBoundingClientRect();
        const narrow = stageBox.width < 640;
        geo.width = stageBox.width;
        geo.cx = stageBox.width / 2;
        geo.cy = barBox.top - stageBox.top + barBox.height / 2 + ringShift;
        geo.barW = barBox.width;
        geo.barH = barBox.height;
        geo.radius = narrow ? Math.max(100, stageBox.width / 2 - 62) : Math.min(stageBox.width * 0.4, 600);
        // A phone-width bar spans the whole ring, so a shallow tilt would flatten the chips into
        // one row under it. Tipping it further keeps a visible front and back.
        const tilt = (narrow ? 58 : 17) * Math.PI / 180;
        geo.sinTilt = Math.sin(tilt);
        geo.cosTilt = Math.cos(tilt);
        geo.focal = geo.radius * 3.4;
        const sample = visible[0] && visible[0].el.firstElementChild;
        geo.chipW = sample ? sample.offsetWidth : 150;
        geo.chipH = sample ? sample.offsetHeight : 72;
      }

      function smoothstep(a, b, v) {
        const t = Math.min(1, Math.max(0, (v - a) / (b - a)));
        return t * t * (3 - 2 * t);
      }

      function place(chip) {
        const theta = chip.angle + rotation;
        const sin = Math.sin(theta);
        const cos = Math.cos(theta);
        const near = (cos + 1) / 2;
        const depth = geo.radius * cos * geo.cosTilt;
        const perspective = geo.focal / (geo.focal - depth);
        const scale = 0.55 + 0.7 * near;
        const x = geo.radius * sin * perspective;
        let y = geo.radius * cos * geo.sinTilt * perspective;

        // Front chips never cross the bar: anything overlapping it sideways slides out from
        // behind and below it before it comes forward in z-order.
        const halfW = geo.chipW * scale / 2;
        const halfH = geo.chipH * scale / 2;
        const clearY = geo.barH / 2 + halfH + 12;
        let front = cos > 0;
        if (Math.abs(x) < geo.barW / 2 + halfW + 8) {
          const blend = smoothstep(-0.45, -0.02, cos);
          y = y + Math.max(0, clearY - y) * blend;
          front = y >= clearY - 0.5;
        }

        const ease = chip.dim ? 0.2 : 1;
        const opacity = (0.42 + 0.58 * Math.min(1, near * 1.5)) * ease;
        const blur = near < 0.45 ? Math.round((0.45 - near) * 8) / 2 : 0;
        const el = chip.el;
        el.style.transform = `translate3d(${(geo.cx + x - geo.chipW / 2).toFixed(1)}px, ${(geo.cy + y - geo.chipH / 2).toFixed(1)}px, 0) scale(${scale.toFixed(3)})`;
        el.style.opacity = opacity.toFixed(3);
        el.style.zIndex = front ? String(100 + Math.round(near * 100)) : String(1 + Math.round(near * 40));
        if (blur !== chip.blur) {
          el.style.filter = blur ? `blur(${blur}px)` : 'none';
          chip.blur = blur;
        }
      }

      function shortest(from, to) {
        let d = (to - from) % TWO_PI;
        if (d > Math.PI) d -= TWO_PI;
        if (d < -Math.PI) d += TWO_PI;
        return d;
      }

      function frontOf(chip) {
        rotationTarget = rotation + shortest(rotation, -chip.target);
      }

      function step(now) {
        if (!running) return;
        const dt = Math.min(0.05, (now - lastFrame) / 1000 || 0.016);
        lastFrame = now;

        const paused = hovered || ringFocused || searchFocused;
        if (drag) {
          velocity *= Math.exp(-dt * 12);
        } else if (rotationTarget !== null) {
          const gap = rotationTarget - rotation;
          rotation += gap * (1 - Math.exp(-dt * 5));
          velocity = 0;
        } else {
          rotation += velocity * dt;
          velocity *= Math.exp(-dt * 1.8);
          if (!paused) rotation += AUTO_SPEED * dt;
        }

        const settle = 1 - Math.exp(-dt * 6);
        visible.forEach(chip => { chip.angle += shortest(chip.angle, chip.target) * settle; });

        // An open results panel pushes the ring down, so what swung to the front stays in view.
        let wantShift = 0;
        if (dropdown.classList.contains('active')) {
          const frontY = geo.radius * geo.sinTilt * (geo.focal / (geo.focal - geo.radius * geo.cosTilt));
          wantShift = Math.max(0, geo.barH / 2 + dropdown.offsetHeight + 6 + geo.chipH * 0.625 + 12 - frontY);
        }
        ringShift += (wantShift - ringShift) * (1 - Math.exp(-dt * 7));
        geo.cy = bar.getBoundingClientRect().top - stage.getBoundingClientRect().top + geo.barH / 2 + ringShift;
        updateLift();

        visible.forEach(place);
        drawDust(dt, paused && !drag && rotationTarget === null ? velocity : velocity + AUTO_SPEED);
        requestAnimationFrame(step);
      }

      // An open results panel needs the room, so the bar rises to just under the headline.
      function updateLift() {
        const open = dropdown.classList.contains('active');
        if (open === barLifted) return;
        barLifted = open;
        if (!open) {
          stage.style.removeProperty('--bar-lift');
          return;
        }
        const rest = stage.getBoundingClientRect().top + stage.clientHeight * 0.36;
        const roof = hero.querySelector('.hero-copy').getBoundingClientRect().bottom + geo.barH / 2 + 18;
        stage.style.setProperty('--bar-lift', `${Math.max(0, rest - roof)}px`);
      }

      function setUpDust() {
        dust.ctx = canvas.getContext('2d');
        if (!dust.ctx) return false;
        const count = hero.clientWidth < 640 ? 40 : 120;
        dust.list = Array.from({ length: count }, () => {
          const depth = 0.25 + Math.random() * 0.75;
          return {
            x: Math.random(),
            y: Math.random(),
            depth,
            size: 0.5 + depth * 1.1,
            alpha: 0.1 + depth * 0.32,
          };
        });
        sizeDust();
        return true;
      }

      function sizeDust() {
        const ratio = Math.min(window.devicePixelRatio || 1, 2);
        dust.w = hero.clientWidth;
        dust.h = hero.clientHeight;
        canvas.width = Math.round(dust.w * ratio);
        canvas.height = Math.round(dust.h * ratio);
        dust.ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
        dust.color = getComputedStyle(document.documentElement).getPropertyValue('--text-primary').trim();
        dust.strength = 0;
      }

      function drawDust(dt, spin) {
        if (!dust.strength) return;
        const ctx = dust.ctx;
        ctx.clearRect(0, 0, dust.w, dust.h);
        dust.px += (dust.tx - dust.px) * (1 - Math.exp(-dt * 3));
        dust.py += (dust.ty - dust.py) * (1 - Math.exp(-dt * 3));
        ctx.fillStyle = dust.color;
        dust.list.forEach(p => {
          p.x = (p.x + spin * dt * 0.05 * p.depth + 1) % 1;
          p.y = (p.y + dt * 0.002 * p.depth) % 1;
          const x = ((p.x * dust.w + dust.px * 26 * p.depth) % dust.w + dust.w) % dust.w;
          const y = ((p.y * dust.h + dust.py * 18 * p.depth) % dust.h + dust.h) % dust.h;
          ctx.globalAlpha = p.alpha * dust.strength;
          ctx.beginPath();
          ctx.arc(x, y, p.size, 0, TWO_PI);
          ctx.fill();
        });
        ctx.globalAlpha = 1;
      }

      function start() {
        if (running || !live || !onScreen || document.hidden) return;
        running = true;
        lastFrame = performance.now();
        requestAnimationFrame(step);
      }

      function stop() {
        running = false;
      }

      function bindPointer() {
        stage.addEventListener('pointerdown', e => {
          if (e.button !== 0 || e.target.closest('.search-wrapper')) return;
          drag = { id: e.pointerId, x: e.clientX, moved: 0, time: e.timeStamp };
          rotationTarget = null;
        });
        stage.addEventListener('pointermove', e => {
          if (!drag || e.pointerId !== drag.id) return;
          const dx = e.clientX - drag.x;
          drag.x = e.clientX;
          drag.moved += Math.abs(dx);
          if (drag.moved > 6) {
            stage.classList.add('is-dragging');
            if (!stage.hasPointerCapture(e.pointerId)) stage.setPointerCapture(e.pointerId);
          }
          const delta = dx / geo.radius;
          rotation += delta;
          const elapsed = Math.max(1, e.timeStamp - drag.time) / 1000;
          velocity = velocity * 0.7 + (delta / elapsed) * 0.3;
          drag.time = e.timeStamp;
        });
        const release = e => {
          if (!drag || e.pointerId !== drag.id) return;
          suppressClick = drag.moved > 6;
          drag = null;
          stage.classList.remove('is-dragging');
          velocity = Math.max(-5, Math.min(5, velocity));
        };
        stage.addEventListener('pointerup', release);
        // pointercancel means the browser took over for a vertical scroll, which is what we want.
        stage.addEventListener('pointercancel', release);
        // A drag that ends on a chip is a spin, not a click.
        ring.addEventListener('click', e => {
          if (suppressClick) e.preventDefault();
          suppressClick = false;
        });
        ring.addEventListener('dragstart', e => e.preventDefault());
        ring.addEventListener('pointerover', e => { if (e.pointerType === 'mouse' && e.target.closest('.orbit-slot')) hovered = true; });
        ring.addEventListener('pointerout', e => { if (e.target.closest('.orbit-slot')) hovered = false; });
        hero.addEventListener('pointermove', e => {
          dust.tx = (e.clientX / window.innerWidth) * 2 - 1;
          dust.ty = (e.clientY / window.innerHeight) * 2 - 1;
        }, { passive: true });
      }

      function bindKeyboard() {
        ring.addEventListener('focusin', e => {
          ringFocused = true;
          const chip = all.find(c => c.el.contains(e.target));
          if (chip) frontOf(chip);
        });
        ring.addEventListener('focusout', e => {
          if (ring.contains(e.relatedTarget)) return;
          ringFocused = false;
          if (!query) rotationTarget = null;
        });
        ring.addEventListener('keydown', e => {
          if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return;
          const index = visible.findIndex(c => c.el.contains(document.activeElement));
          if (index < 0) return;
          e.preventDefault();
          const bySlot = [...visible].sort((a, b) => a.target - b.target);
          const at = bySlot.indexOf(visible[index]);
          const next = bySlot[(at + (e.key === 'ArrowRight' ? -1 : 1) + bySlot.length) % bySlot.length];
          next.el.querySelector('a').focus({ preventScroll: true });
        });
        input.addEventListener('focus', () => { searchFocused = true; });
        input.addEventListener('blur', () => { searchFocused = false; });
      }

      function search(raw) {
        query = (raw || '').trim().toLowerCase();
        matches = query
          ? all.filter(c => c.symbol.toLowerCase().includes(query) || c.name.includes(query))
              .sort((a, b) => Number(b.symbol.toLowerCase().startsWith(query)) - Number(a.symbol.toLowerCase().startsWith(query)))
          : [];
        assignSlots();
        if (live) {
          measure();
          if (query) rotationTarget = rotation + shortest(rotation, 0);
          else if (!ringFocused) rotationTarget = null;
        }
      }

      function refresh() {
        assignSlots();
        if (live) measure();
      }

      function init() {
        visible = chooseVisible();
        assignSlots();
        const calm = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
        if (calm || !window.CSS || !CSS.supports('transform', 'translate3d(0, 0, 0)')) return;

        try {
          stage.classList.remove('orbit-static');
          if (!setUpDust()) throw new Error('canvas unavailable');
          measure();
          visible.forEach(chip => { chip.angle = chip.target; place(chip); });
          live = true;
          bindPointer();
          bindKeyboard();
          window.addEventListener('resize', () => {
            sizeDust();
            assignSlots();
            measure();
          });
          document.addEventListener('visibilitychange', () => { if (document.hidden) stop(); else start(); });
          document.addEventListener('themechange', sizeDust);
          if (window.IntersectionObserver) {
            new IntersectionObserver(entries => {
              onScreen = entries[0].isIntersecting;
              if (onScreen) start(); else stop();
            }).observe(hero);
          }
          start();
        } catch (err) {
          // Anything unsupported falls back to the plain grid, which works without any of this.
          live = false;
          stop();
          stage.classList.add('orbit-static');
          all.forEach(c => { c.el.removeAttribute('style'); });
        }
      }

      return { init, search, refresh };
    })();

    // Enter opens the first thing the dropdown is offering.
    function openFirstSearchResult() {
      const first = document.querySelector('#liveSearchResults a.search-result-item');
      if (first) window.location.href = first.getAttribute('href');
    }

    function openSearchDropdown() {
      const dropdown = document.getElementById('searchDropdown');
      if (dropdown) dropdown.classList.add('active');
      const val = (document.getElementById('globalSearchInput')?.value || '').trim();
      const def = document.getElementById('defaultDropdownContent');
      const res = document.getElementById('liveSearchResults');
      if (!val) {
        if (def) def.style.display = 'block';
        if (res) res.style.display = 'none';
      } else {
        if (def) def.style.display = 'none';
        if (res) res.style.display = 'block';
      }
    }

    function closeSearchDropdown() {
      const dropdown = document.getElementById('searchDropdown');
      if (dropdown) dropdown.classList.remove('active');
    }

    let lookupAbortController = null;
    let lookupDebounceTimer = null;

    function handleSearchType(rawVal) {
      const dropdown = document.getElementById('searchDropdown');
      if (dropdown) dropdown.classList.add('active');
      const val = (rawVal || '').toLowerCase().trim();
      const rawUpper = (rawVal || '').toUpperCase().trim();
      const defaultContent = document.getElementById('defaultDropdownContent');
      const liveResults = document.getElementById('liveSearchResults');

      if (!val) {
        if (defaultContent) defaultContent.style.display = 'block';
        if (liveResults) {
          liveResults.style.display = 'none';
          liveResults.innerHTML = '';
        }
        if (lookupDebounceTimer) clearTimeout(lookupDebounceTimer);
        if (lookupAbortController) lookupAbortController.abort();
        return;
      }

      if (defaultContent) defaultContent.style.display = 'none';
      if (liveResults) liveResults.style.display = 'block';
      // 1. Match Companies & Tickers
      const matchedCompanies = watchlistCompanies.filter(c => 
        (c.symbol || '').toLowerCase().includes(val) ||
        (c.name || '').toLowerCase().includes(val) ||
        (c.sector || '').toLowerCase().includes(val)
      );

      // 2. Match News & Disclosures
      const matchedNews = allItems.filter(it =>
        (it.clean_headline || '').toLowerCase().includes(val) ||
        (it.ticker || '').toLowerCase().includes(val) ||
        (it.form_or_type || '').toLowerCase().includes(val) ||
        (it.category || '').toLowerCase().includes(val) ||
        (it.summary || '').toLowerCase().includes(val)
      );

      // 3. Match Calendar Events
      const matchedCal = calendarEvents.filter(ev =>
        (ev.headline || '').toLowerCase().includes(val) ||
        (ev.ticker || '').toLowerCase().includes(val) ||
        (ev.event_type || '').toLowerCase().includes(val)
      );

      // 4. Match Economic Indicators
      const matchedEcon = econIndicators.filter(ind =>
        (ind.name || '').toLowerCase().includes(val) ||
        (ind.series_id || '').toLowerCase().includes(val) ||
        String(ind.relevant_tickers || '').toLowerCase().includes(val) ||
        (ind.category || '').toLowerCase().includes(val)
      );

      // Check if input directly matches a curated watchlist holding
      const isExactWatchlist = watchlistCompanies.some(c => 
        (c.symbol || '').toUpperCase() === rawUpper || 
        (c.name || '').toLowerCase() === val
      );
      const isSearchTermEligible = val.length >= 2 && /^[a-zA-Z0-9\\s.\\-]{2,40}$/.test(rawVal.trim());
      const isOutsideWatchlist = isSearchTermEligible && !isExactWatchlist && (matchedCompanies.length === 0);

      const totalMatches = matchedCompanies.length + matchedNews.length + matchedCal.length + matchedEcon.length;

      if (!liveResults) return;

      let html = '';

      // If user typed a ticker or company name outside the 30-company watchlist, insert a live Quick Lookup container at top
      if (isOutsideWatchlist) {
        html += `
          <div id="quickLookupCard" class="quick-lookup-card loading">
            <div class="quick-lookup-header">
              <div class="quick-lookup-title-group" id="quickLookupTitleGroup">
                <span class="ticker-badge" id="quickLookupBadge">${escapeHtml(rawUpper)}</span>
                <span class="quick-lookup-badge">Outside your watchlist</span>
              </div>
              <span class="quick-lookup-meta" id="quickLookupStatus">Checking Finnhub</span>
            </div>
            <div id="quickLookupBody" class="lookup-note lookup-body">
              Fetching the latest price and headlines for <strong>${escapeHtml(rawVal.trim())}</strong>...
            </div>
          </div>
        `;
        triggerLiveQuickLookup(rawVal.trim(), totalMatches);
      }

      if (totalMatches === 0 && !isOutsideWatchlist) {
        liveResults.innerHTML = `
          <div class="search-no-results">
            <div class="no-results-icon"><svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></svg></div>
            <div class="no-results-title">No matches. Try something less specific.</div>
            <div class="no-results-sub">Try searching by company ticker (e.g. <em>NVDA</em>, <em>AAPL</em>, <em>NFLX</em>, <em>PLTR</em>), company name (<em>Netflix</em>, <em>Spotify</em>), or form type (<em>8-K</em>).</div>
          </div>
        `;
        return;
      }

      html += '<div class="search-results-list">';

      // Render Company matches
      if (matchedCompanies.length > 0) {
        html += '<div class="dropdown-section-title">Companies</div>';
        matchedCompanies.slice(0, 3).forEach(c => {
          html += `
            <a href="company.html?ticker=${escapeHtml(c.symbol)}" class="search-result-item">
              <div class="search-result-left">
                <span class="ticker-badge ticker-${escapeHtml(c.symbol)}">${escapeHtml(c.symbol)}</span>
                <div class="search-result-info">
                  <div class="search-result-title">${escapeHtml(c.name)}</div>
                  <div class="search-result-sub">${escapeHtml(c.macro_sector || '')}</div>
                </div>
              </div>
              <span class="action-link action-small">Open</span>
            </a>
          `;
        });
      }

      // Render Calendar matches
      if (matchedCal.length > 0) {
        html += '<div class="dropdown-section-title is-spaced">Calendar</div>';
        matchedCal.slice(0, 2).forEach(ev => {
          html += `
            <a href="calendar.html" class="search-result-item">
              <div class="search-result-left">
                <span class="ticker-badge ticker-${escapeHtml(ev.ticker)}">${escapeHtml(ev.ticker)}</span>
                <div class="search-result-info">
                  <div class="search-result-title">${escapeHtml(ev.headline)}</div>
                  <div class="search-result-sub">${escapeHtml(ev.display_date)} &bull; ${escapeHtml(ev.event_type)}</div>
                </div>
              </div>
              <span class="action-link action-small">Open</span>
            </a>
          `;
        });
      }

      // Render economy matches
      if (matchedEcon.length > 0) {
        html += '<div class="dropdown-section-title is-spaced">Economy</div>';
        matchedEcon.slice(0, 2).forEach(ind => {
          html += `
            <a href="economic.html" class="search-result-item">
              <div class="search-result-left">
                <div class="search-result-icon"><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="20" x2="12" y2="10"/><line x1="18" y1="20" x2="18" y2="4"/><line x1="6" y1="20" x2="6" y2="16"/></svg></div>
                <div class="search-result-info">
                  <div class="search-result-title">${escapeHtml(ind.name)}: ${escapeHtml(ind.formatted_value)}</div>
                  <div class="search-result-sub">${escapeHtml(ind.category)}</div>
                </div>
              </div>
              <span class="action-link action-small">Open</span>
            </a>
          `;
        });
      }

      // Render News matches
      if (matchedNews.length > 0) {
        html += '<div class="dropdown-section-title is-spaced">Stories (' + matchedNews.length + ')</div>';
        matchedNews.slice(0, 4).forEach(it => {
          html += `
            <a href="news.html?q=${encodeURIComponent(val)}" class="search-result-item">
              <div class="search-result-left">
                <span class="ticker-badge ticker-${escapeHtml(it.ticker)}">${escapeHtml(it.ticker)}</span>
                <div class="search-result-info">
                  <div class="search-result-title">${escapeHtml(it.clean_headline)}</div>
                  <div class="search-result-sub">${escapeHtml(it.category)} &bull; ${escapeHtml(it.published_date)} &bull; Score: ${escapeHtml(it.score)}</div>
                </div>
              </div>
              <span class="action-link action-small">Open</span>
            </a>
          `;
        });
      }

      html += '</div>';
      liveResults.innerHTML = html;
    }

    function triggerLiveQuickLookup(query, totalMatches) {
      if (lookupDebounceTimer) clearTimeout(lookupDebounceTimer);
      if (lookupAbortController) lookupAbortController.abort();
      lookupAbortController = new AbortController();

      lookupDebounceTimer = setTimeout(async () => {
        const card = document.getElementById('quickLookupCard');
        const headerGroup = document.getElementById('quickLookupTitleGroup');
        const status = document.getElementById('quickLookupStatus');
        const body = document.getElementById('quickLookupBody');
        if (!card || !body) return;

        try {
          const res = await fetch(`/api/lookup?ticker=${encodeURIComponent(query)}`, {
            signal: lookupAbortController.signal,
          });

          const contentType = res.headers.get('content-type') || '';
          if (!contentType.includes('application/json')) {
            card.classList.remove('loading');
            if (status) status.innerHTML = '<span class="tone-flat">Endpoint Pending</span>';
            body.innerHTML = `
              <div class="lookup-note">
                Live quick-lookup endpoint for "<strong>${escapeHtml(query)}</strong>" is currently offline or pending Cloudflare deployment.
                <div class="lookup-hint">Run local dev server or configure FINNHUB_API_KEY on Cloudflare Pages.</div>
              </div>
            `;
            return;
          }

          if (!res.ok) {
            const errData = await res.json().catch(() => ({}));
            if (totalMatches > 0) {
              card.style.display = 'none';
              return;
            }
            card.classList.remove('loading');
            if (status) status.innerHTML = '<span class="tone-flat">Unlisted Ticker</span>';
            body.innerHTML = `
              <div class="lookup-note">
                ${errData.message || errData.error ? escapeHtml(errData.message || errData.error) : `No live quote or news found on Finnhub for "<strong>${escapeHtml(query)}</strong>".`}
                <div class="lookup-hint">Try checking the company or ticker spelling or searching for general keywords.</div>
              </div>
            `;
            return;
          }

          const data = await res.json();
          if (!data || !data.found) {
            if (totalMatches > 0) {
              card.style.display = 'none';
              return;
            }
            card.classList.remove('loading');
            if (status) status.innerHTML = '<span class="tone-flat">No Data</span>';
            body.innerHTML = `
              <div class="lookup-note">
                ${data.message ? escapeHtml(data.message) : `No quote or news records found for <strong>${escapeHtml(query)}</strong>.`}
              </div>
            `;
            return;
          }

          card.classList.remove('loading');
          if (headerGroup && data.symbol) {
            const coName = data.company_name ? `<span class="lookup-name">${escapeHtml(data.company_name)}</span>` : '';
            const resFrom = data.resolved_from ? `<span class="lookup-from">(resolved from "${escapeHtml(data.resolved_from)}")</span>` : '';
            headerGroup.innerHTML = `
              <span class="ticker-badge ticker-${escapeHtml(data.symbol)}">${escapeHtml(data.symbol)}</span>
              ${coName}
              ${resFrom}
              <span class="quick-lookup-badge lookup-badge-gap">Outside your watchlist</span>
            `;
          }

          if (status) {
            const timeStr = data.queried_at ? new Date(data.queried_at).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'}) : 'Live';
            status.innerHTML = `As of ${escapeHtml(timeStr)}`;
          }

          let bodyHtml = '';

          if (data.price) {
            const chg = Number(data.price.change) || 0;
            const chgPct = Number(data.price.change_pct) || 0;
            const cls = chg > 0 ? 'pos' : (chg < 0 ? 'neg' : 'neu');
            const sign = chg > 0 ? '▲ +' : (chg < 0 ? '▼ ' : '');
            const signPct = chgPct > 0 ? '+' : '';

            bodyHtml += `
              <div class="quick-lookup-price-strip">
                <div class="quick-lookup-price-val">$${Number(data.price.current).toFixed(2)}</div>
                <div class="quick-lookup-change ${cls}">
                  ${sign}$${Math.abs(chg).toFixed(2)} (${signPct}${chgPct.toFixed(2)}%)
                </div>
                <div class="quick-lookup-range">
                  Range: $${Number(data.price.low).toFixed(2)} - $${Number(data.price.high).toFixed(2)} &bull; Prev: $${Number(data.price.prev_close).toFixed(2)}
                </div>
              </div>
            `;
          }

          if (data.headlines && data.headlines.length > 0) {
            bodyHtml += `
              <div class="quick-lookup-headlines-title">Recent headlines</div>
              <div class="quick-lookup-headlines-list">
                ${data.headlines.map(h => `
                  <a href="${safeHref(h.url)}" target="_blank" rel="noopener noreferrer" class="quick-lookup-news-item">
                    <div class="quick-lookup-news-headline">${escapeHtml(h.headline)}</div>
                    <div class="quick-lookup-news-meta">
                      <span class="lookup-source">${escapeHtml(h.source)}</span>
                      ${h.time_ago ? `<span>&bull;</span><span>${escapeHtml(h.time_ago)}</span>` : ''}
                      <span class="lookup-read">Read</span>
                    </div>
                  </a>
                `).join('')}
              </div>
            `;
          } else {
            bodyHtml += `
              <div class="lookup-note lookup-gap">No news headlines published in the past 7 days.</div>
            `;
          }

          bodyHtml += `
            <div class="quick-lookup-action-bar">
              <span class="tone-flat">Quote from Finnhub</span>
              <a href="news.html?q=${encodeURIComponent(data.symbol)}" class="action-link action-small">Search the feed</a>
            </div>
          `;

          body.innerHTML = bodyHtml;
        } catch (err) {
          if (err.name === 'AbortError') return;
          if (totalMatches > 0) {
            card.style.display = 'none';
            return;
          }
          card.classList.remove('loading');
          if (status) status.innerHTML = '<span class="tone-flat">Lookup Error</span>';
          body.innerHTML = `
            <div class="lookup-note">
              Unable to query live quick-lookup. <span class="lookup-small">(Endpoint active on Cloudflare Pages deployment)</span>
            </div>
          `;
        }
      }, 350);
    }

    // Close search dropdown on click outside
    document.addEventListener('click', (e) => {
      const searchWrap = document.querySelector('.search-wrapper');
      if (searchWrap && !searchWrap.contains(e.target)) {
        closeSearchDropdown();
      }
    });

    // Close search dropdown on Escape key
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        closeSearchDropdown();
      }
    });

    function initHomePage() {
      renderRecentlyViewed();
      orbit.init();
      const searchInput = document.getElementById('globalSearchInput');
      if (searchInput) {
        searchInput.addEventListener('focus', openSearchDropdown);
        searchInput.addEventListener('input', (e) => {
          handleSearchType(e.target.value);
          orbit.search(e.target.value);
        });
        searchInput.addEventListener('keydown', (e) => {
          if (e.key === 'Enter') {
            e.preventDefault();
            openFirstSearchResult();
          }
        });
      }
    }

    window.addEventListener('focus', renderRecentlyViewed);

    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', initHomePage);
    } else {
      initHomePage();
    }
  </script>
</body>
</html>
"""

# ==============================================================================
# 1B. DEDICATED ANALYTICS & TRENDS TEMPLATE (site/analytics.html)
# ==============================================================================
ANALYTICS_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=5.0">
  <meta name="description" content="Coverage by company and category, peer performance, and pipeline health.">
  <title>StockPulse — Analytics</title>
  <link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' fill='%231b1a17'/%3E%3Cpath d='M6 19h6l3-9 3 13 2-4h6' fill='none' stroke='%23f6f4ee' stroke-width='2'/%3E%3C/svg%3E">
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.7/dist/chart.umd.min.js" integrity="sha384-vsrfeLOOY6KuIYKDlmVH5UiBmgIdB1oEf7p01YgWHuqmOHfZr374+odEv96n9tNC" crossorigin="anonymous"></script>
  <script>""" + THEME_BOOT_JS + """</script>
  <style>
""" + SHARED_CSS + """
  </style>
</head>
<body>
  <div class="app-layout">
    """ + NAVIGATION_LAYOUT_HTML + """

    <main class="app-main">
      <header class="page-header">
        <h1 class="page-title">Analytics</h1>
        <p class="page-standfirst">What we've collected, how a stock compares with its peers, and whether updates are running.</p>
      </header>

      <dl class="company-kpi-ribbon analytics-stat-row">
        <div class="company-kpi-card">
          <dt class="company-kpi-title">Stories</dt>
          <dd class="company-kpi-val">{{ stats.total }}</dd>
          <dd class="company-kpi-sub">Scored and stored</dd>
        </div>
        <div class="company-kpi-card">
          <dt class="company-kpi-title">To read first</dt>
          <dd class="company-kpi-val">{{ stats.high_priority_count }}</dd>
          <dd class="company-kpi-sub">{{ ((stats.high_priority_count / stats.total * 100) if stats.total else 0)|round(1) }}% of stories</dd>
        </div>
        <div class="company-kpi-card">
          <dt class="company-kpi-title">Companies</dt>
          <dd class="company-kpi-val">{{ watchlist_companies|length }}</dd>
          <dd class="company-kpi-sub">On the watchlist</dd>
        </div>
        <div class="company-kpi-card">
          <dt class="company-kpi-title">Categories</dt>
          <dd class="company-kpi-val">{{ stats.by_category|length }}</dd>
          <dd class="company-kpi-sub">In use across stories</dd>
        </div>
      </dl>

      <div class="analytics-grid">
        <figure class="analytics-card">
          <h2 class="fp-heading">Stories per day</h2>
          <figcaption class="econ-note">The five most-covered companies, over the last 14 days with stories.</figcaption>
          <div class="chart-canvas-container">
            <canvas id="timelineChart" role="img" aria-label="Line chart of stories per day for the five most-covered companies."></canvas>
          </div>
        </figure>

        <figure class="analytics-card">
          <h2 class="fp-heading">Stories by category</h2>
          <figcaption class="econ-note">Share of all {{ stats.total }} stories, across {{ stats.by_category|length }} categories.</figcaption>
          <div class="analytics-donut-layout">
            <div class="chart-canvas-container chart-canvas-donut">
              <canvas id="categoryChart" role="img" aria-label="Donut chart of stories by category. The list beside it has every figure."></canvas>
            </div>
            <div class="category-legend-list" id="categoryLegendList"></div>
          </div>
        </figure>
      </div>

      <section class="comparative-perf-card" aria-labelledby="analyticsPerfHeading">
        <h2 class="fp-heading" id="analyticsPerfHeading">3 months against peers and the S&amp;P 500</h2>
        <div class="analytics-perf-tools">
          <p class="econ-note">Percent change since the start of the 3 months, against up to three competitors and the S&amp;P 500.</p>
          <label class="analytics-perf-picker"><span class="filter-label">Company</span>
            <select id="perfCompanySelect" class="econ-select comparative-select" data-change="renderComparativePerformanceChart">
              {% for sec in sector_directory %}
              <optgroup label="{{ sec.name }}">
                {% for co in sec.companies %}
                <option value="{{ co.symbol }}">{{ co.symbol }} · {{ co.name }}</option>
                {% endfor %}
              </optgroup>
              {% endfor %}
            </select>
          </label>
        </div>
        <div class="perf-kpi-grid" id="perfKpiGrid"></div>
        <div class="perf-chart-box" id="perfChartContainer">
          <canvas id="comparativeChartCanvas" role="img" aria-label="Line chart of the selected company, its peers, and the S&amp;P 500. The table below has the figures."></canvas>
        </div>
        <div class="perf-table-wrap" id="perfTableContainer">
          <table class="perf-table" id="perfBreakdownTable"></table>
        </div>
      </section>

      <section class="health-section" id="health" aria-labelledby="analyticsHealthHeading">
        <h2 class="fp-heading" id="analyticsHealthHeading">Data status</h2>
        {% if latest_run %}
        <p class="health-status{% if latest_run.status != 'HEALTHY' %} is-alert{% endif %}">Last update: {{ latest_run.status|lower }}. {{ latest_run.health_message }}</p>
        <p class="econ-note">Updated {{ latest_run.run_timestamp|replace('T', ' ') }}. A typical update brings in {{ latest_run.moving_avg_raw|round|int }} items.</p>
        {% else %}
        <p class="health-status">No pipeline runs recorded yet.</p>
        {% endif %}
        <dl class="company-kpi-ribbon health-grid">
          <div class="company-kpi-card">
            <dt class="company-kpi-title">SEC filings</dt>
            <dd class="company-kpi-val">{{ latest_run.edgar_count if latest_run else '&mdash;'|safe }}</dd>
          </div>
          <div class="company-kpi-card">
            <dt class="company-kpi-title">Company releases</dt>
            <dd class="company-kpi-val">{{ latest_run.company_ir_count if latest_run else '&mdash;'|safe }}</dd>
          </div>
          <div class="company-kpi-card">
            <dt class="company-kpi-title">News stories</dt>
            <dd class="company-kpi-val">{{ latest_run.news_media_count if latest_run else '&mdash;'|safe }}</dd>
          </div>
          <div class="company-kpi-card">
            <dt class="company-kpi-title">After removing duplicates</dt>
            <dd class="company-kpi-val">{{ latest_run.total_unique if latest_run else '&mdash;'|safe }}</dd>
          </div>
          <div class="company-kpi-card">
            <dt class="company-kpi-title">To read first</dt>
            <dd class="company-kpi-val">{{ latest_run.high_impact_count if latest_run else '&mdash;'|safe }}</dd>
          </div>
        </dl>
      </section>
    </main>
  </div>

  <script>
    """ + SHARED_MOBILE_JS + """

    // =========================================================================
    // CHART.JS RICH VISUALIZATIONS WITH PER-TICKER BREAKDOWN & LEADER CALLOUTS
    // =========================================================================
    const rawChartData = {{ chart_data_json|safe }};

    function initCharts() {
      if (typeof Chart === 'undefined') return;

      const isPhone = window.innerWidth <= 480;
      const isNarrow = window.innerWidth <= 768;

      // 1. Per-Ticker Timeline Line Chart with Interactive Legend
      const ctxTimeline = document.getElementById('timelineChart')?.getContext('2d');
      if (ctxTimeline && rawChartData && rawChartData.timeline_dates && rawChartData.timeline_series) {
        const linePalette = ['--series-1', '--series-2', '--series-3', '--series-4', '--series-5', '--series-6'].map(cssColor);

        const sortedTickers = Object.keys(rawChartData.timeline_series).sort((a, b) => {
          const sumA = (rawChartData.timeline_series[a] || []).reduce((s, v) => s + v, 0);
          const sumB = (rawChartData.timeline_series[b] || []).reduce((s, v) => s + v, 0);
          return sumB - sumA;
        });

        const displayTickers = sortedTickers.slice(0, 5);

        const datasets = displayTickers.map((ticker, idx) => {
          const stroke = linePalette[idx];
          return {
            label: ticker,
            data: rawChartData.timeline_series[ticker] || [],
            backgroundColor: stroke,
            borderWidth: 0,
            borderRadius: 2,
            barPercentage: 0.7,
            categoryPercentage: 0.85,
          };
        });

        new Chart(ctxTimeline, {
          type: 'bar',
          data: {
            labels: rawChartData.timeline_dates.map(shortDay),
            datasets: datasets
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: {
              mode: 'index',
              intersect: false,
            },
            plugins: {
              legend: {
                display: true,
                position: 'top',
                align: isPhone ? 'center' : 'end',
                labels: {
                  boxWidth: 8,
                  boxHeight: 8,
                  usePointStyle: true,
                  pointStyle: 'circle',
                  font: { family: CHART_FONT, size: isPhone ? 10 : 11 },
                  color: cssColor('--text-secondary'),
                  padding: isPhone ? 6 : (isNarrow ? 8 : 14)
                }
              },
              tooltip: {
                backgroundColor: cssColor('--text-primary'),
                titleColor: cssColor('--bg-base'),
                bodyColor: cssColor('--bg-base'),
                titleFont: { family: CHART_FONT, size: 11, weight: '500' },
                bodyFont: { family: CHART_FONT, size: 11 },
                padding: 10,
                cornerRadius: 8,
                displayColors: true,
                boxWidth: 8,
                boxHeight: 8,
                usePointStyle: true
              }
            },
            scales: {
              x: {
                stacked: true,
                grid: { display: false, drawBorder: false },
                ticks: { 
                  font: { family: CHART_FONT, size: isPhone ? 8.5 : (isNarrow ? 9 : 10) }, 
                  color: cssColor('--text-muted'),
                  maxTicksLimit: isPhone ? 4 : (isNarrow ? 5 : 8),
                  autoSkip: true,
                  maxRotation: 0
                }
              },
              y: {
                stacked: true,
                beginAtZero: true,
                grid: { color: cssColor('--border-subtle'), drawBorder: false },
                ticks: { 
                  precision: 0, 
                  font: { family: CHART_FONT, size: isPhone ? 8.5 : (isNarrow ? 9 : 10) }, 
                  color: cssColor('--text-muted'), 
                  maxTicksLimit: isPhone ? 4 : 6,
                  stepSize: 1 
                }
              }
            }
          }
        });
      }

      // 2. Category Breakdown Donut Chart with Leader Line Callouts (All 10 Categories)
      const ctxCat = document.getElementById('categoryChart')?.getContext('2d');
      const catLabels = (rawChartData && (rawChartData.categories || rawChartData.category_labels)) || [];
      const catCounts = (rawChartData && rawChartData.category_counts) || [];

      if (ctxCat && catLabels.length > 0) {
        // Color follows the category, not its rank. Beyond the six series colors, categories
        // share a neutral, and the list below names every one.
        const categoryColors = {
          'Earnings & Financials': '--series-1',
          'M&A & Strategic Deals': '--series-2',
          'Regulation & Policy / Litigation': '--series-3',
          'Leadership & Governance': '--series-4',
          'Insider Transactions': '--series-5',
          'Capital Structure & Offerings': '--series-6',
        };
        const sliceColors = catLabels.map(label => cssColor(categoryColors[label] || '--text-muted'));

        const totalCount = catCounts.reduce((a, b) => a + b, 0) || 1;

        const donutCalloutPlugin = {
          id: 'donutCallouts',
          afterDraw(chart) {
            if (chart.width < 250) return;
            const { ctx } = chart;
            const meta = chart.getDatasetMeta(0);
            if (!meta || !meta.data) return;

            ctx.save();
            meta.data.forEach((element, i) => {
              const { x, y, startAngle, endAngle, outerRadius } = element;
              const midAngle = startAngle + (endAngle - startAngle) / 2;
              const val = chart.data.datasets[0].data[i];
              const pct = Math.round((val / totalCount) * 100);
              if (pct < 3) return;

              const cos = Math.cos(midAngle);
              const sin = Math.sin(midAngle);
              const isRight = cos >= 0;

              const r1 = outerRadius + 3;
              const r2 = outerRadius + 11;
              const sx = x + cos * r1;
              const sy = y + sin * r1;
              const ex = x + cos * r2;
              const ey = y + sin * r2;

              const horizLen = 10;
              let endHorizontalX = ex + (isRight ? horizLen : -horizLen);
              if (isRight) {
                endHorizontalX = Math.min(chart.width - 34, Math.max(ex + 4, endHorizontalX));
              } else {
                endHorizontalX = Math.max(34, Math.min(ex - 4, endHorizontalX));
              }

              ctx.beginPath();
              ctx.moveTo(sx, sy);
              ctx.lineTo(ex, ey);
              ctx.lineTo(endHorizontalX, ey);
              ctx.strokeStyle = cssColor('--text-muted');
              ctx.lineWidth = 1;
              ctx.stroke();

              ctx.textAlign = isRight ? 'left' : 'right';
              ctx.textBaseline = 'middle';
              ctx.font = `11px ${CHART_FONT}`;
              ctx.fillStyle = cssColor('--text-primary');
              ctx.fillText(`${pct}%`, endHorizontalX + (isRight ? 3 : -3), ey);
            });
            ctx.restore();
          }
        };

        new Chart(ctxCat, {
          type: 'doughnut',
          data: {
            labels: catLabels,
            datasets: [{
              data: catCounts,
              backgroundColor: sliceColors,
              borderWidth: 2,
              borderColor: cssColor('--bg-base'),
              hoverOffset: 4
            }]
          },
          plugins: [donutCalloutPlugin],
          options: {
            responsive: true,
            maintainAspectRatio: false,
            layout: {
              padding: { top: 15, bottom: 15, left: isPhone ? 15 : 45, right: isPhone ? 15 : 45 }
            },
            cutout: '64%',
            plugins: {
              legend: { display: false },
              tooltip: {
                backgroundColor: cssColor('--text-primary'),
                titleColor: cssColor('--bg-base'),
                bodyColor: cssColor('--bg-base'),
                titleFont: { family: CHART_FONT, size: 11, weight: '500' },
                bodyFont: { family: CHART_FONT, size: 11 },
                padding: 8,
                cornerRadius: 8,
                callbacks: {
                  label: function(context) {
                    const val = context.parsed || 0;
                    const pct = ((val / totalCount) * 100).toFixed(1);
                    return ` ${context.label}: ${val} items (${pct}%)`;
                  }
                }
              }
            }
          }
        });

        const legList = document.getElementById('categoryLegendList');
        if (legList) {
          let legHtml = '';
          catLabels.forEach((label, idx) => {
            const count = catCounts[idx] || 0;
            const pct = Math.round((count / totalCount) * 100);
            const color = sliceColors[idx];
            legHtml += `
              <div class="category-stat-row" title="${escapeHtml(label)}: ${count} (${pct}%)">
                <div class="cat-stat-left">
                  <span class="category-legend-dot" data-color="${escapeHtml(color)}"></span>
                  <span class="cat-stat-name">${escapeHtml(label)}</span>
                </div>
                <div class="cat-stat-right">
                  <span class="cat-stat-count">${count}</span>
                  <span class="cat-stat-pct">${pct}%</span>
                </div>
              </div>
            `;
          });
          legList.innerHTML = legHtml;
          legList.querySelectorAll('[data-color]').forEach(dot => { dot.style.background = dot.dataset.color; });
        }
      }
    }

    // =========================================================================
    // 3-MONTH COMPARATIVE STOCK PERFORMANCE VS COMPETITORS & S&P 500
    // =========================================================================
    const perfData = {{ performance_data_json|safe }};
    let comparativeChartInstance = null;

    function renderComparativePerformanceChart(symbol) {
      if (!perfData || !perfData.companies) return;
      const coData = perfData.companies[symbol];
      if (!coData) return;

      const isPhone = window.innerWidth <= 480;
      const isNarrow = window.innerWidth <= 768;

      const kpiGrid = document.getElementById('perfKpiGrid');
      const table = document.getElementById('perfBreakdownTable');
      const canvas = document.getElementById('comparativeChartCanvas');
      if (!canvas) return;

      const target = coData.target;
      const comps = coData.competitors || [];
      const spy = coData.benchmark;

      const targetColor = cssColor('--text-primary');
      const compColors = [cssColor('--series-1'), cssColor('--series-2'), cssColor('--series-3')];
      const spyColor = cssColor('--text-muted');

      // 1. Populate KPI Ribbon
      if (kpiGrid && target) {
        const tgtPct = target.total_pct_change;

        const alphaPeers = coData.alpha_vs_peers;

        const spyPct = spy ? spy.total_pct_change : 0;
        const avgPeerPct = coData.avg_competitor_pct;

        kpiGrid.innerHTML = `
          <div class="perf-kpi-box">
            <div class="perf-kpi-label">${escapeHtml(symbol)} over 3 months</div>
            <div class="perf-kpi-val ${tgtPct >= 0 ? 'tone-up' : 'tone-down'}">${tgtPct >= 0 ? '+' : ''}${tgtPct.toFixed(2)}%</div>
            <div class="perf-kpi-sub">Latest: $${target.latest_price.toFixed(2)}</div>
          </div>
          <div class="perf-kpi-box">
            <div class="perf-kpi-label">Peers on average</div>
            <div class="perf-kpi-val ${avgPeerPct >= 0 ? 'tone-up' : 'tone-down'}\">${avgPeerPct >= 0 ? '+' : ''}${avgPeerPct.toFixed(2)}%</div>
            <div class="perf-kpi-sub">${escapeHtml(comps.map(c => c.symbol).join(', ') || 'None')}</div>
          </div>
          <div class="perf-kpi-box">
            <div class="perf-kpi-label">S&P 500 (SPY)</div>
            <div class="perf-kpi-val ${spyPct >= 0 ? 'tone-up' : 'tone-down'}\">${spyPct >= 0 ? '+' : ''}${spyPct.toFixed(2)}%</div>
            <div class="perf-kpi-sub">The wider market</div>
          </div>
          <div class="perf-kpi-box">
            <div class="perf-kpi-label">Compared with peers</div>
            <div class="perf-kpi-val ${alphaPeers >= 0 ? 'tone-up' : 'tone-down'}">${alphaPeers >= 0 ? '+' : ''}${alphaPeers.toFixed(2)}%</div>
            <div class="perf-kpi-sub tone-strong ${coData.assessment_type === 'positive' ? 'tone-up' : (coData.assessment_type === 'negative' ? 'tone-down' : 'tone-flat')}">${escapeHtml(plainAssessment(coData.assessment))}</div>
          </div>
        `;
      }

      // 2. Populate Table
      if (table && target) {
        let rowsHtml = `
          <thead>
            <tr>
              <th>Name</th>
              <th>Role</th>
              <th>Start</th>
              <th>Latest</th>
              <th>Change</th>
              <th>Against ${escapeHtml(symbol)}</th>
            </tr>
          </thead>
          <tbody>
            <tr class="perf-row-target">
              <td><span class="ticker-badge ticker-${escapeHtml(symbol)}">${escapeHtml(symbol)}</span> ${escapeHtml(coData.name)}</td>
              <td>This company</td>
              <td class="perf-num">$${target.base_price.toFixed(2)}</td>
              <td class="perf-num">$${target.latest_price.toFixed(2)}</td>
              <td class="perf-num ${target.total_pct_change >= 0 ? 'tone-up' : 'tone-down'}\">${target.total_pct_change >= 0 ? '+' : ''}${target.total_pct_change.toFixed(2)}%</td>
              <td class="perf-num">&mdash;</td>
            </tr>
        `;

        comps.forEach((c, idx) => {
          const delta = (c.total_pct_change - target.total_pct_change).toFixed(2);
          rowsHtml += `
            <tr>
              <td><a href="company.html?ticker=${escapeHtml(c.symbol)}" class="ticker-badge action-small">${escapeHtml(c.symbol)}</a></td>
              <td>Peer</td>
              <td class="perf-num">$${c.base_price.toFixed(2)}</td>
              <td class="perf-num">$${c.latest_price.toFixed(2)}</td>
              <td class="perf-num ${c.total_pct_change >= 0 ? 'tone-up' : 'tone-down'}\">${c.total_pct_change >= 0 ? '+' : ''}${c.total_pct_change.toFixed(2)}%</td>
              <td class="perf-num ${delta >= 0 ? 'tone-up' : 'tone-down'}\">${delta >= 0 ? '+' : ''}${delta}%</td>
            </tr>
          `;
        });

        if (spy) {
          const spyDelta = (spy.total_pct_change - target.total_pct_change).toFixed(2);
          rowsHtml += `
            <tr>
              <td><span class="ticker-badge">SPY</span> S&amp;P 500 ETF</td>
              <td>Benchmark</td>
              <td class="perf-num">$${spy.base_price.toFixed(2)}</td>
              <td class="perf-num">$${spy.latest_price.toFixed(2)}</td>
              <td class="perf-num ${spy.total_pct_change >= 0 ? 'tone-up' : 'tone-down'}\">${spy.total_pct_change >= 0 ? '+' : ''}${spy.total_pct_change.toFixed(2)}%</td>
              <td class="perf-num ${spyDelta >= 0 ? 'tone-up' : 'tone-down'}\">${spyDelta >= 0 ? '+' : ''}${spyDelta}%</td>
            </tr>
          `;
        }

        rowsHtml += `</tbody>`;
        table.innerHTML = rowsHtml;
      }

      // 3. Render Chart.js
      if (comparativeChartInstance) {
        comparativeChartInstance.destroy();
      }

      if (!target || !target.series) return;
      const labels = target.series.map(pt => shortDay(pt.date));

      const datasets = [
        {
          label: symbol,
          data: target.series.map(pt => pt.pct_change),
          borderColor: targetColor,
          borderWidth: 2.5,
          fill: false,
          tension: 0.15,
          pointRadius: 0,
          pointHoverRadius: 5,
        }
      ];

      comps.forEach((c, idx) => {
        const color = compColors[idx % compColors.length];
        datasets.push({
          label: c.symbol,
          data: c.series.map(pt => pt.pct_change),
          borderColor: color,
          borderWidth: 1.5,
          fill: false,
          tension: 0.15,
          pointRadius: 0,
          pointHoverRadius: 4,
        });
      });

      if (spy && spy.series) {
        datasets.push({
          label: 'S&P 500 (SPY)',
          data: spy.series.map(pt => pt.pct_change),
          borderColor: spyColor,
          borderWidth: isPhone ? 1.5 : 2,
          borderDash: [5, 5],
          fill: false,
          tension: 0.25,
          pointRadius: 0,
          pointHoverRadius: 4,
        });
      }

      comparativeChartInstance = new Chart(canvas, {
        type: 'line',
        data: { labels, datasets },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          interaction: { mode: 'index', intersect: false },
          plugins: {
            legend: {
              display: true,
              position: 'top',
              align: isPhone ? 'center' : 'end',
              labels: {
                boxWidth: isPhone ? 10 : 14,
                boxHeight: 3,
                font: { family: CHART_FONT, size: isPhone ? 10 : 11 },
                color: cssColor('--text-secondary'),
                padding: isPhone ? 6 : 10
              }
            },
            tooltip: {
              backgroundColor: cssColor('--text-primary'),
              titleColor: cssColor('--bg-base'),
              bodyColor: cssColor('--bg-base'),
              titleFont: { family: CHART_FONT, size: 12, weight: '500' },
              bodyFont: { family: CHART_FONT, size: 11 },
              padding: 10,
              cornerRadius: 8,
              callbacks: {
                label: function(context) {
                  return `${context.dataset.label}: ${context.parsed.y >= 0 ? '+' : ''}${context.parsed.y.toFixed(2)}%`;
                }
              }
            }
          },
          scales: {
            x: {
              grid: { display: false },
              ticks: {
                maxTicksLimit: isPhone ? 4 : (isNarrow ? 5 : 8),
                font: { family: CHART_FONT, size: isPhone ? 8.5 : 10 },
                color: cssColor('--text-muted'),
                maxRotation: 0
              }
            },
            y: {
              grid: { color: cssColor('--border-subtle') },
              ticks: {
                callback: function(val) { return (val >= 0 ? '+' : '') + val + '%'; },
                font: { family: CHART_FONT, size: isPhone ? 8.5 : 10 },
                color: cssColor('--text-muted'),
                maxTicksLimit: isPhone ? 4 : 6
              }
            }
          }
        }
      });
    }

    function initAnalyticsPage() {
      initCharts();
      renderComparativePerformanceChart('NVDA');
    }

    function redrawAnalyticsCharts() {
      if (typeof Chart === 'undefined') return;
      Object.values(Chart.instances).forEach(chart => chart.destroy());
      comparativeChartInstance = null;
      initCharts();
      renderComparativePerformanceChart(document.getElementById('perfCompanySelect')?.value || 'NVDA');
    }

    document.addEventListener('themechange', redrawAnalyticsCharts);

    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', initAnalyticsPage);
    } else {
      initAnalyticsPage();
    }
  </script>
</body>
</html>
"""

# ==============================================================================
# 2. INTELLIGENCE FEED TEMPLATE (site/news.html)
# ==============================================================================
NEWS_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=5.0">
  <meta name="description" content="Every story on your watchlist, ranked by importance, with filters and summaries.">
  <title>StockPulse — The feed</title>
  <link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' rx='8' fill='%231d1d1f'/%3E%3Cpath d='M6 19h6l3-9 3 13 2-4h6' fill='none' stroke='%23ffffff' stroke-width='2'/%3E%3C/svg%3E">
  <script>""" + THEME_BOOT_JS + """</script>
  <style>
""" + SHARED_CSS + """
  </style>
</head>
<body class="page-feed">
  <div class="app-layout">
    """ + NAVIGATION_LAYOUT_HTML + """

    <main class="app-main">
      <header class="page-header">
        <h1 class="page-title">The feed</h1>
        <p class="page-standfirst">{{ items|length }} stories, most important first.</p>
      </header>

      <div class="view-tabs view-tabs-left" role="tablist" aria-label="Which stories to show">
        <button class="view-tab" role="tab" type="button" data-view="foryou" data-click="setView" aria-selected="false">For you</button>
        <button class="view-tab active" role="tab" type="button" data-view="all" data-click="setView" aria-selected="true">Everything</button>
      </div>
      <p class="follow-footer" id="feedFollowLine" hidden><span data-follow-count></span> · <a href="settings.html">Edit</a> · <button class="link-btn" type="button" data-click="copySetupLink">Copy setup link</button></p>

      <div class="feed-toolbar">
        <input type="text" id="searchInput" class="feed-search" aria-label="Search the feed" placeholder="Search headlines and summaries" data-input="filterItems">
        <div class="feed-toolbar-row">
          <div class="feed-sort" role="group" aria-label="Order">
            <button class="feed-sort-btn active" id="sortScoreBtn" type="button" data-click="sortRows" data-sort="score">By importance</button>
            <button class="feed-sort-btn" id="sortDateBtn" type="button" data-click="sortRows" data-sort="date">By date</button>
          </div>
          <span class="feed-count" id="feedResultCount" aria-live="polite"></span>
          <button class="feed-clear" id="feedClearFilters" type="button" data-click="clearFeedFilters" hidden>Clear filters</button>
        </div>
      </div>

      <details class="controls-panel" id="feedFilters">
        <summary class="feed-filters-toggle">Filters</summary>
        <div class="filter-row">
          <span class="filter-label">Sector</span>
          <div class="feed-sector-bar">
            <button class="feed-sector-btn filter-btn active" type="button" data-sector="ALL" data-click="setFeedSectorFilter">All</button>
            {% for sec in sector_directory %}
            <button class="feed-sector-btn filter-btn" type="button" data-sector="{{ sec.name }}" data-click="setFeedSectorFilter">{{ sec.name }}</button>
            {% endfor %}
          </div>
        </div>

        <div class="filter-row">
          <span class="filter-label">Company</span>
          <div class="feed-ticker-picker-wrap" id="feedTickerPickerWrap">
            <button class="feed-ticker-picker-btn" id="feedTickerPickerBtn" data-click="toggleFeedTickerDropdown" type="button">
              <span id="selectedTickerLabel">All companies</span> <span aria-hidden="true">▾</span>
            </button>
            <div class="feed-ticker-dropdown-menu" id="feedTickerDropdownMenu">
              <div class="feed-ticker-dropdown-search">
                <input type="text" id="feedTickerSearchInput" aria-label="Find a company" placeholder="Find a company" data-input="filterFeedTickerDropdown">
              </div>
              <div class="feed-ticker-dropdown-list" id="feedTickerDropdownList">
                <div class="feed-ticker-item active" data-ticker="ALL" data-sector="ALL" data-click="selectFeedTicker">
                  <span>All companies</span>
                  <span class="pill-count">{{ items|length }}</span>
                </div>
                {% for sec in sector_directory %}
                <div class="feed-dropdown-sec-header" data-sector="{{ sec.name }}">{{ sec.name }}</div>
                {% for co in sec.companies %}
                <div class="feed-ticker-item" data-ticker="{{ co.symbol }}" data-name="{{ co.name|lower }}" data-sector="{{ sec.name }}" data-click="selectFeedTicker">
                  <span><span class="ticker-badge">{{ co.symbol }}</span> {{ co.name }}</span>
                  <span class="pill-count">{{ co.story_count }}</span>
                </div>
                {% endfor %}
                {% endfor %}
              </div>
            </div>
          </div>
        </div>

        <div class="filter-row">
          <span class="filter-label">Category</span>
          <div class="filter-options">
            <button class="filter-btn active" type="button" data-filter-type="category" data-val="ALL" data-click="setCategoryFilter">All</button>
            {% for cat, count in stats.by_category.items() %}
            <button class="filter-btn" type="button" data-filter-type="category" data-val="{{ cat }}" data-click="setCategoryFilter">{{ cat }} <span class="pill-count">{{ count }}</span></button>
            {% endfor %}
          </div>
        </div>

        <div class="filter-row">
          <span class="filter-label">Source</span>
          <div class="filter-options">
            <button class="filter-btn active" type="button" data-filter-type="source" data-val="ALL" data-click="setSourceFilter">All</button>
            <button class="filter-btn" type="button" data-filter-type="source" data-val="news_media" data-click="setSourceFilter">News Media</button>
            <button class="filter-btn" type="button" data-filter-type="source" data-val="sec_edgar" data-click="setSourceFilter">SEC EDGAR</button>
            <button class="filter-btn" type="button" data-filter-type="source" data-val="company_ir" data-click="setSourceFilter">Company Releases</button>
          </div>
        </div>
      </details>

      <div class="feed-list" id="newsBody">
        {% for item in items %}
        <article class="news-row{% if item.score >= 7.0 %} is-high{% if loop.index <= 3 %} is-lead{% endif %}{% endif %}"
            data-score="{{ item.score }}"
            data-date="{{ item.published_date }}"
            data-ticker="{{ item.ticker }}"
            data-tickers="{{ item.ticker }}{% if item.related_tickers_list %},{{ item.related_tickers_list|join(',') }}{% endif %}"
            data-sector="{{ item.macro_sector }}"
            data-source="{{ item.source }}"
            data-category="{{ item.category }}"
            data-text="{{ item.ticker }} {{ item.company_name }} {{ item.macro_sector }} {{ item.category }} {{ item.source_label }} {{ item.form_or_type }} {{ item.clean_headline }} {{ item.headline }} {{ item.cross_ref_summary or '' }} {{ item.summary or '' }}">
          <a href="company.html?ticker={{ item.ticker|urlencode }}" class="ticker-badge" title="{{ item.company_name }}">{{ item.ticker }}</a>
          <div class="feed-body">
            <h3 class="feed-headline"><a href="{{ safe_url(item.url, '#') }}" target="_blank" rel="noopener noreferrer">{{ item.clean_headline }}</a></h3>
            {% if item.story_text %}<p class="feed-summary">{{ figures(item.story_text) }}</p>{% endif %}{% if item.ai_summary %}<p class="feed-takeaway">{{ figures(item.ai_summary) }}</p>{% endif %}
            <p class="follow-reason" hidden></p>
            <details class="feed-details">
              <summary><span class="feed-meta">{{ item.category }} · {{ item.source_label }}{% if item.form_or_type %} · {{ item.form_or_type }}{% endif %}</span></summary>
              <div class="feed-details-body">
                {% if item.cross_references_list %}
                <p class="feed-detail-label">Also relevant to {{ item.cross_references_list|length }} {{ 'company' if item.cross_references_list|length == 1 else 'companies' }}</p>
                <ul class="feed-refs">
                  {% for ref in item.cross_references_list %}
                  <li><a href="company.html?ticker={{ ref.related_ticker|urlencode }}" class="ticker-badge">{{ ref.related_ticker }}</a> {{ ref.impact_note }}</li>
                  {% endfor %}
                </ul>
                {% endif %}
                {% if item.score_breakdown %}<p class="feed-detail-label">How it scored: {{ item.score }}</p><p class="feed-breakdown">{{ item.score_breakdown|replace(' | ', ' · ') }}</p>{% endif %}
                <a href="{{ safe_url(item.url, '#') }}" target="_blank" rel="noopener noreferrer" class="home-more">{% if item.source == 'sec_edgar' %}Read the filing{% elif item.source == 'company_ir' %}Read the release{% else %}Read the article{% endif %}</a>
              </div>
            </details>
          </div>
          <span class="date-cell">{{ short_date(item.published_date) }}</span>
        </article>
        {% endfor %}
        <p class="home-empty" id="feedEmpty" hidden>No stories match these filters.</p>
      </div>
    </main>
  </div>

  <script>
    """ + SHARED_MOBILE_JS + """

    let currentSector = 'ALL';
    let currentTicker = 'ALL';
    let currentCategory = 'ALL';
    let currentSource = 'ALL';
    let currentOrder = 'score';
    const expandedBands = new Set();

    // Only the top of each band shows at first, so the page reads as edited rather than as a dump.
    const BANDS = [
      { key: 'high', label: 'Read first', min: 7, show: 10 },
      { key: 'mid', label: 'Worth knowing', min: 4, show: 5 },
      { key: 'low', label: 'Routine', min: -Infinity, show: 0 },
    ];
    const LEAD_STORIES = 3;

    function bandFor(score) {
      return BANDS.find(b => score >= b.min);
    }

    function setFeedSectorFilter(secName, btn) {
      currentSector = secName;
      document.querySelectorAll('.feed-sector-btn').forEach(b => b.classList.remove('active'));
      if (btn) btn.classList.add('active');

      // A company outside the new sector can't stay selected.
      if (currentTicker !== 'ALL' && secName !== 'ALL') {
        const item = document.querySelector(`#feedTickerDropdownList .feed-ticker-item[data-ticker="${CSS.escape(currentTicker)}"]`);
        if (item && item.dataset.sector !== secName) setTickerFilter('ALL');
      }

      filterItems();
    }

    function toggleFeedTickerDropdown() {
      const menu = document.getElementById('feedTickerDropdownMenu');
      if (menu) {
        menu.classList.toggle('active');
        if (menu.classList.contains('active')) {
          const inp = document.getElementById('feedTickerSearchInput');
          if (inp) {
            inp.value = '';
            filterFeedTickerDropdown('');
            setTimeout(() => inp.focus(), 100);
          }
        }
      }
    }

    function filterFeedTickerDropdown(query) {
      const q = (query || '').toLowerCase().trim();
      const items = document.querySelectorAll('#feedTickerDropdownList .feed-ticker-item');
      const headers = document.querySelectorAll('#feedTickerDropdownList .feed-dropdown-sec-header');
      
      items.forEach(it => {
        const t = (it.getAttribute('data-ticker') || '').toLowerCase();
        const n = (it.getAttribute('data-name') || '').toLowerCase();
        const s = (it.getAttribute('data-sector') || '').toLowerCase();
        if (!q || t.includes(q) || n.includes(q) || s.includes(q)) {
          it.style.display = 'flex';
        } else {
          it.style.display = 'none';
        }
      });

      headers.forEach(h => {
        h.style.display = q ? 'none' : 'block';
      });
    }

    function selectFeedTicker(ticker) {
      const menu = document.getElementById('feedTickerDropdownMenu');
      if (menu) menu.classList.remove('active');

      // Picking a company outside the current sector should show that company, not an empty list.
      const item = document.querySelector(`#feedTickerDropdownList .feed-ticker-item[data-ticker="${CSS.escape(ticker)}"]`);
      if (item && ticker !== 'ALL' && currentSector !== 'ALL' && item.dataset.sector !== currentSector) {
        setFeedSectorFilter('ALL', document.querySelector('.feed-sector-btn[data-sector="ALL"]'));
      }
      setTickerFilter(ticker);
    }

    document.addEventListener('click', (e) => {
      const wrap = document.getElementById('feedTickerPickerWrap');
      if (wrap && !wrap.contains(e.target)) {
        const menu = document.getElementById('feedTickerDropdownMenu');
        if (menu) menu.classList.remove('active');
      }
    });

    function setTickerFilter(ticker) {
      currentTicker = ticker;

      const lbl = document.getElementById('selectedTickerLabel');
      if (lbl) lbl.textContent = (ticker === 'ALL') ? 'All companies' : ticker;

      document.querySelectorAll('#feedTickerDropdownList .feed-ticker-item').forEach(it => {
        it.classList.toggle('active', it.getAttribute('data-ticker') === ticker);
      });

      filterItems();
    }

    function setCategoryFilter(cat, btn) {
      currentCategory = cat;
      document.querySelectorAll('[data-filter-type="category"]').forEach(b => b.classList.remove('active'));
      if (btn) btn.classList.add('active');
      filterItems();
    }

    function setSourceFilter(src, btn) {
      currentSource = src;
      document.querySelectorAll('[data-filter-type="source"]').forEach(b => b.classList.remove('active'));
      if (btn) btn.classList.add('active');
      filterItems();
    }

    function filterItems() {
      const q = (document.getElementById('searchInput')?.value || '').toLowerCase().trim();
      const rows = document.querySelectorAll('.news-row');
      const follows = followedSet();
      const hidden = hiddenTypes();
      const forYou = currentView() === 'foryou';
      const line = document.getElementById('feedFollowLine');
      if (line) line.hidden = !forYou;

      rows.forEach(row => {
        const rowTicker = row.getAttribute('data-ticker');
        const rowTickers = (row.getAttribute('data-tickers') || '').split(',');
        const rowSector = row.getAttribute('data-sector');
        const rowCategory = row.getAttribute('data-category');
        const rowSource = row.getAttribute('data-source');
        const rowText = (row.getAttribute('data-text') || '').toLowerCase();

        let matchSector = (currentSector === 'ALL') || (rowSector === currentSector);
        let matchTicker = (currentTicker === 'ALL') || rowTickers.includes(currentTicker);
        let matchCat = (currentCategory === 'ALL') || (rowCategory === currentCategory);
        let matchSrc = (currentSource === 'ALL') || (rowSource === currentSource);
        let matchQuery = !q || rowText.includes(q);
        const matchView = !forYou
          || (rowTickers.some(t => follows.has(t)) && !hidden.has(storyType(rowSource, rowCategory)));
        const why = row.querySelector('.follow-reason');
        if (why) {
          why.textContent = forYou ? followReason(rowTicker, rowTickers) : '';
          why.hidden = !why.textContent;
        }

        row.dataset.match = (matchView && matchSector && matchTicker && matchCat && matchSrc && matchQuery) ? '1' : '0';
      });

      renderGroups();
    }

    function filtersActive() {
      const q = (document.getElementById('searchInput')?.value || '').trim();
      return Boolean(q) || currentSector !== 'ALL' || currentTicker !== 'ALL' || currentCategory !== 'ALL' || currentSource !== 'ALL';
    }

    function clearFeedFilters() {
      const box = document.getElementById('searchInput');
      if (box) box.value = '';
      currentCategory = 'ALL';
      currentSource = 'ALL';
      document.querySelectorAll('.filter-btn').forEach(b => {
        b.classList.toggle('active', b.dataset.val === 'ALL' || b.dataset.sector === 'ALL');
      });
      currentSector = 'ALL';
      setTickerFilter('ALL');
    }

    function groupHeader(key, label, count) {
      const head = document.createElement('div');
      head.className = 'feed-group';
      head.dataset.key = key;
      const title = document.createElement('h2');
      title.className = 'feed-group-title';
      title.textContent = label;
      const meta = document.createElement('span');
      meta.className = 'feed-group-note';
      meta.textContent = `${count} ${count === 1 ? 'story' : 'stories'}`;
      head.append(title, meta);
      return head;
    }

    function moreButton(key, hiddenCount) {
      const btn = document.createElement('button');
      const open = expandedBands.has(key);
      btn.type = 'button';
      btn.className = 'feed-more';
      btn.dataset.key = key;
      btn.textContent = open ? 'Show fewer' : `Show ${hiddenCount} more`;
      btn.setAttribute('aria-expanded', String(open));
      btn.addEventListener('click', () => {
        if (open) expandedBands.delete(key);
        else expandedBands.add(key);
        renderGroups();
        document.querySelector(`.feed-more[data-key="${key}"]`)?.focus({ preventScroll: true });
      });
      return btn;
    }

    // Draws the group headings, marks the lead stories, and shortens each band until it is asked
    // for or filtered into.
    function renderGroups() {
      const body = document.getElementById('newsBody');
      body.querySelectorAll('.feed-group, .feed-more').forEach(h => h.remove());
      const rows = Array.from(body.querySelectorAll('.news-row'));
      const active = filtersActive();
      const edited = currentOrder === 'score' && !active;
      const groups = new Map();
      let leads = 0;

      rows.forEach(row => {
        const matched = row.dataset.match !== '0';
        const band = bandFor(parseFloat(row.dataset.score));
        const key = currentOrder === 'score' ? band.key : row.dataset.date;
        let collapsed = false;
        if (matched) {
          if (!groups.has(key)) groups.set(key, { first: row, last: null, count: 0, band, hidden: 0 });
          const group = groups.get(key);
          collapsed = edited && group.count >= band.show && !expandedBands.has(key);
          group.count += 1;
          if (collapsed) group.hidden += 1;
          else group.last = row;
        }
        row.hidden = !matched || collapsed;
        const lead = edited && matched && band.key === 'high' && leads < LEAD_STORIES;
        row.classList.toggle('is-lead', lead);
        if (lead) leads += 1;
      });

      groups.forEach((group, key) => {
        const label = currentOrder === 'score'
          ? group.band.label
          : (() => {
              const parts = key.split('-').map(Number);
              return new Date(parts[0], parts[1] - 1, parts[2]).toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' });
            })();
        body.insertBefore(groupHeader(key, label, group.count), group.first);
        if (edited && (group.hidden || expandedBands.has(key)) && group.count > group.band.show) {
          body.insertBefore(moreButton(key, group.hidden), group.last ? group.last.nextSibling : group.first);
        }
      });

      const shown = Array.from(groups.values()).reduce((sum, g) => sum + g.count, 0);
      const countEl = document.getElementById('feedResultCount');
      if (countEl) countEl.textContent = active ? `${shown} of ${rows.length} stories` : '';
      const clearBtn = document.getElementById('feedClearFilters');
      if (clearBtn) clearBtn.hidden = !active;
      const empty = document.getElementById('feedEmpty');
      if (empty) {
        empty.hidden = shown !== 0;
        const forYou = currentView() === 'foryou';
        empty.innerHTML = forYou && !followsAnything()
          ? 'You aren’t following anything yet. Pick companies or sectors in <a href="settings.html">Your feed</a>, or switch to Everything.'
          : (forYou && hiddenTypes().size
            ? 'No stories match. Some story types are hidden in <a href="settings.html">Your feed</a>.'
            : 'No stories match these filters.');
      }
    }

    function sortRows(criterion) {
      currentOrder = criterion;
      const body = document.getElementById('newsBody');
      const empty = document.getElementById('feedEmpty');
      const rows = Array.from(body.querySelectorAll('.news-row'));

      document.getElementById('sortScoreBtn')?.classList.toggle('active', criterion === 'score');
      document.getElementById('sortDateBtn')?.classList.toggle('active', criterion === 'date');

      rows.sort((a, b) => {
        if (criterion === 'score') {
          return parseFloat(b.getAttribute('data-score')) - parseFloat(a.getAttribute('data-score'));
        }
        return b.getAttribute('data-date').localeCompare(a.getAttribute('data-date'));
      });

      rows.forEach(r => body.insertBefore(r, empty));
      renderGroups();
    }

    // URL parameter auto-filter (?ticker=NVDA or ?q=keyword)
    window.addEventListener('DOMContentLoaded', () => {
      const params = new URLSearchParams(window.location.search);
      const urlTicker = params.get('ticker');
      const urlQ = params.get('q');

      // Only a ticker that appears in the picker can filter; anything else from the URL is ignored.
      const pickable = urlTicker && [...document.querySelectorAll('#feedTickerDropdownList .feed-ticker-item')]
        .some(it => it.dataset.ticker === urlTicker.toUpperCase());
      if (pickable) {
        setTickerFilter(urlTicker.toUpperCase());
      }
      if (urlQ) {
        const searchBox = document.getElementById('searchInput');
        if (searchBox) {
          searchBox.value = urlQ;
        }
      }
      sortRows('score');
      filterItems();
    });

    document.addEventListener('followchange', () => filterItems());
  </script>
</body>
</html>
"""

# ==============================================================================
# 3. FORTHCOMING CORPORATE CALENDAR TEMPLATE (site/calendar.html)
# ==============================================================================
CALENDAR_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=5.0">
  <meta name="description" content="Upcoming earnings calls, dividends, conferences, and SEC deadlines for your watchlist.">
  <title>StockPulse — Calendar</title>
  <link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' rx='8' fill='%231d1d1f'/%3E%3Cpath d='M6 19h6l3-9 3 13 2-4h6' fill='none' stroke='%23ffffff' stroke-width='2'/%3E%3C/svg%3E">
  <script>""" + THEME_BOOT_JS + """</script>
  <style>
""" + SHARED_CSS + """
  </style>
</head>
<body>
  <div class="app-layout">
    """ + NAVIGATION_LAYOUT_HTML + """

    <main class="app-main">
      <header class="page-header">
        <h1 class="page-title">Calendar</h1>
        <p class="page-standfirst">
          {% if calendar_events %}{{ calendar_events|length }} events ahead. Next: {{ calendar_events[0].headline }}, {{ calendar_events[0].relative_badge|lower }}.
          {% else %}Nothing scheduled yet.{% endif %}
        </p>
      </header>

      {% if calendar_view.marks %}
      <figure class="cal-timeline" aria-label="Events on a timeline">
        <div class="cal-track">
          <span class="cal-month cal-today" data-left="{{ calendar_view.today_pos }}">Today</span>
          {% for m in calendar_view.months %}
          <span class="cal-month" data-left="{{ m.pos }}">{{ m.label }}</span>
          {% endfor %}
          {% for mark in calendar_view.marks %}
          <a class="cal-mark{% if mark.estimated %} is-estimated{% endif %}" href="#{{ mark.anchor }}" data-event-type="{{ mark.event_type }}" data-left="{{ mark.pos }}" data-bottom="{{ mark.lane * 12 }}" title="{{ mark.date }}: {{ mark.ticker }} {{ mark.kind }}{% if mark.estimated %} (estimated){% endif %}" aria-label="{{ mark.date }}: {{ mark.ticker }} {{ mark.kind }}"></a>
          {% endfor %}
        </div>
        <figcaption class="cal-legend">
          <span><i class="cal-key is-earnings"></i>Earnings</span>
          <span><i class="cal-key is-dividend"></i>Dividend</span>
          <span><i class="cal-key is-sec"></i>SEC deadline</span>
          <span><i class="cal-key is-conference"></i>Conference</span>
          <span><i class="cal-key is-estimated"></i>Hollow means estimated from filing rules</span>
        </figcaption>
      </figure>
      {% endif %}

      <div class="controls-panel cal-filters">
        <div class="filter-options" role="group" aria-label="Filter events">
          <button class="filter-btn active cal-filter-btn" type="button" data-val="ALL" data-click="filterCalendar">All <span class="pill-count">{{ calendar_events|length }}</span></button>
          <button class="filter-btn cal-filter-btn" type="button" data-val="Earnings" data-click="filterCalendar">Earnings</button>
          <button class="filter-btn cal-filter-btn" type="button" data-val="Dividend" data-click="filterCalendar">Dividends</button>
          <button class="filter-btn cal-filter-btn" type="button" data-val="SEC" data-click="filterCalendar">SEC deadlines</button>
          <button class="filter-btn cal-filter-btn" type="button" data-val="Conference" data-click="filterCalendar">Conferences</button>
        </div>
      </div>

      <div id="calendarGrid">
        {% for week in calendar_view.weeks %}
        <section class="cal-week">
          <h2 class="cal-week-title">{{ week.label }}</h2>
          {% for ev in week.events %}
          <article class="calendar-card" id="{{ ev.anchor }}" data-event-type="{{ ev.event_type }}" data-source-type="{{ ev.source_type }}">
            <div class="cal-when">
              <span class="cal-date">{{ short_date(ev.event_date) }}</span>
              <span class="cal-relative">{{ ev.relative_badge }}</span>
            </div>
            <a href="company.html?ticker={{ ev.ticker|urlencode }}" class="ticker-badge" title="{{ ev.company_name }}">{{ ev.ticker }}</a>
            <div class="cal-body">
              <h3 class="cal-headline">{{ ev.headline }}</h3>
              <p class="cal-details">{{ ev.kind }}{% if ev.source_type == 'ESTIMATED_RULE' %} · <span class="cal-estimated">Estimated</span>{% endif %}{% if ev.details %} · {{ ev.details }}{% endif %}</p>
            </div>
            {% if ev.source_url and ev.source_url.startswith('http') %}
            <a href="{{ safe_url(ev.source_url) }}" target="_blank" rel="noopener noreferrer" class="cal-source">{% if ev.source_type == 'ESTIMATED_RULE' %}SEC filings{% else %}Source{% endif %}</a>
            {% endif %}
          </article>
          {% endfor %}
        </section>
        {% else %}
        <p class="home-empty">No upcoming events. They appear here after the next pipeline run.</p>
        {% endfor %}
      </div>
    </main>
  </div>

  <script>
    """ + SHARED_MOBILE_JS + """

    function matchesCalendarFilter(evType, type) {
      if (type === 'ALL') return true;
      if (type === 'SEC') return evType.includes('SEC') || evType.includes('Statutory');
      return evType.includes(type);
    }

    // Positions come from the data, and the CSP allows them to be set from script but not inline.
    document.querySelectorAll('.cal-track [data-left]').forEach(el => {
      el.style.left = `${Number(el.dataset.left)}%`;
      if (el.dataset.bottom) el.style.bottom = `${Number(el.dataset.bottom)}px`;
    });

    function filterCalendar(type, btn) {
      document.querySelectorAll('.cal-filter-btn').forEach(b => b.classList.remove('active'));
      if (btn) btn.classList.add('active');

      document.querySelectorAll('.calendar-card').forEach(card => {
        card.hidden = !matchesCalendarFilter(card.getAttribute('data-event-type') || '', type);
      });
      document.querySelectorAll('.cal-mark').forEach(mark => {
        mark.classList.toggle('is-dimmed', !matchesCalendarFilter(mark.getAttribute('data-event-type') || '', type));
      });
      document.querySelectorAll('.cal-week').forEach(week => {
        week.hidden = !week.querySelector('.calendar-card:not([hidden])');
      });
    }
  </script>
</body>
</html>
"""

# ==============================================================================
# 4. MACROECONOMIC INTELLIGENCE TEMPLATE (site/economic.html)
# ==============================================================================
ECONOMIC_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=5.0">
  <meta name="description" content="Economic indicators and the watchlist holdings each one touches.">
  <title>StockPulse — Economy</title>
  <link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' rx='8' fill='%231d1d1f'/%3E%3Cpath d='M6 19h6l3-9 3 13 2-4h6' fill='none' stroke='%23ffffff' stroke-width='2'/%3E%3C/svg%3E">
  <script>""" + THEME_BOOT_JS + """</script>
  <style>
""" + SHARED_CSS + """
  </style>
</head>
<body>
  <div class="app-layout">
    """ + NAVIGATION_LAYOUT_HTML + """

    <main class="app-main">
      <header class="page-header">
        <h1 class="page-title">Economy</h1>
        <p class="page-standfirst">{{ economic_indicators|length }} indicators, and the companies each one affects.</p>
      </header>

      <details class="controls-panel" id="econFilters">
        <summary class="feed-filters-toggle">Filters</summary>
        <div class="filter-row">
          <span class="filter-label">Sector</span>
          <div class="feed-sector-bar">
            <button class="filter-btn active econ-sec-btn" type="button" data-sector="ALL" data-click="filterEconomicBySector">All</button>
            {% for sec in sector_directory %}
            <button class="filter-btn econ-sec-btn" type="button" data-sector="{{ sec.name }}" data-click="filterEconomicBySector">{{ sec.name }}</button>
            {% endfor %}
          </div>
        </div>
        <div class="filter-row">
          <label class="filter-label" for="econTickerSelect">Company</label>
          <select class="econ-select" id="econTickerSelect" data-change="filterEconomicByTicker">
            <option value="ALL">All companies</option>
            {% for sec in sector_directory %}
            <optgroup label="{{ sec.name }}" data-sector="{{ sec.name }}">
              {% for co in sec.companies %}
              <option value="{{ co.symbol }}">{{ co.symbol }} · {{ co.name }}</option>
              {% endfor %}
            </optgroup>
            {% endfor %}
          </select>
        </div>
      </details>

      <div class="econ-ledger" id="economicCardsGrid">
        {% for ind in economic_indicators %}
        <article class="economic-card" data-indicator-id="{{ ind.indicator_id }}" data-relevant-tickers="{{ ind.relevant_tickers }}">
          <div class="econ-name">
            <h2 class="economic-series-name">{{ ind.name }}</h2>
            <p class="econ-sub">{{ ind.category }} · As of {{ short_date(ind.observation_date) }}</p>
          </div>
          <div class="sparkline-wrapper" id="sparkline-{{ ind.indicator_id }}" data-history='{{ ind.history_json|default("[]") }}' data-unit="{{ ind.unit }}">
            <svg class="sparkline-svg" id="svg-{{ ind.indicator_id }}" viewBox="0 0 280 60" aria-hidden="true"></svg>
            <div class="sparkline-labels">
              <span class="spark-start"></span>
              <span class="spark-end"></span>
            </div>
          </div>
          <div class="econ-figure">
            <div class="economic-val">{{ ind.formatted_value.split(' (')[0] }}</div>
            {% if ' (' in ind.formatted_value %}<div class="econ-sub">({{ ind.formatted_value.split(' (', 1)[1] }}</div>{% endif %}
            <div class="econ-change">
              {% if ind.change_direction == 'up' %}▲ +{{ ind.change_value }}
              {% elif ind.change_direction == 'down' %}▼ {{ ind.change_value }}
              {% else %}Steady{% endif %}
            </div>
          </div>
          <details class="feed-details econ-details">
            <summary><span class="feed-meta">Why it matters, and the {{ ind.tickers_list|length }} companies it affects</span></summary>
            <div class="feed-details-body">
              {% if ind.ai_synthesis %}
              <p class="feed-detail-label">Why it matters</p>
              <p class="feed-takeaway">{{ ind.ai_synthesis }}</p>
              {% endif %}
              {% if ind.context_note %}<p class="feed-detail-label">What it measures</p><p>{{ ind.context_note }}</p>{% endif %}
              <p class="feed-detail-label">Companies</p>
              <p class="econ-holdings">{% for sym in ind.tickers_list %}<a href="company.html?ticker={{ sym|urlencode }}" class="ticker-badge">{{ sym }}</a> {% endfor %}</p>
            </div>
          </details>
        </article>
        {% endfor %}
      </div>

      {% set short_names = {'interest_rates': 'Rates', 'treasury_10y': '10Y', 'inflation': 'CPI', 'crude_oil': 'Oil', 'unemployment': 'Jobs'} %}
      <section class="econ-section" aria-labelledby="econMatrixHeading">
        <h2 class="fp-heading" id="econMatrixHeading">Who feels what</h2>
        <p class="econ-note">A dot means that indicator affects the company.</p>
        <div class="table-container">
          <table class="econ-matrix">
            <thead>
              <tr>
                <th scope="col">Company</th>
                {% for ind in economic_indicators %}
                <th scope="col" class="mx-col" title="{{ ind.name }}">{{ short_names.get(ind.indicator_id, ind.name) }}</th>
                {% endfor %}
                <th scope="col" class="mx-factors">Other factors</th>
              </tr>
            </thead>
            <tbody id="matrixTableBody">
              {% for sec in sector_directory %}
              <tr class="matrix-sector" data-sector="{{ sec.name }}"><th scope="rowgroup" colspan="{{ economic_indicators|length + 2 }}">{{ sec.name }}</th></tr>
              {% for co in sec.companies %}
              <tr class="matrix-row" data-ticker="{{ co.symbol }}" data-sector="{{ co.macro_sector }}">
                <th scope="row"><a href="company.html?ticker={{ co.symbol|urlencode }}" class="ticker-badge" title="{{ co.name }}">{{ co.symbol }}</a> <span class="mx-name">{{ co.name }}</span></th>
                {% for ind in economic_indicators %}
                <td class="mx-col">{% if co.symbol in ind.tickers_list %}<span class="mx-dot" role="img" aria-label="{{ co.symbol }} is sensitive to {{ ind.name }}"></span>{% endif %}</td>
                {% endfor %}
                <td class="mx-factors">{{ (co.macro_sensitivities or [])|join(', ')|replace('_', ' ') }}</td>
              </tr>
              {% endfor %}
              {% endfor %}
            </tbody>
          </table>
        </div>
      </section>

      <section class="econ-section" aria-labelledby="econScheduleHeading">
        <h2 class="fp-heading" id="econScheduleHeading">Coming up</h2>
        {% if economic_schedule and economic_schedule|selectattr('passed')|list|length == economic_schedule|length %}
        <p class="econ-note econ-stale">Every date on this schedule has passed. It is a fixed list and needs updating.</p>
        {% endif %}
        <ul class="econ-schedule">
          {% for ev in economic_schedule %}
          <li class="econ-release{% if ev.passed %} is-passed{% endif %}">
            <span class="cal-when"><span class="cal-date">{{ short_date(ev.date) }}</span><span class="cal-relative">{{ ev.timing }}</span></span>
            <div>
              <h3 class="cal-headline">{{ ev.title }}</h3>
              <p class="cal-details">{{ ev.authority }} · Expected: {{ ev.consensus }}</p>
            </div>
          </li>
          {% endfor %}
        </ul>
      </section>
    </main>
  </div>

  <script>
    """ + SHARED_MOBILE_JS + """

    let currentEconSector = 'ALL';
    let currentEconTicker = 'ALL';

    function renderEconSparklines() {
      const wrappers = document.querySelectorAll('.sparkline-wrapper');
      wrappers.forEach(wrap => {
        const svg = wrap.querySelector('.sparkline-svg');
        const rawHist = wrap.getAttribute('data-history');
        const unit = wrap.getAttribute('data-unit') || '';
        let history = [];
        try {
          history = JSON.parse(rawHist || '[]');
        } catch (e) {
          history = [];
        }
        if (!history || history.length < 2) return;

        const width = 280;
        const height = 60;
        const padX = 8;
        const padY = 8;

        const values = history.map(d => d.value);
        let minVal = Math.min(...values);
        let maxVal = Math.max(...values);
        if (minVal === maxVal) {
          minVal -= 1;
          maxVal += 1;
        }
        const range = maxVal - minVal;

        const points = history.map((pt, i) => {
          const x = padX + (i / (history.length - 1)) * (width - 2 * padX);
          const y = height - padY - ((pt.value - minVal) / range) * (height - 2 * padY);
          return { x, y, date: pt.date, value: pt.value };
        });

        const pathD = points.map((p, i) => (i === 0 ? `M ${p.x.toFixed(1)} ${p.y.toFixed(1)}` : `L ${p.x.toFixed(1)} ${p.y.toFixed(1)}`)).join(' ');
        const lastPt = points[points.length - 1];

        svg.setAttribute('viewBox', `0 0 ${width} ${height}`);
        svg.innerHTML = `
          <path d="${pathD}" fill="none" stroke="var(--accent)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" />
          <circle cx="${lastPt.x.toFixed(1)}" cy="${lastPt.y.toFixed(1)}" r="4" fill="var(--accent)" />
          <circle class="hover-dot" cx="0" cy="0" r="4.5" fill="var(--accent)" display="none" />
        `;

        // Update labels
        const startLabel = wrap.querySelector('.spark-start');
        const endLabel = wrap.querySelector('.spark-end');
        if (startLabel) startLabel.textContent = `${new Date(history[0].date.substring(0, 7) + '-15').toLocaleDateString('en-US', { month: 'short', year: 'numeric' })}: ${history[0].value}${unit.includes('%') ? '%' : ''}`;
        if (endLabel) endLabel.textContent = `${history[history.length - 1].value}${unit.includes('%') ? '%' : ''}`;

        // Create tooltip
        let tooltip = wrap.querySelector('.sparkline-tooltip');
        if (!tooltip) {
          tooltip = document.createElement('div');
          tooltip.className = 'sparkline-tooltip';
          wrap.appendChild(tooltip);
        }

        const hoverDot = svg.querySelector('.hover-dot');

        wrap.addEventListener('mousemove', (e) => {
          const rect = svg.getBoundingClientRect();
          const mouseX = e.clientX - rect.left;
          const pct = Math.max(0, Math.min(1, mouseX / rect.width));
          const idx = Math.min(history.length - 1, Math.max(0, Math.round(pct * (history.length - 1))));
          const activePt = points[idx];

          if (hoverDot) {
            hoverDot.setAttribute('cx', activePt.x.toFixed(1));
            hoverDot.setAttribute('cy', activePt.y.toFixed(1));
            hoverDot.style.display = 'block';
          }

          tooltip.style.display = 'block';
          tooltip.style.left = `${(activePt.x / width) * 100}%`;
          tooltip.style.top = `${(activePt.y / height) * 100}%`;
          tooltip.textContent = `${activePt.date}: ${activePt.value}${unit.includes('%') ? '%' : (unit.includes('$') ? ' ' + unit : '')}`;
        });

        wrap.addEventListener('mouseleave', () => {
          if (hoverDot) hoverDot.style.display = 'none';
          if (tooltip) tooltip.style.display = 'none';
        });
      });
    }

    function filterEconomicBySector(sector, btn) {
      currentEconSector = sector;
      document.querySelectorAll('.econ-sec-btn').forEach(b => b.classList.remove('active'));
      if (btn) btn.classList.add('active');

      // The company list only offers companies in the chosen sector.
      const select = document.getElementById('econTickerSelect');
      if (select) {
        select.querySelectorAll('optgroup').forEach(group => {
          const inSector = sector === 'ALL' || group.dataset.sector === sector;
          group.hidden = !inSector;
          group.disabled = !inSector;
        });
        const chosen = select.options[select.selectedIndex];
        if (chosen && chosen.parentElement.disabled) {
          select.value = 'ALL';
          currentEconTicker = 'ALL';
        }
      }

      applyEconomicFilters();
    }

    function filterEconomicByTicker(ticker) {
      currentEconTicker = ticker;
      applyEconomicFilters();
    }

    function applyEconomicFilters() {
      document.querySelectorAll('.economic-card').forEach(card => {
        const relevant = (card.getAttribute('data-relevant-tickers') || '').split(',').map(v => v.trim());
        card.hidden = currentEconTicker !== 'ALL' && !relevant.includes(currentEconTicker);
      });

      document.querySelectorAll('.matrix-row').forEach(row => {
        const secMatch = currentEconSector === 'ALL' || row.getAttribute('data-sector') === currentEconSector;
        const tickMatch = currentEconTicker === 'ALL' || row.getAttribute('data-ticker') === currentEconTicker;
        row.hidden = !(secMatch && tickMatch);
      });

      document.querySelectorAll('.matrix-sector').forEach(head => {
        const visible = Array.from(document.querySelectorAll('.matrix-row')).some(row => !row.hidden && row.getAttribute('data-sector') === head.dataset.sector);
        head.hidden = !visible;
      });
    }

    document.addEventListener('DOMContentLoaded', () => {
      renderEconSparklines();
    });
  </script>
</body>
</html>
"""

# ==============================================================================
# 5. PER-COMPANY DEEP-DIVE TEMPLATE (site/company.html)
# ==============================================================================
SETTINGS_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=5.0">
  <meta name="description" content="Choose the companies, sectors and kinds of story that show under For you.">
  <title>StockPulse — Your feed</title>
  <link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' rx='8' fill='%231d1d1f'/%3E%3Cpath d='M6 19h6l3-9 3 13 2-4h6' fill='none' stroke='%23ffffff' stroke-width='2'/%3E%3C/svg%3E">
  <script>""" + THEME_BOOT_JS + """</script>
  <style>
""" + SHARED_CSS + """
  </style>
</head>
<body class="page-settings">
  <div class="app-layout">
    """ + NAVIGATION_LAYOUT_HTML + """

    <main class="app-main">
      <header class="page-header">
        <h1 class="page-title">Your feed</h1>
        <p class="page-standfirst">Choose what shows under For you. <span data-follow-count></span>.</p>
      </header>

      <section class="settings-section" aria-labelledby="settingsViewHeading">
        <h2 class="settings-heading" id="settingsViewHeading">Start on</h2>
        <div class="view-tabs view-tabs-left" role="tablist" aria-label="Which tab Home and the Feed open on">
          <button class="view-tab" role="tab" type="button" data-view="foryou" data-click="setView" aria-selected="false">For you</button>
          <button class="view-tab" role="tab" type="button" data-view="all" data-click="setView" aria-selected="false">Everything</button>
        </div>
      </section>

      <section class="settings-section" aria-labelledby="settingsSectorHeading">
        <h2 class="settings-heading" id="settingsSectorHeading">Sectors</h2>
        <p class="settings-note">Following a sector follows every company in it, including ones added later.</p>
        <div class="picker-chips">
          {% for sec in sector_directory %}
          <button class="chip" type="button" data-click="toggleSector" data-sector-toggle="{{ sec.name }}" aria-pressed="false">{{ sec.name }} <span class="chip-count">{{ sec.count }}</span></button>
          {% endfor %}
        </div>
      </section>

      <section class="settings-section" aria-labelledby="settingsCompanyHeading">
        <h2 class="settings-heading" id="settingsCompanyHeading">Companies</h2>
        <input type="text" class="feed-search" id="settingsCompanyFilter" aria-label="Find a company" placeholder="Find a company or ticker" data-input="filterSettingsCompanies">
        {% for sec in sector_directory %}
        <details class="settings-group" data-sector-group="{{ sec.name }}">
          <summary class="settings-group-head"><span class="settings-group-name">{{ sec.name }}</span><span class="settings-group-meta" data-group-meta>{{ sec.count }} {{ 'company' if sec.count == 1 else 'companies' }}</span></summary>
          <ul class="follow-suggest">
            {% for co in sec.companies %}
            <li data-filter-text="{{ co.symbol|lower }} {{ co.name|lower }} {{ sec.name|lower }}" data-follow-mark="{{ co.symbol }}">
              <a class="follow-suggest-name settings-co" href="company.html?ticker={{ co.symbol|urlencode }}"><span class="settings-co-ticker">{{ co.symbol }}</span><span class="settings-co-name">{{ co.name }}</span></a>
              <span class="settings-via">In a sector you follow</span>
              <button class="follow-btn" type="button" data-click="toggleFollow" data-ticker="{{ co.symbol }}" aria-pressed="false">Follow</button>
            </li>
            {% endfor %}
          </ul>
        </details>
        {% endfor %}
        <p class="home-empty" id="settingsCompanyEmpty" hidden>No company matches.</p>
      </section>

      <section class="settings-section" aria-labelledby="settingsTypeHeading">
        <h2 class="settings-heading" id="settingsTypeHeading">Kinds of story in For you</h2>
        <p class="settings-note">Everything always shows every story.</p>
        <ul class="settings-toggles">
          {% for key, label in story_type_labels.items() %}
          <li>
            <button class="type-toggle" type="button" data-click="toggleStoryType" data-type-toggle="{{ key }}" aria-pressed="true">
              <span class="type-toggle-text"><span class="type-toggle-label">{{ label }}</span><span class="type-toggle-count">{{ story_type_counts[key] }} {{ 'story' if story_type_counts[key] == 1 else 'stories' }} right now</span></span>
              <span class="switch" aria-hidden="true"></span>
            </button>
          </li>
          {% endfor %}
        </ul>
      </section>

      <section class="settings-section" aria-labelledby="settingsDeviceHeading">
        <h2 class="settings-heading" id="settingsDeviceHeading">Saved in this browser</h2>
        <p class="settings-note">Your choices stay on this device. Nothing is sent anywhere, so a different phone, a private window or clearing site data starts fresh. To use them somewhere else, open this link there.</p>
        <div class="settings-actions">
          <button class="setup-yes" type="button" data-click="copySetupLink">Copy setup link</button>
          <button class="setup-no" type="button" data-click="resetFeed">Start over</button>
        </div>
      </section>
    </main>
  </div>

  <script>
    """ + SHARED_MOBILE_JS + """

    // Searching opens the sectors with a match and closes the rest; clearing the box folds them again.
    function filterSettingsCompanies(value) {
      const q = String(value || '').toLowerCase().trim();
      let shown = 0;
      document.querySelectorAll('.settings-group').forEach(group => {
        let any = false;
        group.querySelectorAll('li[data-filter-text]').forEach(li => {
          const match = !q || li.dataset.filterText.includes(q);
          li.hidden = !match;
          if (match) { any = true; shown += 1; }
        });
        group.hidden = !any;
        group.open = Boolean(q) && any;
      });
      const empty = document.getElementById('settingsCompanyEmpty');
      if (empty) empty.hidden = shown > 0;
    }

    // A company followed through its sector says so, and its own button stays available.
    // Each folded sector says how many of its companies are followed.
    function markSectorFollows() {
      const state = followState();
      const sectors = new Set(state.sectors);
      const direct = new Set(state.symbols);
      document.querySelectorAll('.settings-group').forEach(group => {
        const rows = [...group.querySelectorAll('li[data-follow-mark]')];
        const whole = sectors.has(group.dataset.sectorGroup);
        rows.forEach(li => {
          const via = li.querySelector('.settings-via');
          if (via) via.hidden = !whole || direct.has(li.dataset.followMark);
        });
        const n = rows.filter(li => direct.has(li.dataset.followMark)).length;
        const meta = group.querySelector('[data-group-meta]');
        if (meta) {
          meta.textContent = whole
            ? 'Following the whole sector'
            : `${plural(rows.length, 'company', 'companies')}${n ? `, following ${n}` : ''}`;
        }
      });
    }

    document.addEventListener('followchange', markSectorFollows);
    document.addEventListener('DOMContentLoaded', markSectorFollows);
  </script>
</body>
</html>
"""


COMPANY_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=5.0">
  <meta name="description" content="Your watchlist by sector, with a file on each company: performance, stories, events, and relationships.">
  <title>StockPulse — Companies</title>
  <link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' rx='8' fill='%231d1d1f'/%3E%3Cpath d='M6 19h6l3-9 3 13 2-4h6' fill='none' stroke='%23ffffff' stroke-width='2'/%3E%3C/svg%3E">
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.7/dist/chart.umd.min.js" integrity="sha384-vsrfeLOOY6KuIYKDlmVH5UiBmgIdB1oEf7p01YgWHuqmOHfZr374+odEv96n9tNC" crossorigin="anonymous"></script>
  <script>""" + THEME_BOOT_JS + """</script>
  <style>
""" + SHARED_CSS + """
  </style>
</head>
<body>
  <div class="app-layout">
    """ + NAVIGATION_LAYOUT_HTML + """

    <main class="app-main">
      {% set watchlist_symbols = watchlist_companies|map(attribute='symbol')|list %}
      <header class="page-header">
        <h1 class="page-title">Companies</h1>
        <p class="page-standfirst">{{ watchlist_companies|length }} on the watchlist. Pick one to see its news and price.</p>
      </header>

      <details class="company-directory-browser" id="companyDirectory" open>
        <summary class="feed-filters-toggle">All companies</summary>
        <input type="text" class="feed-search" id="companyStripFilter" aria-label="Find a company" placeholder="Find a ticker, company, or sector" data-input="filterCompanyStrip">
        <p class="econ-note">Percentages show how far each stock is ahead of or behind the S&amp;P 500 over 3 months.</p>
        <div class="company-browser-grid company-strip" id="companyStripContainer">
          {% for sec in sector_directory %}
          <section class="company-browser-sector">
            <h2 class="company-browser-sector-name">{{ sec.name }}</h2>
            {% for co in sec.companies %}
            <button class="company-browser-card company-strip-pill" type="button"
                    data-ticker="{{ co.symbol }}"
                    data-name="{{ co.name|lower }}"
                    data-sector="{{ co.macro_sector|lower }} {{ co.sector|replace('_', ' ')|lower }}"
                    data-follow-mark="{{ co.symbol }}"
                    data-click="switchCompany">
              <span class="company-browser-card-left">
                <span class="ticker-badge">{{ co.symbol }}</span>
                <span class="company-browser-card-info">
                  <span class="company-browser-card-name">{{ co.name }}</span>
                  <span class="company-browser-card-sec">{{ co.sector|replace('_', ' ')|title }}</span>
                </span>
              </span>
              <span class="company-browser-card-stats">
                {% if performance_data and co.symbol in (performance_data.companies or {}) %}
                <span class="company-browser-card-alpha {% if co.alpha_vs_spy > 0 %}tone-up{% elif co.alpha_vs_spy < 0 %}tone-down{% else %}tone-flat{% endif %}">{% if co.alpha_vs_spy > 0 %}+{% endif %}{{ co.alpha_vs_spy }}%</span>
                {% endif %}
                <span class="company-browser-card-stories">{{ co.story_count }} {% if co.story_count == 1 %}story{% else %}stories{% endif %}</span>
              </span>
            </button>
            {% endfor %}
          </section>
          {% endfor %}
        </div>
      </details>

      {% for co in watchlist_companies %}
      {% set co_news = [] %}
      {% for it in items %}
        {% if it.ticker == co.symbol or (it.related_tickers_list and co.symbol in it.related_tickers_list) %}
          {% set _ = co_news.append(it) %}
        {% endif %}
      {% endfor %}

      {% set co_events = [] %}
      {% for ev in calendar_events %}
        {% if ev.ticker == co.symbol %}
          {% set _ = co_events.append(ev) %}
        {% endif %}
      {% endfor %}

      {% set ns = namespace(high_count=0, edgar_count=0, ir_count=0, news_count=0) %}
      {% for it in co_news %}
        {% if it.score >= 7.0 %}{% set ns.high_count = ns.high_count + 1 %}{% endif %}
        {% if it.source == 'sec_edgar' %}{% set ns.edgar_count = ns.edgar_count + 1 %}{% endif %}
        {% if it.source == 'company_ir' %}{% set ns.ir_count = ns.ir_count + 1 %}{% endif %}
        {% if it.source == 'news_media' %}{% set ns.news_count = ns.news_count + 1 %}{% endif %}
      {% endfor %}

      <article class="company-profile-container" id="profile-{{ co.symbol }}" data-ticker="{{ co.symbol }}"{% if not loop.first %} hidden{% endif %}>
        <header class="company-hero-box">
          <p class="company-hero-symbol">{{ co.symbol }} · {{ co.sector|replace('_', ' ')|title }}</p>
          <div class="company-hero-title-row">
            <h2 class="company-hero-name">{{ co.name }}</h2>
            <button class="follow-btn" type="button" data-click="toggleFollow" data-ticker="{{ co.symbol }}" aria-pressed="false">Follow</button>
          </div>
          {% set price = ((performance_data or {}).get('companies') or {}).get(co.symbol, {}).get('target', {}).get('latest_price') %}
          {% if co.move_pct is not none and price is number %}
          <p class="company-price"><span class="company-price-val">${{ "%.2f"|format(price) }}</span> <span class="company-price-move {{ 'tone-up' if co.move_pct >= 0 else 'tone-down' }}">{{ "%+.2f"|format(co.move_pct) }}%</span> <span class="company-price-span">over 3 months</span></p>
          {% endif %}
          {% if co.notes %}<p class="company-notes-card">{{ co.notes }}</p>{% endif %}
          <p class="company-links">
            {% if co.cik %}<a href="https://www.sec.gov/edgar/browse/?CIK={{ co.cik|urlencode }}" target="_blank" rel="noopener noreferrer">SEC filings ↗</a>{% endif %}
            {% if co.newsroom_url or co.ir_page_url or co.ir_feed_url %}<a href="{{ safe_url(co.newsroom_url or co.ir_page_url or co.ir_feed_url) }}" target="_blank" rel="noopener noreferrer">Newsroom ↗</a>{% endif %}
            <span>Regulators: {{ (co.regulators or ['SEC'])|join(', ')|replace('_', ' ') }}</span>
          </p>

          <dl class="company-kpi-ribbon">
            <div class="company-kpi-card">
              <dt class="company-kpi-title">Stories</dt>
              <dd class="company-kpi-val">{{ co_news|length }}</dd>
              <dd class="company-kpi-sub">{{ ns.news_count }} news, {{ ns.edgar_count }} SEC, {{ ns.ir_count }} releases</dd>
            </div>
            <div class="company-kpi-card">
              <dt class="company-kpi-title">To read first</dt>
              <dd class="company-kpi-val">{{ ns.high_count }}</dd>
            </div>
            <div class="company-kpi-card">
              <dt class="company-kpi-title">Next event</dt>
              <dd class="company-kpi-val">{% if co_events %}{{ short_date(co_events[0].event_date) }}{% else %}None{% endif %}</dd>
              <dd class="company-kpi-sub">{% if co_events %}{{ event_kind(co_events[0].event_type or '') }}{% else %}Nothing scheduled{% endif %}</dd>
            </div>
            <div class="company-kpi-card">
              <dt class="company-kpi-title">Connections</dt>
              <dd class="company-kpi-val">{{ (co.key_customers|length if co.key_customers else 0) + (co.key_suppliers|length if co.key_suppliers else 0) + (co.competitors|length if co.competitors else 0) }}</dd>
              <dd class="company-kpi-sub">{{ co.key_customers|length if co.key_customers else 0 }} customers, {{ co.key_suppliers|length if co.key_suppliers else 0 }} suppliers, {{ co.competitors|length if co.competitors else 0 }} competitors</dd>
            </div>
          </dl>
        </header>

        <section class="comparative-perf-card" id="compPerfCard-{{ co.symbol }}" aria-label="Three-month performance">
          <h3 class="fp-heading">3 months against peers and the S&amp;P 500</h3>
          <p class="econ-note">Is {{ co.symbol }}'s move normal or unusual? Percent change since the start of the 3 months.</p>
          <div class="perf-kpi-grid" id="compPerfKpi-{{ co.symbol }}"></div>
          <div class="perf-chart-box"><canvas id="compPerfCanvas-{{ co.symbol }}" role="img" aria-label="Line chart of {{ co.symbol }}, its peers, and the S&amp;P 500. The table below has the figures."></canvas></div>
          <div class="perf-table-wrap">
            <table class="perf-table" id="compPerfTable-{{ co.symbol }}"></table>
          </div>
        </section>

        <div class="company-grid-layout">
          <section class="company-card-deck" aria-label="Stories">
            <h3 class="fp-heading">Stories</h3>
            <div class="company-feed-tools">
              <div class="filter-options" role="group" aria-label="Filter by source">
                <button class="filter-btn active company-source-filter-btn" type="button" data-source="ALL" data-ticker="{{ co.symbol }}" data-click="filterCompanyNews">All <span class="pill-count">{{ co_news|length }}</span></button>
                <button class="filter-btn company-source-filter-btn" type="button" data-source="news_media" data-ticker="{{ co.symbol }}" data-click="filterCompanyNews">News <span class="pill-count">{{ ns.news_count }}</span></button>
                <button class="filter-btn company-source-filter-btn" type="button" data-source="sec_edgar" data-ticker="{{ co.symbol }}" data-click="filterCompanyNews">SEC <span class="pill-count">{{ ns.edgar_count }}</span></button>
                <button class="filter-btn company-source-filter-btn" type="button" data-source="company_ir" data-ticker="{{ co.symbol }}" data-click="filterCompanyNews">Releases <span class="pill-count">{{ ns.ir_count }}</span></button>
              </div>
              <input type="text" class="feed-search company-feed-search-input" id="search-{{ co.symbol }}" data-ticker="{{ co.symbol }}" aria-label="Search {{ co.symbol }} stories" placeholder="Search {{ co.symbol }} stories" data-input="searchCompanyFeed">
            </div>

            {% if co_news %}
              {% for it in co_news %}
              <article class="company-news-item{% if it.score >= 7.0 %} is-high{% endif %}" data-source="{{ it.source }}">
                <div class="feed-body">
                  <h4 class="feed-headline"><a href="{{ safe_url(it.url, '#') }}" target="_blank" rel="noopener noreferrer">{{ it.clean_headline }}</a></h4>
                  {% if it.story_text %}<p class="feed-summary">{{ figures(it.story_text) }}</p>{% endif %}
                  <details class="feed-details">
                    <summary><span class="feed-meta">{{ it.category }} · {{ it.source_label }}{% if it.form_or_type %} · {{ it.form_or_type }}{% endif %}</span></summary>
                    <div class="feed-details-body">
                      {% if it.cross_references_list %}
                      <p class="feed-detail-label">Also relevant to {{ it.cross_references_list|length }} {{ 'company' if it.cross_references_list|length == 1 else 'companies' }}</p>
                      <ul class="feed-refs">
                        {% for ref in it.cross_references_list %}
                        <li>{% if ref.related_ticker in watchlist_symbols %}<a href="company.html?ticker={{ ref.related_ticker|urlencode }}" data-ticker="{{ ref.related_ticker }}" data-click="openCompany" class="ticker-badge">{{ ref.related_ticker }}</a>{% else %}<span class="company-outside">{{ ref.related_ticker }}</span>{% endif %} {{ ref.impact_note }}</li>
                        {% endfor %}
                      </ul>
                      {% endif %}
                      {% if it.score_breakdown %}<p class="feed-detail-label">How it scored: {{ it.score }}</p><p class="feed-breakdown">{{ it.score_breakdown|replace(' | ', ' · ') }}</p>{% endif %}
                      <a href="{{ safe_url(it.url, '#') }}" target="_blank" rel="noopener noreferrer" class="home-more">{% if it.source == 'sec_edgar' %}Read the filing{% elif it.source == 'company_ir' %}Read the release{% else %}Read the article{% endif %}</a>
                    </div>
                  </details>
                </div>
                <span class="date-cell">{{ short_date(it.published_date) }}</span>
              </article>
              {% endfor %}
              <p class="fp-empty company-feed-empty" hidden>No stories match.</p>
            {% else %}
              <p class="home-empty">No stories recorded for {{ co.symbol }} in this period.</p>
            {% endif %}
          </section>

          <aside class="company-side-deck">
            <section class="company-side-box">
              <h3 class="fp-heading">Coming up</h3>
              {% if co_events %}
              <ul class="fp-side-list">
                {% for ev in co_events %}
                <li class="fp-event">
                  <span class="fp-event-date">{{ short_date(ev.event_date) }}</span>
                  <span class="fp-event-text">{{ ev.headline }}<span class="company-side-sub">{{ ev.relative_badge }} · {{ event_kind(ev.event_type or '') }}</span></span>
                </li>
                {% endfor %}
              </ul>
              {% else %}
              <p class="home-empty">Nothing scheduled.</p>
              {% endif %}
            </section>

            <section class="company-side-box">
              <h3 class="fp-heading">What in the economy affects it</h3>
              <ul class="fp-side-list">
                {% for ind in economic_indicators %}
                {% if ind.tickers_list and co.symbol in ind.tickers_list %}
                <li class="fp-indicator" title="{{ ind.context_note }}">
                  <span>{{ ind.name }}</span>
                  <span class="fp-indicator-value">{{ ind.formatted_value.split(' (')[0] }}</span>
                </li>
                {% endif %}
                {% endfor %}
              </ul>
              {% if co.macro_sensitivities %}<p class="company-side-note">Also watching: {{ co.macro_sensitivities|join(', ')|replace('_', ' ') }}</p>{% endif %}
            </section>

            <section class="company-side-box">
              <h3 class="fp-heading">Customers, suppliers and competitors</h3>
              {% for label, names in [('Customers', co.key_customers), ('Suppliers', co.key_suppliers), ('Competitors', co.competitors)] %}
              {% if names %}
              <p class="feed-detail-label">{{ label }}</p>
              <p class="company-names">{% for name in names %}{% if name in watchlist_symbols %}<a href="company.html?ticker={{ name|urlencode }}" data-ticker="{{ name }}" data-click="openCompany" class="ticker-badge">{{ name }}</a>{% else %}<span class="company-outside">{{ name }}</span>{% endif %}{% if not loop.last %}<span class="company-sep">, </span>{% endif %}{% endfor %}</p>
              {% endif %}
              {% endfor %}
            </section>
          </aside>
        </div>
      </article>
      {% endfor %}
    </main>
  </div>

  <script>
    """ + SHARED_MOBILE_JS + """

    const perfData = {{ performance_data_json|safe }};
    const companyChartInstances = {};

    function trackRecentlyViewedCompany(ticker) {
      if (!ticker) return;
      try {
        const sym = ticker.toUpperCase().trim();
        let stored = JSON.parse(localStorage.getItem('stockpulse_recently_viewed') || '[]');
        if (!Array.isArray(stored)) stored = [];
        stored = stored.filter(item => {
          const s = typeof item === 'string' ? item : item.symbol;
          return s && s.toUpperCase() !== sym;
        });
        stored.unshift({
          symbol: sym,
          visitedAt: Date.now()
        });
        localStorage.setItem('stockpulse_recently_viewed', JSON.stringify(stored.slice(0, 8)));
      } catch (e) {
        console.error('Failed to track recently viewed company:', e);
      }
    }

    function renderCompanyComparativeChart(symbol) {
      if (!perfData || !perfData.companies) return;
      const coData = perfData.companies[symbol];
      if (!coData) return;

      const isPhone = window.innerWidth <= 480;
      const isNarrow = window.innerWidth <= 768;

      const kpiGrid = document.getElementById('compPerfKpi-' + symbol);
      const table = document.getElementById('compPerfTable-' + symbol);
      const canvas = document.getElementById('compPerfCanvas-' + symbol);
      if (!canvas) return;

      const target = coData.target;
      const comps = coData.competitors || [];
      const spy = coData.benchmark;

      const targetColor = cssColor('--text-primary');
      const compColors = [cssColor('--series-1'), cssColor('--series-2'), cssColor('--series-3')];
      const spyColor = cssColor('--text-muted');

      // 1. KPI Ribbon
      if (kpiGrid && target) {
        const tgtPct = target.total_pct_change;

        const alphaPeers = coData.alpha_vs_peers;

        const spyPct = spy ? spy.total_pct_change : 0;
        const avgPeerPct = coData.avg_competitor_pct;

        kpiGrid.innerHTML = `
          <div class="perf-kpi-box">
            <div class="perf-kpi-label">${escapeHtml(symbol)} over 3 months</div>
            <div class="perf-kpi-val ${tgtPct >= 0 ? 'tone-up' : 'tone-down'}">${tgtPct >= 0 ? '+' : ''}${tgtPct.toFixed(2)}%</div>
            <div class="perf-kpi-sub">Latest: $${target.latest_price.toFixed(2)}</div>
          </div>
          <div class="perf-kpi-box">
            <div class="perf-kpi-label">Peers on average</div>
            <div class="perf-kpi-val ${avgPeerPct >= 0 ? 'tone-up' : 'tone-down'}\">${avgPeerPct >= 0 ? '+' : ''}${avgPeerPct.toFixed(2)}%</div>
            <div class="perf-kpi-sub">${escapeHtml(comps.map(c => c.symbol).join(', ') || 'None')}</div>
          </div>
          <div class="perf-kpi-box">
            <div class="perf-kpi-label">S&P 500 (SPY)</div>
            <div class="perf-kpi-val ${spyPct >= 0 ? 'tone-up' : 'tone-down'}\">${spyPct >= 0 ? '+' : ''}${spyPct.toFixed(2)}%</div>
            <div class="perf-kpi-sub">The wider market</div>
          </div>
          <div class="perf-kpi-box">
            <div class="perf-kpi-label">Compared with peers</div>
            <div class="perf-kpi-val ${alphaPeers >= 0 ? 'tone-up' : 'tone-down'}">${alphaPeers >= 0 ? '+' : ''}${alphaPeers.toFixed(2)}%</div>
            <div class="perf-kpi-sub tone-strong ${coData.assessment_type === 'positive' ? 'tone-up' : (coData.assessment_type === 'negative' ? 'tone-down' : 'tone-flat')}">${escapeHtml(plainAssessment(coData.assessment))}</div>
          </div>
        `;
      }

      // 2. Peer Table
      if (table && target) {
        let rowsHtml = `
          <thead>
            <tr>
              <th>Name</th>
              <th>Role</th>
              <th>Start</th>
              <th>Latest</th>
              <th>Change</th>
              <th>Against ${escapeHtml(symbol)}</th>
            </tr>
          </thead>
          <tbody>
            <tr class="perf-row-target">
              <td><span class="ticker-badge ticker-${escapeHtml(symbol)}">${escapeHtml(symbol)}</span> ${escapeHtml(coData.name)}</td>
              <td>This company</td>
              <td class="perf-num">$${target.base_price.toFixed(2)}</td>
              <td class="perf-num">$${target.latest_price.toFixed(2)}</td>
              <td class="perf-num ${target.total_pct_change >= 0 ? 'tone-up' : 'tone-down'}\">${target.total_pct_change >= 0 ? '+' : ''}${target.total_pct_change.toFixed(2)}%</td>
              <td class="perf-num">&mdash;</td>
            </tr>
        `;

        comps.forEach((c, idx) => {
          const delta = (c.total_pct_change - target.total_pct_change).toFixed(2);
          rowsHtml += `
            <tr>
              <td>${document.getElementById('profile-' + c.symbol) ? `<a href="company.html?ticker=${encodeURIComponent(c.symbol)}" data-ticker="${escapeHtml(c.symbol)}" data-click="openCompany" class="ticker-badge">${escapeHtml(c.symbol)}</a>` : `<span class="ticker-badge">${escapeHtml(c.symbol)}</span>`}</td>
              <td>Peer</td>
              <td class="perf-num">$${c.base_price.toFixed(2)}</td>
              <td class="perf-num">$${c.latest_price.toFixed(2)}</td>
              <td class="perf-num ${c.total_pct_change >= 0 ? 'tone-up' : 'tone-down'}\">${c.total_pct_change >= 0 ? '+' : ''}${c.total_pct_change.toFixed(2)}%</td>
              <td class="perf-num ${delta >= 0 ? 'tone-up' : 'tone-down'}\">${delta >= 0 ? '+' : ''}${delta}%</td>
            </tr>
          `;
        });

        if (spy) {
          const spyDelta = (spy.total_pct_change - target.total_pct_change).toFixed(2);
          rowsHtml += `
            <tr>
              <td><span class="ticker-badge">SPY</span> S&amp;P 500 ETF</td>
              <td>Benchmark</td>
              <td class="perf-num">$${spy.base_price.toFixed(2)}</td>
              <td class="perf-num">$${spy.latest_price.toFixed(2)}</td>
              <td class="perf-num ${spy.total_pct_change >= 0 ? 'tone-up' : 'tone-down'}\">${spy.total_pct_change >= 0 ? '+' : ''}${spy.total_pct_change.toFixed(2)}%</td>
              <td class="perf-num ${spyDelta >= 0 ? 'tone-up' : 'tone-down'}\">${spyDelta >= 0 ? '+' : ''}${spyDelta}%</td>
            </tr>
          `;
        }

        rowsHtml += `</tbody>`;
        table.innerHTML = rowsHtml;
      }

      // 3. Render Chart
      if (companyChartInstances[symbol]) {
        companyChartInstances[symbol].destroy();
      }

      if (!target || !target.series) return;
      const labels = target.series.map(pt => shortDay(pt.date));

      const datasets = [
        {
          label: symbol,
          data: target.series.map(pt => pt.pct_change),
          borderColor: targetColor,
          borderWidth: 2.5,
          fill: false,
          tension: 0.15,
          pointRadius: 0,
          pointHoverRadius: 5,
        }
      ];

      comps.forEach((c, idx) => {
        const color = compColors[idx % compColors.length];
        datasets.push({
          label: c.symbol,
          data: c.series.map(pt => pt.pct_change),
          borderColor: color,
          borderWidth: 1.5,
          fill: false,
          tension: 0.15,
          pointRadius: 0,
          pointHoverRadius: 4,
        });
      });

      if (spy && spy.series) {
        datasets.push({
          label: 'S&P 500 (SPY)',
          data: spy.series.map(pt => pt.pct_change),
          borderColor: spyColor,
          borderWidth: isPhone ? 1.5 : 2,
          borderDash: [5, 5],
          fill: false,
          tension: 0.25,
          pointRadius: 0,
          pointHoverRadius: 4,
        });
      }

      companyChartInstances[symbol] = new Chart(canvas, {
        type: 'line',
        data: { labels, datasets },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          interaction: { mode: 'index', intersect: false },
          plugins: {
            legend: {
              display: true,
              position: 'top',
              align: isPhone ? 'center' : 'end',
              labels: {
                boxWidth: isPhone ? 10 : 14,
                boxHeight: 3,
                font: { family: CHART_FONT, size: isPhone ? 10 : 11 },
                color: cssColor('--text-secondary'),
                padding: isPhone ? 8 : 12
              }
            },
            tooltip: {
              backgroundColor: cssColor('--text-primary'),
              titleColor: cssColor('--bg-base'),
              bodyColor: cssColor('--bg-base'),
              titleFont: { family: CHART_FONT, size: 12, weight: '500' },
              bodyFont: { family: CHART_FONT, size: 11 },
              padding: 10,
              cornerRadius: 8,
              callbacks: {
                label: function(context) {
                  return `${context.dataset.label}: ${context.parsed.y >= 0 ? '+' : ''}${context.parsed.y.toFixed(2)}%`;
                }
              }
            }
          },
          scales: {
            x: {
              grid: { display: false },
              ticks: {
                maxTicksLimit: isPhone ? 4 : (isNarrow ? 5 : 8),
                font: { family: CHART_FONT, size: isPhone ? 8.5 : 10 },
                color: cssColor('--text-muted'),
                maxRotation: 0
              }
            },
            y: {
              grid: { color: cssColor('--border-subtle') },
              ticks: {
                callback: function(val) { return (val >= 0 ? '+' : '') + val + '%'; },
                font: { family: CHART_FONT, size: isPhone ? 8.5 : 10 },
                color: cssColor('--text-muted'),
                maxTicksLimit: isPhone ? 4 : 6
              }
            }
          }
        }
      });
    }

    function filterCompanyStrip(rawVal) {
      const q = (rawVal || '').toLowerCase().trim();
      document.querySelectorAll('.company-strip-pill').forEach(pill => {
        const haystack = [pill.dataset.ticker, pill.dataset.name, pill.dataset.sector].join(' ').toLowerCase();
        pill.hidden = Boolean(q) && !haystack.includes(q);
      });
      document.querySelectorAll('.company-browser-sector').forEach(group => {
        group.hidden = !group.querySelector('.company-strip-pill:not([hidden])');
      });
    }

    function applyCompanyFeedFilter(container, source, query) {
      let shown = 0;
      container.querySelectorAll('.company-news-item').forEach(row => {
        const sourceMatch = source === 'ALL' || row.getAttribute('data-source') === source;
        const textMatch = !query || (row.textContent || '').toLowerCase().includes(query);
        row.hidden = !(sourceMatch && textMatch);
        if (!row.hidden) shown += 1;
      });
      const empty = container.querySelector('.company-feed-empty');
      if (empty) empty.hidden = shown !== 0;
    }

    function searchCompanyFeed(ticker, rawVal) {
      const container = document.getElementById('profile-' + ticker);
      if (!container) return;

      const activeSourceBtn = container.querySelector('.company-source-filter-btn.active');
      const activeSource = activeSourceBtn ? activeSourceBtn.getAttribute('data-source') || 'ALL' : 'ALL';
      applyCompanyFeedFilter(container, activeSource, (rawVal || '').toLowerCase().trim());
    }

    let currentCompany = null;

    // showOnly: load a company without counting it as viewed, as on a bare visit to the directory.
    function switchCompany(ticker, pushState = true, showOnly = false) {
      const allProfiles = document.querySelectorAll('.company-profile-container');
      let target = document.getElementById('profile-' + ticker);
      const found = Boolean(target);
      if (!target) {
        target = allProfiles[0];
        if (!target) return;
        ticker = target.getAttribute('data-ticker');
      }
      allProfiles.forEach(el => { el.hidden = el !== target; });
      currentCompany = ticker;

      const directory = document.getElementById('companyDirectory');
      if (directory) directory.open = showOnly;
      if (found && !showOnly) trackRecentlyViewedCompany(ticker);

      renderCompanyComparativeChart(ticker);

      document.querySelectorAll('.company-strip-pill').forEach(pill => {
        pill.classList.toggle('active', pill.getAttribute('data-ticker') === ticker);
      });

      window.scrollTo({ top: 0, behavior: 'smooth' });

      if (pushState) {
        const newUrl = new URL(window.location);
        newUrl.searchParams.set('ticker', ticker);
        window.history.pushState({ ticker: ticker }, '', newUrl);
      }
    }

    function filterCompanyNews(ticker, source, btn) {
      const container = document.getElementById('profile-' + ticker);
      if (!container) return;

      container.querySelectorAll('.company-source-filter-btn').forEach(b => b.classList.remove('active'));
      if (btn) btn.classList.add('active');

      const searchInput = document.getElementById('search-' + ticker);
      applyCompanyFeedFilter(container, source, (searchInput ? searchInput.value : '').toLowerCase().trim());
    }

    window.addEventListener('popstate', () => {
      const ticker = new URLSearchParams(window.location.search).get('ticker');
      const safe = ticker && /^[A-Za-z0-9.\\-]{1,10}$/.test(ticker) ? ticker.toUpperCase() : '';
      switchCompany(safe || 'NVDA', false, !ticker);
    });

    document.addEventListener('themechange', () => {
      if (currentCompany) renderCompanyComparativeChart(currentCompany);
    });

    window.addEventListener('DOMContentLoaded', () => {
      const requested = new URLSearchParams(window.location.search).get('ticker');
      const known = requested && /^[A-Za-z0-9.\\-]{1,10}$/.test(requested) &&
        document.getElementById('profile-' + requested.toUpperCase());
      if (known) {
        switchCompany(requested.toUpperCase(), false);
      } else if (requested) {
        // Anything else, hostile or just unknown, is treated as a ticker we don't cover.
        switchCompany('', false);
      } else {
        switchCompany('NVDA', false, true);
      }
    });
  </script>
</body>
</html>
"""


# ==============================================================================
# MASTER RENDER ENGINE
# ==============================================================================
def _short_date(value: Optional[str]) -> str:
    """Turn '2026-11-04' into 'Nov 4'. Anything unparseable is returned unchanged."""
    try:
        parsed = datetime.strptime(str(value), "%Y-%m-%d")
    except ValueError:
        return str(value or "")
    return f"{parsed.strftime('%b')} {parsed.day}"


def _event_kind(event_type: str) -> str:
    """Short label for a calendar event type, matching the page's filter groups."""
    if "Earnings" in event_type:
        return "Earnings call"
    if "Dividend" in event_type:
        return "Dividend"
    if "SEC" in event_type or "Statutory" in event_type:
        return "SEC deadline"
    return "Conference"


def _calendar_view(events: List[Dict[str, Any]], today: Optional[date] = None) -> Dict[str, Any]:
    """Lay calendar events out for the timeline strip and the week-by-week agenda."""
    today = today or date.today()
    dated = []
    for index, event in enumerate(events):
        try:
            when = date.fromisoformat(str(event.get("event_date")))
        except ValueError:
            continue
        dated.append((when, dict(event, kind=_event_kind(event.get("event_type") or ""), anchor=f"event-{index}")))
    if not dated:
        return {"marks": [], "months": [], "weeks": [], "today_pos": 0}

    start = min(today, dated[0][0])
    end = max(start + timedelta(days=28), max(when for when, _ in dated))
    span = max((end - start).days, 1)

    def position(when: date) -> float:
        return round((when - start).days / span * 100, 2)

    months = []
    cursor = date(start.year, start.month, 1)
    while cursor <= end:
        # Skip a month label that would collide with the "Today" label.
        if cursor >= start and position(cursor) - position(today) > 7:
            months.append({"label": cursor.strftime("%b"), "pos": position(cursor)})
        cursor = date(cursor.year + cursor.month // 12, cursor.month % 12 + 1, 1)

    marks = []
    lanes: Dict[date, int] = {}
    weeks: Dict[date, Dict[str, Any]] = {}
    this_monday = today - timedelta(days=today.weekday())
    for when, event in dated:
        lane = lanes.get(when, 0)
        lanes[when] = lane + 1
        marks.append({
            "pos": position(when),
            "lane": min(lane, 3),
            "anchor": event["anchor"],
            "ticker": event.get("ticker"),
            "kind": event["kind"],
            "event_type": event.get("event_type"),
            "estimated": event.get("source_type") == "ESTIMATED_RULE",
            "date": _short_date(event.get("event_date")),
        })
        monday = when - timedelta(days=when.weekday())
        if monday == this_monday:
            label = "This week"
        elif monday == this_monday + timedelta(days=7):
            label = "Next week"
        elif monday < this_monday:
            label = "Past"
        else:
            label = f"Week of {_short_date(monday.isoformat())}"
        weeks.setdefault(monday, {"label": label, "events": []})["events"].append(event)

    return {"marks": marks, "months": months, "weeks": [weeks[k] for k in sorted(weeks)], "today_pos": position(today)}


def _economic_schedule(events: List[Dict[str, Any]], today: Optional[date] = None) -> List[Dict[str, Any]]:
    """Sort releases by date and work out timing now, since the stored labels can be stale."""
    today = today or date.today()
    rows = []
    for event in events:
        row = dict(event, passed=False, timing="")
        try:
            when = date.fromisoformat(str(event.get("date")))
        except ValueError:
            rows.append(row)
            continue
        row["passed"] = when < today
        row["timing"] = "Date passed" if row["passed"] else calculate_relative_badge(when.isoformat(), today)
        rows.append(row)
    return sorted(rows, key=lambda r: str(r.get("date")))


def _orbit_companies(
    items: List[Dict[str, Any]], companies: List[Dict[str, Any]], today: Optional[date] = None
) -> List[Dict[str, Any]]:
    """Watchlist companies for the Home ring, biggest recent story first; no stories go last.

    "New" means published in the last 7 days, the same window the live lookup uses for news.
    """
    today = today or date.today()
    top_scores: Dict[str, float] = {}
    new_counts: Dict[str, int] = {}
    for item in items:
        ticker, score = item.get("ticker"), item.get("score")
        if not ticker or score is None:
            continue
        top_scores[ticker] = max(score, top_scores.get(ticker, score))
        try:
            age = (today - date.fromisoformat(str(item.get("published_date"))[:10])).days
        except ValueError:
            continue
        if 0 <= age <= 7:
            new_counts[ticker] = new_counts.get(ticker, 0) + 1
    ranked = [
        {
            "symbol": co.get("symbol", ""),
            "name": co.get("name", ""),
            "top_score": top_scores.get(co.get("symbol")),
            "new_count": new_counts.get(co.get("symbol"), 0),
            "move_pct": co.get("move_pct"),
            "spark": co.get("spark", ""),
        }
        for co in companies
    ]
    ranked.sort(key=lambda co: (co["top_score"] is None, -(co["top_score"] or 0), -co["new_count"], co["symbol"]))
    return ranked


def _sparkline_points(series: Any, width: int = 100, height: int = 28, samples: int = 24) -> str:
    """SVG polyline points for a price series, thinned out so 30 chips stay small in the page."""
    closes = [pt["close"] for pt in series or []
              if isinstance(pt, dict) and isinstance(pt.get("close"), (int, float))]
    if len(closes) < 2:
        return ""
    step = max(1, (len(closes) - 1) / (samples - 1))
    picked = [closes[round(i * step)] for i in range(int((len(closes) - 1) / step) + 1)]
    if picked[-1] != closes[-1]:
        picked.append(closes[-1])
    low, high = min(picked), max(picked)
    spread = (high - low) or 1
    last = len(picked) - 1
    return " ".join(f"{i * width / last:.1f},{height - (v - low) / spread * height:.1f}" for i, v in enumerate(picked))


def _heat_class(pct: float) -> str:
    """The map's colour step. Under 2% either way reads as flat."""
    size = abs(pct)
    if size < 2:
        return "heat-n"
    level = 1 if size < 8 else (2 if size < 16 else 3)
    return f"heat-{'u' if pct > 0 else 'd'}{level}"


# The five kinds of story someone can hide from For you. storyType() in the shared script sorts
# stories the same way as _story_type here.
STORY_TYPES = {
    "news": "News articles",
    "releases": "Company press releases",
    "results": "Results and reports",
    "insider": "Insider trades",
    "filings": "Other SEC filings",
}


def _story_type(item: Dict[str, Any]) -> str:
    category = item.get("category") or ""
    source = item.get("source") or ""
    if category == "Insider Transactions":
        return "insider"
    if category == "Earnings & Financials":
        return "results"
    if source == "sec_edgar":
        return "filings"
    if source == "company_ir":
        return "releases"
    return "news"


SEC_BOILERPLATE = "Official SEC submission"
FIGURE_PATTERN = re.compile(
    r"(?:US)?[$€£]\s?\d(?:[\d,.]*\d)?(?:\s?(?:million|billion|trillion|bn)\b)?"
    r"|[+\-−]?\d[\d,.]*\s?(?:%|percent\b)"
    r"|\b\d[\d,.]*\s(?:million|billion|trillion)\b",
    re.IGNORECASE,
)


def _story_text(item: Dict[str, Any]) -> str:
    """What the source itself said, which is where the real numbers are.

    SEC items only carry a filing reference, so they get nothing rather than filler. Sources cut
    long text off; a trailing fragment is dropped unless it has a figure in it.
    """
    text = clean_text(item.get("summary", "") or "")
    if not text or text.startswith(SEC_BOILERPLATE):
        return ""
    text = re.sub(r"(?<=[a-z%)])\.(?=[A-Z])", ". ", text)
    if text.endswith(("...", "…")):
        body = text.rstrip(".… ")
        ends = [m.end() for m in re.finditer(r"[.!?][\"”’]?\s", body)]
        if ends and ends[-1] >= 60 and not re.search(r"\d", body[ends[-1]:]):
            return body[:ends[-1]].strip()
        return body + "…"
    return text


def _ai_summary(item: Dict[str, Any]) -> str:
    """Gemini's summary, only when it passed the number check (keyword templates are never shown)."""
    if not str(item.get("summary_origin") or "").startswith("ai:"):
        return ""
    return clean_text(item.get("llm_summary", "") or "")


def _figures_html(text: str) -> Markup:
    """Escape the text, then pick out money and percentages so they can be scanned."""
    return Markup(FIGURE_PATTERN.sub(lambda m: f'<strong class="fig">{m.group(0)}</strong>', str(escape(text or ""))))


def _next_earnings(events: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """The first earnings event in an already date-sorted calendar, if any."""
    for event in events:
        if "earning" in f"{event.get('event_type', '')} {event.get('headline', '')}".lower():
            return event
    return None


def _script_json(value: Any) -> str:
    """Serialize for a <script> block: no scraped text can end the block or open an HTML comment in it."""
    return (
        json.dumps(value)
        .replace("</", "<\\/")
        .replace("<!--", "\\u003c!--")
        .replace("<script", "\\u003cscript")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def _safe_url(value: Any, fallback: str = "#") -> str:
    """Only absolute http(s) links reach an href, so a javascript: link in the data goes nowhere."""
    text = str(value or "").strip()
    return text if SAFE_URL_PATTERN.fullmatch(text) else fallback


def _inline_hashes(html: str) -> Dict[str, List[str]]:
    """SHA-256 source expressions for each inline script and style block in a rendered page."""
    def digest(block: str) -> str:
        return "'sha256-" + base64.b64encode(hashlib.sha256(block.encode("utf-8")).digest()).decode("ascii") + "'"

    return {
        "script": sorted({digest(b) for b in INLINE_SCRIPT_PATTERN.findall(html)}),
        "style": sorted({digest(b) for b in INLINE_STYLE_PATTERN.findall(html)}),
    }


def _content_security_policy(html: str) -> str:
    """The policy for one rendered page. Inline code runs only if it matches this exact render."""
    hashes = _inline_hashes(html)
    script_sources = list(hashes["script"])
    if CHART_JS_URL in html:
        script_sources.append(CHART_JS_URL)
    return "; ".join([
        "default-src 'none'",
        "script-src " + " ".join(script_sources),
        "style-src " + " ".join(hashes["style"]),
        "img-src 'self' data:",
        "connect-src 'self'",
        "base-uri 'none'",
        "form-action 'none'",
        "frame-ancestors 'none'",
    ])


def _headers_file(policies: Dict[str, str]) -> str:
    """Cloudflare Pages _headers: shared headers for everything, plus each page's own CSP."""
    lines = [
        "# Generated by pipeline/render.py. The hashes change on every render, so do not edit by hand.",
        "/*",
        "  X-Content-Type-Options: nosniff",
        "  X-Frame-Options: DENY",
        "  Referrer-Policy: strict-origin-when-cross-origin",
        "  Permissions-Policy: camera=(), microphone=(), geolocation=(), payment=(), usb=()",
        "",
    ]
    for fname, policy in policies.items():
        stem = fname[: -len(".html")]
        # Pages serves /news.html at /news, and index.html at /.
        paths = ["/", "/index", "/index.html"] if stem == "index" else [f"/{stem}", f"/{fname}"]
        for path in paths:
            lines += [path, f"  Content-Security-Policy: {policy}", ""]
    return "\n".join(lines)


def render_dashboard(
    output_path: Optional[str] = None,
    db_path: Optional[str] = None,
    performance_data: Optional[Dict[str, Any]] = None,
) -> str:
    """Render all 5 static HTML pages (Overview, Feed, Calendar, Macro, Company Detail) to disk."""
    if output_path is None:
        site_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "site")
        os.makedirs(site_dir, exist_ok=True)
        primary_output = os.path.join(site_dir, "index.html")
    else:
        primary_output = output_path
        site_dir = os.path.dirname(output_path)
        os.makedirs(site_dir, exist_ok=True)

    # 1. Fetch data from SQLite
    raw_items = get_all_news_items(limit=None, db_path=db_path)
    priority_items = get_top_priority_items(limit=6, db_path=db_path)
    stats = get_news_stats(db_path=db_path)
    chart_data = get_chart_data(db_path=db_path)
    economic_indicators = get_economic_indicators(db_path=db_path)
    if not economic_indicators:
        try:
            from pipeline.economic import collect_economic_indicators
            economic_indicators = collect_economic_indicators(db_path=db_path)
        except Exception as e:
            logger.warning("Could not auto-seed economic indicators: %s", e)

    try:
        from pipeline.economic import get_upcoming_economic_events
        upcoming_economic_events = get_upcoming_economic_events()
    except Exception as e:
        logger.warning("Could not get upcoming economic events: %s", e)
        upcoming_economic_events = []

    calendar_events = get_forthcoming_calendar(limit=30, db_path=db_path)
    recent_runs = get_recent_pipeline_runs(limit=5, db_path=db_path)
    latest_run = recent_runs[0] if recent_runs else None
    now_str = datetime.now().strftime("%b %d, %Y %H:%M:%S")

    # 2. Enrich items with human-readable headlines & macro sectors
    items = []
    for it in raw_items:
        it_copy = dict(it)
        it_copy["clean_headline"] = format_human_headline(it_copy)
        it_copy["story_text"], it_copy["ai_summary"] = _story_text(it_copy), _ai_summary(it_copy)
        it_copy["macro_sector"] = get_company_macro_sector(it_copy.get("ticker", ""), it_copy.get("category", ""))
        items.append(it_copy)

    enriched_priority = []
    for it in priority_items:
        it_copy = dict(it)
        it_copy["clean_headline"] = format_human_headline(it_copy)
        it_copy["story_text"], it_copy["ai_summary"] = _story_text(it_copy), _ai_summary(it_copy)
        it_copy["macro_sector"] = get_company_macro_sector(it_copy.get("ticker", ""), it_copy.get("category", ""))
        enriched_priority.append(it_copy)

    # 3. Load watchlist and build sector directory
    watchlist_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "watchlist.yaml")
    raw_watchlist_companies: List[Dict[str, Any]] = []
    if os.path.exists(watchlist_path):
        with open(watchlist_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
            raw_watchlist_companies = cfg.get("tickers", [])

    # 4. Comparative stock performance data
    if performance_data is None:
        try:
            from collectors.stock_prices import collect_comparative_performance
            performance_data = collect_comparative_performance(watchlist_path=watchlist_path)
        except Exception as e:
            logger.warning("Could not collect comparative performance data: %s", e)
            performance_data = {}

    perf_companies = (performance_data or {}).get("companies", {})
    ticker_counts = stats.get("by_ticker", {})

    enriched_watchlist: List[Dict[str, Any]] = []
    sector_directory_map: Dict[str, List[Dict[str, Any]]] = {sec: [] for sec in SECTOR_METADATA}

    for co in raw_watchlist_companies:
        co_copy = dict(co)
        sym = co_copy.get("symbol", "")
        macro_sec = get_company_macro_sector(sym, co_copy.get("sector", ""))
        co_copy["macro_sector"] = macro_sec
        co_copy["sector_icon"] = SECTOR_METADATA.get(macro_sec, {}).get("icon", "")
        co_copy["story_count"] = ticker_counts.get(sym, 0)

        # Performance snippet
        co_perf = perf_companies.get(sym, {})
        co_copy["perf_total_pct"] = co_perf.get("target", {}).get("total_pct_change", 0.0)
        # Unlike the 0.0 above, None means no price data, so nothing gets drawn as if it were flat.
        move = co_perf.get("target", {}).get("total_pct_change")
        spark = _sparkline_points(co_perf.get("target", {}).get("series"))
        has_move = isinstance(move, (int, float)) and bool(spark)
        co_copy["move_pct"] = move if has_move else None
        co_copy["spark"] = spark if has_move else ""
        co_copy["alpha_vs_spy"] = co_perf.get("alpha_vs_spy", 0.0)
        co_copy["alpha_vs_peers"] = co_perf.get("alpha_vs_peers", 0.0)
        co_copy["assessment"] = co_perf.get("assessment", "In-Line")
        co_copy["assessment_type"] = co_perf.get("assessment_type", "neutral")

        enriched_watchlist.append(co_copy)
        if macro_sec not in sector_directory_map:
            sector_directory_map[macro_sec] = []
        sector_directory_map[macro_sec].append(co_copy)

    sector_directory = []
    for sec_name, meta in SECTOR_METADATA.items():
        cos = sector_directory_map.get(sec_name, [])
        if cos:
            sector_directory.append({
                "name": sec_name,
                "icon": meta["icon"],
                "description": meta["description"],
                "count": len(cos),
                "companies": cos,
            })

    common_context = {
        "short_date": _short_date,
        "safe_url": _safe_url,
        "economic_schedule": _economic_schedule(upcoming_economic_events),
        "event_kind": _event_kind,
        "calendar_view": _calendar_view(calendar_events),
        "orbit_companies": _orbit_companies(items, enriched_watchlist),
        "next_earnings": _next_earnings(calendar_events),
        "heat_class": _heat_class,
        "figures": _figures_html,
        "watchlist_moves": sorted(
            (c for c in enriched_watchlist if c["move_pct"] is not None),
            key=lambda c: c["move_pct"],
            reverse=True,
        ),
        "items": items,
        "priority_items": enriched_priority,
        "stats": stats,
        "chart_data_json": _script_json(chart_data),
        "economic_indicators": economic_indicators,
        "upcoming_economic_events": upcoming_economic_events,
        "calendar_events": calendar_events,
        "recent_runs": recent_runs,
        "latest_run": latest_run,
        "generated_at": now_str,
        "watchlist_companies": enriched_watchlist,
        "sector_directory": sector_directory,
        "company_sectors": {c["symbol"]: c["macro_sector"] for c in enriched_watchlist},
        "story_type_labels": STORY_TYPES,
        "story_type_counts": {k: sum(1 for it in items if _story_type(it) == k) for k in STORY_TYPES},
        "sector_directory_json": _script_json([
            {
                "name": s["name"],
                "icon": s["icon"],
                "count": s["count"],
                "companies": [
                    {
                        "symbol": c["symbol"],
                        "name": c["name"],
                        "sector": c["sector"],
                        "macro_sector": c["macro_sector"],
                        "story_count": c["story_count"],
                        "alpha_vs_spy": c["alpha_vs_spy"],
                        "perf_total_pct": c["perf_total_pct"],
                    } for c in s["companies"]
                ]
            } for s in sector_directory
        ]),
        "performance_data": performance_data,
        "performance_data_json": _script_json(performance_data or {}),
    }

    # 4. Render and save all 7 pages
    pages = [
        ("index.html", INDEX_TEMPLATE, "home"),
        ("news.html", NEWS_TEMPLATE, "news"),
        ("calendar.html", CALENDAR_TEMPLATE, "calendar"),
        ("economic.html", ECONOMIC_TEMPLATE, "economic"),
        ("company.html", COMPANY_TEMPLATE, "company"),
        ("analytics.html", ANALYTICS_TEMPLATE, "analytics"),
        ("settings.html", SETTINGS_TEMPLATE, "settings"),
    ]

    policies: Dict[str, str] = {}
    for fname, tmpl_str, active_page in pages:
        tmpl = Template(tmpl_str, autoescape=True)
        ctx = dict(common_context)
        ctx["active_page"] = active_page
        rendered = tmpl.render(**ctx)
        policies[fname] = _content_security_policy(rendered)

        out_file = os.path.join(site_dir, fname)
        with open(out_file, "w", encoding="utf-8") as f:
            f.write(rendered)
        logger.info("Rendered page: %s", out_file)

    with open(os.path.join(site_dir, "_headers"), "w", encoding="utf-8") as f:
        f.write(_headers_file(policies))

    return primary_output
