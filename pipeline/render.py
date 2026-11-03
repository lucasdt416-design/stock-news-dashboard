"""Multi-page static HTML dashboard generator with responsive architecture & organic editorial design (Phase 7).

Unified Shared Layout & Organic Flow System:
- Organic Design Language: Softer, larger border-radius tokens (14px–36px), atmospheric ambient backdrop meshes, and soft diffused shadows replacing rigid rectangular grids.
- Asymmetric & Varied Card Layouts:
  1. Home (index.html): Asymmetric Hero Bento Deck with a prominent Featured Intelligence Card, companion Catalyst Beacon, and Macro Pulse widget; curved analytics charts and health hub.
  2. Feed (news.html): Editorial Priority Suite with a spacious Lead #1 Feature Card and staggered secondary cards; floating rounded filter pills.
  3. Calendar (calendar.html): Spotlight Next Milestone Banner with prominent date box and countdown badge, followed by organic cards.
  4. Macro (economic.html): Anchor rate cards (Fed Funds & Inflation) with oversized focal metrics, followed by responsive sensitivity matrices.
- Brand Polish: Removed "Cloud Intelligence" tagline from beneath the StockPulse logo for clean, centered typography.
- Bulletproof Search Dropdown: Nested flex constraints (min-width: 0, text-overflow: ellipsis, box-sizing: border-box) guaranteeing zero overflow outside the search container.
- Responsive top navbar, off-canvas slide-over drawer, and bottom navigation bar.

Generates:
1. site/index.html    - Home / Overview: Hero greeting, live search, widget preview cards & rich charts
2. site/news.html     - Full Intelligence Feed: Priority Panel, Filters, Search, Sort & News Table
3. site/calendar.html - Forthcoming Corporate Calendar: Earnings calls, Dividends, Filing Deadlines
4. site/economic.html - Macroeconomic Intelligence: FRED indicators, Live Sensitivity Filtering & Matrix
"""

import json
import logging
import os
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional
import yaml
from jinja2 import Template
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
    :root {
      color-scheme: light;
      --bg-base: #f6f4ee;
      --bg-surface: #fbfaf6;
      --bg-surface-elevated: #edeae2;
      --bg-surface-glass: var(--bg-surface);
      --bg-surface-highlight: #e3dfd5;
      --bg-hover: #efece4;
      --border-subtle: #e8e5dc;
      --border-card: #d9d5ca;
      --border-glass: var(--border-card);
      --text-primary: #1b1a17;
      --text-secondary: #4a4740;
      --text-muted: #6d6961;
      --accent: #1f4e6b;
      --accent-soft: #e3e9ea;
      --on-accent: #fbfaf6;
      --pos: #2a6b4a;
      --pos-soft: #e3ebe2;
      --neg: #a63d2f;
      --neg-soft: #f1e2dc;
      --warn: #85641b;
      --warn-soft: #eee6d0;
      --scrim: rgba(27, 26, 23, 0.45);

      /* Older names kept so existing components inherit the new palette. */
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

      --font-serif: 'Newsreader', Georgia, 'Times New Roman', serif;
      --font-sans: 'IBM Plex Sans', -apple-system, 'Helvetica Neue', Arial, sans-serif;
      --font-mono: 'IBM Plex Mono', ui-monospace, Menlo, monospace;

      --radius-xs: 2px;
      --radius-sm: 3px;
      --radius-md: 4px;
      --radius-lg: 4px;
      --radius-xl: 4px;
      --radius-2xl: 4px;
      --radius-full: 3px;

      --shadow-sm: none;
      --shadow-card: none;
      --shadow-hover: none;
      --shadow-float: none;
      --shadow-dropdown: 0 8px 24px rgba(27, 26, 23, 0.12);
      --shadow-modal: 0 8px 24px rgba(27, 26, 23, 0.18);

      --transition-fast: 0.12s ease-out;
      --transition-normal: 0.18s ease-out;
    }

    @media (prefers-color-scheme: dark) {
      :root:not([data-theme="light"]) {
        color-scheme: dark;
        --bg-base: #151412;
        --bg-surface: #1b1a17;
        --bg-surface-elevated: #272520;
        --bg-surface-highlight: #322f29;
        --bg-hover: #23211d;
        --border-subtle: #272520;
        --border-card: #37342e;
        --text-primary: #ece8df;
        --text-secondary: #bdb8ac;
        --text-muted: #98938a;
        --accent: #93bad0;
        --accent-soft: #232c30;
        --on-accent: #151412;
        --pos: #84c3a0;
        --pos-soft: #1f2b24;
        --neg: #e39484;
        --neg-soft: #33211d;
        --warn: #d3b56f;
        --warn-soft: #2e2818;
        --scrim: rgba(0, 0, 0, 0.6);
        --shadow-dropdown: 0 8px 24px rgba(0, 0, 0, 0.5);
        --shadow-modal: 0 8px 24px rgba(0, 0, 0, 0.6);
      }
    }

    :root[data-theme="dark"] {
      color-scheme: dark;
      --bg-base: #151412;
      --bg-surface: #1b1a17;
      --bg-surface-elevated: #272520;
      --bg-surface-highlight: #322f29;
      --bg-hover: #23211d;
      --border-subtle: #272520;
      --border-card: #37342e;
      --text-primary: #ece8df;
      --text-secondary: #bdb8ac;
      --text-muted: #98938a;
      --accent: #93bad0;
      --accent-soft: #232c30;
      --on-accent: #151412;
      --pos: #84c3a0;
      --pos-soft: #1f2b24;
      --neg: #e39484;
      --neg-soft: #33211d;
      --warn: #d3b56f;
      --warn-soft: #2e2818;
      --scrim: rgba(0, 0, 0, 0.6);
      --shadow-dropdown: 0 8px 24px rgba(0, 0, 0, 0.5);
      --shadow-modal: 0 8px 24px rgba(0, 0, 0, 0.6);
    }

    button, input, select, textarea {
      font: inherit;
    }

    h1, h2, h3 {
      font-family: var(--font-serif);
      font-weight: 500;
      letter-spacing: -0.01em;
      font-optical-sizing: auto;
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
    .comparative-select { max-width: 100%; min-width: 0; }

    /* Mobile Segmented View Toggle (Comparative Performance Module) */
    .perf-mobile-toggle {
      display: none;
      background: var(--bg-surface-elevated);
      border: 1px solid var(--border-card);
      border-radius: var(--radius-full);
      padding: 0.25rem;
      gap: 0.25rem;
      margin-bottom: 1rem;
      width: 100%;
    }

    .perf-toggle-btn {
      flex: 1;
      padding: 0.4rem 0.75rem;
      border: none;
      background: transparent;
      border-radius: var(--radius-full);
      font-size: 0.78rem;
      font-weight: 700;
      color: var(--text-muted);
      cursor: pointer;
      transition: all var(--transition-fast);
      text-align: center;
    }

    .perf-toggle-btn.active {
      background: var(--bg-surface);
      color: var(--text-primary);
      box-shadow: var(--shadow-sm);
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

      .hero-title {
        font-size: 1.85rem !important;
      }

      .analytics-grid {
        grid-template-columns: 1fr !important;
        gap: 1.25rem !important;
      }

      .priority-section, .health-section {
        padding: 1.25rem !important;
      }
    }

    /* Dedicated Phone Viewports (<= 640px and <= 480px / 375px - 414px) */
    @media (max-width: 640px) {
      .app-main {
        padding: 0.85rem 0.85rem calc(5.5rem + env(safe-area-inset-bottom)) 0.85rem !important;
      }

      .hero-title {
        font-size: 1.55rem !important;
        line-height: 1.25 !important;
      }

      .bento-card {
        padding: 1.15rem !important;
        border-radius: var(--radius-lg) !important;
      }

      .comparative-perf-card {
        padding: 1rem !important;
        border-radius: var(--radius-lg) !important;
      }

      .comparative-perf-header {
        flex-direction: column !important;
        align-items: flex-start !important;
        gap: 0.75rem !important;
      }

      .perf-mobile-toggle {
        display: flex !important;
      }

      .perf-kpi-grid {
        grid-template-columns: repeat(2, 1fr) !important;
        gap: 0.5rem !important;
      }

      .perf-kpi-val {
        font-size: 1.05rem !important;
      }

      .analytics-card {
        padding: 1rem !important;
        border-radius: var(--radius-lg) !important;
      }

      .health-section {
        padding: 1rem !important;
        border-radius: var(--radius-lg) !important;
      }

      .health-grid {
        grid-template-columns: 1fr !important;
        gap: 0.65rem !important;
      }

      .health-header {
        flex-direction: column !important;
        align-items: flex-start !important;
        gap: 0.5rem !important;
      }
    }

    /* Sidebar Brand (Logo and Title Only - No Tagline) */
    .sidebar-brand {
      display: block;
      text-decoration: none;
      color: inherit;
    }

    .brand-title {
      font-family: var(--font-serif);
      font-size: 1.4rem;
      font-weight: 500;
      letter-spacing: -0.015em;
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

    .nav-count {
      font-family: var(--font-mono);
      font-size: 0.72rem;
      color: var(--text-muted);
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

    .pulse-dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      display: inline-block;
    }

    .catalyst-ticker, .ticker-badge {
      white-space: nowrap !important;
      word-break: keep-all !important;
      overflow-wrap: normal !important;
      display: inline-block;
    }

    .hero-title {
      font-size: 2.65rem;
      font-weight: 600;
      letter-spacing: -0.04em;
      color: var(--text-primary);
      margin-bottom: 0.55rem;
      word-break: normal;
      overflow-wrap: normal;
      line-height: 1.18;
    }

    /* Global Search & Command Bar (⌘K) with Bulletproof Overflow Containment */
    .search-wrapper {
      position: relative;
      width: 100%;
      margin: 0 0 3rem;
      z-index: 20;
    }

    .search-box {
      display: flex;
      align-items: center;
      gap: 0.7rem;
      border-bottom: 1px solid var(--text-primary);
      padding: 0.7rem 0;
      cursor: text;
    }

    .search-icon-wrap { display: flex; color: var(--text-muted); flex-shrink: 0; }

    .search-input {
      flex: 1;
      min-width: 0;
      border: none;
      outline: none;
      background: transparent;
      font-size: 1rem;
      color: var(--text-primary);
    }

    .search-input::placeholder { color: var(--text-muted); }

    .search-shortcut {
      font-family: var(--font-mono);
      font-size: 0.72rem;
      color: var(--text-muted);
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
    .feed-headline { font-size: 1.08rem; font-weight: 400; line-height: 1.3; letter-spacing: 0; overflow-wrap: anywhere; }
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
    .fp-more { display: inline-block; margin-top: 0.9rem; font-size: 0.84rem; color: var(--accent); text-decoration: none; }
    .fp-more:hover { text-decoration: underline; text-underline-offset: 3px; }
    .fp-empty { color: var(--text-muted); font-size: 0.92rem; padding: 0.5rem 0; }

    .fp-side { display: flex; flex-direction: column; gap: 2.75rem; }
    .fp-heading { font-size: 1.15rem; padding-bottom: 0.5rem; border-bottom: 1px solid var(--text-primary); }
    .fp-side-list { list-style: none; }
    .fp-event, .fp-indicator { padding: 0.6rem 0; border-bottom: 1px solid var(--border-subtle); font-size: 0.86rem; }
    .fp-event { display: grid; grid-template-columns: 3.5rem minmax(0, 1fr); gap: 0.5rem; align-items: baseline; }
    .fp-event-date { font-family: var(--font-mono); font-size: 0.76rem; color: var(--text-muted); }
    .fp-indicator { display: flex; justify-content: space-between; align-items: baseline; gap: 1rem; color: var(--text-secondary); }
    .fp-indicator-value { font-family: var(--font-mono); font-size: 0.82rem; color: var(--text-primary); white-space: nowrap; }

    .fp-index { margin-bottom: 3.5rem; }
    .fp-index-row { display: grid; grid-template-columns: 10rem minmax(0, 1fr); gap: 1rem; padding: 0.7rem 0; border-bottom: 1px solid var(--border-subtle); align-items: baseline; }
    .fp-index-row dt { font-size: 0.86rem; color: var(--text-secondary); }
    .fp-index-row dd { display: flex; flex-wrap: wrap; gap: 0.25rem 1.1rem; }
    .fp-index-item { font-family: var(--font-mono); font-size: 0.86rem; color: var(--text-primary); text-decoration: none; padding: 0.15rem 0; }
    .fp-index-item:hover { color: var(--accent); }
    .fp-index-item sup { font-size: 0.64rem; color: var(--text-muted); margin-left: 0.15rem; line-height: 0; }

    .fp-heading-row { display: flex; justify-content: space-between; align-items: baseline; border-bottom: 1px solid var(--text-primary); }
    .fp-heading-row .fp-heading { border-bottom: none; }
    .fp-clear { background: none; border: none; color: var(--text-muted); font-size: 0.8rem; cursor: pointer; min-height: 32px; }
    .fp-clear:hover { color: var(--text-primary); }
    .fp-recent-list { list-style: none; }
    .fp-recent a { display: grid; grid-template-columns: 3.75rem minmax(0, 1fr) auto; gap: 0.75rem; align-items: baseline; padding: 0.6rem 0; border-bottom: 1px solid var(--border-subtle); color: inherit; text-decoration: none; font-size: 0.9rem; }
    .fp-recent a:hover .fp-recent-name { color: var(--accent); }
    .fp-recent-when { font-size: 0.76rem; color: var(--text-muted); }
    [hidden] { display: none !important; }

    @media (max-width: 860px) {
      .fp-grid { grid-template-columns: minmax(0, 1fr); gap: 2.75rem; }
      .fp-index-row { grid-template-columns: minmax(0, 1fr); gap: 0.25rem; }
      .fp-index-item { padding: 0.45rem 0; }
      .fp-index-row dd { gap: 0 1.25rem; }
      .fp-more { padding: 0.35rem 0; }
      .fp-clear { min-height: 44px; }
      .search-shortcut { display: none; }
      .dropdown-tabs-grid { grid-template-columns: minmax(0, 1fr); }
    }

    .bento-card {
      background: var(--bg-surface-glass);
      border: 1px solid var(--border-glass);
      border-radius: var(--radius-lg);
      padding: 1.65rem;
      box-shadow: var(--shadow-card);
      text-decoration: none;
      color: inherit;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      transition: all var(--transition-normal);
      min-width: 0;
      position: relative;
      overflow: hidden;
    }

    .bento-card:hover {
      border-color: var(--border-card);
      box-shadow: var(--shadow-hover);
      transform: translateY(-2px);
    }

    /* Recently Viewed Companies Quick Access Deck */
    .recently-viewed-section {
      margin-bottom: 2.75rem;
      width: 100%;
      position: relative;
      z-index: 1;
    }

    /* Section Headers */
    .section-header-row {
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 0.85rem;
      margin-bottom: 1.5rem;
    }

    .section-heading {
      font-size: 1.35rem;
      font-weight: 600;
      letter-spacing: -0.025em;
      color: var(--text-primary);
    }

    .section-time-pill {
      display: inline-flex;
      align-items: center;
      gap: 0.4rem;
      background: var(--bg-surface-glass);
      border: 1px solid var(--border-card);
      padding: 0.4rem 0.85rem;
      border-radius: var(--radius-full);
      font-size: 0.8rem;
      font-weight: 600;
      color: var(--text-secondary);
      max-width: 100%;
      box-shadow: var(--shadow-sm);
    }

    /* Analytics Grid & Cards */
    .analytics-grid {
      display: grid;
      grid-template-columns: 3fr 2fr;
      gap: 1.5rem;
      margin-bottom: 3.5rem;
    }

    .analytics-card {
      background: var(--bg-surface-glass);
      border: 1px solid var(--border-glass);
      border-radius: var(--radius-lg);
      padding: 1.75rem;
      box-shadow: var(--shadow-card);
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      min-width: 0;
    }

    .analytics-card-header {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      margin-bottom: 1.25rem;
      gap: 0.5rem;
      flex-wrap: wrap;
    }

    .analytics-card-title {
      font-size: 0.82rem;
      font-weight: 700;
      color: var(--text-muted);
      text-transform: uppercase;
      letter-spacing: 0.05em;
      margin-bottom: 0.25rem;
    }

    .analytics-metric-val {
      font-family: var(--font-mono);
      font-size: 2rem;
      font-weight: 600;
      color: var(--text-primary);
      display: flex;
      align-items: center;
      gap: 0.5rem;
    }

    .analytics-delta-pill {
      font-size: 0.75rem;
      font-weight: 700;
      color: var(--accent-emerald);
      background: var(--pos-soft);
      padding: 0.2rem 0.55rem;
      border-radius: var(--radius-full);
    }

    .chart-canvas-container {
      position: relative;
      height: 250px;
      width: 100%;
      min-height: 200px;
    }

    .category-legend-list {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
      gap: 0.5rem;
      margin-top: 1.25rem;
      padding-top: 1rem;
      border-top: 1px solid var(--border-card);
    }

    .category-stat-row {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 0.5rem;
      padding: 0.45rem 0.65rem;
      border-radius: var(--radius-sm);
      background: var(--bg-surface-elevated);
      border: 1px solid var(--border-card);
      transition: background 0.15s ease, border-color 0.15s ease;
    }

    .category-stat-row:hover {
      background: var(--bg-base);
      border-color: var(--border-card);
    }

    .cat-stat-left {
      display: flex;
      align-items: center;
      gap: 0.5rem;
      min-width: 0;
      flex: 1;
    }

    .category-legend-dot {
      width: 9px;
      height: 9px;
      border-radius: 50%;
      flex-shrink: 0;
      box-shadow: 0 0 0 2px var(--bg-surface);
    }

    .cat-stat-name {
      font-size: 0.78rem;
      font-weight: 600;
      color: var(--text-primary);
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    .cat-stat-right {
      display: flex;
      align-items: center;
      gap: 0.35rem;
      flex-shrink: 0;
    }

    .cat-stat-count {
      font-family: var(--font-mono);
      font-size: 0.76rem;
      font-weight: 700;
      color: var(--text-primary);
    }

    .cat-stat-pct {
      font-family: var(--font-mono);
      font-size: 0.68rem;
      font-weight: 600;
      color: var(--text-muted);
      background: var(--bg-surface-elevated);
      padding: 0.1rem 0.35rem;
      border-radius: 4px;
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

    .form-type-pill {
      font-family: var(--font-mono);
      font-size: 0.68rem;
      font-weight: 700;
      color: var(--text-muted);
      background: var(--bg-surface-elevated);
      padding: 0.15rem 0.5rem;
      border-radius: 6px;
      border: 1px solid var(--border-card);
      display: inline-block;
      flex-shrink: 0;
      white-space: nowrap;
    }

    .category-badge {
      font-size: 0.72rem;
      font-weight: 700;
      padding: 0.2rem 0.55rem;
      border-radius: var(--radius-full);
      display: inline-block;
      background: var(--bg-surface-elevated);
      color: var(--text-secondary);
      border: 1px solid var(--border-card);
      white-space: nowrap;
      flex-shrink: 0;
    }

    /* Distinct Source Badges */
    .source-badge {
      display: inline-flex;
      align-items: center;
      gap: 0.3rem;
      font-size: 0.7rem;
      font-weight: 700;
      padding: 0.18rem 0.55rem;
      border-radius: var(--radius-full);
      white-space: nowrap;
      letter-spacing: 0.01em;
      text-decoration: none;
      flex-shrink: 0;
    }

    .source-badge-edgar {
      background: var(--bg-surface-elevated);
      color: var(--text-secondary);
      border: 1px solid var(--border-card);
    }

    .source-badge-ir {
      background: var(--accent-soft);
      color: var(--accent);
      border: 1px solid var(--accent-soft);
    }

    .source-badge-news {
      background: var(--pos-soft);
      color: var(--pos);
      border: 1px solid var(--pos-soft);
    }

    /* Score Badges */
    .score-badge {
      font-family: var(--font-mono);
      font-weight: 600;
      font-size: 0.85rem;
      padding: 0.22rem 0.6rem;
      border-radius: var(--radius-sm);
      display: inline-flex;
      align-items: center;
      gap: 0.2rem;
      flex-shrink: 0;
      white-space: nowrap;
    }

    .score-high {
      background: var(--pos-soft);
      color: var(--pos);
      border: 1px solid var(--pos-soft);
    }

    .score-med {
      background: var(--warn-soft);
      color: var(--warn);
      border: 1px solid var(--warn-soft);
    }

    .score-low {
      background: var(--bg-surface-elevated);
      color: var(--text-muted);
      border: 1px solid var(--border-card);
    }

    /* Company Page Specific Styles */
    .company-strip-wrap {
      margin-bottom: 1.5rem;
      overflow-x: auto;
      padding-bottom: 0.5rem;
      -webkit-overflow-scrolling: touch;
    }
    .company-strip {
      display: flex;
      gap: 0.5rem;
      align-items: center;
      min-width: max-content;
    }
    .company-strip-pill {
      display: inline-flex;
      align-items: center;
      gap: 0.45rem;
      padding: 0.45rem 0.85rem;
      border-radius: var(--radius-full);
      background: var(--bg-surface);
      border: 1px solid var(--border-card);
      color: var(--text-secondary);
      font-size: 0.82rem;
      font-weight: 600;
      cursor: pointer;
      text-decoration: none;
      transition: all 0.2s ease;
    }
    .company-strip-pill:hover {
      border-color: var(--border-accent);
      color: var(--text-primary);
      transform: translateY(-1px);
    }
    .company-strip-pill.active {
      background: var(--accent-blue);
      color: var(--on-accent);
      border-color: var(--accent-blue);
      box-shadow: 0 4px 12px var(--accent-soft);
    }
    .company-strip-pill.active .ticker-badge {
      background: var(--bg-surface);
      color: var(--on-accent);
      border-color: var(--bg-surface);
    }

    .company-hero-box {
      background: var(--bg-surface);
      border: 1px solid var(--border-card);
      border-radius: var(--radius-lg);
      padding: 1.5rem 1.75rem;
      margin-bottom: 1.5rem;
      box-shadow: var(--shadow-sm);
    }
    .company-hero-header {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      flex-wrap: wrap;
      gap: 1rem;
      border-bottom: 1px solid var(--border-card);
      padding-bottom: 1.25rem;
      margin-bottom: 1.25rem;
    }
    .company-hero-left {
      display: flex;
      align-items: center;
      gap: 1rem;
    }
    .company-hero-symbol {
      font-family: var(--font-mono);
      font-size: 1.5rem;
      font-weight: 600;
      padding: 0.35rem 0.95rem;
      border-radius: var(--radius-md);
      background: var(--bg-surface-elevated);
      border: 2px solid var(--border-card);
      color: var(--text-primary);
    }
    .company-hero-name {
      font-size: 1.45rem;
      font-weight: 600;
      color: var(--text-primary);
      margin: 0;
      line-height: 1.2;
    }
    .company-meta-pills {
      display: flex;
      align-items: center;
      gap: 0.45rem;
      flex-wrap: wrap;
      margin-top: 0.35rem;
    }
    .company-notes-card {
      background: var(--bg-base);
      border: 1px solid var(--border-card);
      border-radius: var(--radius-md);
      padding: 0.85rem 1.1rem;
      font-size: 0.84rem;
      color: var(--text-secondary);
      line-height: 1.5;
      margin-top: 0.85rem;
    }

    .company-kpi-ribbon {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 0.75rem;
      margin-top: 1.15rem;
    }
    .company-kpi-card {
      background: var(--bg-base);
      border: 1px solid var(--border-card);
      border-radius: var(--radius-md);
      padding: 0.85rem 1.1rem;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      transition: all 0.15s ease;
    }
    .company-kpi-card:hover {
      border-color: var(--border-card);
      transform: translateY(-1px);
    }
    .company-kpi-title {
      font-size: 0.68rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: var(--text-muted);
      margin-bottom: 0.25rem;
    }
    .company-kpi-val {
      font-family: var(--font-mono);
      font-size: 1.25rem;
      font-weight: 600;
      color: var(--text-primary);
      line-height: 1.2;
    }
    .company-kpi-sub {
      font-size: 0.72rem;
      color: var(--text-secondary);
      margin-top: 0.25rem;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    .company-grid-layout {
      display: grid;
      grid-template-columns: 1fr 360px;
      gap: 1.5rem;
    }
    @media (max-width: 1024px) {
      .company-grid-layout {
        grid-template-columns: 1fr;
      }
    }

    .company-card-deck {
      display: flex;
      flex-direction: column;
      gap: 1.25rem;
    }
    .company-side-deck {
      display: flex;
      flex-direction: column;
      gap: 1.25rem;
    }
    .company-feed-item {
      background: var(--bg-surface);
      border: 1px solid var(--border-card);
      border-radius: var(--radius-md);
      padding: 1.1rem 1.25rem;
      transition: all 0.15s ease;
    }
    .company-feed-item:hover {
      border-color: var(--border-card);
      box-shadow: var(--shadow-sm);
    }
    .company-feed-top {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 0.5rem;
      gap: 0.5rem;
      flex-wrap: wrap;
    }
    .company-feed-title {
      font-size: 0.98rem;
      font-weight: 700;
      color: var(--text-primary);
      margin-bottom: 0.35rem;
      line-height: 1.4;
    }
    .company-side-box {
      background: var(--bg-surface);
      border: 1px solid var(--border-card);
      border-radius: var(--radius-lg);
      padding: 1.25rem;
      box-shadow: var(--shadow-sm);
    }
    .company-side-title {
      font-size: 0.92rem;
      font-weight: 600;
      color: var(--text-primary);
      display: flex;
      align-items: center;
      gap: 0.5rem;
      margin-bottom: 0.85rem;
      padding-bottom: 0.65rem;
      border-bottom: 1px solid var(--border-card);
    }

    /* Collapsible Cross-Reference Accordion */
    .crossref-badges-wrap {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 0.35rem;
      margin-top: 0.45rem;
      max-width: 100%;
    }

    .crossref-badge {
      display: inline-flex;
      align-items: center;
      gap: 0.25rem;
      font-size: 0.72rem;
      font-weight: 600;
      padding: 0.18rem 0.5rem;
      border-radius: var(--radius-sm);
      background: var(--accent-soft);
      color: var(--accent);
      border: 1px solid var(--accent-soft);
      max-width: 100%;
      flex-wrap: wrap;
    }

    .crossref-rel-pill {
      font-size: 0.62rem;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.04em;
      padding: 0.1rem 0.35rem;
      border-radius: 4px;
      white-space: nowrap;
    }

    .crossref-customer {
      background: var(--pos-soft);
      color: var(--pos);
      border: 1px solid var(--pos-soft);
    }

    .crossref-supplier {
      background: var(--warn-soft);
      color: var(--warn);
      border: 1px solid var(--warn-soft);
    }

    .crossref-accordion {
      display: inline-block;
      margin-top: 0.2rem;
      max-width: 100%;
    }

    .crossref-summary-pill {
      font-size: 0.72rem;
      font-weight: 700;
      color: var(--accent);
      background: var(--accent-soft);
      border: 1px solid var(--accent-soft);
      border-radius: var(--radius-full);
      padding: 0.22rem 0.65rem;
      cursor: pointer;
      list-style: none;
      display: inline-flex;
      align-items: center;
      gap: 0.35rem;
      transition: all var(--transition-fast);
      user-select: none;
      max-width: 100%;
      word-break: normal;
    }

    .crossref-summary-pill::-webkit-details-marker {
      display: none;
    }

    .crossref-summary-pill:hover {
      background: var(--accent-soft);
      border-color: var(--accent-soft);
    }

    .accordion-arrow {
      font-size: 0.75rem;
      transition: transform var(--transition-fast);
      display: inline-block;
    }

    .crossref-accordion[open] .accordion-arrow {
      transform: rotate(180deg);
    }

    .crossref-dropdown-content {
      margin-top: 0.5rem;
      padding: 0.65rem 0.85rem;
      background: var(--bg-surface);
      border: 1px solid var(--border-card);
      border-radius: var(--radius-md);
      display: flex;
      flex-direction: column;
      gap: 0.45rem;
      box-shadow: var(--shadow-dropdown);
      max-width: 100%;
    }

    .crossref-dropdown-item {
      display: flex;
      align-items: center;
      flex-wrap: wrap;
      gap: 0.4rem;
      font-size: 0.75rem;
      padding: 0.15rem 0;
    }

    /* Why It Matters Callout Box */
    .why-matters-box {
      margin-top: 0.6rem;
      background: var(--accent-soft);
      border-left: 4px solid var(--accent-blue);
      padding: 0.65rem 0.95rem;
      border-radius: 0 var(--radius-md) var(--radius-md) 0;
      font-size: 0.835rem;
      color: var(--accent);
      line-height: 1.5;
    }

    .why-tag {
      font-weight: 700;
      color: var(--accent);
      font-size: 0.75rem;
      text-transform: uppercase;
      letter-spacing: 0.03em;
      display: inline-flex;
      align-items: center;
      gap: 0.25rem;
      white-space: nowrap;
    }

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
    table {
      width: 100%;
      min-width: 680px;
      border-collapse: collapse;
      text-align: left;
      font-size: 0.875rem;
    }

    th {
      background: var(--bg-surface);
      color: var(--text-muted);
      font-size: 0.75rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      padding: 1rem 1.15rem;
      border-bottom: 1px solid var(--border-card);
      white-space: nowrap;
    }

    td {
      padding: 1.25rem 1.15rem;
      border-bottom: 1px solid var(--border-card);
      vertical-align: top;
    }

    tr.news-row:hover td {
      background: var(--bg-surface);
    }

    .summary-text {
      color: var(--text-secondary);
      font-size: 0.825rem;
      line-height: 1.45;
      margin-top: 0.35rem;
    }

    .calendar-date-box {
      background: var(--bg-surface);
      border: 1px solid var(--border-card);
      border-radius: var(--radius-md);
      padding: 0.4rem 0.65rem;
      text-align: center;
      width: 56px;
      min-width: 56px;
      flex-shrink: 0;
      align-self: flex-start;
      box-shadow: var(--shadow-sm);
    }

    .calendar-date-month {
      font-size: 0.65rem;
      font-weight: 600;
      color: var(--accent-blue);
      text-transform: uppercase;
      letter-spacing: 0.04em;
    }

    .calendar-date-day {
      font-family: var(--font-mono);
      font-size: 1.35rem;
      font-weight: 600;
      color: var(--text-primary);
      line-height: 1.1;
    }

    /* Macroeconomic Intelligence Grid & Anchor Cards */
    .economic-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
      gap: 1.35rem;
    }

    .economic-card {
      background: var(--bg-surface-glass);
      border: 1px solid var(--border-glass);
      border-radius: var(--radius-lg);
      padding: 1.5rem;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      transition: all var(--transition-fast);
      box-shadow: var(--shadow-sm);
      min-width: 0;
    }

    .economic-card:hover {
      transform: translateY(-2px);
      border-color: var(--border-card);
      box-shadow: var(--shadow-card);
    }

    .economic-card-anchor {
      background: var(--bg-surface);
      border: 1px solid var(--accent-soft);
      box-shadow: var(--shadow-hover);
    }

    .economic-card-top {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      margin-bottom: 0.95rem;
      gap: 0.5rem;
      flex-wrap: wrap;
    }

    .economic-category-badge {
      font-size: 0.65rem;
      font-weight: 600;
      letter-spacing: 0.06em;
      text-transform: uppercase;
      color: var(--text-muted);
      background: var(--bg-surface-elevated);
      padding: 0.22rem 0.55rem;
      border-radius: var(--radius-full);
      border: 1px solid var(--border-card);
    }

    .economic-trend-badge {
      font-size: 0.72rem;
      font-weight: 700;
      padding: 0.22rem 0.6rem;
      border-radius: var(--radius-full);
      display: inline-flex;
      align-items: center;
      gap: 0.25rem;
    }

    .trend-up   { background: var(--neg-soft); color: var(--neg); border: 1px solid var(--neg-soft); }
    .trend-down { background: var(--pos-soft); color: var(--pos); border: 1px solid var(--pos-soft); }
    .trend-flat { background: var(--bg-surface-elevated); color: var(--text-secondary); border: 1px solid var(--border-card); }

    .economic-val {
      font-family: var(--font-mono);
      font-size: 2.1rem;
      font-weight: 600;
      color: var(--text-primary);
      line-height: 1;
      margin-bottom: 0.45rem;
    }

    .economic-val-anchor {
      font-size: 2.5rem;
      color: var(--text-primary);
    }

    .economic-series-name {
      font-size: 1.05rem;
      font-weight: 700;
      color: var(--text-primary);
      margin: 0 0 0.35rem 0;
    }

    .economic-context {
      font-size: 0.82rem;
      color: var(--text-secondary);
      line-height: 1.45;
      margin-bottom: 1.15rem;
    }

    .economic-tickers-wrap {
      border-top: 1px solid var(--border-card);
      padding-top: 0.95rem;
      display: flex;
      flex-direction: column;
      gap: 0.45rem;
    }

    .economic-tickers-label {
      font-size: 0.72rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: var(--text-muted);
    }

    .economic-tickers-list {
      display: flex;
      flex-wrap: wrap;
      gap: 0.35rem;
    }

    /* Macro Economic Calendar Strip */
    .macro-events-strip {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
      gap: 1rem;
      margin-bottom: 2rem;
    }

    .macro-event-card {
      background: var(--bg-surface-glass);
      border: 1px solid var(--border-glass);
      border-radius: var(--radius-lg);
      padding: 1.15rem 1.25rem;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      gap: 0.85rem;
      box-shadow: var(--shadow-sm);
      transition: all var(--transition-fast);
      position: relative;
      overflow: hidden;
    }

    .macro-event-card::before {
      content: '';
      position: absolute;
      top: 0;
      left: 0;
      width: 4px;
      height: 100%;
      background: var(--bg-surface);
      border-radius: 4px 0 0 4px;
    }

    .macro-event-card:hover {
      transform: translateY(-2px);
      border-color: var(--border-card);
      box-shadow: var(--shadow-card);
    }

    .macro-event-top {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 0.5rem;
    }

    .macro-event-authority {
      font-size: 0.68rem;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: var(--text-muted);
    }

    .macro-event-countdown {
      font-size: 0.7rem;
      font-weight: 700;
      padding: 0.2rem 0.55rem;
      border-radius: var(--radius-full);
      background: var(--accent-soft);
      color: var(--accent);
      border: 1px solid var(--accent-soft);
    }

    .macro-event-title {
      font-size: 0.95rem;
      font-weight: 700;
      color: var(--text-primary);
      line-height: 1.35;
      margin: 0.35rem 0 0 0;
    }

    .macro-event-date-row {
      display: flex;
      align-items: center;
      gap: 0.4rem;
      font-size: 0.8rem;
      font-weight: 600;
      color: var(--text-secondary);
    }

    .macro-event-consensus {
      font-size: 0.76rem;
      color: var(--text-secondary);
      background: var(--bg-surface-elevated);
      border: 1px solid var(--border-card);
      border-radius: var(--radius-sm);
      padding: 0.35rem 0.55rem;
      line-height: 1.35;
    }

    .macro-event-consensus strong {
      color: var(--text-primary);
    }

    /* Sparkline Chart Component */
    .sparkline-wrapper {
      position: relative;
      margin: 0.85rem 0 0.65rem 0;
      padding: 0.35rem 0 0.15rem 0;
      background: var(--bg-surface);
      border: 1px solid var(--border-card);
      border-radius: var(--radius-md);
      padding: 0.5rem 0.65rem 0.35rem 0.65rem;
    }

    .sparkline-svg {
      width: 100%;
      height: 60px;
      overflow: visible;
      display: block;
    }

    .sparkline-labels {
      display: flex;
      justify-content: space-between;
      align-items: center;
      font-size: 0.68rem;
      font-family: var(--font-mono);
      color: var(--text-muted);
      margin-top: 0.25rem;
    }

    .sparkline-tooltip {
      position: absolute;
      display: none;
      background: var(--scrim);
      color: var(--on-accent);
      padding: 0.3rem 0.55rem;
      border-radius: var(--radius-sm);
      font-size: 0.72rem;
      font-family: var(--font-mono);
      pointer-events: none;
      z-index: 20;
      white-space: nowrap;
      transform: translate(-50%, -120%);
      box-shadow: var(--shadow-sm);
    }

    /* AI Macro Synthesis Box */
    .ai-synthesis-card {
      background: var(--bg-surface);
      border: 1px solid var(--accent-soft);
      border-radius: var(--radius-md);
      padding: 0.75rem 0.9rem;
      margin: 0.85rem 0 1.15rem 0;
      position: relative;
    }

    .ai-synthesis-head {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 0.35rem;
      gap: 0.5rem;
    }

    .ai-synthesis-badge {
      display: inline-flex;
      align-items: center;
      gap: 0.35rem;
      font-size: 0.68rem;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: var(--accent);
    }

    .ai-synthesis-badge svg {
      color: var(--accent);
    }

    .ai-synthesis-meta {
      font-size: 0.68rem;
      color: var(--text-muted);
    }

    .ai-synthesis-content {
      font-size: 0.825rem;
      color: var(--text-primary);
      line-height: 1.45;
      font-weight: 500;
      font-style: normal;
    }

    /* Health Section */
    .health-section {
      background: var(--bg-surface-glass);
      border: 1px solid var(--border-glass);
      border-radius: var(--radius-xl);
      padding: 2rem;
      box-shadow: var(--shadow-card);
      margin-top: 3.5rem;
      min-width: 0;
    }

    .health-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 0.75rem;
      padding-bottom: 1.35rem;
      border-bottom: 1px solid var(--border-card);
      margin-bottom: 1.75rem;
    }

    .health-title-group {
      display: flex;
      align-items: center;
      gap: 0.85rem;
      flex-wrap: wrap;
    }

    .health-title {
      font-size: 1.25rem;
      font-weight: 600;
      color: var(--text-primary);
    }

    .health-status-badge {
      font-size: 0.75rem;
      font-weight: 600;
      letter-spacing: 0.05em;
      text-transform: uppercase;
      padding: 0.3rem 0.75rem;
      border-radius: var(--radius-full);
      display: inline-flex;
      align-items: center;
      gap: 0.4rem;
    }

    .health-badge-healthy  { background: var(--pos-soft); color: var(--pos); border: 1px solid var(--pos-soft); }

    .health-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
      gap: 1.15rem;
      margin-bottom: 1.5rem;
    }

    .health-metric-card {
      background: var(--bg-base);
      border: 1px solid var(--border-card);
      border-radius: var(--radius-md);
      padding: 1.25rem;
      min-width: 0;
    }

    .health-metric-title {
      font-size: 0.72rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: var(--text-muted);
      margin-bottom: 0.4rem;
    }

    .health-metric-val {
      font-family: var(--font-mono);
      font-size: 1.65rem;
      font-weight: 600;
      color: var(--text-primary);
      line-height: 1.1;
      margin-bottom: 0.25rem;
    }

    .health-metric-sub {
      font-size: 0.72rem;
      color: var(--text-secondary);
    }

    /* Comparative Stock Performance Module */
    .comparative-perf-card {
      background: var(--bg-surface);
      border: 1px solid var(--border-card);
      border-radius: var(--radius-xl);
      padding: 1.5rem 1.75rem;
      box-shadow: var(--shadow-sm);
      margin-bottom: 1.75rem;
    }
    .comparative-perf-header {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      flex-wrap: wrap;
      gap: 1rem;
      margin-bottom: 1.25rem;
      padding-bottom: 1.15rem;
      border-bottom: 1px solid var(--border-card);
    }
    .comparative-select {
      background: var(--bg-base);
      border: 1px solid var(--border-card);
      border-radius: var(--radius-md);
      padding: 0.45rem 1rem;
      font-size: 0.88rem;
      font-weight: 700;
      color: var(--text-primary);
      outline: none;
      cursor: pointer;
    }
    .perf-kpi-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
      gap: 0.75rem;
      margin-bottom: 1.25rem;
    }
    .perf-kpi-box {
      background: var(--bg-base);
      border: 1px solid var(--border-card);
      border-radius: var(--radius-md);
      padding: 0.85rem 1rem;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
    }
    .perf-kpi-label {
      font-size: 0.68rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: var(--text-muted);
      margin-bottom: 0.25rem;
    }
    .perf-kpi-val {
      font-family: var(--font-mono);
      font-size: 1.25rem;
      font-weight: 600;
      line-height: 1.2;
    }
    .perf-kpi-sub {
      font-size: 0.72rem;
      color: var(--text-secondary);
      margin-top: 0.25rem;
    }
    .perf-table-wrap {
      margin-top: 1.25rem;
      overflow-x: auto;
    }
    .perf-table {
      width: 100%;
      border-collapse: collapse;
      font-size: 0.82rem;
    }
    .perf-table th {
      text-align: left;
      font-weight: 700;
      color: var(--text-muted);
      padding: 0.5rem 0.75rem;
      border-bottom: 1px solid var(--border-card);
      text-transform: uppercase;
      font-size: 0.68rem;
      letter-spacing: 0.05em;
    }
    .perf-table td {
      padding: 0.6rem 0.75rem;
      border-bottom: 1px solid var(--border-card);
      color: var(--text-primary);
    }

    /* Company Page Categorized Directory Browser */
    .company-directory-browser {
      background: var(--bg-surface);
      border: 1px solid var(--border-card);
      border-radius: var(--radius-lg);
      padding: 1.25rem 1.5rem;
      margin-bottom: 1.5rem;
      box-shadow: var(--shadow-sm);
    }
    .company-browser-top {
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 0.75rem;
      margin-bottom: 1rem;
    }
    .company-browser-sectors {
      display: flex;
      gap: 0.35rem;
      overflow-x: auto;
      scrollbar-width: none;
      padding-bottom: 0.25rem;
      margin-bottom: 1rem;
    }
    .company-browser-sectors::-webkit-scrollbar {
      display: none;
    }
    .company-browser-sec-btn {
      display: inline-flex;
      align-items: center;
      gap: 0.35rem;
      padding: 0.35rem 0.75rem;
      border-radius: var(--radius-full);
      background: var(--bg-surface-elevated);
      border: 1px solid var(--border-card);
      font-size: 0.76rem;
      font-weight: 700;
      color: var(--text-secondary);
      cursor: pointer;
      white-space: nowrap;
      transition: all var(--transition-fast);
    }
    .company-browser-sec-btn:hover {
      border-color: var(--accent-blue);
      color: var(--text-primary);
    }
    .company-browser-sec-btn.active {
      background: var(--accent-blue);
      color: var(--on-accent);
      border-color: var(--accent-blue);
    }
    .company-browser-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(230px, 1fr));
      gap: 0.65rem;
      max-height: 320px;
      overflow-y: auto;
      padding-right: 0.25rem;
    }
    .company-browser-card {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 0.6rem;
      padding: 0.6rem 0.75rem;
      min-height: 60px;
      border-radius: var(--radius-md);
      background: var(--bg-surface);
      border: 1.5px solid var(--border-card);
      cursor: pointer;
      text-align: left;
      transition: all var(--transition-fast);
      width: 100%;
      box-sizing: border-box;
    }
    .company-browser-card:hover {
      border-color: var(--accent-blue);
      background: var(--accent-soft);
      transform: translateY(-1px);
    }
    .company-browser-card.active {
      border-color: var(--accent-blue);
      background: var(--accent-blue-soft);
      box-shadow: 0 0 0 2px var(--accent-soft);
    }
    .company-browser-card.active .company-browser-card-name {
      color: var(--accent-blue);
      font-weight: 600;
    }
    .company-browser-card-left {
      display: flex;
      align-items: center;
      gap: 0.55rem;
      min-width: 0;
      flex: 1 1 auto;
      overflow: hidden;
    }
    .company-browser-card-info {
      flex: 1 1 auto;
      min-width: 0;
      overflow: hidden;
      display: flex;
      flex-direction: column;
      justify-content: center;
    }
    .company-browser-card-name {
      font-size: 0.81rem;
      font-weight: 700;
      color: var(--text-primary);
      line-height: 1.25;
      display: -webkit-box;
      -webkit-line-clamp: 2;
      -webkit-box-orient: vertical;
      overflow: hidden;
      text-overflow: ellipsis;
      word-break: break-word;
    }
    .company-browser-card-sec {
      font-size: 0.68rem;
      color: var(--text-muted);
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      margin-top: 0.15rem;
      line-height: 1.2;
    }
    .company-browser-card-stats {
      display: flex;
      flex-direction: column;
      align-items: flex-end;
      justify-content: center;
      flex-shrink: 0;
      text-align: right;
      margin-left: auto;
      padding-left: 0.35rem;
    }
    .company-browser-card-alpha {
      font-family: var(--font-mono);
      font-size: 0.72rem;
      font-weight: 700;
      line-height: 1.2;
    }
    .company-browser-card-stories {
      font-size: 0.65rem;
      color: var(--text-muted);
      white-space: nowrap;
      margin-top: 0.15rem;
      line-height: 1.2;
    }

    /* Feed Sector Filter Bar & Ticker Popover */
"""

# ==============================================================================
# RESPONSIVE NAVIGATION MACROS (SIDEBAR + MOBILE HEADER + MOBILE BOTTOM NAV)
# ==============================================================================
NAVIGATION_LAYOUT_HTML = """
<div class="mobile-top-header">
  <a href="index.html" class="sidebar-brand"><span class="brand-title">StockPulse</span></a>
  <div class="mobile-header-right">
    <button class="mobile-action-btn" onclick="focusMobileSearch()" aria-label="Search">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></svg>
    </button>
    <button class="mobile-hamburger-btn" onclick="toggleMobileNav()" aria-label="Toggle navigation drawer">
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><line x1="3" y1="8" x2="21" y2="8"/><line x1="3" y1="16" x2="21" y2="16"/></svg>
    </button>
  </div>
</div>

<div class="mobile-drawer-backdrop" id="mobileBackdrop" onclick="closeMobileNav()"></div>

<aside class="app-sidebar" id="appSidebar">
  <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:2.25rem;">
    <a href="index.html" class="sidebar-brand"><span class="brand-title">StockPulse</span></a>
    <button class="sidebar-close-btn" onclick="closeMobileNav()" aria-label="Close navigation">&times;</button>
  </div>

  <nav class="sidebar-nav" aria-label="Pages">
    <a href="index.html" class="nav-link {% if active_page == 'home' %}active{% endif %}" onclick="closeMobileNav()"><span class="nav-text">Home</span></a>
    <a href="company.html" class="nav-link {% if active_page == 'company' %}active{% endif %}" onclick="closeMobileNav()"><span class="nav-text">Companies</span><span class="nav-count">{{ watchlist_companies|length }}</span></a>
    <a href="news.html" class="nav-link {% if active_page == 'news' %}active{% endif %}" onclick="closeMobileNav()"><span class="nav-text">Feed</span><span class="nav-count">{{ stats.total }}</span></a>
    <a href="calendar.html" class="nav-link {% if active_page == 'calendar' %}active{% endif %}" onclick="closeMobileNav()"><span class="nav-text">Calendar</span><span class="nav-count">{{ calendar_events|length }}</span></a>
    <a href="economic.html" class="nav-link {% if active_page == 'economic' %}active{% endif %}" onclick="closeMobileNav()"><span class="nav-text">Economy</span><span class="nav-count">{{ economic_indicators|length }}</span></a>
    <a href="analytics.html" class="nav-link {% if active_page == 'analytics' %}active{% endif %}" onclick="closeMobileNav()"><span class="nav-text">Analytics</span></a>
  </nav>

  <div class="sidebar-footer">
    {% if latest_run %}
    <div{% if latest_run.status != 'HEALTHY' %} class="sidebar-status-alert"{% endif %}>Pipeline: {{ latest_run.status|lower }}</div>
    {% else %}
    <div>No pipeline runs recorded</div>
    {% endif %}
    <div>Updated: {{ generated_at }}</div>
    <button class="theme-toggle" id="themeToggle" type="button" onclick="cycleTheme()">Theme: auto</button>
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

function currentThemeChoice() {
  return document.documentElement.dataset.theme || 'auto';
}

function labelThemeToggle() {
  const btn = document.getElementById('themeToggle');
  if (btn) btn.textContent = 'Theme: ' + currentThemeChoice();
}

function cycleTheme() {
  const next = { auto: 'light', light: 'dark', dark: 'auto' }[currentThemeChoice()];
  if (next === 'auto') delete document.documentElement.dataset.theme;
  else document.documentElement.dataset.theme = next;
  try {
    if (next === 'auto') localStorage.removeItem('stockpulse_theme');
    else localStorage.setItem('stockpulse_theme', next);
  } catch (e) { /* storage may be blocked; the choice just won't persist */ }
  labelThemeToggle();
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
"""


# ==============================================================================
# 1. HOME / OVERVIEW TEMPLATE (site/index.html)
# ==============================================================================
INDEX_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=5.0">
  <meta name="description" content="A morning briefing on your watchlist: top stories, upcoming events, and the economy.">
  <title>StockPulse — What's on the agenda?</title>
  <link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' fill='%231b1a17'/%3E%3Cpath d='M6 19h6l3-9 3 13 2-4h6' fill='none' stroke='%23f6f4ee' stroke-width='2'/%3E%3C/svg%3E">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@400;500;600&family=Newsreader:opsz,wght@6..72,400;6..72,500;6..72,600&display=swap" rel="stylesheet">
  <script>""" + THEME_BOOT_JS + """</script>
  <style>
""" + SHARED_CSS + """
  </style>
</head>
<body>
  <div class="app-layout">
    """ + NAVIGATION_LAYOUT_HTML + """

    <main class="app-main">
      <header class="fp-masthead">
        <p class="fp-dateline">{{ generated_at[:12] }}</p>
        <h1 class="fp-title">What's on the agenda?</h1>
        <p class="fp-standfirst">
          {{ stats.high_priority_count }} of {{ stats.total }} stories scored 7 or higher.
          {% if calendar_events %}Next on the calendar: {{ calendar_events[0].headline }}, {{ calendar_events[0].relative_badge|lower }}.{% endif %}
        </p>
      </header>

      <div class="search-wrapper" id="heroSearchWrapper">
        <div class="search-box" id="globalSearchBox">
          <span class="search-icon-wrap">
            <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></svg>
          </span>
          <input type="text" id="globalSearchInput" class="search-input" aria-label="Search" placeholder="Search companies, filings, events" onfocus="openSearchDropdown()" oninput="handleSearchType(this.value)">
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
          <div id="liveSearchResults" style="display:none;"></div>
        </div>
      </div>

      <div class="fp-grid">
        <section class="fp-main" aria-label="Top stories">
          {% if priority_items %}
          {% set lead = priority_items[0] %}
          <article class="fp-lead">
            <p class="fp-kicker">Read first</p>
            <h2 class="fp-lead-title"><a href="{{ lead.url if lead.url.startswith('http') else 'news.html' }}" target="_blank" rel="noopener noreferrer">{{ lead.clean_headline }}</a></h2>
            {% if lead.llm_summary %}<p class="fp-lead-summary">{{ lead.llm_summary }}</p>{% endif %}
            <p class="fp-meta">
              <a class="ticker-badge" href="company.html?ticker={{ lead.ticker|urlencode }}">{{ lead.ticker }}</a>
              <span>{{ short_date(lead.published_date) }}</span>
              <span>{{ lead.source_label }}</span>
              <span title="{{ lead.score_breakdown }}">Score {{ lead.score }}</span>
            </p>
          </article>

          {% if priority_items|length > 1 %}
          <ol class="fp-list">
            {% for it in priority_items[1:] %}
            <li class="fp-row">
              <a class="ticker-badge" href="company.html?ticker={{ it.ticker|urlencode }}">{{ it.ticker }}</a>
              <a class="fp-row-title" href="{{ it.url if it.url.startswith('http') else 'news.html' }}" target="_blank" rel="noopener noreferrer">{{ it.clean_headline }}</a>
              <span class="fp-score" title="{{ it.score_breakdown }}">{{ it.score }}</span>
            </li>
            {% endfor %}
          </ol>
          {% endif %}
          {% else %}
          <p class="fp-empty">No stories yet. They appear here after the next pipeline run.</p>
          {% endif %}
          <a class="fp-more" href="news.html">All {{ stats.total }} stories</a>
        </section>

        <aside class="fp-side">
          <section aria-labelledby="fpNextHeading">
            <h2 class="fp-heading" id="fpNextHeading">Coming up</h2>
            {% if calendar_events %}
            <ul class="fp-side-list">
              {% for ev in calendar_events[:4] %}
              <li class="fp-event">
                <span class="fp-event-date">{{ short_date(ev.event_date) }}</span>
                <span class="fp-event-text"><a class="ticker-badge" href="company.html?ticker={{ ev.ticker|urlencode }}">{{ ev.ticker }}</a> {{ event_kind(ev.event_type or '') }}</span>
              </li>
              {% endfor %}
            </ul>
            {% else %}
            <p class="fp-empty">No upcoming events.</p>
            {% endif %}
            <a class="fp-more" href="calendar.html">Full calendar</a>
          </section>

          <section aria-labelledby="fpEconHeading">
            <h2 class="fp-heading" id="fpEconHeading">Economy</h2>
            {% if economic_indicators %}
            <ul class="fp-side-list">
              {% for ind in economic_indicators %}
              <li class="fp-indicator">
                <span>{{ ind.name }}</span>
                <span class="fp-indicator-value">{{ ind.formatted_value.split(' (')[0] }}</span>
              </li>
              {% endfor %}
            </ul>
            {% else %}
            <p class="fp-empty">No indicators available.</p>
            {% endif %}
            <a class="fp-more" href="economic.html">All indicators</a>
          </section>
        </aside>
      </div>

      <section class="fp-index" aria-labelledby="fpIndexHeading">
        <h2 class="fp-heading" id="fpIndexHeading">The watchlist, by sector</h2>
        <dl class="fp-index-list">
          {% for sec in sector_directory %}
          <div class="fp-index-row">
            <dt>{{ sec.name }}</dt>
            <dd>
              {% for co in sec.companies %}
              <a class="fp-index-item" href="company.html?ticker={{ co.symbol|urlencode }}" title="{{ co.name }}: {{ co.story_count }} stories">{{ co.symbol }}<sup>{{ co.story_count }}</sup></a>
              {% endfor %}
            </dd>
          </div>
          {% endfor %}
        </dl>
      </section>

      <section class="recently-viewed-section" id="recentlyViewedSection" aria-labelledby="fpRecentHeading" hidden>
        <div class="fp-heading-row">
          <h2 class="fp-heading" id="fpRecentHeading">Recently Viewed Companies</h2>
          <button class="fp-clear" id="clearRecentlyViewedBtn" type="button" onclick="clearRecentlyViewed()">Clear</button>
        </div>
        <ul class="fp-recent-list" id="recentlyViewedGrid"></ul>
      </section>
    </main>
  </div>

  <script>
    """ + SHARED_MOBILE_JS + """

    const allItems = {{ items|tojson|safe }};
    const calendarEvents = {{ calendar_events|tojson|safe }};
    const econIndicators = {{ economic_indicators|tojson|safe }};
    const watchlistCompanies = {{ watchlist_companies|tojson|safe }};

    function renderRecentlyViewed() {
      const section = document.getElementById('recentlyViewedSection');
      const grid = document.getElementById('recentlyViewedGrid');
      if (!grid || !section) return;

      let stored = [];
      try {
        stored = JSON.parse(localStorage.getItem('stockpulse_recently_viewed') || '[]');
      } catch (e) {
        stored = [];
      }

      // Nothing viewed yet means nothing to show, rather than an invented starter list.
      if (!Array.isArray(stored) || stored.length === 0) {
        section.hidden = true;
        grid.innerHTML = '';
        return;
      }

      const companies = {};
      (watchlistCompanies || []).forEach(c => { companies[c.symbol] = c; });

      section.hidden = false;
      grid.innerHTML = stored.slice(0, 8).map(item => {
        const sym = String(typeof item === 'string' ? item : item.symbol).toUpperCase();
        const co = companies[sym] || { name: sym };
        let when = '';
        if (item.visitedAt) {
          const diffSec = Math.floor((Date.now() - item.visitedAt) / 1000);
          if (diffSec < 60) when = 'Just now';
          else if (diffSec < 3600) when = `${Math.floor(diffSec / 60)}m ago`;
          else if (diffSec < 86400) when = `${Math.floor(diffSec / 3600)}h ago`;
          else when = `${Math.floor(diffSec / 86400)}d ago`;
        }
        return `
          <li class="fp-recent">
            <a href="company.html?ticker=${encodeURIComponent(sym)}">
              <span class="ticker-badge">${escapeHtml(sym)}</span>
              <span class="fp-recent-name">${escapeHtml(co.name)}</span>
              <span class="fp-recent-when">${escapeHtml(when)}</span>
            </a>
          </li>`;
      }).join('');
    }

    function clearRecentlyViewed() {
      localStorage.removeItem('stockpulse_recently_viewed');
      renderRecentlyViewed();
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
        (it.llm_summary || '').toLowerCase().includes(val)
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
        (ind.relevant_tickers || '').toLowerCase().includes(val) ||
        (ind.category || '').toLowerCase().includes(val)
      );

      // Check if input directly matches a curated watchlist holding
      const isExactWatchlist = watchlistCompanies.some(c => 
        (c.symbol || '').toUpperCase() === rawUpper || 
        (c.name || '').toLowerCase() === val
      );
      const isSearchTermEligible = val.length >= 2 && /^[a-zA-Z0-9\s.\-]{2,40}$/.test(rawVal.trim());
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
            <div id="quickLookupBody" style="font-size:0.8rem; color:var(--text-muted); padding:0.25rem 0;">
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
                  <div class="search-result-sub">${escapeHtml(c.sector)}</div>
                </div>
              </div>
              <span class="action-link" style="font-size:0.75rem;">Open</span>
            </a>
          `;
        });
      }

      // Render Calendar matches
      if (matchedCal.length > 0) {
        html += '<div class="dropdown-section-title" style="margin-top:0.6rem;">Calendar</div>';
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
              <span class="action-link" style="font-size:0.75rem;">Open</span>
            </a>
          `;
        });
      }

      // Render Macroeconomic matches
      if (matchedEcon.length > 0) {
        html += '<div class="dropdown-section-title" style="margin-top:0.6rem;">Economy</div>';
        matchedEcon.slice(0, 2).forEach(ind => {
          html += `
            <a href="economic.html" class="search-result-item">
              <div class="search-result-left">
                <div class="search-result-icon"><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="20" x2="12" y2="10"/><line x1="18" y1="20" x2="18" y2="4"/><line x1="6" y1="20" x2="6" y2="16"/></svg></div>
                <div class="search-result-info">
                  <div class="search-result-title">${escapeHtml(ind.name)}: ${escapeHtml(ind.formatted_value)}</div>
                  <div class="search-result-sub">${escapeHtml(ind.category)} &bull; Relevant: ${escapeHtml(ind.relevant_tickers)}</div>
                </div>
              </div>
              <span class="action-link" style="font-size:0.75rem;">Open</span>
            </a>
          `;
        });
      }

      // Render News matches
      if (matchedNews.length > 0) {
        html += '<div class="dropdown-section-title" style="margin-top:0.6rem;">Stories (' + matchedNews.length + ')</div>';
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
              <span class="action-link" style="font-size:0.75rem;">Open</span>
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
            if (status) status.innerHTML = '<span style="color:var(--text-muted);">Endpoint Pending</span>';
            body.innerHTML = `
              <div style="font-size:0.8rem; color:var(--text-muted); line-height:1.4;">
                Live quick-lookup endpoint for "<strong>${escapeHtml(query)}</strong>" is currently offline or pending Cloudflare deployment.
                <div style="margin-top:0.35rem; font-size:0.72rem;">Run local dev server or configure FINNHUB_API_KEY on Cloudflare Pages.</div>
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
            if (status) status.innerHTML = '<span style="color:var(--text-muted);">Unlisted Ticker</span>';
            body.innerHTML = `
              <div style="font-size:0.8rem; color:var(--text-muted); line-height:1.4;">
                ${errData.message || errData.error ? escapeHtml(errData.message || errData.error) : `No live quote or news found on Finnhub for "<strong>${escapeHtml(query)}</strong>".`}
                <div style="margin-top:0.35rem; font-size:0.72rem;">Try checking the company or ticker spelling or searching for general keywords.</div>
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
            if (status) status.innerHTML = '<span style="color:var(--text-muted);">No Data</span>';
            body.innerHTML = `
              <div style="font-size:0.8rem; color:var(--text-muted);">
                ${data.message ? escapeHtml(data.message) : `No quote or news records found for <strong>${escapeHtml(query)}</strong>.`}
              </div>
            `;
            return;
          }

          card.classList.remove('loading');
          if (headerGroup && data.symbol) {
            const coName = data.company_name ? `<span style="font-weight:700; color:var(--text-primary); font-size:0.88rem; margin-left:0.4rem;">${escapeHtml(data.company_name)}</span>` : '';
            const resFrom = data.resolved_from ? `<span style="font-size:0.72rem; color:var(--text-muted); margin-left:0.3rem;">(resolved from "${escapeHtml(data.resolved_from)}")</span>` : '';
            headerGroup.innerHTML = `
              <span class="ticker-badge ticker-${escapeHtml(data.symbol)}">${escapeHtml(data.symbol)}</span>
              ${coName}
              ${resFrom}
              <span class="quick-lookup-badge" style="margin-left:0.35rem;">Outside your watchlist</span>
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
                      <span style="font-weight:600; color:var(--text-secondary);">${escapeHtml(h.source)}</span>
                      ${h.time_ago ? `<span>&bull;</span><span>${escapeHtml(h.time_ago)}</span>` : ''}
                      <span style="margin-left:auto; color:var(--accent-blue); font-weight:700;">Read</span>
                    </div>
                  </a>
                `).join('')}
              </div>
            `;
          } else {
            bodyHtml += `
              <div style="font-size:0.78rem; color:var(--text-muted); margin-top:0.25rem;">No news headlines published in the past 7 days.</div>
            `;
          }

          bodyHtml += `
            <div class="quick-lookup-action-bar">
              <span style="color:var(--text-muted);">Quote from Finnhub</span>
              <a href="news.html?q=${encodeURIComponent(data.symbol)}" class="action-link" style="font-size:0.75rem;">Search the feed</a>
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
          if (status) status.innerHTML = '<span style="color:var(--text-muted);">Lookup Error</span>';
          body.innerHTML = `
            <div style="font-size:0.8rem; color:var(--text-muted);">
              Unable to query live quick-lookup. <span style="font-size:0.72rem;">(Endpoint active on Cloudflare Pages deployment)</span>
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
      const searchInput = document.getElementById('globalSearchInput');
      if (searchInput) {
        searchInput.addEventListener('input', (e) => {
          handleSearchType(e.target.value);
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
  <meta name="description" content="Dedicated Analytics Hub for StockPulse: filing velocity trends, disclosure category breakdowns, peer comparative performance, and automated pipeline telemetry.">
  <title>StockPulse — Analytics &amp; Performance Trends</title>
  <link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' fill='%231b1a17'/%3E%3Cpath d='M6 19h6l3-9 3 13 2-4h6' fill='none' stroke='%23f6f4ee' stroke-width='2'/%3E%3C/svg%3E">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@400;500;600&family=Newsreader:opsz,wght@6..72,400;6..72,500;6..72,600&display=swap" rel="stylesheet">
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.7/dist/chart.umd.min.js"></script>
  <script>""" + THEME_BOOT_JS + """</script>
  <style>
""" + SHARED_CSS + """
  </style>
</head>
<body>
  <div class="app-layout">
    """ + NAVIGATION_LAYOUT_HTML + """

    <main class="app-main">
      <!-- Analytics Header Hero Banner -->
      <div class="page-header" style="margin-bottom:1.75rem;">
        <div style="display:flex; justify-content:space-between; align-items:flex-start; flex-wrap:wrap; gap:1rem;">
          <div>
            <div style="display:flex; align-items:center; gap:0.5rem; margin-bottom:0.35rem;">
              <span class="category-badge" style="background:var(--accent-soft); color:var(--accent); border-color:var(--accent-soft); font-size:0.72rem; font-weight: 600;">INTELLIGENCE ANALYTICS</span>
              <span class="section-time-pill" style="font-size:0.75rem; padding:0.2rem 0.65rem;">
                <span class="pulse-dot" style="background:var(--pos);"></span> Live Telemetry
              </span>
            </div>
            <h1 style="font-size:1.85rem; font-weight: 600; color:var(--text-primary); letter-spacing:-0.02em; margin:0 0 0.35rem 0;">Analytics &amp; Performance Trends</h1>
            <p style="font-size:0.9rem; color:var(--text-muted); margin:0; max-width:720px;">
              Multi-dimensional analysis of disclosure velocity, thematic category allocations, 3-month peer stock returns vs. S&amp;P 500, and data pipeline safeguards.
            </p>
          </div>
          <div style="display:flex; align-items:center; gap:0.6rem;">
            <button class="section-time-pill" onclick="window.location.reload()" style="cursor:pointer; border:1px solid var(--border-card); background:var(--bg-surface-elevated); padding:0.45rem 0.85rem; font-weight:600;" title="Refresh live telemetry">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="margin-right:0.35rem;"><path d="M21 12a9 9 0 0 0-9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/><path d="M3 12a9 9 0 0 0 9 9 9.75 9.75 0 0 0 6.74-2.74L21 16"/><path d="M16 21h5v-5"/></svg>
              Refresh Data
            </button>
          </div>
        </div>

        <!-- Quick Summary Stat Cards -->
        <div class="analytics-stat-row" style="display:grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap:1rem; margin-top:1.5rem;">
          <div class="bento-card" style="padding:1.15rem;">
            <div style="font-size:0.75rem; font-weight:700; color:var(--text-muted); text-transform:uppercase;">Total Disclosures</div>
            <div style="font-family: var(--font-mono); font-size:1.6rem; font-weight: 600; color:var(--text-primary); margin:0.25rem 0;">{{ stats.total }}</div>
            <div style="font-size:0.72rem; color:var(--pos); font-weight:600;">Indexed &amp; Scored</div>
          </div>
          <div class="bento-card" style="padding:1.15rem;">
            <div style="font-size:0.75rem; font-weight:700; color:var(--text-muted); text-transform:uppercase;">High Priority (≥ 7.0)</div>
            <div style="font-family: var(--font-mono); font-size:1.6rem; font-weight: 600; color:var(--warn); margin:0.25rem 0;">{{ stats.high_priority_count }}</div>
            <div style="font-size:0.72rem; color:var(--text-muted);">{{ ((stats.high_priority_count / stats.total * 100) if stats.total else 0) | round(1) }}% of total volume</div>
          </div>
          <div class="bento-card" style="padding:1.15rem;">
            <div style="font-size:0.75rem; font-weight:700; color:var(--text-muted); text-transform:uppercase;">Monitored Companies</div>
            <div style="font-family: var(--font-mono); font-size:1.6rem; font-weight: 600; color:var(--accent-blue); margin:0.25rem 0;">{{ watchlist_companies|length }}</div>
            <div style="font-size:0.72rem; color:var(--text-muted);">EDGAR, IR &amp; News</div>
          </div>
          <div class="bento-card" style="padding:1.15rem;">
            <div style="font-size:0.75rem; font-weight:700; color:var(--text-muted); text-transform:uppercase;">Categories Classified</div>
            <div style="font-family: var(--font-mono); font-size:1.6rem; font-weight: 600; color:var(--accent); margin:0.25rem 0;">{{ stats.by_category|length }}</div>
            <div style="font-size:0.72rem; color:var(--text-muted);">AI classification rules</div>
          </div>
        </div>
      </div>

      <!-- Section 1: Velocity & Category Breakdown -->
      <div class="section-header-row" style="padding-top:0.5rem; margin-bottom:0.85rem;">
        <h2 class="section-heading" style="font-size:1.25rem;">Velocity &amp; Category Breakdown</h2>
        <span class="section-time-pill">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect width="18" height="18" x="3" y="4" rx="2" ry="2"/><line x1="16" x2="16" y1="2" y2="6"/><line x1="8" x2="8" y1="2" y2="6"/><line x1="3" x2="21" y1="10" y2="10"/></svg>
          Multi-Day Lookback
        </span>
      </div>

      <div class="analytics-grid">
        <!-- Metric Card 1: Rich Disclosure Trend Graph with Gradients -->
        <div class="analytics-card">
          <div>
            <div class="analytics-card-header">
              <div>
                <div class="analytics-card-title">Daily Filing &amp; Intelligence Velocity</div>
                <div class="analytics-metric-val">
                  {{ stats.total }} <span class="analytics-delta-pill">↗ Active Trend</span>
                </div>
              </div>
              <span class="section-time-pill" style="font-size:0.75rem;">Top Tickers</span>
            </div>
            <div class="chart-canvas-container">
              <canvas id="timelineChart"></canvas>
            </div>
          </div>
        </div>

        <!-- Metric Card 2: Category Breakdown Donut with Data Callout Badges -->
        <div class="analytics-card">
          <div>
            <div class="analytics-card-header">
              <div>
                <div class="analytics-card-title">Intelligence by Category</div>
                <div class="analytics-metric-val" style="font-size:1.5rem;">
                  {{ stats.by_category|length }} Categories
                </div>
              </div>
              <span class="section-time-pill" style="font-size:0.75rem;">Slices &amp; Callouts</span>
            </div>
            <div class="chart-canvas-container" style="height: 220px;">
              <canvas id="categoryChart"></canvas>
            </div>
          </div>
          
          <div class="category-legend-list" id="categoryLegendList">
            <!-- Dynamically populated legend badges with counts & percentages -->
          </div>
        </div>
      </div>

      <!-- Section 2: 3-Month Comparative Performance vs Peers & S&P 500 -->
      <div class="comparative-perf-card" style="margin-top:2rem;">
        <div class="comparative-perf-header">
          <div>
            <div style="display:flex; align-items:center; gap:0.6rem; flex-wrap:wrap;">
              <span class="category-badge" style="background:var(--accent-soft); color:var(--accent); border-color:var(--accent-soft); font-size:0.72rem;">MARKET CONTEXT</span>
              <h3 style="font-size:1.2rem; font-weight: 600; color:var(--text-primary); margin:0;">3-Month Comparative Performance vs. Peers &amp; S&amp;P 500</h3>
            </div>
            <p style="font-size:0.835rem; color:var(--text-muted); margin:0.35rem 0 0 0;">
              Contextual move analysis: Normalized % return (Day 0 = 0.0%) against top 3 competitors and the S&amp;P 500 (SPY) benchmark.
            </p>
          </div>

          <!-- Watchlist Company Selector Dropdown -->
          <div style="display:flex; align-items:center; gap:0.6rem; width:100%; max-width:320px;">
            <label for="perfCompanySelect" style="font-size:0.78rem; font-weight:700; color:var(--text-muted); text-transform:uppercase;">Select Stock:</label>
            <select id="perfCompanySelect" class="comparative-select" style="flex:1;" onchange="renderComparativePerformanceChart(this.value)">
              {% for sec in sector_directory %}
              <optgroup label="{{ sec.name }} ({{ sec.count }})">
                {% for co in sec.companies %}
                <option value="{{ co.symbol }}">{{ co.symbol }} — {{ co.name }}</option>
                {% endfor %}
              </optgroup>
              {% endfor %}
            </select>
          </div>
        </div>

        <!-- Mobile Segmented View Toggle (Chart vs Table) -->
        <div class="perf-mobile-toggle">
          <button class="perf-toggle-btn active" id="perfToggleChartBtn" onclick="switchPerfView('chart')">Chart View</button>
          <button class="perf-toggle-btn" id="perfToggleTableBtn" onclick="switchPerfView('table')">Comparison Table</button>
        </div>

        <!-- Real-time Alpha & Return Metrics Ribbon -->
        <div class="perf-kpi-grid" id="perfKpiGrid">
          <!-- Dynamically populated via JS based on selected company -->
        </div>

        <!-- Interactive Chart Canvas Container -->
        <div id="perfChartContainer" style="position:relative; height:280px; width:100%;">
          <canvas id="comparativeChartCanvas"></canvas>
        </div>

        <!-- Competitor Breakdown Table Container -->
        <div class="perf-table-wrap" id="perfTableContainer">
          <table class="perf-table" id="perfBreakdownTable">
            <!-- Dynamically populated table -->
          </table>
        </div>
      </div>

      <!-- Section 3: Health & Pipeline Safeguards -->
      <section class="health-section" id="health" style="margin-top:2rem;">
        <div class="health-header">
          <div class="health-title-group">
            <h3 class="health-title">Pipeline Health &amp; Safeguards</h3>
            <span class="health-status-badge health-badge-healthy">
              <span class="pulse-dot" style="background:var(--pos);"></span>
              HEALTHY &bull; OPERATIONAL
            </span>
          </div>
          <div style="font-size:0.75rem; color:var(--text-muted);">
            Moving Avg Baseline: {{ latest_run.moving_avg_raw if latest_run else 570 }} items/run
          </div>
        </div>

        <div class="health-grid" style="grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));">
          <div class="health-metric-card">
            <div class="health-metric-title">SEC EDGAR Filings</div>
            <div class="health-metric-val" style="color:var(--pos);">{{ latest_run.edgar_count if latest_run else 450 }}</div>
            <div class="health-metric-sub">{{ watchlist_companies|length }} companies queried</div>
          </div>
          <div class="health-metric-card">
            <div class="health-metric-title">Company Releases</div>
            <div class="health-metric-val" style="color:var(--accent-blue);">{{ latest_run.company_ir_count if latest_run else 100 }}</div>
            <div class="health-metric-sub">Official press room feeds</div>
          </div>
          <div class="health-metric-card">
            <div class="health-metric-title">News Media Coverage</div>
            <div class="health-metric-val" style="color:var(--pos);">{{ latest_run.news_media_count if latest_run and latest_run.news_media_count is defined else stats.by_source.get('News Media', 0) }}</div>
            <div class="health-metric-sub">Finnhub 3rd-party journalism</div>
          </div>
          <div class="health-metric-card">
            <div class="health-metric-title">Total Unique Yield</div>
            <div class="health-metric-val" style="color:var(--accent);">{{ latest_run.total_unique if latest_run else stats.total }}</div>
            <div class="health-metric-sub">After deduplication</div>
          </div>
          <div class="health-metric-card">
            <div class="health-metric-title">High Priority Stories</div>
            <div class="health-metric-val" style="color:var(--warn);">{{ latest_run.high_impact_count if latest_run else stats.high_priority_count }}</div>
            <div class="health-metric-sub">Score ≥ 7.0 / 10.0</div>
          </div>
        </div>
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
        const linePalette = [
          { stroke: '#2563eb', fillTop: 'rgba(37, 99, 235, 0.20)', fillBot: 'rgba(37, 99, 235, 0.0)' },
          { stroke: '#10b981', fillTop: 'rgba(16, 185, 129, 0.18)', fillBot: 'rgba(16, 185, 129, 0.0)' },
          { stroke: '#7c3aed', fillTop: 'rgba(124, 58, 237, 0.18)', fillBot: 'rgba(124, 58, 237, 0.0)' },
          { stroke: '#f59e0b', fillTop: 'rgba(245, 158, 11, 0.18)', fillBot: 'rgba(245, 158, 11, 0.0)' },
          { stroke: '#0284c7', fillTop: 'rgba(2, 132, 199, 0.18)', fillBot: 'rgba(2, 132, 199, 0.0)' },
          { stroke: '#e11d48', fillTop: 'rgba(225, 29, 72, 0.18)', fillBot: 'rgba(225, 29, 72, 0.0)' },
        ];

        const sortedTickers = Object.keys(rawChartData.timeline_series).sort((a, b) => {
          const sumA = (rawChartData.timeline_series[a] || []).reduce((s, v) => s + v, 0);
          const sumB = (rawChartData.timeline_series[b] || []).reduce((s, v) => s + v, 0);
          return sumB - sumA;
        });

        // On mobile phones, focus on top 3-4 series to avoid cramped line clutter
        const displayTickers = sortedTickers.slice(0, isPhone ? 3 : 5);

        const datasets = displayTickers.map((ticker, idx) => {
          const theme = linePalette[idx % linePalette.length];
          const grad = ctxTimeline.createLinearGradient(0, 0, 0, 220);
          grad.addColorStop(0, theme.fillTop);
          grad.addColorStop(1, theme.fillBot);

          return {
            label: ticker,
            data: rawChartData.timeline_series[ticker] || [],
            borderColor: theme.stroke,
            backgroundColor: grad,
            borderWidth: isPhone ? 1.8 : (isNarrow ? 2.0 : 2.5),
            fill: true,
            tension: 0.38,
            pointBackgroundColor: '#ffffff',
            pointBorderColor: theme.stroke,
            pointBorderWidth: 1.5,
            pointRadius: isPhone ? 2 : (isNarrow ? 2.5 : 3.5),
            pointHoverRadius: 5,
            pointHoverBackgroundColor: theme.stroke,
            pointHoverBorderColor: '#ffffff',
            pointHoverBorderWidth: 2,
          };
        });

        new Chart(ctxTimeline, {
          type: 'line',
          data: {
            labels: rawChartData.timeline_dates,
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
                  font: { family: 'Inter', size: isPhone ? 10 : (isNarrow ? 10 : 11), weight: '600' },
                  color: '#475569',
                  padding: isPhone ? 6 : (isNarrow ? 8 : 14)
                }
              },
              tooltip: {
                backgroundColor: '#0f172a',
                titleColor: '#f8fafc',
                bodyColor: '#e2e8f0',
                titleFont: { family: 'Inter', size: 11, weight: 'bold' },
                bodyFont: { family: 'JetBrains Mono', size: 11 },
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
                grid: { display: false, drawBorder: false },
                ticks: { 
                  font: { family: 'JetBrains Mono', size: isPhone ? 8.5 : (isNarrow ? 9 : 10) }, 
                  color: '#64748b',
                  maxTicksLimit: isPhone ? 4 : (isNarrow ? 5 : 8),
                  autoSkip: true,
                  maxRotation: 0
                }
              },
              y: {
                beginAtZero: true,
                grid: { color: 'rgba(226, 232, 240, 0.6)', drawBorder: false },
                ticks: { 
                  precision: 0, 
                  font: { family: 'JetBrains Mono', size: isPhone ? 8.5 : (isNarrow ? 9 : 10) }, 
                  color: '#64748b', 
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
        const sliceColors = [
          '#2563eb', '#10b981', '#7c3aed', '#f59e0b', '#0284c7', 
          '#e11d48', '#8b5cf6', '#ec4899', '#059669', '#d97706', '#64748b', '#0ea5e9'
        ];

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
              ctx.strokeStyle = 'var(--text-muted)';
              ctx.lineWidth = 1.2;
              ctx.stroke();

              ctx.textAlign = isRight ? 'left' : 'right';
              ctx.textBaseline = 'middle';
              ctx.font = '600 10px Inter, sans-serif';
              ctx.fillStyle = 'var(--text-primary)';
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
              backgroundColor: sliceColors.slice(0, catLabels.length),
              borderWidth: 2,
              borderColor: '#ffffff',
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
                backgroundColor: '#0f172a',
                titleColor: '#f8fafc',
                bodyColor: '#e2e8f0',
                titleFont: { family: 'Inter', size: 11, weight: 'bold' },
                bodyFont: { family: 'JetBrains Mono', size: 11 },
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
            const color = sliceColors[idx % sliceColors.length];
            legHtml += `
              <div class="category-stat-row" title="${escapeHtml(label)}: ${count} (${pct}%)">
                <div class="cat-stat-left">
                  <span class="category-legend-dot" style="background:${color};"></span>
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
        }
      }
    }

    // =========================================================================
    // 3-MONTH COMPARATIVE STOCK PERFORMANCE VS COMPETITORS & S&P 500
    // =========================================================================
    const perfData = {{ performance_data_json|safe }};
    let comparativeChartInstance = null;

    function switchPerfView(view) {
      const chartContainer = document.getElementById('perfChartContainer');
      const tableContainer = document.getElementById('perfTableContainer');
      const chartBtn = document.getElementById('perfToggleChartBtn');
      const tableBtn = document.getElementById('perfToggleTableBtn');

      if (view === 'table') {
        if (chartContainer) chartContainer.style.display = 'none';
        if (tableContainer) tableContainer.style.display = 'block';
        chartBtn?.classList.remove('active');
        tableBtn?.classList.add('active');
      } else {
        if (chartContainer) chartContainer.style.display = 'block';
        if (tableContainer) tableContainer.style.display = 'none';
        tableBtn?.classList.remove('active');
        chartBtn?.classList.add('active');
        if (comparativeChartInstance) comparativeChartInstance.resize();
      }
    }

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

      const targetColor = 'var(--accent)';
      const compColors = ['#ea580c', '#0284c7', '#9333ea'];
      const spyColor = 'var(--text-muted)';

      // 1. Populate KPI Ribbon
      if (kpiGrid && target) {
        const tgtPct = target.total_pct_change;
        const tgtColor = tgtPct >= 0 ? 'var(--pos)' : 'var(--neg)';
        const tgtArrow = tgtPct >= 0 ? '↗' : '↘';

        const alphaPeers = coData.alpha_vs_peers;
        const alphaPeersColor = alphaPeers >= 0 ? 'var(--pos)' : 'var(--neg)';

        const spyPct = spy ? spy.total_pct_change : 0;
        const avgPeerPct = coData.avg_competitor_pct;

        kpiGrid.innerHTML = `
          <div class="perf-kpi-box">
            <div class="perf-kpi-label">${escapeHtml(symbol)} 3M Return</div>
            <div class="perf-kpi-val" style="color:${tgtColor};">${tgtArrow} ${tgtPct >= 0 ? '+' : ''}${tgtPct.toFixed(2)}%</div>
            <div class="perf-kpi-sub">Latest: $${target.latest_price.toFixed(2)}</div>
          </div>
          <div class="perf-kpi-box">
            <div class="perf-kpi-label">Top Peers Avg</div>
            <div class="perf-kpi-val" style="color:${avgPeerPct >= 0 ? 'var(--pos)' : 'var(--neg)'};">${avgPeerPct >= 0 ? '+' : ''}${avgPeerPct.toFixed(2)}%</div>
            <div class="perf-kpi-sub">${escapeHtml(comps.map(c => c.symbol).join(', ') || 'None')}</div>
          </div>
          <div class="perf-kpi-box">
            <div class="perf-kpi-label">S&P 500 (SPY)</div>
            <div class="perf-kpi-val" style="color:${spyPct >= 0 ? 'var(--pos)' : 'var(--neg)'};">${spyPct >= 0 ? '+' : ''}${spyPct.toFixed(2)}%</div>
            <div class="perf-kpi-sub">Broad Market Benchmark</div>
          </div>
          <div class="perf-kpi-box">
            <div class="perf-kpi-label">Peer Relative Alpha</div>
            <div class="perf-kpi-val" style="color:${alphaPeersColor};">${alphaPeers >= 0 ? '+' : ''}${alphaPeers.toFixed(2)}%</div>
            <div class="perf-kpi-sub" style="font-weight:700; color:${coData.assessment_type === 'positive' ? 'var(--pos)' : (coData.assessment_type === 'negative' ? 'var(--neg)' : 'var(--text-secondary)')};">${escapeHtml(coData.assessment)}</div>
          </div>
        `;
      }

      // 2. Populate Table
      if (table && target) {
        let rowsHtml = `
          <thead>
            <tr>
              <th>Ticker / Entity</th>
              <th>Role</th>
              <th>Base (3M)</th>
              <th>Latest</th>
              <th>3M % Change</th>
              <th>Alpha</th>
            </tr>
          </thead>
          <tbody>
            <tr style="background:var(--accent-soft); font-weight:700;">
              <td><span class="ticker-badge ticker-${escapeHtml(symbol)}">${escapeHtml(symbol)}</span> ${escapeHtml(coData.name)}</td>
              <td><span class="form-type-pill" style="background:var(--accent-soft); color:var(--accent);">Target</span></td>
              <td style="font-family: var(--font-mono);">$${target.base_price.toFixed(2)}</td>
              <td style="font-family: var(--font-mono);">$${target.latest_price.toFixed(2)}</td>
              <td style="font-family: var(--font-mono); color:${target.total_pct_change >= 0 ? 'var(--pos)' : 'var(--neg)'};">${target.total_pct_change >= 0 ? '+' : ''}${target.total_pct_change.toFixed(2)}%</td>
              <td style="font-family: var(--font-mono); color:var(--text-muted);">&mdash;</td>
            </tr>
        `;

        comps.forEach((c, idx) => {
          const delta = (c.total_pct_change - target.total_pct_change).toFixed(2);
          rowsHtml += `
            <tr>
              <td><a href="company.html?ticker=${escapeHtml(c.symbol)}" class="ticker-badge" style="font-size:0.75rem;">${escapeHtml(c.symbol)}</a></td>
              <td><span class="form-type-pill">Peer #${idx+1}</span></td>
              <td style="font-family: var(--font-mono);">$${c.base_price.toFixed(2)}</td>
              <td style="font-family: var(--font-mono);">$${c.latest_price.toFixed(2)}</td>
              <td style="font-family: var(--font-mono); color:${c.total_pct_change >= 0 ? 'var(--pos)' : 'var(--neg)'};">${c.total_pct_change >= 0 ? '+' : ''}${c.total_pct_change.toFixed(2)}%</td>
              <td style="font-family: var(--font-mono); color:${delta >= 0 ? 'var(--pos)' : 'var(--neg)'};">${delta >= 0 ? '+' : ''}${delta}%</td>
            </tr>
          `;
        });

        if (spy) {
          const spyDelta = (spy.total_pct_change - target.total_pct_change).toFixed(2);
          rowsHtml += `
            <tr style="border-top:2px dashed var(--border-card);">
              <td><span class="form-type-pill" style="background:var(--bg-surface-elevated); color:var(--text-secondary); font-weight:700;">SPY</span> S&amp;P 500 ETF</td>
              <td><span class="form-type-pill">Benchmark</span></td>
              <td style="font-family: var(--font-mono);">$${spy.base_price.toFixed(2)}</td>
              <td style="font-family: var(--font-mono);">$${spy.latest_price.toFixed(2)}</td>
              <td style="font-family: var(--font-mono); color:${spy.total_pct_change >= 0 ? 'var(--pos)' : 'var(--neg)'};">${spy.total_pct_change >= 0 ? '+' : ''}${spy.total_pct_change.toFixed(2)}%</td>
              <td style="font-family: var(--font-mono); color:${spyDelta >= 0 ? 'var(--pos)' : 'var(--neg)'};">${spyDelta >= 0 ? '+' : ''}${spyDelta}%</td>
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
      const labels = target.series.map(pt => pt.date);

      const datasets = [
        {
          label: `${symbol} (Target)`,
          data: target.series.map(pt => pt.pct_change),
          borderColor: targetColor,
          backgroundColor: 'rgba(37, 99, 235, 0.08)',
          borderWidth: isPhone ? 2.2 : 3,
          fill: true,
          tension: 0.25,
          pointRadius: 0,
          pointHoverRadius: 5,
        }
      ];

      comps.forEach((c, idx) => {
        const color = compColors[idx % compColors.length];
        datasets.push({
          label: `${c.symbol} (Peer)`,
          data: c.series.map(pt => pt.pct_change),
          borderColor: color,
          borderWidth: isPhone ? 1.5 : 2,
          fill: false,
          tension: 0.25,
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
                font: { family: 'Inter', size: isPhone ? 10 : 11, weight: '600' },
                color: '#475569',
                padding: isPhone ? 6 : 10
              }
            },
            tooltip: {
              backgroundColor: '#0f172a',
              titleFont: { family: 'Inter', size: 12, weight: '700' },
              bodyFont: { family: 'JetBrains Mono', size: 11 },
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
                font: { family: 'JetBrains Mono', size: isPhone ? 8.5 : 10 },
                color: '#94a3b8',
                maxRotation: 0
              }
            },
            y: {
              grid: { color: 'rgba(226, 232, 240, 0.8)' },
              ticks: {
                callback: function(val) { return (val >= 0 ? '+' : '') + val + '%'; },
                font: { family: 'JetBrains Mono', size: isPhone ? 8.5 : 10 },
                color: '#94a3b8',
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
  <meta name="description" content="Every story on your watchlist, ranked by importance, with filters and takeaways.">
  <title>StockPulse — The feed</title>
  <link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' fill='%231b1a17'/%3E%3Cpath d='M6 19h6l3-9 3 13 2-4h6' fill='none' stroke='%23f6f4ee' stroke-width='2'/%3E%3C/svg%3E">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@400;500;600&family=Newsreader:opsz,wght@6..72,400;6..72,500;6..72,600&display=swap" rel="stylesheet">
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
        <h1 class="page-title">The feed</h1>
        <p class="page-standfirst">{{ items|length }} stories, ranked by how much they deserve your time.</p>
      </header>

      <div class="feed-toolbar">
        <input type="text" id="searchInput" class="feed-search" aria-label="Search the feed" placeholder="Search headlines and takeaways" oninput="filterItems()">
        <div class="feed-toolbar-row">
          <div class="feed-sort" role="group" aria-label="Order">
            <button class="feed-sort-btn active" id="sortScoreBtn" type="button" onclick="sortRows('score')">By importance</button>
            <button class="feed-sort-btn" id="sortDateBtn" type="button" onclick="sortRows('date')">By date</button>
          </div>
          <span class="feed-count" id="feedResultCount" aria-live="polite"></span>
          <button class="feed-clear" id="feedClearFilters" type="button" onclick="clearFeedFilters()" hidden>Clear filters</button>
        </div>
      </div>

      <details class="controls-panel" id="feedFilters">
        <summary class="feed-filters-toggle">Filters</summary>
        <div class="filter-row">
          <span class="filter-label">Sector</span>
          <div class="feed-sector-bar">
            <button class="feed-sector-btn filter-btn active" type="button" data-sector="ALL" onclick="setFeedSectorFilter('ALL', this)">All</button>
            {% for sec in sector_directory %}
            <button class="feed-sector-btn filter-btn" type="button" data-sector="{{ sec.name }}" onclick="setFeedSectorFilter(this.dataset.sector, this)">{{ sec.name }}</button>
            {% endfor %}
          </div>
        </div>

        <div class="filter-row">
          <span class="filter-label">Company</span>
          <div class="feed-ticker-picker-wrap" id="feedTickerPickerWrap">
            <button class="feed-ticker-picker-btn" id="feedTickerPickerBtn" onclick="toggleFeedTickerDropdown()" type="button">
              <span id="selectedTickerLabel">All companies</span> <span aria-hidden="true">▾</span>
            </button>
            <div class="feed-ticker-dropdown-menu" id="feedTickerDropdownMenu">
              <div class="feed-ticker-dropdown-search">
                <input type="text" id="feedTickerSearchInput" aria-label="Find a company" placeholder="Find a company" oninput="filterFeedTickerDropdown(this.value)">
              </div>
              <div class="feed-ticker-dropdown-list" id="feedTickerDropdownList">
                <div class="feed-ticker-item active" data-ticker="ALL" data-sector="ALL" onclick="selectFeedTicker('ALL')">
                  <span>All companies</span>
                  <span class="pill-count">{{ items|length }}</span>
                </div>
                {% for sec in sector_directory %}
                <div class="feed-dropdown-sec-header" data-sector="{{ sec.name }}">{{ sec.name }}</div>
                {% for co in sec.companies %}
                <div class="feed-ticker-item" data-ticker="{{ co.symbol }}" data-name="{{ co.name|lower }}" data-sector="{{ sec.name }}" onclick="selectFeedTicker(this.dataset.ticker)">
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
            <button class="filter-btn active" type="button" data-filter-type="category" data-val="ALL" onclick="setCategoryFilter('ALL', this)">All</button>
            {% for cat, count in stats.by_category.items() %}
            <button class="filter-btn" type="button" data-filter-type="category" data-val="{{ cat }}" onclick="setCategoryFilter(this.dataset.val, this)">{{ cat }} <span class="pill-count">{{ count }}</span></button>
            {% endfor %}
          </div>
        </div>

        <div class="filter-row">
          <span class="filter-label">Source</span>
          <div class="filter-options">
            <button class="filter-btn active" type="button" data-filter-type="source" data-val="ALL" onclick="setSourceFilter('ALL', this)">All</button>
            <button class="filter-btn" type="button" data-filter-type="source" data-val="news_media" onclick="setSourceFilter('news_media', this)">News Media</button>
            <button class="filter-btn" type="button" data-filter-type="source" data-val="sec_edgar" onclick="setSourceFilter('sec_edgar', this)">SEC EDGAR</button>
            <button class="filter-btn" type="button" data-filter-type="source" data-val="company_ir" onclick="setSourceFilter('company_ir', this)">Company Releases</button>
          </div>
        </div>
      </details>

      <div class="feed-list" id="newsBody">
        {% for item in items %}
        <article class="news-row{% if item.score >= 7.0 %} is-high{% endif %}"
            data-score="{{ item.score }}"
            data-date="{{ item.published_date }}"
            data-ticker="{{ item.ticker }}"
            data-tickers="{{ item.ticker }}{% if item.related_tickers_list %},{{ item.related_tickers_list|join(',') }}{% endif %}"
            data-sector="{{ item.macro_sector }}"
            data-source="{{ item.source }}"
            data-category="{{ item.category }}"
            data-text="{{ item.ticker }} {{ item.company_name }} {{ item.macro_sector }} {{ item.category }} {{ item.source_label }} {{ item.form_or_type }} {{ item.clean_headline }} {{ item.headline }} {{ item.cross_ref_summary or '' }} {{ item.llm_summary or '' }} {{ item.summary or '' }}">
          <span class="feed-score" title="{{ item.score_breakdown }}">{{ item.score }}</span>
          <a href="company.html?ticker={{ item.ticker|urlencode }}" class="ticker-badge" title="{{ item.company_name }}">{{ item.ticker }}</a>
          <div class="feed-body">
            <h3 class="feed-headline"><a href="{{ item.url if item.url.startswith('http') else '#' }}" target="_blank" rel="noopener noreferrer">{{ item.clean_headline }}</a></h3>
            {% if item.llm_summary and item.score >= 7.0 %}<p class="feed-takeaway">{{ item.llm_summary }}</p>{% endif %}
            <details class="feed-details">
              <summary><span class="feed-meta">{{ item.category }} · {{ item.source_label }}{% if item.form_or_type %} · {{ item.form_or_type }}{% endif %}</span></summary>
              <div class="feed-details-body">
                {% if item.llm_summary and item.score < 7.0 %}<p class="feed-takeaway">{{ item.llm_summary }}</p>{% endif %}
                {% if item.summary %}<p>{{ item.summary }}</p>{% endif %}
                {% if item.cross_references_list %}
                <p class="feed-detail-label">Also relevant to {{ item.cross_references_list|length }} {{ 'company' if item.cross_references_list|length == 1 else 'companies' }}</p>
                <ul class="feed-refs">
                  {% for ref in item.cross_references_list %}
                  <li><a href="company.html?ticker={{ ref.related_ticker|urlencode }}" class="ticker-badge">{{ ref.related_ticker }}</a> {{ ref.impact_note }}</li>
                  {% endfor %}
                </ul>
                {% endif %}
                {% if item.score_breakdown %}<p class="feed-detail-label">How it scored</p><p class="feed-breakdown">{{ item.score_breakdown|replace(' | ', ' · ') }}</p>{% endif %}
                <a href="{{ item.url if item.url.startswith('http') else '#' }}" target="_blank" rel="noopener noreferrer" class="fp-more">{% if item.source == 'sec_edgar' %}Read the filing{% elif item.source == 'company_ir' %}Read the release{% else %}Read the article{% endif %}</a>
              </div>
            </details>
          </div>
          <span class="date-cell">{{ short_date(item.published_date) }}</span>
        </article>
        {% endfor %}
        <p class="fp-empty" id="feedEmpty" hidden>No stories match these filters.</p>
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
    let onFileOpen = false;

    const BANDS = [
      { key: 'high', label: 'Read first', note: 'Score 7 and above', min: 7 },
      { key: 'mid', label: 'Worth knowing', note: 'Score 4 to 7', min: 4 },
      { key: 'low', label: 'On file', note: 'Below 4, mostly routine', min: -Infinity },
    ];

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

        row.dataset.match = (matchSector && matchTicker && matchCat && matchSrc && matchQuery) ? '1' : '0';
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

    function groupHeader(key, label, note, count, toggle) {
      const head = document.createElement('div');
      head.className = 'feed-group';
      head.dataset.key = key;
      const title = document.createElement('h2');
      title.className = 'feed-group-title';
      title.textContent = label;
      const meta = document.createElement('span');
      meta.className = 'feed-group-note';
      meta.textContent = note ? `${count} · ${note}` : String(count);
      head.append(title, meta);
      if (toggle) {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'feed-group-toggle';
        btn.textContent = onFileOpen ? 'Hide' : 'Show';
        btn.setAttribute('aria-expanded', String(onFileOpen));
        btn.addEventListener('click', () => {
          onFileOpen = !onFileOpen;
          renderGroups();
        });
        head.append(btn);
      }
      return head;
    }

    // Draws the group headings, and collapses "On file" until it is asked for or filtered into.
    function renderGroups() {
      const body = document.getElementById('newsBody');
      body.querySelectorAll('.feed-group').forEach(h => h.remove());
      const rows = Array.from(body.querySelectorAll('.news-row'));
      const active = filtersActive();
      const groups = new Map();

      rows.forEach(row => {
        const matched = row.dataset.match !== '0';
        let key;
        if (currentOrder === 'score') {
          key = bandFor(parseFloat(row.dataset.score)).key;
        } else {
          key = row.dataset.date;
        }
        if (matched) {
          if (!groups.has(key)) groups.set(key, { first: row, count: 0 });
          groups.get(key).count += 1;
        }
        const collapsed = currentOrder === 'score' && key === 'low' && !onFileOpen && !active;
        row.hidden = !matched || collapsed;
      });

      groups.forEach((group, key) => {
        let head;
        if (currentOrder === 'score') {
          const band = BANDS.find(b => b.key === key);
          head = groupHeader(key, band.label, band.note, group.count, key === 'low' && !active);
        } else {
          const parts = key.split('-').map(Number);
          const label = new Date(parts[0], parts[1] - 1, parts[2]).toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' });
          head = groupHeader(key, label, '', group.count, false);
        }
        body.insertBefore(head, group.first);
      });

      const shown = Array.from(groups.values()).reduce((sum, g) => sum + g.count, 0);
      const countEl = document.getElementById('feedResultCount');
      if (countEl) countEl.textContent = active ? `${shown} of ${rows.length} stories` : '';
      const clearBtn = document.getElementById('feedClearFilters');
      if (clearBtn) clearBtn.hidden = !active;
      const empty = document.getElementById('feedEmpty');
      if (empty) empty.hidden = shown !== 0;
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

      if (urlTicker) {
        setTickerFilter(urlTicker);
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
  <link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' fill='%231b1a17'/%3E%3Cpath d='M6 19h6l3-9 3 13 2-4h6' fill='none' stroke='%23f6f4ee' stroke-width='2'/%3E%3C/svg%3E">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@400;500;600&family=Newsreader:opsz,wght@6..72,400;6..72,500;6..72,600&display=swap" rel="stylesheet">
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
          <span class="cal-month cal-today" style="left:{{ calendar_view.today_pos }}%;">Today</span>
          {% for m in calendar_view.months %}
          <span class="cal-month" style="left:{{ m.pos }}%;">{{ m.label }}</span>
          {% endfor %}
          {% for mark in calendar_view.marks %}
          <a class="cal-mark{% if mark.estimated %} is-estimated{% endif %}" href="#{{ mark.anchor }}" data-event-type="{{ mark.event_type }}" style="left:{{ mark.pos }}%; bottom:{{ mark.lane * 12 }}px;" title="{{ mark.date }}: {{ mark.ticker }} {{ mark.kind }}{% if mark.estimated %} (estimated){% endif %}" aria-label="{{ mark.date }}: {{ mark.ticker }} {{ mark.kind }}"></a>
          {% endfor %}
        </div>
        <figcaption class="cal-legend">
          <span><i class="cal-key"></i>Confirmed</span>
          <span><i class="cal-key is-estimated"></i>Estimated from filing rules</span>
        </figcaption>
      </figure>
      {% endif %}

      <div class="controls-panel cal-filters">
        <div class="filter-options" role="group" aria-label="Filter events">
          <button class="filter-btn active cal-filter-btn" type="button" data-val="ALL" onclick="filterCalendar('ALL', this)">All <span class="pill-count">{{ calendar_events|length }}</span></button>
          <button class="filter-btn cal-filter-btn" type="button" data-val="Earnings" onclick="filterCalendar('Earnings', this)">Earnings Calls</button>
          <button class="filter-btn cal-filter-btn" type="button" data-val="Dividend" onclick="filterCalendar('Dividend', this)">Dividend Dates</button>
          <button class="filter-btn cal-filter-btn" type="button" data-val="SEC" onclick="filterCalendar('SEC', this)">SEC Filing Deadlines</button>
          <button class="filter-btn cal-filter-btn" type="button" data-val="Conference" onclick="filterCalendar('Conference', this)">Conferences</button>
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
            <a href="{{ ev.source_url }}" target="_blank" rel="noopener noreferrer" class="cal-source">{% if ev.source_type == 'ESTIMATED_RULE' %}SEC filings{% else %}Source{% endif %}</a>
            {% endif %}
          </article>
          {% endfor %}
        </section>
        {% else %}
        <p class="fp-empty">No upcoming events. They appear here after the next pipeline run.</p>
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
  <meta name="description" content="Macroeconomic intelligence panel mapping Federal Reserve (FRED) interest rates, 10Y Treasuries, CPI inflation, WTI Crude, and unemployment to company sensitivities.">
  <title>StockPulse — Macroeconomic Snapshot &amp; Sensitivities</title>
  <link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' fill='%231b1a17'/%3E%3Cpath d='M6 19h6l3-9 3 13 2-4h6' fill='none' stroke='%23f6f4ee' stroke-width='2'/%3E%3C/svg%3E">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@400;500;600&family=Newsreader:opsz,wght@6..72,400;6..72,500;6..72,600&display=swap" rel="stylesheet">
  <script>""" + THEME_BOOT_JS + """</script>
  <style>
""" + SHARED_CSS + """
  </style>
</head>
<body>
  <div class="app-layout">
    """ + NAVIGATION_LAYOUT_HTML + """

    <main class="app-main">
      <header class="section-header-row" style="padding-bottom:1.25rem; border-bottom:1px solid var(--border-card); margin-bottom:1.75rem;">
        <div>
          <h1 class="hero-title" style="font-size:2rem; text-align:left; margin-bottom:0.25rem;">Macroeconomic Intelligence</h1>
          <p style="font-size:0.92rem; color:var(--text-muted);">Federal Reserve Bank of St. Louis (FRED) live benchmark indicators mapped to portfolio sensitivities with AI impact analysis</p>
        </div>
        <div style="display:flex; align-items:center; gap:0.5rem;">
          <span class="section-time-pill" style="color:var(--accent-blue); font-weight:700;">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="20" x2="12" y2="10"/><line x1="18" y1="20" x2="18" y2="4"/><line x1="6" y1="20" x2="6" y2="16"/></svg>
            St. Louis Fed (FRED) Feed
          </span>
        </div>
      </header>

      <!-- Upcoming High-Impact Macroeconomic Events Strip -->
      <section style="margin-bottom: 2rem;">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:0.85rem;">
          <div style="display:flex; align-items:center; gap:0.5rem;">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" style="color:var(--accent-blue);"><rect x="3" y="4" width="18" height="18" rx="2" ry="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>
            <h2 style="font-size:1.05rem; font-weight: 600; color:var(--text-primary); margin:0;">Upcoming Macroeconomic Releases &amp; Decisions</h2>
          </div>
          <span style="font-size:0.75rem; color:var(--text-muted); font-weight:600;">Federal Reserve &amp; Agency Schedule</span>
        </div>

        <div class="macro-events-strip">
          {% for ev in upcoming_economic_events %}
          <div class="macro-event-card">
            <div>
              <div class="macro-event-top">
                <span class="macro-event-authority">{{ ev.authority }}</span>
                <span class="macro-event-countdown">{{ ev.relative_badge }}</span>
              </div>
              <h3 class="macro-event-title">{{ ev.title }}</h3>
            </div>
            <div>
              <div class="macro-event-date-row" style="margin-bottom:0.45rem;">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="4" width="18" height="18" rx="2" ry="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>
                <span>{{ ev.display_date }}</span>
              </div>
              <div class="macro-event-consensus">
                <strong>Expectation:</strong> {{ ev.consensus }}
              </div>
            </div>
          </div>
          {% endfor %}
        </div>
      </section>

      <!-- Sector & Ticker Filter for Sensitivities -->
      <div class="controls-panel">
        <div style="margin-bottom:0.75rem;">
          <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:0.4rem; flex-wrap:wrap; gap:0.5rem;">
            <span class="filter-label" style="margin-bottom:0;">Filter by Sector:</span>
            <a href="company.html" class="form-type-pill" style="text-decoration:none; background:var(--accent-soft); color:var(--accent); border-color:var(--accent-soft); font-size:0.72rem; font-weight:700;">Company Directory ↗</a>
          </div>
          <div class="feed-sector-bar">
            <button class="feed-sector-btn active econ-sec-btn" data-sector="ALL" onclick="filterEconomicBySector('ALL', this)">
              All Sectors <span class="pill-count">{{ watchlist_companies|length }}</span>
            </button>
            {% for sec in sector_directory %}
            <button class="feed-sector-btn econ-sec-btn" data-sector="{{ sec.name }}" onclick="filterEconomicBySector('{{ sec.name }}', this)">
              {{ sec.name }} <span class="pill-count">{{ sec.count }}</span>
            </button>
            {% endfor %}
          </div>
        </div>

        <div class="filter-row" style="align-items:center; gap:0.5rem; flex-wrap:wrap;">
          <span class="filter-label">Filter Company:</span>
          <button class="filter-btn active econ-filter-btn" data-val="ALL" data-sector="ALL" onclick="filterEconomicByTicker('ALL', this)">All Watchlist Tickers</button>
          {% for co in watchlist_companies %}
          <button class="filter-btn econ-filter-btn" data-val="{{ co.symbol }}" data-sector="{{ co.macro_sector }}" onclick="filterEconomicByTicker('{{ co.symbol }}', this)" title="{{ co.name }}">
            <span class="ticker-badge ticker-{{ co.symbol }}" style="font-size:0.68rem; padding:0.05rem 0.3rem;">{{ co.symbol }}</span>
          </button>
          {% endfor %}
        </div>
      </div>

      <!-- Economic Indicator Cards (Featuring Anchored Focal Cards) -->
      <div class="economic-grid" id="economicCardsGrid" style="margin-bottom:3rem;">
        {% for ind in economic_indicators %}
        <div class="economic-card {% if loop.index <= 2 %}economic-card-anchor{% endif %}" 
             data-indicator-id="{{ ind.indicator_id }}"
             data-relevant-tickers="{{ ind.relevant_tickers }}">
          <div>
            <div class="economic-card-top">
              <span class="economic-category-badge">{{ ind.category }} &bull; {{ ind.series_id }}</span>
              <span class="economic-trend-badge {% if ind.change_direction == 'up' %}trend-up{% elif ind.change_direction == 'down' %}trend-down{% else %}trend-flat{% endif %}">
                {% if ind.change_direction == 'up' %}▲ +{{ ind.change_value }}
                {% elif ind.change_direction == 'down' %}▼ {{ ind.change_value }}
                {% else %}■ Steady{% endif %}
              </span>
            </div>

            <div class="economic-val {% if loop.index <= 2 %}economic-val-anchor{% endif %}">{{ ind.formatted_value }}</div>
            <h4 class="economic-series-name">{{ ind.name }}</h4>

            <!-- Sparkline Mini-Chart (12-24 Month Historical Trend) -->
            <div class="sparkline-wrapper" id="sparkline-{{ ind.indicator_id }}" data-history='{{ ind.history_json|default("[]") }}' data-unit="{{ ind.unit }}">
              <svg class="sparkline-svg" id="svg-{{ ind.indicator_id }}" viewBox="0 0 280 60" preserveAspectRatio="none">
                <!-- Dynamically rendered by renderEconSparklines() -->
              </svg>
              <div class="sparkline-labels">
                <span class="spark-start">12M Trend</span>
                <span class="spark-end">{{ ind.observation_date }}</span>
              </div>
            </div>

            <!-- AI-Generated Synthesis Box -->
            {% if ind.ai_synthesis %}
            <div class="ai-synthesis-card">
              <div class="ai-synthesis-head">
                <span class="ai-synthesis-badge">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>
                  AI Macro Takeaway
                </span>
                <span class="ai-synthesis-meta">Observed {{ ind.observation_date }}</span>
              </div>
              <div class="ai-synthesis-content">
                {{ ind.ai_synthesis }}
              </div>
            </div>
            {% endif %}

            <p class="economic-context">{{ ind.context_note }}</p>
          </div>

          <div class="economic-tickers-wrap">
            <div class="economic-tickers-label">Direct Watchlist Sensitivities ({{ ind.tickers_list|length }} Companies):</div>
            <div class="economic-tickers-list">
              {% for sym in ind.tickers_list %}
              <a href="company.html?ticker={{ sym }}" class="ticker-badge ticker-{{ sym }}">{{ sym }}</a>
              {% endfor %}
            </div>
          </div>
        </div>
        {% endfor %}
      </div>

      <!-- Watchlist Sensitivity Matrix Table -->
      <section style="background:var(--bg-surface-glass); backdrop-filter:blur(16px); border:1px solid var(--border-glass); border-radius:var(--radius-xl); padding:2rem; box-shadow:var(--shadow-card);">
        <h3 style="font-size:1.25rem; font-weight: 600; color:var(--text-primary); margin-bottom:0.35rem;">Watchlist Sensitivity Matrix</h3>
        <p style="font-size:0.88rem; color:var(--text-secondary); margin-bottom:1.5rem;">Documented sensitivities driving company-specific macroeconomic exposure</p>

        <div class="table-container">
          <table>
            <thead>
              <tr>
                <th style="width: 110px;">Ticker</th>
                <th>Company Name</th>
                <th>Sector</th>
                <th>Key Macro Sensitivities</th>
              </tr>
            </thead>
            <tbody id="matrixTableBody">
              {% for co in watchlist_companies %}
              <tr class="matrix-row" data-ticker="{{ co.symbol }}" data-sector="{{ co.macro_sector }}">
                <td>
                  <a href="company.html?ticker={{ co.symbol }}" class="ticker-badge ticker-{{ co.symbol }}">{{ co.symbol }}</a>
                </td>
                <td style="font-weight:700; color:var(--text-primary);">
                  {{ co.name }}
                </td>
                <td>
                  <span class="category-badge">{{ co.sector | replace('_', ' ') | title }}</span>
                </td>
                <td style="font-size:0.835rem; color:var(--text-secondary); line-height:1.45;">
                  {% if co.sensitivities %}
                    {{ co.sensitivities|join(', ') }}
                  {% else %}
                    General macroeconomic interest rate, inflation, and consumer spending sensitivity.
                  {% endif %}
                </td>
              </tr>
              {% endfor %}
            </tbody>
          </table>
        </div>
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
        const areaD = `${pathD} L ${points[points.length - 1].x.toFixed(1)} ${height} L ${points[0].x.toFixed(1)} ${height} Z`;

        const gradId = 'grad-' + Math.random().toString(36).substr(2, 9);
        const lastPt = points[points.length - 1];

        svg.setAttribute('viewBox', `0 0 ${width} ${height}`);
        svg.innerHTML = `
          <defs>
            <linearGradient id="${gradId}" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stop-color="var(--accent)" stop-opacity="0.32" />
              <stop offset="100%" stop-color="var(--accent)" stop-opacity="0.0" />
            </linearGradient>
          </defs>
          <path d="${areaD}" fill="url(#${gradId})" />
          <path d="${pathD}" fill="none" stroke="var(--accent)" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" />
          <circle cx="${lastPt.x.toFixed(1)}" cy="${lastPt.y.toFixed(1)}" r="4.5" fill="var(--accent)" stroke="var(--bg-surface)" stroke-width="2" />
          <circle class="hover-dot" cx="0" cy="0" r="4.5" fill="var(--text-primary)" stroke="var(--bg-surface)" stroke-width="2" style="display:none;" />
        `;

        // Update labels
        const startLabel = wrap.querySelector('.spark-start');
        const endLabel = wrap.querySelector('.spark-end');
        if (startLabel) startLabel.textContent = `${history[0].date.substring(0, 7)}: ${history[0].value}${unit.includes('%') ? '%' : ''}`;
        if (endLabel) endLabel.textContent = `Latest: ${history[history.length - 1].value}${unit.includes('%') ? '%' : ''}`;

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

      const pills = document.querySelectorAll('.econ-filter-btn');
      pills.forEach(pill => {
        const pSec = pill.getAttribute('data-sector');
        const pVal = pill.getAttribute('data-val');
        if (pVal === 'ALL') {
          pill.style.display = 'inline-flex';
        } else if (sector === 'ALL' || pSec === sector) {
          pill.style.display = 'inline-flex';
        } else {
          pill.style.display = 'none';
        }
      });

      // If current ticker is hidden, reset to ALL
      if (currentEconTicker !== 'ALL') {
        const activePill = document.querySelector(`.econ-filter-btn[data-val="${currentEconTicker}"]`);
        if (activePill && activePill.style.display === 'none') {
          filterEconomicByTicker('ALL', document.querySelector('.econ-filter-btn[data-val="ALL"]'));
        }
      }

      applyEconomicFilters();
    }

    function filterEconomicByTicker(ticker, btn) {
      currentEconTicker = ticker;
      document.querySelectorAll('.econ-filter-btn').forEach(b => b.classList.remove('active'));
      if (btn) btn.classList.add('active');
      applyEconomicFilters();
    }

    function applyEconomicFilters() {
      const cards = document.querySelectorAll('.economic-card');
      cards.forEach(card => {
        const relevant = (card.getAttribute('data-relevant-tickers') || '').split(',').map(s => s.trim());
        if (currentEconTicker === 'ALL') {
          card.style.display = 'flex';
        } else if (relevant.includes(currentEconTicker)) {
          card.style.display = 'flex';
        } else {
          card.style.display = 'none';
        }
      });

      const matrixRows = document.querySelectorAll('.matrix-row');
      matrixRows.forEach(row => {
        const rTicker = row.getAttribute('data-ticker');
        const rSector = row.getAttribute('data-sector');
        const secMatch = (currentEconSector === 'ALL' || rSector === currentEconSector);
        const tickMatch = (currentEconTicker === 'ALL' || rTicker === currentEconTicker);
        if (secMatch && tickMatch) {
          row.style.display = '';
        } else {
          row.style.display = 'none';
        }
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
COMPANY_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=5.0">
  <meta name="description" content="Dedicated single-stock company profile with multi-source news (SEC filings, Company Releases, News Media), upcoming calendar milestones, macroeconomic sensitivities, and supply chain ecosystem.">
  <title>StockPulse — Company Directory</title>
  <link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' fill='%231b1a17'/%3E%3Cpath d='M6 19h6l3-9 3 13 2-4h6' fill='none' stroke='%23f6f4ee' stroke-width='2'/%3E%3C/svg%3E">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@400;500;600&family=Newsreader:opsz,wght@6..72,400;6..72,500;6..72,600&display=swap" rel="stylesheet">
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.7/dist/chart.umd.min.js"></script>
  <script>""" + THEME_BOOT_JS + """</script>
  <style>
""" + SHARED_CSS + """
  </style>
</head>
<body>
  <div class="app-layout">
    """ + NAVIGATION_LAYOUT_HTML + """

    <main class="app-main">
      <header class="section-header-row" style="padding-bottom:1.25rem; border-bottom:1px solid var(--border-card); margin-bottom:1.5rem;">
        <div>
          <h1 class="hero-title" style="font-size:2rem; text-align:left; margin-bottom:0.25rem;">Company Directory</h1>
          <p style="font-size:0.92rem; color:var(--text-muted);">Browse all {{ watchlist_companies|length }} monitored holdings, search by ticker or sector, and inspect 360° deep-dive intelligence profiles</p>
        </div>
        <div style="display:flex; align-items:center; gap:0.5rem;">
          <span class="section-time-pill">
            <span class="pulse-dot" style="background:var(--pos);"></span> {{ watchlist_companies|length }} Monitored Holdings
          </span>
        </div>
      </header>

      <!-- Unified Company Directory & Sector Browser Component -->
      <section class="company-directory-browser">
        <div class="company-browser-top">
          <div>
            <div style="display:flex; align-items:center; gap:0.45rem;">
              <span style="font-size:1.05rem; font-weight: 600; color:var(--text-primary);">Browse Holdings</span>
              <span class="category-badge" style="font-size:0.7rem; font-weight: 600; padding:0.1rem 0.45rem;">{{ watchlist_companies|length }} Companies</span>
            </div>
            <div style="font-size:0.78rem; color:var(--text-muted); margin-top:0.15rem;">Select any company to load its interactive deep-dive research profile below</div>
          </div>
          <div style="display:flex; align-items:center; gap:0.5rem; flex-wrap:wrap;">
            <div style="position:relative; width:100%; max-width:280px;">
              <input type="text" id="companyStripFilter" placeholder="Search ticker, company, or sector..." oninput="filterCompanyStrip(this.value)" style="width:100%; background:var(--bg-base); border:1.5px solid var(--border-card); border-radius:var(--radius-full); padding:0.42rem 0.95rem; font-size:0.82rem; color:var(--text-primary); outline:none;">
            </div>
          </div>
        </div>

        <!-- Sector Category Filter Tabs -->
        <div class="company-browser-sectors">
          <button class="company-browser-sec-btn active" data-sector="ALL" onclick="filterCompanySector('ALL', this)">
            All Sectors <span class="tab-count" style="font-family: var(--font-mono); font-size:0.68rem; margin-left:0.2rem;">{{ watchlist_companies|length }}</span>
          </button>
          {% for sec in sector_directory %}
          <button class="company-browser-sec-btn" data-sector="{{ sec.name }}" onclick="filterCompanySector('{{ sec.name }}', this)">
            {{ sec.name }} <span class="tab-count" style="font-family: var(--font-mono); font-size:0.68rem; margin-left:0.2rem;">{{ sec.count }}</span>
          </button>
          {% endfor %}
        </div>

        <!-- 30 Holdings Grid (Retains .company-strip & .company-strip-pill for tests and styles) -->
        <div class="company-strip-wrap" style="overflow:visible;">
          <div class="company-browser-grid company-strip" id="companyStripContainer">
            {% for co in watchlist_companies %}
            <button class="company-browser-card company-strip-pill {% if loop.first %}active{% endif %}" 
                    data-ticker="{{ co.symbol }}" 
                    data-name="{{ co.name|lower }}"
                    data-sector="{{ co.macro_sector|lower }}"
                    onclick="switchCompany('{{ co.symbol }}')"
                    title="{{ co.name }} ({{ co.symbol }}) — {{ co.macro_sector }}">
              <div class="company-browser-card-left">
                <span class="ticker-badge ticker-{{ co.symbol }}" style="font-size:0.75rem; padding:0.12rem 0.45rem; flex-shrink:0;">{{ co.symbol }}</span>
                <div class="company-browser-card-info">
                  <div class="company-browser-card-name">{{ co.name }}</div>
                  <div class="company-browser-card-sec">{{ co.sector | replace('_', ' ') | title }}</div>
                </div>
              </div>
              <div class="company-browser-card-stats">
                <div class="company-browser-card-alpha" style="color:{% if co.alpha_vs_spy > 0 %}var(--pos){% elif co.alpha_vs_spy < 0 %}var(--neg){% else %}var(--text-muted){% endif %};">
                  {% if co.alpha_vs_spy > 0 %}+{% endif %}{{ co.alpha_vs_spy }}%
                </div>
                <div class="company-browser-card-stories">{{ co.story_count }} {% if co.story_count == 1 %}story{% else %}stories{% endif %}</div>
              </div>
            </button>
            {% endfor %}
          </div>
        </div>
      </section>

      <!-- Container for each company (one shown at a time) -->
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

      <div class="company-profile-container" id="profile-{{ co.symbol }}" data-ticker="{{ co.symbol }}" style="{% if not loop.first %}display:none;{% endif %}">
        
        <!-- Company Hero Header Box -->
        <div class="company-hero-box">
          <div class="company-hero-header">
            <div class="company-hero-left">
              <div class="company-hero-symbol ticker-{{ co.symbol }}">{{ co.symbol }}</div>
              <div>
                <h2 class="company-hero-name">{{ co.name }}</h2>
                <div class="company-meta-pills">
                  <span class="category-badge" style="font-size:0.75rem;">{{ co.sector | replace('_', ' ') | title }}</span>
                  {% if co.cik %}
                  <a href="https://www.sec.gov/edgar/browse/?CIK={{ co.cik }}" target="_blank" rel="noopener noreferrer" class="form-type-pill" style="text-decoration:none;" title="View SEC EDGAR Submissions">
                    CIK: {{ co.cik }} ↗
                  </a>
                  {% endif %}
                  {% if co.newsroom_url or co.ir_page_url or co.ir_feed_url %}
                  <a href="{{ co.newsroom_url or co.ir_page_url or co.ir_feed_url }}" target="_blank" rel="noopener noreferrer" class="form-type-pill" style="text-decoration:none;" title="View {{ co.name }} Official Newsroom &amp; Press Releases">
                    Newsroom ↗
                  </a>
                  {% endif %}
                </div>
              </div>
            </div>

            <div style="display:flex; flex-direction:column; align-items:flex-end; gap:0.4rem;">
              <div style="font-size:0.72rem; font-weight:700; color:var(--text-muted); text-transform:uppercase; letter-spacing:0.05em;">Key Regulators</div>
              <div style="display:flex; gap:0.35rem; flex-wrap:wrap; justify-content:flex-end;">
                {% if co.regulators %}
                  {% for reg in co.regulators %}
                  <span class="form-type-pill" style="background:var(--bg-base); color:var(--text-secondary); border-color:var(--border-card);">{{ reg }}</span>
                  {% endfor %}
                {% else %}
                  <span class="form-type-pill">SEC</span>
                {% endif %}
              </div>
            </div>
          </div>

          {% if co.notes %}
          <div class="company-notes-card">
            <strong style="color:var(--text-primary);">Analyst Strategic Focus:</strong> {{ co.notes }}
          </div>
          {% endif %}

          <!-- Company Vital Metrics Ribbon -->
          <div class="company-kpi-ribbon">
            <div class="company-kpi-card">
              <div class="company-kpi-title">Intelligence Disclosures</div>
              <div class="company-kpi-val">{{ co_news|length }}</div>
              <div class="company-kpi-sub">
                {{ ns.news_count }} News &bull; {{ ns.edgar_count }} SEC &bull; {{ ns.ir_count }} IR
              </div>
            </div>

            <div class="company-kpi-card">
              <div class="company-kpi-title">High-Impact Signals</div>
              <div class="company-kpi-val" style="color:{% if ns.high_count > 0 %}var(--neg){% else %}var(--pos){% endif %};">
                {{ ns.high_count }}
              </div>
              <div class="company-kpi-sub">Materiality Score &ge; 7.0</div>
            </div>

            <div class="company-kpi-card">
              <div class="company-kpi-title">Next Event</div>
              <div class="company-kpi-val" style="font-size:1.02rem;">
                {% if co_events %}
                  {{ co_events[0].display_date }}
                {% else %}
                  None Scheduled
                {% endif %}
              </div>
              <div class="company-kpi-sub" title="{% if co_events %}{{ co_events[0].headline }}{% endif %}">
                {% if co_events %}{{ co_events[0].headline }}{% else %}Next 60 days clear{% endif %}
              </div>
            </div>

            <div class="company-kpi-card">
              <div class="company-kpi-title">Ecosystem Network</div>
              <div class="company-kpi-val">
                {{ (co.key_customers|length if co.key_customers else 0) + (co.key_suppliers|length if co.key_suppliers else 0) + (co.competitors|length if co.competitors else 0) }}
              </div>
              <div class="company-kpi-sub">
                {{ co.key_customers|length if co.key_customers else 0 }} Customers &bull; {{ co.key_suppliers|length if co.key_suppliers else 0 }} Suppliers &bull; {{ co.competitors|length if co.competitors else 0 }} Competitors
              </div>
            </div>
          </div>
        </div>

        <!-- 3-Month Comparative Performance Card for this stock -->
        <div class="comparative-perf-card" style="margin-bottom:1.5rem;">
          <div class="comparative-perf-header">
            <div>
              <div style="display:flex; align-items:center; gap:0.6rem;">
                <span class="category-badge" style="background:var(--accent-soft); color:var(--accent); border-color:var(--accent-soft); font-size:0.72rem;">MARKET CONTEXT</span>
                <h3 style="font-size:1.15rem; font-weight: 600; color:var(--text-primary); margin:0;">3-Month Performance vs. Competitors &amp; S&amp;P 500</h3>
              </div>
              <p style="font-size:0.82rem; color:var(--text-muted); margin:0.3rem 0 0 0;">
                Is {{ co.symbol }}'s move normal or unusual? Normalized % change since Day 0 relative to top 3 competitors and the S&amp;P 500 (SPY).
              </p>
            </div>
            <div style="display:flex; align-items:center; gap:0.4rem;">
              <span class="ticker-badge ticker-{{ co.symbol }}" style="font-size:0.85rem; padding:0.25rem 0.6rem;">{{ co.symbol }}</span>
            </div>
          </div>

          <div class="perf-kpi-grid" id="compPerfKpi-{{ co.symbol }}">
            <!-- Dynamically populated via JS -->
          </div>

          <div style="position:relative; height:280px; width:100%;">
            <canvas id="compPerfCanvas-{{ co.symbol }}"></canvas>
          </div>

          <div class="perf-table-wrap">
            <table class="perf-table" id="compPerfTable-{{ co.symbol }}">
              <!-- Dynamically populated via JS -->
            </table>
          </div>
        </div>

        <!-- 2-Column Main Deck -->
        <div class="company-grid-layout">
          
          <!-- Left Main Column: Intelligence Feed across all 3 sources -->
          <div class="company-card-deck">
            <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:0.75rem; background:var(--bg-surface); padding:1rem 1.25rem; border:1px solid var(--border-card); border-radius:var(--radius-lg); box-shadow:var(--shadow-sm);">
              <div>
                <h3 style="font-size:1.05rem; font-weight: 600; color:var(--text-primary); margin:0;">Intelligence Feed</h3>
                <div style="font-size:0.75rem; color:var(--text-muted); margin-top:0.15rem;">News Media &bull; SEC EDGAR &bull; Company Releases ({{ co_news|length }} Total)</div>
              </div>

              <!-- In-Page Source Filters -->
              <div style="display:flex; gap:0.35rem; flex-wrap:wrap; align-items:center;">
                <button class="filter-btn active company-source-filter-btn" data-source="ALL" onclick="filterCompanyNews('{{ co.symbol }}', 'ALL', this)">All ({{ co_news|length }})</button>
                <button class="filter-btn company-source-filter-btn" data-source="news_media" onclick="filterCompanyNews('{{ co.symbol }}', 'news_media', this)">News Media ({{ ns.news_count }})</button>
                <button class="filter-btn company-source-filter-btn" data-source="sec_edgar" onclick="filterCompanyNews('{{ co.symbol }}', 'sec_edgar', this)">SEC EDGAR ({{ ns.edgar_count }})</button>
                <button class="filter-btn company-source-filter-btn" data-source="company_ir" onclick="filterCompanyNews('{{ co.symbol }}', 'company_ir', this)">Company Releases ({{ ns.ir_count }})</button>
              </div>
            </div>

            <!-- In-Page Keyword Search Bar -->
            <div style="background:var(--bg-surface); border:1px solid var(--border-card); border-radius:var(--radius-md); padding:0.6rem 0.95rem; display:flex; align-items:center; gap:0.6rem;">
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="color:var(--text-muted);"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></svg>
              <input type="text" class="company-feed-search-input" id="search-{{ co.symbol }}" placeholder="Search within {{ co.symbol }} disclosures (e.g. revenue, CEO, lawsuit, chip, contract)..." oninput="searchCompanyFeed('{{ co.symbol }}', this.value)" style="border:none; background:transparent; width:100%; outline:none; font-size:0.84rem; color:var(--text-primary);">
            </div>

            <!-- Feed Items List -->
            {% if co_news %}
              {% for it in co_news %}
              <div class="company-feed-item company-news-item" data-source="{{ it.source }}">
                <div class="company-feed-top">
                  <div style="display:flex; align-items:center; gap:0.45rem; flex-wrap:wrap;">
                    <span class="score-badge {% if it.score >= 7.0 %}score-high{% elif it.score >= 4.0 %}score-med{% else %}score-low{% endif %}" title="{{ it.score_breakdown }}">
                      {{ it.score }}
                    </span>
                    <span class="source-badge {% if it.source == 'sec_edgar' %}source-badge-edgar{% elif it.source == 'company_ir' %}source-badge-ir{% else %}source-badge-news{% endif %}">
                      {{ it.source_label }}
                    </span>
                    {% if it.form_or_type %}
                    <span class="form-type-pill">{{ it.form_or_type }}</span>
                    {% endif %}
                    <span class="category-badge">{{ it.category }}</span>
                  </div>
                  <span class="date-cell">{{ it.published_date }}</span>
                </div>

                <div class="company-feed-title">{{ it.clean_headline }}</div>

                {% if it.cross_references_list %}
                  {% if it.cross_references_list|length == 1 %}
                    {% set ref = it.cross_references_list[0] %}
                    <div class="crossref-badges-wrap" style="margin-bottom:0.45rem;">
                      <span class="crossref-badge" title="{{ ref.impact_note }}">
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/></svg>
                        <span class="crossref-rel-pill {% if ref.relation_type == 'Customer' %}crossref-customer{% else %}crossref-supplier{% endif %}">{{ ref.relation_type }}</span>
                        <a href="company.html?ticker={{ ref.related_ticker }}" onclick="event.preventDefault(); switchCompany('{{ ref.related_ticker }}')" class="ticker-badge" style="font-size:0.65rem; padding:0.05rem 0.35rem;">{{ ref.related_ticker }}</a>
                        ({{ ref.matched_entity }})
                      </span>
                    </div>
                  {% else %}
                    <div class="crossref-badges-wrap" style="margin-bottom:0.45rem;">
                      <details class="crossref-accordion">
                        <summary class="crossref-summary-pill">
                          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/></svg>
                          Also relevant to {{ it.cross_references_list|length }} companies <span class="accordion-arrow">▾</span>
                        </summary>
                        <div class="crossref-dropdown-content">
                          {% for ref in it.cross_references_list %}
                          <div class="crossref-dropdown-item" title="{{ ref.impact_note }}">
                            <span class="crossref-rel-pill {% if ref.relation_type == 'Customer' %}crossref-customer{% else %}crossref-supplier{% endif %}">{{ ref.relation_type }}</span>
                            <a href="company.html?ticker={{ ref.related_ticker }}" onclick="event.preventDefault(); switchCompany('{{ ref.related_ticker }}')" class="ticker-badge" style="font-size:0.65rem; padding:0.05rem 0.35rem;">{{ ref.related_ticker }}</a>
                            <span style="font-size:0.75rem; color:var(--text-secondary);">{{ ref.impact_note }}</span>
                          </div>
                          {% endfor %}
                        </div>
                      </details>
                    </div>
                  {% endif %}
                {% endif %}

                {% if it.llm_summary %}
                <div class="why-matters-box" style="margin-top:0.4rem; margin-bottom:0.5rem;">
                  <span class="why-tag">
                    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M15 14c.2-1 .7-1.7 1.5-2.5 1-.9 1.5-2.2 1.5-3.5A6 6 0 0 0 6 8c0 1 .2 2.2 1.5 3.5.7.7 1.3 1.5 1.5 2.5"/><path d="M9 18h6"/><path d="M10 22h4"/></svg>
                    Takeaway:
                  </span>
                  {{ it.llm_summary }}
                </div>
                {% endif %}

                <p class="summary-text" style="font-size:0.835rem; margin-bottom:0.65rem;">{{ it.summary }}</p>

                <div style="display:flex; justify-content:flex-end;">
                  <a href="{{ it.url }}" target="_blank" rel="noopener noreferrer" class="action-link" style="font-size:0.78rem;">
                    {% if it.source == 'sec_edgar' %}View SEC Filing ↗{% elif it.source == 'company_ir' %}View Press Release ↗{% else %}Read Full Article ↗{% endif %}
                  </a>
                </div>
              </div>
              {% endfor %}
            {% else %}
              <div class="company-feed-item" style="text-align:center; padding:2.5rem 1rem; color:var(--text-muted);">
                <div style="margin-bottom:0.5rem; color:var(--text-muted);"><svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75"><path d="M4 22h16a2 2 0 0 0 2-2V4a2 2 0 0 0-2-2H8a2 2 0 0 0-2 2v16a2 2 0 0 1-2 2Zm0 0a2 2 0 0 1-2-2v-9c0-1.1.9-2 2-2h2"/><path d="M18 14h-8"/><path d="M15 18h-5"/><path d="M10 6h8v4h-8V6Z"/></svg></div>
                <div style="font-weight:700; color:var(--text-primary);">No Recent Disclosures Found</div>
                <div style="font-size:0.82rem; margin-top:0.25rem;">No filings, company releases, or news media recorded in this period for {{ co.symbol }}.</div>
              </div>
            {% endif %}
          </div>

          <!-- Right Sidebar Column: Calendar, Sensitivities, Supply Chain -->
          <div class="company-side-deck">
            
            <!-- Box 1: Upcoming Corporate Calendar -->
            <div class="company-side-box">
              <div class="company-side-title">
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect width="18" height="18" x="3" y="4" rx="2" ry="2"/><line x1="16" x2="16" y1="2" y2="6"/><line x1="8" x2="8" y1="2" y2="6"/><line x1="3" x2="21" y1="10" y2="10"/></svg>
                Forthcoming Calendar ({{ co_events|length }})
              </div>

              {% if co_events %}
                <div style="display:flex; flex-direction:column; gap:0.65rem;">
                  {% for ev in co_events %}
                  <div style="display:flex; align-items:flex-start; gap:0.75rem; padding:0.6rem 0.75rem; background:var(--bg-base); border-radius:var(--radius-md); border:1px solid var(--border-card);">
                    <div class="calendar-date-box" style="width:42px; min-width:42px; padding:0.18rem 0.35rem;">
                      <div class="calendar-date-month" style="font-size:0.6rem;">{{ ev.event_date[5:7] | replace('01','JAN') | replace('02','FEB') | replace('03','MAR') | replace('04','APR') | replace('05','MAY') | replace('06','JUN') | replace('07','JUL') | replace('08','AUG') | replace('09','SEP') | replace('10','OCT') | replace('11','NOV') | replace('12','DEC') }}</div>
                      <div class="calendar-date-day" style="font-size:1.05rem;">{{ ev.event_date[8:10] }}</div>
                    </div>
                    <div style="flex:1; min-width:0;">
                      <div style="font-size:0.835rem; font-weight:700; color:var(--text-primary); line-height:1.3;">{{ ev.headline }}</div>
                      <div style="font-size:0.72rem; color:var(--text-muted); margin-top:0.2rem;">{{ ev.relative_badge }} &bull; {{ ev.event_type }}</div>
                    </div>
                  </div>
                  {% endfor %}
                </div>
              {% else %}
                <div style="font-size:0.82rem; color:var(--text-muted); text-align:center; padding:1rem 0;">
                  No scheduled earnings or dividend dates in next 60 days.
                </div>
              {% endif %}
            </div>

            <!-- Box 2: Macroeconomic Sensitivities (FRED) -->
            <div class="company-side-box">
              <div class="company-side-title">
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="20" x2="12" y2="10"/><line x1="18" y1="20" x2="18" y2="4"/><line x1="6" y1="20" x2="6" y2="16"/></svg>
                Macroeconomic Sensitivities
              </div>

              <div style="display:flex; flex-direction:column; gap:0.65rem;">
                {% for ind in economic_indicators %}
                  {% if ind.tickers_list and co.symbol in ind.tickers_list %}
                  <div style="padding:0.65rem 0.85rem; background:var(--bg-base); border:1px solid var(--border-card); border-radius:var(--radius-md);">
                    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:0.25rem;">
                      <span style="font-size:0.82rem; font-weight:700; color:var(--text-primary);">{{ ind.name }}</span>
                      <span style="font-family: var(--font-mono); font-size:0.88rem; font-weight: 600; color:var(--accent-blue);">{{ ind.formatted_value }}</span>
                    </div>
                    <div style="font-size:0.75rem; color:var(--text-secondary); line-height:1.4;">{{ ind.context_note }}</div>
                  </div>
                  {% endif %}
                {% endfor %}
                
                {% if co.macro_sensitivities %}
                <div style="margin-top:0.4rem; padding-top:0.65rem; border-top:1px solid var(--border-card);">
                  <div style="font-size:0.72rem; font-weight:700; color:var(--text-muted); margin-bottom:0.35rem; text-transform:uppercase;">Specific Macro Factors</div>
                  <div style="display:flex; flex-wrap:wrap; gap:0.35rem;">
                    {% for m in co.macro_sensitivities %}
                    <span class="category-badge" style="font-size:0.7rem;">{{ m | replace('_', ' ') | title }}</span>
                    {% endfor %}
                  </div>
                </div>
                {% endif %}
              </div>
            </div>

            <!-- Box 3: Supply Chain & Corporate Ecosystem -->
            <div class="company-side-box">
              <div class="company-side-title">
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/></svg>
                Corporate Ecosystem
              </div>

              <!-- Key Customers -->
              {% if co.key_customers %}
              <div style="margin-bottom:0.85rem;">
                <div style="font-size:0.72rem; font-weight:700; color:var(--pos); text-transform:uppercase; margin-bottom:0.35rem;">Key Customers</div>
                <div style="display:flex; flex-wrap:wrap; gap:0.35rem;">
                  {% for cust in co.key_customers %}
                  <a href="company.html?ticker={{ cust }}" onclick="event.preventDefault(); switchCompany('{{ cust }}')" class="crossref-badge" style="text-decoration:none; cursor:pointer;">
                    <span class="crossref-rel-pill crossref-customer">Customer</span>
                    <strong>{{ cust }}</strong>
                  </a>
                  {% endfor %}
                </div>
              </div>
              {% endif %}

              <!-- Key Suppliers -->
              {% if co.key_suppliers %}
              <div style="margin-bottom:0.85rem;">
                <div style="font-size:0.72rem; font-weight:700; color:var(--accent); text-transform:uppercase; margin-bottom:0.35rem;">Key Suppliers</div>
                <div style="display:flex; flex-wrap:wrap; gap:0.35rem;">
                  {% for supp in co.key_suppliers %}
                  <a href="company.html?ticker={{ supp }}" onclick="event.preventDefault(); switchCompany('{{ supp }}')" class="crossref-badge" style="text-decoration:none; cursor:pointer;">
                    <span class="crossref-rel-pill crossref-supplier">Supplier</span>
                    <strong>{{ supp }}</strong>
                  </a>
                  {% endfor %}
                </div>
              </div>
              {% endif %}

              <!-- Competitors -->
              {% if co.competitors %}
              <div>
                <div style="font-size:0.72rem; font-weight:700; color:var(--warn); text-transform:uppercase; margin-bottom:0.35rem;">Competitors</div>
                <div style="display:flex; flex-wrap:wrap; gap:0.35rem;">
                  {% for comp in co.competitors %}
                  <a href="company.html?ticker={{ comp }}" onclick="event.preventDefault(); switchCompany('{{ comp }}')" class="ticker-badge ticker-{{ comp }}" style="font-size:0.72rem; text-decoration:none; cursor:pointer;">{{ comp }}</a>
                  {% endfor %}
                </div>
              </div>
              {% endif %}
            </div>

          </div>
        </div>
      </div>
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

      const targetColor = 'var(--accent)';
      const compColors = ['#ea580c', '#0284c7', '#9333ea'];
      const spyColor = 'var(--text-muted)';

      // 1. KPI Ribbon
      if (kpiGrid && target) {
        const tgtPct = target.total_pct_change;
        const tgtColor = tgtPct >= 0 ? 'var(--pos)' : 'var(--neg)';
        const tgtArrow = tgtPct >= 0 ? '↗' : '↘';

        const alphaPeers = coData.alpha_vs_peers;
        const alphaPeersColor = alphaPeers >= 0 ? 'var(--pos)' : 'var(--neg)';

        const spyPct = spy ? spy.total_pct_change : 0;
        const avgPeerPct = coData.avg_competitor_pct;

        kpiGrid.innerHTML = `
          <div class="perf-kpi-box">
            <div class="perf-kpi-label">${escapeHtml(symbol)} 3M Return</div>
            <div class="perf-kpi-val" style="color:${tgtColor};">${tgtArrow} ${tgtPct >= 0 ? '+' : ''}${tgtPct.toFixed(2)}%</div>
            <div class="perf-kpi-sub">Latest: $${target.latest_price.toFixed(2)}</div>
          </div>
          <div class="perf-kpi-box">
            <div class="perf-kpi-label">Top Peers Avg</div>
            <div class="perf-kpi-val" style="color:${avgPeerPct >= 0 ? 'var(--pos)' : 'var(--neg)'};">${avgPeerPct >= 0 ? '+' : ''}${avgPeerPct.toFixed(2)}%</div>
            <div class="perf-kpi-sub">${escapeHtml(comps.map(c => c.symbol).join(', ') || 'None')}</div>
          </div>
          <div class="perf-kpi-box">
            <div class="perf-kpi-label">S&P 500 (SPY)</div>
            <div class="perf-kpi-val" style="color:${spyPct >= 0 ? 'var(--pos)' : 'var(--neg)'};">${spyPct >= 0 ? '+' : ''}${spyPct.toFixed(2)}%</div>
            <div class="perf-kpi-sub">Broad Market Benchmark</div>
          </div>
          <div class="perf-kpi-box">
            <div class="perf-kpi-label">Peer Relative Alpha</div>
            <div class="perf-kpi-val" style="color:${alphaPeersColor};">${alphaPeers >= 0 ? '+' : ''}${alphaPeers.toFixed(2)}%</div>
            <div class="perf-kpi-sub" style="font-weight:700; color:${coData.assessment_type === 'positive' ? 'var(--pos)' : (coData.assessment_type === 'negative' ? 'var(--neg)' : 'var(--text-secondary)')};">${escapeHtml(coData.assessment)}</div>
          </div>
        `;
      }

      // 2. Peer Table
      if (table && target) {
        let rowsHtml = `
          <thead>
            <tr>
              <th>Ticker / Entity</th>
              <th>Role</th>
              <th>Base (3M)</th>
              <th>Latest</th>
              <th>3M % Change</th>
              <th>Alpha</th>
            </tr>
          </thead>
          <tbody>
            <tr style="background:var(--accent-soft); font-weight:700;">
              <td><span class="ticker-badge ticker-${escapeHtml(symbol)}">${escapeHtml(symbol)}</span> ${escapeHtml(coData.name)}</td>
              <td><span class="form-type-pill" style="background:var(--accent-soft); color:var(--accent);">Target</span></td>
              <td style="font-family: var(--font-mono);">$${target.base_price.toFixed(2)}</td>
              <td style="font-family: var(--font-mono);">$${target.latest_price.toFixed(2)}</td>
              <td style="font-family: var(--font-mono); color:${target.total_pct_change >= 0 ? 'var(--pos)' : 'var(--neg)'};">${target.total_pct_change >= 0 ? '+' : ''}${target.total_pct_change.toFixed(2)}%</td>
              <td style="font-family: var(--font-mono); color:var(--text-muted);">&mdash;</td>
            </tr>
        `;

        comps.forEach((c, idx) => {
          const delta = (c.total_pct_change - target.total_pct_change).toFixed(2);
          rowsHtml += `
            <tr>
              <td><a href="company.html?ticker=${escapeHtml(c.symbol)}" onclick="event.preventDefault(); switchCompany('${escapeHtml(c.symbol)}')" class="ticker-badge" style="font-size:0.75rem; cursor:pointer;">${escapeHtml(c.symbol)}</a></td>
              <td><span class="form-type-pill">Peer #${idx+1}</span></td>
              <td style="font-family: var(--font-mono);">$${c.base_price.toFixed(2)}</td>
              <td style="font-family: var(--font-mono);">$${c.latest_price.toFixed(2)}</td>
              <td style="font-family: var(--font-mono); color:${c.total_pct_change >= 0 ? 'var(--pos)' : 'var(--neg)'};">${c.total_pct_change >= 0 ? '+' : ''}${c.total_pct_change.toFixed(2)}%</td>
              <td style="font-family: var(--font-mono); color:${delta >= 0 ? 'var(--pos)' : 'var(--neg)'};">${delta >= 0 ? '+' : ''}${delta}%</td>
            </tr>
          `;
        });

        if (spy) {
          const spyDelta = (spy.total_pct_change - target.total_pct_change).toFixed(2);
          rowsHtml += `
            <tr style="border-top:2px dashed var(--border-card);">
              <td><span class="form-type-pill" style="background:var(--bg-surface-elevated); color:var(--text-secondary); font-weight:700;">SPY</span> S&amp;P 500 ETF</td>
              <td><span class="form-type-pill">Benchmark</span></td>
              <td style="font-family: var(--font-mono);">$${spy.base_price.toFixed(2)}</td>
              <td style="font-family: var(--font-mono);">$${spy.latest_price.toFixed(2)}</td>
              <td style="font-family: var(--font-mono); color:${spy.total_pct_change >= 0 ? 'var(--pos)' : 'var(--neg)'};">${spy.total_pct_change >= 0 ? '+' : ''}${spy.total_pct_change.toFixed(2)}%</td>
              <td style="font-family: var(--font-mono); color:${spyDelta >= 0 ? 'var(--pos)' : 'var(--neg)'};">${spyDelta >= 0 ? '+' : ''}${spyDelta}%</td>
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
      const labels = target.series.map(pt => pt.date);

      const datasets = [
        {
          label: `${symbol} (Target)`,
          data: target.series.map(pt => pt.pct_change),
          borderColor: targetColor,
          backgroundColor: 'rgba(37, 99, 235, 0.08)',
          borderWidth: isPhone ? 2.2 : 3,
          fill: true,
          tension: 0.25,
          pointRadius: 0,
          pointHoverRadius: 5,
        }
      ];

      comps.forEach((c, idx) => {
        const color = compColors[idx % compColors.length];
        datasets.push({
          label: `${c.symbol} (Peer)`,
          data: c.series.map(pt => pt.pct_change),
          borderColor: color,
          borderWidth: isPhone ? 1.5 : 2,
          fill: false,
          tension: 0.25,
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
                font: { family: 'Inter', size: isPhone ? 10 : 11, weight: '600' },
                color: '#475569',
                padding: isPhone ? 6 : 10
              }
            },
            tooltip: {
              backgroundColor: '#0f172a',
              titleFont: { family: 'Inter', size: 12, weight: '700' },
              bodyFont: { family: 'JetBrains Mono', size: 11 },
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
                font: { family: 'JetBrains Mono', size: isPhone ? 8.5 : 10 },
                color: '#94a3b8',
                maxRotation: 0
              }
            },
            y: {
              grid: { color: 'rgba(226, 232, 240, 0.8)' },
              ticks: {
                callback: function(val) { return (val >= 0 ? '+' : '') + val + '%'; },
                font: { family: 'JetBrains Mono', size: isPhone ? 8.5 : 10 },
                color: '#94a3b8',
                maxTicksLimit: isPhone ? 4 : 6
              }
            }
          }
        }
      });
    }

    let currentCompanySector = 'ALL';

    function filterCompanySector(secName, btn) {
      currentCompanySector = secName;
      document.querySelectorAll('.company-browser-sec-btn').forEach(b => b.classList.remove('active'));
      if (btn) btn.classList.add('active');

      const q = (document.getElementById('companyStripFilter')?.value || '').toLowerCase().trim();
      applyCompanyCardFilters(q);
    }

    function filterCompanyStrip(rawVal) {
      const q = (rawVal || '').toLowerCase().trim();
      applyCompanyCardFilters(q);
    }

    function applyCompanyCardFilters(q) {
      const pills = document.querySelectorAll('.company-strip-pill');
      pills.forEach(pill => {
        const sym = (pill.getAttribute('data-ticker') || '').toLowerCase();
        const name = (pill.getAttribute('data-name') || '').toLowerCase();
        const sec = (pill.getAttribute('data-sector') || '').toLowerCase();

        const sectorMatch = (currentCompanySector === 'ALL' || sec === currentCompanySector.toLowerCase());
        const textMatch = (!q || sym.includes(q) || name.includes(q) || sec.includes(q));

        if (sectorMatch && textMatch) {
          pill.style.display = 'flex';
        } else {
          pill.style.display = 'none';
        }
      });
    }

    function searchCompanyFeed(ticker, rawVal) {
      const container = document.getElementById('profile-' + ticker);
      if (!container) return;

      const q = (rawVal || '').toLowerCase().trim();
      const activeSourceBtn = container.querySelector('.company-source-filter-btn.active');
      const activeSource = activeSourceBtn ? activeSourceBtn.getAttribute('data-source') || 'ALL' : 'ALL';

      const rows = container.querySelectorAll('.company-news-item');
      rows.forEach(row => {
        const rowSource = row.getAttribute('data-source');
        const sourceMatch = (activeSource === 'ALL' || rowSource === activeSource);
        const text = (row.textContent || '').toLowerCase();
        const textMatch = (!q || text.includes(q));

        if (sourceMatch && textMatch) {
          row.style.display = 'block';
        } else {
          row.style.display = 'none';
        }
      });
    }

    function switchCompany(ticker, pushState = true) {
      const allProfiles = document.querySelectorAll('.company-profile-container');
      allProfiles.forEach(el => el.style.display = 'none');
      
      const target = document.getElementById('profile-' + ticker);
      if (target) {
        target.style.display = 'block';
      } else if (allProfiles.length > 0) {
        allProfiles[0].style.display = 'block';
        ticker = allProfiles[0].getAttribute('data-ticker');
      }

      // Track visit in localStorage for Home page quick access
      trackRecentlyViewedCompany(ticker);

      // Render comparative chart for this company
      renderCompanyComparativeChart(ticker);

      // Update switcher pills
      document.querySelectorAll('.company-strip-pill').forEach(pill => {
        if (pill.getAttribute('data-ticker') === ticker) {
          pill.classList.add('active');
          pill.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'center' });
        } else {
          pill.classList.remove('active');
        }
      });

      // Scroll window to top
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
      const query = (searchInput ? searchInput.value : '').toLowerCase().trim();

      const rows = container.querySelectorAll('.company-news-item');
      rows.forEach(row => {
        const rowSource = row.getAttribute('data-source');
        const sourceMatch = (source === 'ALL' || rowSource === source);
        const text = (row.textContent || '').toLowerCase();
        const textMatch = (!query || text.includes(query));

        if (sourceMatch && textMatch) {
          row.style.display = 'block';
        } else {
          row.style.display = 'none';
        }
      });
    }

    window.addEventListener('popstate', (e) => {
      const params = new URLSearchParams(window.location.search);
      const ticker = params.get('ticker') || 'NVDA';
      switchCompany(ticker, false);
    });

    window.addEventListener('DOMContentLoaded', () => {
      const params = new URLSearchParams(window.location.search);
      const ticker = (params.get('ticker') || 'NVDA').toUpperCase();
      switchCompany(ticker, false);
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


def _script_json(value: Any) -> str:
    """Serialize for a <script> block, so text containing '</script>' cannot end the block."""
    return json.dumps(value).replace("</", "<\\/")


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
        it_copy["macro_sector"] = get_company_macro_sector(it_copy.get("ticker", ""), it_copy.get("category", ""))
        items.append(it_copy)

    enriched_priority = []
    for it in priority_items:
        it_copy = dict(it)
        it_copy["clean_headline"] = format_human_headline(it_copy)
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
        "event_kind": _event_kind,
        "calendar_view": _calendar_view(calendar_events),
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

    # 4. Render and save all 6 pages
    pages = [
        ("index.html", INDEX_TEMPLATE, "home"),
        ("news.html", NEWS_TEMPLATE, "news"),
        ("calendar.html", CALENDAR_TEMPLATE, "calendar"),
        ("economic.html", ECONOMIC_TEMPLATE, "economic"),
        ("company.html", COMPANY_TEMPLATE, "company"),
        ("analytics.html", ANALYTICS_TEMPLATE, "analytics"),
    ]

    for fname, tmpl_str, active_page in pages:
        tmpl = Template(tmpl_str, autoescape=True)
        ctx = dict(common_context)
        ctx["active_page"] = active_page
        rendered = tmpl.render(**ctx)

        out_file = os.path.join(site_dir, fname)
        with open(out_file, "w", encoding="utf-8") as f:
            f.write(rendered)
        logger.info("Rendered page: %s", out_file)

    return primary_output
