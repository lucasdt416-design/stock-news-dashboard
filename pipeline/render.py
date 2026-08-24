"""Multi-page static HTML dashboard generator with responsive mobile architecture (Phase 6).

Mobile & UX Enhancements:
- Responsive Mobile Header with Brand, Quick Ask AI, and slide-over hamburger drawer.
- Floating/Pinned Mobile Bottom Navigation Bar (Home, Feed, Calendar, Macro) with safe-area insets.
- Responsive Chart.js resizing with adaptive font sizes, axis skip rules, and legend positioning on narrow viewports.
- Donut chart viewport clipping protection and stacked mobile legend grid.
- Strict text wrapping (overflow-wrap: anywhere) and smooth horizontal swipe containers for tables at 375px, 390px, 414px viewports.
- Live guessing search autocomplete & helpful empty state.
- Next Catalyst hero badge tracker.

Generates:
1. site/index.html    - Home / Overview: Hero greeting, live search, widget preview cards & rich charts
2. site/news.html     - Full Intelligence Feed: Priority Panel, Filters, Search, Sort & News Table
3. site/calendar.html - Forthcoming Corporate Calendar: Earnings calls, Dividends, Filing Deadlines
4. site/economic.html - Macroeconomic Intelligence: FRED indicators, Live Sensitivity Filtering & Matrix
"""

import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional
import yaml
from jinja2 import Template
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
    raw = item.get("headline", "") or ""
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
# SHARED BASE CSS & RESPONSIVE DESIGN SYSTEM
# ==============================================================================
SHARED_CSS = """
    :root {
      --bg-base: #f8fafc;
      --bg-surface: #ffffff;
      --bg-surface-elevated: #f1f5f9;
      --bg-surface-highlight: #e2e8f0;
      --bg-hover: #f1f5f9;
      --border-subtle: #f1f5f9;
      --border-card: #e2e8f0;
      --border-accent: #2563eb;
      --text-primary: #0f172a;
      --text-secondary: #475569;
      --text-muted: #64748b;
      --accent-blue: #2563eb;
      --accent-orange-dark: #c2410c;
      --accent-orange-main: #ea580c;
      --accent-indigo: #4f46e5;
      --accent-emerald: #10b981;
      --accent-amber: #d97706;
      --accent-purple: #7c3aed;
      --accent-rose: #e11d48;
      --accent-cyan: #0284c7;
      --radius-sm: 6px;
      --radius-md: 10px;
      --radius-lg: 14px;
      --radius-xl: 20px;
      --shadow-sm: 0 1px 2px 0 rgba(0, 0, 0, 0.05);
      --shadow-card: 0 1px 3px 0 rgba(0, 0, 0, 0.07), 0 1px 2px -1px rgba(0, 0, 0, 0.07);
      --shadow-dropdown: 0 12px 30px -4px rgba(0, 0, 0, 0.12), 0 4px 6px -2px rgba(0, 0, 0, 0.05);
      --shadow-modal: 0 25px 50px -12px rgba(0, 0, 0, 0.25);
      --transition-fast: 0.15s ease;
      --transition-normal: 0.25s ease;
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
      color: var(--text-primary);
      font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      min-height: 100vh;
      line-height: 1.5;
      overflow-x: hidden;
      width: 100%;
    }

    /* Layout with Persistent Desktop Sidebar & Mobile Off-Canvas Drawer */
    .app-layout {
      display: flex;
      min-height: 100vh;
      width: 100%;
      position: relative;
    }

    .app-sidebar {
      width: 250px;
      background: var(--bg-surface);
      border-right: 1px solid var(--border-card);
      display: flex;
      flex-direction: column;
      position: fixed;
      top: 0;
      bottom: 0;
      left: 0;
      z-index: 100;
      overflow-y: auto;
      padding: 1.5rem 1.15rem;
      transition: transform var(--transition-normal);
    }

    .app-main {
      flex: 1;
      margin-left: 250px;
      padding: 2rem 3rem 4rem 3rem;
      max-width: 1440px;
      width: calc(100% - 250px);
      min-width: 0; /* Prevents flex children from bursting out */
    }

    /* Mobile Header & Bottom Navigation Bar */
    .mobile-top-header {
      display: none;
      position: sticky;
      top: 0;
      left: 0;
      right: 0;
      z-index: 900;
      background: rgba(255, 255, 255, 0.95);
      backdrop-filter: blur(10px);
      border-bottom: 1px solid var(--border-card);
      padding: 0.65rem 1rem;
      align-items: center;
      justify-content: space-between;
    }

    .mobile-header-left {
      display: flex;
      align-items: center;
      gap: 0.6rem;
      text-decoration: none;
      color: inherit;
    }

    .mobile-header-right {
      display: flex;
      align-items: center;
      gap: 0.5rem;
    }

    .mobile-hamburger-btn {
      width: 36px;
      height: 36px;
      border-radius: var(--radius-md);
      background: var(--bg-surface-elevated);
      border: 1px solid var(--border-card);
      color: var(--text-primary);
      display: flex;
      align-items: center;
      justify-content: center;
      cursor: pointer;
      padding: 0;
    }

    .mobile-drawer-backdrop {
      display: none;
      position: fixed;
      top: 0;
      left: 0;
      right: 0;
      bottom: 0;
      background: rgba(15, 23, 42, 0.45);
      backdrop-filter: blur(3px);
      z-index: 1050;
      opacity: 0;
      transition: opacity var(--transition-normal);
    }

    .mobile-drawer-backdrop.active {
      display: block;
      opacity: 1;
    }

    .mobile-bottom-nav {
      display: none;
      position: fixed;
      bottom: 0;
      left: 0;
      right: 0;
      z-index: 950;
      background: #ffffff;
      border-top: 1px solid var(--border-card);
      padding: 0.4rem 0.25rem calc(0.4rem + env(safe-area-inset-bottom)) 0.25rem;
      box-shadow: 0 -2px 10px rgba(0, 0, 0, 0.05);
      justify-content: space-around;
      align-items: center;
    }

    .mobile-tab-link {
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      gap: 0.15rem;
      padding: 0.25rem 0.65rem;
      color: var(--text-muted);
      text-decoration: none;
      font-size: 0.68rem;
      font-weight: 600;
      border-radius: var(--radius-md);
      transition: all var(--transition-fast);
      flex: 1;
      text-align: center;
    }

    .mobile-tab-link.active {
      color: var(--accent-blue);
      font-weight: 700;
    }

    .mobile-tab-link.active svg {
      stroke: var(--accent-blue);
    }

    .mobile-tab-link svg {
      width: 20px;
      height: 20px;
      stroke-width: 2;
    }

    .sidebar-close-btn {
      display: none;
      background: transparent;
      border: none;
      font-size: 1.35rem;
      color: var(--text-muted);
      cursor: pointer;
      padding: 0.25rem 0.5rem;
      line-height: 1;
    }

    /* Responsive Breakpoints */
    @media (max-width: 1080px) {
      .app-sidebar {
        width: 220px;
        padding: 1.25rem 1rem;
      }
      .app-main {
        margin-left: 220px;
        width: calc(100% - 220px);
        padding: 1.75rem 1.5rem 3rem 1.5rem;
      }
    }

    @media (max-width: 768px) {
      .mobile-top-header {
        display: flex;
      }
      .mobile-bottom-nav {
        display: flex;
      }
      .top-header-bar {
        display: none !important;
      }
      .sidebar-close-btn {
        display: block;
      }
      .app-sidebar {
        position: fixed;
        top: 0;
        bottom: 0;
        left: 0;
        width: 280px;
        z-index: 1100;
        transform: translateX(-100%);
        box-shadow: var(--shadow-modal);
      }
      .app-sidebar.mobile-open {
        transform: translateX(0);
      }
      .app-main {
        margin-left: 0;
        width: 100%;
        padding: 1.25rem 1rem calc(5.5rem + env(safe-area-inset-bottom)) 1rem;
      }
      .hero-container {
        margin: 0.75rem auto 1.75rem auto !important;
      }
      .hero-title {
        font-size: 1.75rem !important;
      }
      .hero-subtext {
        font-size: 0.85rem !important;
        margin-bottom: 1.25rem !important;
      }
      .search-wrapper {
        margin-bottom: 1.75rem !important;
      }
      .quick-widgets-row {
        grid-template-columns: 1fr !important;
        gap: 0.75rem !important;
        margin-bottom: 1.75rem !important;
      }
      .analytics-grid {
        grid-template-columns: 1fr !important;
        gap: 1rem !important;
      }
      .analytics-card {
        padding: 1.1rem !important;
      }
      .priority-section, .controls-panel, .health-section {
        padding: 1.1rem !important;
      }
    }

    /* Top Navigation Bar */
    .top-header-bar {
      display: flex;
      justify-content: flex-end;
      align-items: center;
      gap: 0.75rem;
      margin-bottom: 1.5rem;
    }

    .top-header-btn {
      font-size: 0.82rem;
      font-weight: 600;
      color: var(--text-secondary);
      text-decoration: none;
      display: inline-flex;
      align-items: center;
      gap: 0.4rem;
      padding: 0.45rem 0.85rem;
      border-radius: var(--radius-md);
      background: var(--bg-surface);
      border: 1px solid var(--border-card);
      cursor: pointer;
      transition: all var(--transition-fast);
      box-shadow: var(--shadow-sm);
    }

    .top-header-btn:hover {
      background: var(--bg-surface-elevated);
      color: var(--text-primary);
      border-color: #cbd5e1;
    }

    .top-header-btn.btn-ai {
      color: #4338ca;
      background: #eef2ff;
      border-color: #c7d2fe;
    }

    .top-header-btn.btn-ai:hover {
      background: #e0e7ff;
      border-color: #a5b4fc;
      color: #3730a3;
    }

    /* Sidebar Brand */
    .sidebar-brand {
      display: flex;
      align-items: center;
      gap: 0.75rem;
      padding-bottom: 1.25rem;
      border-bottom: 1px solid var(--border-card);
      margin-bottom: 1.25rem;
      text-decoration: none;
      color: inherit;
    }

    .logo-badge {
      width: 36px;
      height: 36px;
      border-radius: var(--radius-md);
      background: linear-gradient(135deg, #c2410c, #9a3412);
      display: flex;
      align-items: center;
      justify-content: center;
      color: #ffffff;
      box-shadow: 0 2px 8px rgba(194, 65, 12, 0.35);
      flex-shrink: 0;
    }

    .brand-title {
      font-size: 1.05rem;
      font-weight: 800;
      letter-spacing: -0.02em;
      color: var(--text-primary);
      line-height: 1.2;
    }

    .brand-subtitle {
      font-size: 0.68rem;
      color: #c2410c;
      font-weight: 700;
      letter-spacing: 0.05em;
      text-transform: uppercase;
    }

    .nav-section-title {
      font-size: 0.68rem;
      font-weight: 800;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      color: var(--text-muted);
      margin-bottom: 0.5rem;
      padding-left: 0.5rem;
    }

    .sidebar-nav {
      display: flex;
      flex-direction: column;
      gap: 0.25rem;
      flex: 1;
    }

    .nav-link {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 0.65rem 0.85rem;
      border-radius: var(--radius-md);
      color: var(--text-secondary);
      text-decoration: none;
      font-size: 0.88rem;
      font-weight: 600;
      transition: all var(--transition-fast);
    }

    .nav-link:hover {
      background: var(--bg-surface-elevated);
      color: var(--text-primary);
    }

    .nav-link.active {
      background: #eff6ff;
      color: #1d4ed8;
      font-weight: 700;
    }

    .nav-item-left {
      display: flex;
      align-items: center;
      gap: 0.75rem;
    }

    .nav-svg {
      width: 18px;
      height: 18px;
      stroke-width: 2;
      stroke: currentColor;
      flex-shrink: 0;
    }

    .nav-count {
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.72rem;
      font-weight: 700;
      background: var(--bg-surface-elevated);
      color: var(--text-muted);
      padding: 0.15rem 0.45rem;
      border-radius: 999px;
    }

    .nav-link.active .nav-count {
      background: #dbeafe;
      color: #1e40af;
    }

    .sidebar-footer {
      padding-top: 1.25rem;
      border-top: 1px solid var(--border-card);
      margin-top: 1.25rem;
    }

    .sidebar-health-box {
      background: var(--bg-surface-elevated);
      border: 1px solid var(--border-card);
      border-radius: var(--radius-md);
      padding: 0.75rem;
    }

    .pulse-dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      display: inline-block;
    }

    /* Hero Greeting Section */
    .hero-container {
      display: flex;
      flex-direction: column;
      align-items: center;
      text-align: center;
      margin: 1.5rem auto 2.5rem auto;
      max-width: 780px;
      width: 100%;
    }

    .hero-badge {
      display: inline-flex;
      align-items: center;
      gap: 0.45rem;
      background: #ffffff;
      border: 1px solid var(--border-card);
      padding: 0.35rem 0.95rem;
      border-radius: 999px;
      font-size: 0.8rem;
      font-weight: 600;
      color: var(--text-secondary);
      box-shadow: var(--shadow-sm);
      margin-bottom: 1.25rem;
      transition: all var(--transition-fast);
      text-decoration: none;
      max-width: 100%;
      text-align: center;
      word-break: break-word;
      overflow-wrap: anywhere;
    }

    .hero-badge:hover {
      border-color: var(--accent-blue);
      color: var(--accent-blue);
      box-shadow: var(--shadow-card);
      transform: translateY(-1px);
    }

    .hero-title {
      font-size: 2.35rem;
      font-weight: 800;
      letter-spacing: -0.03em;
      color: var(--text-primary);
      margin-bottom: 0.5rem;
      word-break: break-word;
      overflow-wrap: anywhere;
    }

    .hero-subtext {
      font-size: 0.95rem;
      color: var(--text-muted);
      line-height: 1.5;
      margin-bottom: 1.75rem;
      word-break: break-word;
      overflow-wrap: anywhere;
    }

    /* Global Search & Command Bar (⌘K) */
    .search-wrapper {
      position: relative;
      width: 100%;
      max-width: 680px;
      margin: 0 auto 2.5rem auto;
    }

    .search-box {
      display: flex;
      align-items: center;
      background: #ffffff;
      border: 1px solid var(--border-card);
      border-radius: var(--radius-lg);
      padding: 0.75rem 1.15rem;
      box-shadow: 0 2px 10px rgba(0, 0, 0, 0.04);
      transition: all var(--transition-fast);
      cursor: text;
    }

    .search-box:focus-within, .search-box.focused {
      border-color: var(--accent-blue);
      box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.12), 0 4px 15px rgba(0, 0, 0, 0.06);
    }

    .search-icon-wrap {
      display: flex;
      align-items: center;
      color: var(--text-muted);
      margin-right: 0.75rem;
      flex-shrink: 0;
    }

    .search-input {
      flex: 1;
      min-width: 0;
      border: none;
      outline: none;
      background: transparent;
      font-size: 0.92rem;
      font-family: inherit;
      color: var(--text-primary);
    }

    .search-input::placeholder {
      color: #94a3b8;
    }

    .search-shortcut {
      display: inline-flex;
      align-items: center;
      gap: 0.2rem;
      background: var(--bg-surface-elevated);
      border: 1px solid var(--border-card);
      border-radius: 4px;
      padding: 0.15rem 0.45rem;
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.7rem;
      font-weight: 700;
      color: var(--text-muted);
      flex-shrink: 0;
    }

    /* Tab Suggestions & Live Autocomplete Dropdown */
    .search-dropdown {
      position: absolute;
      top: calc(100% + 8px);
      left: 0;
      right: 0;
      background: #ffffff;
      border: 1px solid var(--border-card);
      border-radius: var(--radius-lg);
      box-shadow: var(--shadow-dropdown);
      padding: 1rem;
      z-index: 200;
      display: none;
      max-height: 400px;
      overflow-y: auto;
    }

    .search-dropdown.active {
      display: block;
      animation: fadeIn 0.15s ease-out;
    }

    @keyframes fadeIn {
      from { opacity: 0; transform: translateY(-4px); }
      to { opacity: 1; transform: translateY(0); }
    }

    .dropdown-section-title {
      font-size: 0.7rem;
      font-weight: 800;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      color: var(--text-muted);
      margin-bottom: 0.5rem;
      padding-left: 0.25rem;
    }

    .dropdown-tabs-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 0.5rem;
      margin-bottom: 1rem;
    }

    .dropdown-tab-card {
      display: flex;
      align-items: center;
      gap: 0.75rem;
      padding: 0.65rem 0.85rem;
      background: var(--bg-base);
      border: 1px solid var(--border-card);
      border-radius: var(--radius-md);
      text-decoration: none;
      color: var(--text-primary);
      transition: all var(--transition-fast);
      min-width: 0;
    }

    .dropdown-tab-card:hover {
      background: #eff6ff;
      border-color: #bfdbfe;
      transform: translateY(-1px);
    }

    .dropdown-tab-icon {
      width: 22px;
      height: 22px;
      color: var(--accent-blue);
      display: flex;
      align-items: center;
      justify-content: center;
      flex-shrink: 0;
    }

    .dropdown-tab-title {
      font-size: 0.85rem;
      font-weight: 700;
      color: var(--text-primary);
      line-height: 1.2;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    .dropdown-tab-sub {
      font-size: 0.72rem;
      color: var(--text-muted);
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    .dropdown-tickers-wrap {
      padding-top: 0.75rem;
      border-top: 1px solid var(--border-card);
    }

    .dropdown-tickers-list {
      display: flex;
      flex-wrap: wrap;
      gap: 0.35rem;
      margin-top: 0.35rem;
    }

    .ticker-jump-pill {
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.75rem;
      font-weight: 700;
      padding: 0.2rem 0.55rem;
      border-radius: 4px;
      background: var(--bg-surface-elevated);
      border: 1px solid var(--border-card);
      color: var(--text-secondary);
      text-decoration: none;
      transition: all var(--transition-fast);
    }

    .ticker-jump-pill:hover {
      background: #eff6ff;
      border-color: #93c5fd;
      color: #1d4ed8;
    }

    /* Live Search Results List */
    .search-results-list {
      display: flex;
      flex-direction: column;
      gap: 0.4rem;
    }

    .search-result-item {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 0.75rem;
      padding: 0.65rem 0.85rem;
      border-radius: var(--radius-md);
      background: var(--bg-base);
      border: 1px solid var(--border-card);
      text-decoration: none;
      color: var(--text-primary);
      transition: all var(--transition-fast);
      min-width: 0;
    }

    .search-result-item:hover {
      background: #eff6ff;
      border-color: #bfdbfe;
      transform: translateY(-1px);
    }

    .search-result-left {
      display: flex;
      align-items: center;
      gap: 0.65rem;
      min-width: 0;
      flex: 1;
    }

    .search-result-icon {
      width: 20px;
      height: 20px;
      color: var(--accent-blue);
      flex-shrink: 0;
      display: flex;
      align-items: center;
      justify-content: center;
    }

    .search-result-title {
      font-size: 0.85rem;
      font-weight: 700;
      color: var(--text-primary);
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    .search-result-sub {
      font-size: 0.72rem;
      color: var(--text-secondary);
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    .search-no-results {
      text-align: center;
      padding: 1.75rem 1rem;
      color: var(--text-muted);
    }

    .no-results-icon {
      font-size: 1.5rem;
      margin-bottom: 0.35rem;
    }

    .no-results-title {
      font-size: 0.88rem;
      font-weight: 700;
      color: var(--text-primary);
      margin-bottom: 0.25rem;
      word-break: break-word;
    }

    .no-results-sub {
      font-size: 0.75rem;
      color: var(--text-muted);
      word-break: break-word;
    }

    /* Top Quick Preview Widgets Row */
    .quick-widgets-row {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
      gap: 1.25rem;
      margin-bottom: 2.5rem;
    }

    .quick-widget-card {
      background: #ffffff;
      border: 1px solid var(--border-card);
      border-radius: var(--radius-lg);
      padding: 1.25rem;
      box-shadow: var(--shadow-card);
      text-decoration: none;
      color: inherit;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      transition: all var(--transition-fast);
      min-width: 0;
    }

    .quick-widget-card:hover {
      border-color: #cbd5e1;
      box-shadow: 0 4px 15px rgba(0, 0, 0, 0.05);
      transform: translateY(-1px);
    }

    .quick-widget-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 0.75rem;
    }

    .quick-widget-title {
      font-size: 0.88rem;
      font-weight: 700;
      color: var(--text-primary);
      display: flex;
      align-items: center;
      gap: 0.35rem;
    }

    .quick-widget-arrow {
      color: var(--text-muted);
      font-size: 0.9rem;
    }

    .quick-widget-btn {
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 0.45rem;
      background: var(--bg-base);
      border: 1px solid var(--border-card);
      border-radius: var(--radius-md);
      padding: 0.65rem 0.85rem;
      font-size: 0.82rem;
      font-weight: 600;
      color: var(--text-secondary);
      transition: all var(--transition-fast);
      text-align: center;
      word-break: break-word;
    }

    .quick-widget-card:hover .quick-widget-btn {
      background: #eff6ff;
      border-color: #bfdbfe;
      color: #1d4ed8;
    }

    /* Section Headers */
    .section-header-row {
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 0.75rem;
      margin-bottom: 1.25rem;
    }

    .section-heading {
      font-size: 1.25rem;
      font-weight: 800;
      letter-spacing: -0.02em;
      color: var(--text-primary);
      word-break: break-word;
    }

    .section-time-pill {
      display: inline-flex;
      align-items: center;
      gap: 0.4rem;
      background: #ffffff;
      border: 1px solid var(--border-card);
      padding: 0.35rem 0.75rem;
      border-radius: var(--radius-sm);
      font-size: 0.8rem;
      font-weight: 600;
      color: var(--text-secondary);
      max-width: 100%;
      flex-wrap: wrap;
    }

    /* Analytics Grid & Cards */
    .analytics-grid {
      display: grid;
      grid-template-columns: 3fr 2fr;
      gap: 1.25rem;
      margin-bottom: 2.5rem;
    }

    .analytics-card {
      background: #ffffff;
      border: 1px solid var(--border-card);
      border-radius: var(--radius-lg);
      padding: 1.5rem;
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
      margin-bottom: 1rem;
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
      font-family: 'JetBrains Mono', monospace;
      font-size: 1.85rem;
      font-weight: 800;
      color: var(--text-primary);
      display: flex;
      align-items: center;
      gap: 0.5rem;
    }

    .analytics-delta-pill {
      font-size: 0.75rem;
      font-weight: 700;
      color: var(--accent-emerald);
      background: rgba(16, 185, 129, 0.1);
      padding: 0.15rem 0.45rem;
      border-radius: 4px;
    }

    .chart-canvas-container {
      position: relative;
      height: 250px;
      width: 100%;
      min-height: 200px;
    }

    .category-legend-list {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
      gap: 0.45rem;
      margin-top: 1rem;
      padding-top: 0.85rem;
      border-top: 1px solid var(--border-card);
    }

    .category-legend-pill {
      display: inline-flex;
      align-items: center;
      gap: 0.35rem;
      background: var(--bg-surface-elevated);
      border: 1px solid var(--border-card);
      border-radius: 6px;
      padding: 0.3rem 0.5rem;
      font-size: 0.72rem;
      color: var(--text-secondary);
      min-width: 0;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    .category-legend-pill strong {
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    .category-legend-dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      flex-shrink: 0;
    }

    /* Ticker & Form Badges */
    .ticker-badge {
      font-family: 'JetBrains Mono', monospace;
      font-weight: 700;
      font-size: 0.78rem;
      padding: 0.18rem 0.5rem;
      border-radius: 4px;
      display: inline-block;
      letter-spacing: 0.02em;
      background: #f1f5f9;
      color: #334155;
      border: 1px solid #cbd5e1;
      flex-shrink: 0;
    }

    .form-type-pill {
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.68rem;
      font-weight: 700;
      color: var(--text-muted);
      background: var(--bg-surface-elevated);
      padding: 0.12rem 0.45rem;
      border-radius: 4px;
      border: 1px solid var(--border-card);
      display: inline-block;
      flex-shrink: 0;
    }

    .category-badge {
      font-size: 0.72rem;
      font-weight: 700;
      padding: 0.18rem 0.5rem;
      border-radius: var(--radius-sm);
      display: inline-block;
      background: var(--bg-surface-elevated);
      color: var(--text-secondary);
      border: 1px solid var(--border-card);
      white-space: nowrap;
      flex-shrink: 0;
    }

    .source-tag {
      font-size: 0.72rem;
      color: var(--text-muted);
      font-weight: 500;
    }

    /* Score Badges */
    .score-badge {
      font-family: 'JetBrains Mono', monospace;
      font-weight: 800;
      font-size: 0.85rem;
      padding: 0.2rem 0.55rem;
      border-radius: var(--radius-sm);
      display: inline-flex;
      align-items: center;
      gap: 0.2rem;
      flex-shrink: 0;
    }

    .score-high {
      background: #dcfce7;
      color: #15803d;
      border: 1px solid #bbf7d0;
    }

    .score-med {
      background: #fef3c7;
      color: #b45309;
      border: 1px solid #fde68a;
    }

    .score-low {
      background: #f1f5f9;
      color: #64748b;
      border: 1px solid #e2e8f0;
    }

    /* Collapsible Cross-Reference Accordion */
    .crossref-badges-wrap {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 0.35rem;
      margin-top: 0.35rem;
      max-width: 100%;
    }

    .crossref-badge {
      display: inline-flex;
      align-items: center;
      gap: 0.25rem;
      font-size: 0.7rem;
      font-weight: 600;
      padding: 0.15rem 0.45rem;
      border-radius: var(--radius-sm);
      background: #eef2ff;
      color: #4338ca;
      border: 1px solid #c7d2fe;
      max-width: 100%;
      flex-wrap: wrap;
    }

    .crossref-rel-pill {
      font-size: 0.62rem;
      font-weight: 800;
      text-transform: uppercase;
      letter-spacing: 0.04em;
      padding: 0.08rem 0.3rem;
      border-radius: 3px;
    }

    .crossref-customer {
      background: #dcfce7;
      color: #15803d;
      border: 1px solid #86efac;
    }

    .crossref-supplier {
      background: #fef3c7;
      color: #b45309;
      border: 1px solid #fcd34d;
    }

    .crossref-accordion {
      display: inline-block;
      margin-top: 0.2rem;
      max-width: 100%;
    }

    .crossref-summary-pill {
      font-size: 0.72rem;
      font-weight: 700;
      color: #4338ca;
      background: #eef2ff;
      border: 1px solid #c7d2fe;
      border-radius: var(--radius-sm);
      padding: 0.18rem 0.55rem;
      cursor: pointer;
      list-style: none;
      display: inline-flex;
      align-items: center;
      gap: 0.35rem;
      transition: all var(--transition-fast);
      user-select: none;
      max-width: 100%;
      word-break: break-word;
      overflow-wrap: anywhere;
    }

    .crossref-summary-pill::-webkit-details-marker {
      display: none;
    }

    .crossref-summary-pill:hover {
      background: #e0e7ff;
      border-color: #a5b4fc;
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
      margin-top: 0.45rem;
      padding: 0.5rem 0.65rem;
      background: #ffffff;
      border: 1px solid var(--border-card);
      border-radius: var(--radius-sm);
      display: flex;
      flex-direction: column;
      gap: 0.4rem;
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
      word-break: break-word;
      overflow-wrap: anywhere;
    }

    /* Why It Matters Callout Box */
    .why-matters-box {
      margin-top: 0.45rem;
      background: #eff6ff;
      border-left: 3px solid var(--accent-blue);
      padding: 0.5rem 0.75rem;
      border-radius: 0 var(--radius-sm) var(--radius-sm) 0;
      font-size: 0.825rem;
      color: #1e3a8a;
      line-height: 1.45;
      word-break: break-word;
      overflow-wrap: anywhere;
    }

    .why-tag {
      font-weight: 700;
      color: #1d4ed8;
      font-size: 0.75rem;
      text-transform: uppercase;
      letter-spacing: 0.03em;
      display: inline-flex;
      align-items: center;
      gap: 0.25rem;
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
      transition: color var(--transition-fast);
      white-space: nowrap;
    }

    .action-link:hover {
      color: #1d4ed8;
      text-decoration: underline;
    }

    /* Primary Button */
    .btn-primary {
      background: var(--accent-blue);
      color: #ffffff;
      padding: 0.55rem 1.15rem;
      border-radius: var(--radius-md);
      font-weight: 600;
      font-size: 0.85rem;
      text-decoration: none;
      display: inline-flex;
      align-items: center;
      gap: 0.4rem;
      border: none;
      cursor: pointer;
      transition: all var(--transition-fast);
      box-shadow: var(--shadow-sm);
      white-space: nowrap;
    }

    .btn-primary:hover {
      background: #1d4ed8;
      box-shadow: var(--shadow-card);
    }

    /* Filter Controls */
    .controls-panel {
      background: #ffffff;
      border: 1px solid var(--border-card);
      border-radius: var(--radius-lg);
      padding: 1.35rem;
      margin-bottom: 1.75rem;
      box-shadow: var(--shadow-card);
      min-width: 0;
    }

    .filter-row {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 0.45rem;
      margin-bottom: 0.85rem;
    }

    .filter-row:last-child {
      margin-bottom: 0;
    }

    .filter-label {
      font-size: 0.75rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: var(--text-muted);
      min-width: 65px;
    }

    .filter-btn {
      background: var(--bg-surface-elevated);
      border: 1px solid var(--border-card);
      color: var(--text-secondary);
      font-size: 0.78rem;
      font-weight: 600;
      padding: 0.35rem 0.65rem;
      border-radius: var(--radius-sm);
      cursor: pointer;
      transition: all var(--transition-fast);
      display: inline-flex;
      align-items: center;
      gap: 0.35rem;
      white-space: nowrap;
    }

    .filter-btn:hover {
      background: #e2e8f0;
      color: var(--text-primary);
    }

    .filter-btn.active {
      background: var(--accent-blue);
      color: #ffffff;
      border-color: var(--accent-blue);
    }

    .pill-count {
      font-size: 0.7rem;
      opacity: 0.85;
      font-family: 'JetBrains Mono', monospace;
    }

    /* Table Styles */
    .table-container {
      background: #ffffff;
      border: 1px solid var(--border-card);
      border-radius: var(--radius-lg);
      overflow-x: auto;
      -webkit-overflow-scrolling: touch;
      box-shadow: var(--shadow-card);
      width: 100%;
    }

    table {
      width: 100%;
      min-width: 680px; /* Allows smooth horizontal swipe on mobile */
      border-collapse: collapse;
      text-align: left;
      font-size: 0.875rem;
    }

    th {
      background: #f8fafc;
      color: var(--text-muted);
      font-size: 0.75rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      padding: 0.85rem 1rem;
      border-bottom: 1px solid var(--border-card);
      white-space: nowrap;
    }

    td {
      padding: 1.1rem 1rem;
      border-bottom: 1px solid var(--border-card);
      vertical-align: top;
    }

    tr.news-row:hover td {
      background: #f8fafc;
    }

    .headline-text {
      font-weight: 700;
      color: var(--text-primary);
      margin-bottom: 0.25rem;
      font-size: 0.95rem;
      line-height: 1.35;
      word-break: break-word;
      overflow-wrap: anywhere;
    }

    .summary-text {
      color: var(--text-secondary);
      font-size: 0.825rem;
      line-height: 1.45;
      margin-top: 0.35rem;
      word-break: break-word;
      overflow-wrap: anywhere;
    }

    .date-cell {
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.78rem;
      color: var(--text-muted);
      white-space: nowrap;
    }

    /* Priority Section & Grid */
    .priority-section {
      background: #ffffff;
      border: 1px solid var(--border-card);
      border-radius: var(--radius-lg);
      padding: 1.75rem;
      margin-bottom: 2.25rem;
      box-shadow: var(--shadow-card);
      min-width: 0;
    }

    .priority-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 0.75rem;
      margin-bottom: 1.5rem;
      padding-bottom: 1rem;
      border-bottom: 1px solid var(--border-card);
    }

    .priority-title-wrap {
      display: flex;
      align-items: center;
      gap: 0.75rem;
    }

    .priority-badge-icon {
      background: #fef3c7;
      color: #b45309;
      border: 1px solid #fde68a;
      padding: 0.3rem 0.65rem;
      border-radius: var(--radius-sm);
      font-size: 0.75rem;
      font-weight: 800;
      letter-spacing: 0.05em;
      display: inline-flex;
      align-items: center;
      gap: 0.3rem;
      flex-shrink: 0;
    }

    .priority-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
      gap: 1.25rem;
    }

    .priority-card {
      background: #f8fafc;
      border: 1px solid var(--border-card);
      border-radius: var(--radius-md);
      padding: 1.35rem;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      transition: all var(--transition-fast);
      min-width: 0;
    }

    .priority-card:hover {
      transform: translateY(-1px);
      border-color: #cbd5e1;
      box-shadow: var(--shadow-card);
      background: #ffffff;
    }

    .priority-card-top {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 0.75rem;
      gap: 0.5rem;
      flex-wrap: wrap;
    }

    .priority-rank-pill {
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.72rem;
      font-weight: 800;
      color: var(--text-muted);
      background: #ffffff;
      padding: 0.15rem 0.45rem;
      border-radius: 4px;
      border: 1px solid var(--border-card);
    }

    .priority-score-pill {
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.82rem;
      font-weight: 800;
      color: #15803d;
      background: #dcfce7;
      border: 1px solid #bbf7d0;
      padding: 0.2rem 0.55rem;
      border-radius: 4px;
      flex-shrink: 0;
    }

    .priority-card-headline {
      font-size: 0.98rem;
      font-weight: 700;
      color: var(--text-primary);
      margin: 0.5rem 0;
      line-height: 1.35;
      word-break: break-word;
      overflow-wrap: anywhere;
    }

    .priority-card-summary {
      font-size: 0.8rem;
      color: var(--text-secondary);
      line-height: 1.4;
      word-break: break-word;
      overflow-wrap: anywhere;
    }

    .priority-card-footer {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding-top: 0.85rem;
      border-top: 1px solid var(--border-card);
      margin-top: 1rem;
      gap: 0.5rem;
      flex-wrap: wrap;
    }

    /* Forthcoming Corporate Calendar Grid */
    .calendar-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
      gap: 1.25rem;
    }

    .calendar-card {
      background: #ffffff;
      border: 1px solid var(--border-card);
      border-radius: var(--radius-md);
      padding: 1.35rem;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      transition: all var(--transition-fast);
      box-shadow: var(--shadow-sm);
      min-width: 0;
    }

    .calendar-card:hover {
      transform: translateY(-1px);
      border-color: #cbd5e1;
      box-shadow: var(--shadow-card);
    }

    .calendar-card-estimated {
      border: 1px dashed #cbd5e1;
      background: #f8fafc;
    }

    .calendar-card-top {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      margin-bottom: 0.85rem;
      gap: 0.5rem;
    }

    .calendar-origin-badge {
      font-size: 0.62rem;
      font-weight: 800;
      padding: 0.15rem 0.4rem;
      border-radius: 4px;
      letter-spacing: 0.04em;
    }

    .origin-sourced {
      background: #dcfce7;
      color: #15803d;
      border: 1px solid #bbf7d0;
    }

    .origin-estimated {
      background: #f1f5f9;
      color: #475569;
      border: 1px solid #cbd5e1;
    }

    .calendar-type-pill {
      font-size: 0.72rem;
      font-weight: 700;
      padding: 0.2rem 0.5rem;
      border-radius: 4px;
      display: inline-flex;
      align-items: center;
      gap: 0.3rem;
      width: fit-content;
    }

    .cal-type-earnings   { background: #eff6ff; color: #1d4ed8; border: 1px solid #bfdbfe; }
    .cal-type-dividend   { background: #dcfce7; color: #15803d; border: 1px solid #bbf7d0; }
    .cal-type-sec        { background: #f3e8ff; color: #7e22ce; border: 1px solid #e9d5ff; }
    .cal-type-conference { background: #fef3c7; color: #b45309; border: 1px solid #fde68a; }

    .calendar-date-box {
      background: #f8fafc;
      border: 1px solid var(--border-card);
      border-radius: var(--radius-md);
      padding: 0.4rem 0.65rem;
      text-align: center;
      min-width: 54px;
      flex-shrink: 0;
    }

    .calendar-date-month {
      font-size: 0.65rem;
      font-weight: 800;
      color: var(--accent-blue);
      text-transform: uppercase;
    }

    .calendar-date-day {
      font-family: 'JetBrains Mono', monospace;
      font-size: 1.35rem;
      font-weight: 800;
      color: var(--text-primary);
      line-height: 1.1;
    }

    .calendar-card-headline {
      font-size: 0.95rem;
      font-weight: 700;
      color: var(--text-primary);
      margin: 0.4rem 0;
      line-height: 1.35;
      word-break: break-word;
      overflow-wrap: anywhere;
    }

    .calendar-card-details {
      font-size: 0.8rem;
      color: var(--text-secondary);
      margin: 0 0 1rem 0;
      line-height: 1.45;
      word-break: break-word;
      overflow-wrap: anywhere;
    }

    .calendar-card-bottom {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding-top: 0.75rem;
      border-top: 1px solid var(--border-card);
      gap: 0.5rem;
      flex-wrap: wrap;
    }

    .relative-badge {
      font-size: 0.75rem;
      font-weight: 600;
      color: var(--text-muted);
      display: inline-flex;
      align-items: center;
      gap: 0.25rem;
    }

    /* Macroeconomic Intelligence Grid & Cards */
    .economic-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
      gap: 1.25rem;
    }

    .economic-card {
      background: #ffffff;
      border: 1px solid var(--border-card);
      border-radius: var(--radius-md);
      padding: 1.35rem;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      transition: all var(--transition-fast);
      box-shadow: var(--shadow-sm);
      min-width: 0;
    }

    .economic-card:hover {
      transform: translateY(-1px);
      border-color: #cbd5e1;
      box-shadow: var(--shadow-card);
    }

    .economic-card-top {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      margin-bottom: 0.85rem;
      gap: 0.5rem;
      flex-wrap: wrap;
    }

    .economic-category-badge {
      font-size: 0.65rem;
      font-weight: 800;
      letter-spacing: 0.06em;
      text-transform: uppercase;
      color: var(--text-muted);
      background: var(--bg-surface-elevated);
      padding: 0.2rem 0.5rem;
      border-radius: 4px;
      border: 1px solid var(--border-card);
    }

    .economic-trend-badge {
      font-size: 0.72rem;
      font-weight: 700;
      padding: 0.2rem 0.55rem;
      border-radius: 4px;
      display: inline-flex;
      align-items: center;
      gap: 0.25rem;
    }

    .trend-up   { background: #fee2e2; color: #b91c1c; border: 1px solid #fecaca; }
    .trend-down { background: #dcfce7; color: #15803d; border: 1px solid #bbf7d0; }
    .trend-flat { background: #f1f5f9; color: #475569; border: 1px solid #cbd5e1; }

    .economic-val {
      font-family: 'JetBrains Mono', monospace;
      font-size: 1.95rem;
      font-weight: 800;
      color: var(--text-primary);
      line-height: 1;
      margin-bottom: 0.4rem;
    }

    .economic-series-name {
      font-size: 1rem;
      font-weight: 700;
      color: var(--text-primary);
      margin: 0 0 0.35rem 0;
      word-break: break-word;
      overflow-wrap: anywhere;
    }

    .economic-context {
      font-size: 0.8rem;
      color: var(--text-secondary);
      line-height: 1.45;
      margin-bottom: 1rem;
      word-break: break-word;
      overflow-wrap: anywhere;
    }

    .economic-tickers-wrap {
      border-top: 1px solid var(--border-card);
      padding-top: 0.85rem;
      display: flex;
      flex-direction: column;
      gap: 0.4rem;
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

    /* Health Section */
    .health-section {
      background: #ffffff;
      border: 1px solid var(--border-card);
      border-radius: var(--radius-lg);
      padding: 1.75rem;
      box-shadow: var(--shadow-card);
      margin-top: 2.5rem;
      min-width: 0;
    }

    .health-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 0.75rem;
      padding-bottom: 1.25rem;
      border-bottom: 1px solid var(--border-card);
      margin-bottom: 1.5rem;
    }

    .health-title-group {
      display: flex;
      align-items: center;
      gap: 0.85rem;
      flex-wrap: wrap;
    }

    .health-title {
      font-size: 1.15rem;
      font-weight: 800;
      color: var(--text-primary);
    }

    .health-status-badge {
      font-size: 0.75rem;
      font-weight: 800;
      letter-spacing: 0.05em;
      text-transform: uppercase;
      padding: 0.25rem 0.65rem;
      border-radius: 999px;
      display: inline-flex;
      align-items: center;
      gap: 0.4rem;
    }

    .health-badge-healthy  { background: #dcfce7; color: #15803d; border: 1px solid #86efac; }
    .health-badge-warning  { background: #fef3c7; color: #b45309; border: 1px solid #fde68a; }
    .health-badge-critical { background: #fee2e2; color: #b91c1c; border: 1px solid #fca5a5; }

    .health-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
      gap: 1rem;
      margin-bottom: 1.5rem;
    }

    .health-metric-card {
      background: var(--bg-base);
      border: 1px solid var(--border-card);
      border-radius: var(--radius-md);
      padding: 1.1rem;
      min-width: 0;
    }

    .health-metric-title {
      font-size: 0.72rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: var(--text-muted);
      margin-bottom: 0.35rem;
    }

    .health-metric-val {
      font-family: 'JetBrains Mono', monospace;
      font-size: 1.5rem;
      font-weight: 800;
      color: var(--text-primary);
      line-height: 1.1;
      margin-bottom: 0.25rem;
    }

    .health-metric-sub {
      font-size: 0.72rem;
      color: var(--text-secondary);
    }

    /* Ask AI Assistant Interactive Modal */
    .ai-modal-backdrop {
      position: fixed;
      top: 0;
      left: 0;
      right: 0;
      bottom: 0;
      background: rgba(15, 23, 42, 0.5);
      backdrop-filter: blur(4px);
      z-index: 2000;
      display: none;
      align-items: center;
      justify-content: center;
      padding: 1rem;
    }

    .ai-modal-backdrop.active {
      display: flex;
      animation: fadeIn 0.15s ease-out;
    }

    .ai-modal-card {
      background: #ffffff;
      border: 1px solid var(--border-card);
      border-radius: var(--radius-xl);
      box-shadow: var(--shadow-modal);
      width: 100%;
      max-width: 620px;
      max-height: 90vh;
      display: flex;
      flex-direction: column;
      overflow: hidden;
    }

    .ai-modal-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 1rem 1.25rem;
      border-bottom: 1px solid var(--border-card);
    }

    .ai-modal-icon-badge {
      width: 32px;
      height: 32px;
      border-radius: 8px;
      background: #eef2ff;
      color: #4338ca;
      display: flex;
      align-items: center;
      justify-content: center;
      flex-shrink: 0;
    }

    .ai-modal-close {
      background: transparent;
      border: none;
      font-size: 1.35rem;
      color: var(--text-muted);
      cursor: pointer;
      padding: 0.25rem;
      border-radius: 4px;
      line-height: 1;
    }

    .ai-modal-close:hover {
      color: var(--text-primary);
      background: var(--bg-surface-elevated);
    }

    .ai-modal-body {
      padding: 1.25rem;
      overflow-y: auto;
      display: flex;
      flex-direction: column;
      gap: 0.85rem;
    }

    .ai-input-wrap {
      display: flex;
      gap: 0.5rem;
      background: var(--bg-base);
      border: 1px solid var(--border-card);
      border-radius: var(--radius-md);
      padding: 0.35rem;
    }

    .ai-input-wrap input {
      flex: 1;
      min-width: 0;
      border: none;
      outline: none;
      background: transparent;
      padding: 0.4rem 0.65rem;
      font-size: 0.9rem;
      font-family: inherit;
      color: var(--text-primary);
    }

    .ai-chips-wrap {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 0.35rem;
    }

    .ai-chip {
      font-size: 0.75rem;
      font-weight: 600;
      color: var(--text-secondary);
      background: var(--bg-surface-elevated);
      border: 1px solid var(--border-card);
      border-radius: 999px;
      padding: 0.2rem 0.65rem;
      cursor: pointer;
      transition: all var(--transition-fast);
      white-space: nowrap;
    }

    .ai-chip:hover {
      background: #eff6ff;
      border-color: #bfdbfe;
      color: #1d4ed8;
    }

    .ai-results-container {
      border: 1px solid var(--border-card);
      border-radius: var(--radius-md);
      background: var(--bg-base);
      max-height: 280px;
      overflow-y: auto;
      padding: 0.75rem;
    }
"""

# ==============================================================================
# RESPONSIVE NAVIGATION MACROS (SIDEBAR + MOBILE HEADER + MOBILE BOTTOM NAV)
# ==============================================================================
NAVIGATION_LAYOUT_HTML = """
<!-- Mobile Sticky Top Header -->
<div class="mobile-top-header">
  <a href="index.html" class="mobile-header-left">
    <div class="logo-badge" style="width:30px; height:30px;">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
        <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>
      </svg>
    </div>
    <span style="font-size:0.95rem; font-weight:800; color:var(--text-primary);">StockPulse</span>
  </a>
  <div class="mobile-header-right">
    <button class="top-header-btn btn-ai" style="padding:0.35rem 0.65rem; font-size:0.75rem;" onclick="openAiModal()">
      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m12 3-1.9 5.8a2 2 0 0 1-1.3 1.3L3 12l5.8 1.9a2 2 0 0 1 1.3 1.3L12 21l1.9-5.8a2 2 0 0 1 1.3-1.3L21 12l-5.8-1.9a2 2 0 0 1-1.3-1.3Z"/></svg>
      Ask AI
    </button>
    <button class="mobile-hamburger-btn" onclick="toggleMobileNav()" aria-label="Toggle navigation drawer">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="18" x2="21" y2="18"/></svg>
    </button>
  </div>
</div>

<!-- Backdrop Overlay for Mobile Drawer -->
<div class="mobile-drawer-backdrop" id="mobileBackdrop" onclick="closeMobileNav()"></div>

<!-- Slide-over Drawer / Desktop Sidebar -->
<aside class="app-sidebar" id="appSidebar">
  <div style="display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid var(--border-card); padding-bottom:1.25rem; margin-bottom:1.25rem;">
    <a href="index.html" class="sidebar-brand" style="border-bottom:none; margin-bottom:0; padding-bottom:0;">
      <div class="logo-badge">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
          <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>
        </svg>
      </div>
      <div>
        <div class="brand-title">StockPulse</div>
        <div class="brand-subtitle">Cloud Intelligence</div>
      </div>
    </a>
    <button class="sidebar-close-btn" onclick="closeMobileNav()" aria-label="Close navigation">&times;</button>
  </div>

  <div class="nav-section-title">Navigation</div>
  <nav class="sidebar-nav">
    <a href="index.html" class="nav-link {% if active_page == 'home' %}active{% endif %}" onclick="closeMobileNav()">
      <div class="nav-item-left">
        <svg class="nav-svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m3 9 9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg>
        <span class="nav-text">Home</span>
      </div>
    </a>
    <a href="news.html" class="nav-link {% if active_page == 'news' %}active{% endif %}" onclick="closeMobileNav()">
      <div class="nav-item-left">
        <svg class="nav-svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 22h16a2 2 0 0 0 2-2V4a2 2 0 0 0-2-2H8a2 2 0 0 0-2 2v16a2 2 0 0 1-2 2Zm0 0a2 2 0 0 1-2-2v-9c0-1.1.9-2 2-2h2"/><path d="M18 14h-8"/><path d="M15 18h-5"/><path d="M10 6h8v4h-8V6Z"/></svg>
        <span class="nav-text">Intelligence Feed</span>
      </div>
      <span class="nav-count">{{ stats.total }}</span>
    </a>
    <a href="calendar.html" class="nav-link {% if active_page == 'calendar' %}active{% endif %}" onclick="closeMobileNav()">
      <div class="nav-item-left">
        <svg class="nav-svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect width="18" height="18" x="3" y="4" rx="2" ry="2"/><line x1="16" x2="16" y1="2" y2="6"/><line x1="8" x2="8" y1="2" y2="6"/><line x1="3" x2="21" y1="10" y2="10"/></svg>
        <span class="nav-text">Corporate Calendar</span>
      </div>
      <span class="nav-count">{{ calendar_events|length }}</span>
    </a>
    <a href="economic.html" class="nav-link {% if active_page == 'economic' %}active{% endif %}" onclick="closeMobileNav()">
      <div class="nav-item-left">
        <svg class="nav-svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="20" x2="12" y2="10"/><line x1="18" y1="20" x2="18" y2="4"/><line x1="6" y1="20" x2="6" y2="16"/></svg>
        <span class="nav-text">Economic Snapshot</span>
      </div>
      <span class="nav-count">{{ economic_indicators|length }}</span>
    </a>
    <a href="index.html#analyticsSection" class="nav-link" onclick="closeMobileNav()">
      <div class="nav-item-left">
        <svg class="nav-svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/></svg>
        <span class="nav-text">Analytics &amp; Health</span>
      </div>
    </a>
  </nav>

  <div class="sidebar-footer">
    <div class="sidebar-health-box">
      <div style="display:flex; align-items:center; gap:0.45rem; margin-bottom:0.25rem;">
        <span class="pulse-dot" style="background:#10b981;"></span>
        <span style="font-size:0.75rem; font-weight:700; color:#15803d;">ALL SYSTEMS HEALTHY</span>
      </div>
      <div style="font-size:0.68rem; color:var(--text-muted); line-height:1.4;">
        15 Watchlist Companies<br>
        Updated: {{ generated_at }}
      </div>
    </div>
  </div>
</aside>

<!-- Mobile Bottom Navigation Bar -->
<div class="mobile-bottom-nav">
  <a href="index.html" class="mobile-tab-link {% if active_page == 'home' %}active{% endif %}">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><path d="m3 9 9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg>
    <span>Home</span>
  </a>
  <a href="news.html" class="mobile-tab-link {% if active_page == 'news' %}active{% endif %}">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><path d="M4 22h16a2 2 0 0 0 2-2V4a2 2 0 0 0-2-2H8a2 2 0 0 0-2 2v16a2 2 0 0 1-2 2Zm0 0a2 2 0 0 1-2-2v-9c0-1.1.9-2 2-2h2"/><path d="M18 14h-8"/><path d="M15 18h-5"/><path d="M10 6h8v4h-8V6Z"/></svg>
    <span>Feed</span>
  </a>
  <a href="calendar.html" class="mobile-tab-link {% if active_page == 'calendar' %}active{% endif %}">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><rect width="18" height="18" x="3" y="4" rx="2" ry="2"/><line x1="16" x2="16" y1="2" y2="6"/><line x1="8" x2="8" y1="2" y2="6"/><line x1="3" x2="21" y1="10" y2="10"/></svg>
    <span>Calendar</span>
  </a>
  <a href="economic.html" class="mobile-tab-link {% if active_page == 'economic' %}active{% endif %}">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><line x1="12" y1="20" x2="12" y2="10"/><line x1="18" y1="20" x2="18" y2="4"/><line x1="6" y1="20" x2="6" y2="16"/></svg>
    <span>Macro</span>
  </a>
</div>
"""

# JavaScript for Mobile Drawer
SHARED_MOBILE_JS = """
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
"""

# ==============================================================================
# 1. HOME / OVERVIEW TEMPLATE (site/index.html)
# ==============================================================================
INDEX_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=5.0">
  <meta name="description" content="Personal stock news dashboard overview with widget preview cards, rich disclosure trends, and instant search suggestions.">
  <title>StockPulse — What's on the agenda?</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600;700&display=swap" rel="stylesheet">
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.7/dist/chart.umd.min.js"></script>
  <style>
""" + SHARED_CSS + """
  </style>
</head>
<body>
  <div class="app-layout">
    """ + NAVIGATION_LAYOUT_HTML + """

    <main class="app-main">
      <!-- Top Right Bar for Desktop -->
      <div class="top-header-bar">
        <button class="top-header-btn btn-ai" onclick="openAiModal()">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m12 3-1.9 5.8a2 2 0 0 1-1.3 1.3L3 12l5.8 1.9a2 2 0 0 1 1.3 1.3L12 21l1.9-5.8a2 2 0 0 1 1.3-1.3L21 12l-5.8-1.9a2 2 0 0 1-1.3-1.3Z"/></svg>
          Ask AI
        </button>
        <a href="#analyticsSection" class="top-header-btn">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/></svg>
          Analytics
        </a>
        <span class="section-time-pill" style="font-size:0.75rem; padding:0.25rem 0.6rem;">
          <span class="pulse-dot" style="background:#10b981;"></span> Live
        </span>
      </div>

      <!-- Hero Greeting Section -->
      <div class="hero-container">
        <a href="calendar.html" class="hero-badge">
          <span class="pulse-dot" style="background:#10b981; margin-right:0.2rem; flex-shrink:0;"></span>
          {% if calendar_events %}
          ⚡ Next Catalyst: <strong>{{ calendar_events[0].ticker }}</strong> ({{ calendar_events[0].display_date }}) &bull; {{ priority_items|length }} Priority Disclosures ↗
          {% else %}
          ⚡ <strong>{{ priority_items|length }} Priority Disclosures Active</strong> &bull; 15 Companies Monitored ↗
          {% endif %}
        </a>
        <h1 class="hero-title">What's on the agenda?</h1>
        <p class="hero-subtext">Review overnight SEC filings, company announcements, corporate calendar dates, and FRED macroeconomic sensitivities.</p>
      </div>

      <!-- Global Search & Command Bar (⌘K) with Tab Suggestions & Live Autocomplete -->
      <div class="search-wrapper">
        <div class="search-box" id="globalSearchBox">
          <span class="search-icon-wrap">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></svg>
          </span>
          <input type="text" id="globalSearchInput" class="search-input" placeholder="Search disclosures, tickers, calendar events, FRED..." onfocus="openSearchDropdown()" oninput="handleSearchType(this.value)">
          <span class="search-shortcut">⌘ K</span>
        </div>

        <!-- Interactive Live Suggestions / Autocomplete Dropdown -->
        <div class="search-dropdown" id="searchDropdown">
          <div id="defaultDropdownContent">
            <div class="dropdown-section-title">Suggested Pages &amp; Views</div>
            <div class="dropdown-tabs-grid">
              <a href="news.html" class="dropdown-tab-card">
                <div class="dropdown-tab-icon">
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 22h16a2 2 0 0 0 2-2V4a2 2 0 0 0-2-2H8a2 2 0 0 0-2 2v16a2 2 0 0 1-2 2Zm0 0a2 2 0 0 1-2-2v-9c0-1.1.9-2 2-2h2"/><path d="M18 14h-8"/><path d="M15 18h-5"/><path d="M10 6h8v4h-8V6Z"/></svg>
                </div>
                <div>
                  <div class="dropdown-tab-title">Intelligence Feed</div>
                  <div class="dropdown-tab-sub">{{ stats.total }} Scored Disclosures</div>
                </div>
              </a>
              <a href="calendar.html" class="dropdown-tab-card">
                <div class="dropdown-tab-icon">
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect width="18" height="18" x="3" y="4" rx="2" ry="2"/><line x1="16" x2="16" y1="2" y2="6"/><line x1="8" x2="8" y1="2" y2="6"/><line x1="3" x2="21" y1="10" y2="10"/></svg>
                </div>
                <div>
                  <div class="dropdown-tab-title">Corporate Calendar</div>
                  <div class="dropdown-tab-sub">{{ calendar_events|length }} Upcoming Events</div>
                </div>
              </a>
              <a href="economic.html" class="dropdown-tab-card">
                <div class="dropdown-tab-icon">
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="20" x2="12" y2="10"/><line x1="18" y1="20" x2="18" y2="4"/><line x1="6" y1="20" x2="6" y2="16"/></svg>
                </div>
                <div>
                  <div class="dropdown-tab-title">Economic Snapshot</div>
                  <div class="dropdown-tab-sub">{{ economic_indicators|length }} FRED Indicators</div>
                </div>
              </a>
              <a href="#analyticsSection" class="dropdown-tab-card" onclick="closeSearchDropdown()">
                <div class="dropdown-tab-icon">
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/></svg>
                </div>
                <div>
                  <div class="dropdown-tab-title">Analytics &amp; Trends</div>
                  <div class="dropdown-tab-sub">Metrics &amp; Safeguards</div>
                </div>
              </a>
            </div>

            <div class="dropdown-tickers-wrap">
              <div class="dropdown-section-title">Jump to Watchlist Ticker</div>
              <div class="dropdown-tickers-list">
                {% for sym in ['NVDA', 'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'TSLA', 'JPM', 'JNJ', 'XOM', 'WMT', 'DIS', 'KO', 'PFE', 'BA'] %}
                <a href="news.html?ticker={{ sym }}" class="ticker-jump-pill">{{ sym }}</a>
                {% endfor %}
              </div>
            </div>
          </div>

          <!-- Dynamic Live Search Results Container -->
          <div id="liveSearchResults" style="display:none;"></div>
        </div>
      </div>

      <!-- Top Quick Preview Widgets Row -->
      <div class="quick-widgets-row">
        <a href="news.html" class="quick-widget-card">
          <div class="quick-widget-header">
            <span class="quick-widget-title">Priority Intelligence ›</span>
            <span class="quick-widget-arrow">›</span>
          </div>
          <div class="quick-widget-btn">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>
            {{ priority_items|length }} High-Impact Disclosures
          </div>
        </a>

        <a href="calendar.html" class="quick-widget-card">
          <div class="quick-widget-header">
            <span class="quick-widget-title">Upcoming Dates ›</span>
            <span class="quick-widget-arrow">›</span>
          </div>
          <div class="quick-widget-btn">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect width="18" height="18" x="3" y="4" rx="2" ry="2"/><line x1="16" x2="16" y1="2" y2="6"/><line x1="8" x2="8" y1="2" y2="6"/><line x1="3" x2="21" y1="10" y2="10"/></svg>
            {% if calendar_events %}Next: {{ calendar_events[0].ticker }} ({{ calendar_events[0].display_date }}){% else %}14 Scheduled Events{% endif %}
          </div>
        </a>

        <a href="economic.html" class="quick-widget-card">
          <div class="quick-widget-header">
            <span class="quick-widget-title">Macroeconomic Pulse ›</span>
            <span class="quick-widget-arrow">›</span>
          </div>
          <div class="quick-widget-btn">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="20" x2="12" y2="10"/><line x1="18" y1="20" x2="18" y2="4"/><line x1="6" y1="20" x2="6" y2="16"/></svg>
            Fed Funds: 3.75% &bull; CPI: 3.4%
          </div>
        </a>
      </div>

      <!-- Analytics Section -->
      <div id="analyticsSection" class="section-header-row" style="padding-top:1rem;">
        <h2 class="section-heading">Analytics &amp; Trends</h2>
        <div style="display:flex; align-items:center; gap:0.5rem;">
          <span class="section-time-pill">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect width="18" height="18" x="3" y="4" rx="2" ry="2"/><line x1="16" x2="16" y1="2" y2="6"/><line x1="8" x2="8" y1="2" y2="6"/><line x1="3" x2="21" y1="10" y2="10"/></svg>
            Last 24 hours
          </span>
          <button class="section-time-pill" onclick="window.location.reload()" style="cursor:pointer; border:1px solid var(--border-card);">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12a9 9 0 0 0-9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/><path d="M3 12a9 9 0 0 0 9 9 9.75 9.75 0 0 0 6.74-2.74L21 16"/><path d="M16 21h5v-5"/></svg>
          </button>
        </div>
      </div>

      <div class="analytics-grid">
        <!-- Metric Card 1: Rich Disclosure Trend Graph with Gradients -->
        <div class="analytics-card">
          <div>
            <div class="analytics-card-header">
              <div>
                <div class="analytics-card-title">Daily Filing &amp; Intelligence Velocity</div>
                <div class="analytics-metric-val">
                  {{ stats.total }} <span class="analytics-delta-pill">↗ 100.0%</span>
                </div>
              </div>
              <span class="section-time-pill" style="font-size:0.75rem;">15 Core Tickers</span>
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
            <div class="chart-canvas-container" style="height: 190px;">
              <canvas id="categoryChart"></canvas>
            </div>
          </div>
          
          <div class="category-legend-list" id="categoryLegendList">
            <!-- Dynamically populated legend badges with counts & percentages -->
          </div>
        </div>
      </div>

      <!-- Health Section -->
      <section class="health-section" id="health">
        <div class="health-header">
          <div class="health-title-group">
            <h3 class="health-title">Pipeline Health &amp; Safeguards</h3>
            <span class="health-status-badge health-badge-healthy">
              <span class="pulse-dot" style="background:#10b981;"></span>
              HEALTHY &bull; OPERATIONAL
            </span>
          </div>
          <div style="font-size:0.75rem; color:var(--text-muted);">
            Moving Avg Baseline: {{ latest_run.moving_avg_raw if latest_run else 570 }} items/run
          </div>
        </div>

        <div class="health-grid">
          <div class="health-metric-card">
            <div class="health-metric-title">SEC EDGAR Filings</div>
            <div class="health-metric-val" style="color:#15803d;">{{ latest_run.edgar_count if latest_run else 450 }}</div>
            <div class="health-metric-sub">15 companies queried</div>
          </div>
          <div class="health-metric-card">
            <div class="health-metric-title">Company IR Releases</div>
            <div class="health-metric-val" style="color:var(--accent-blue);">{{ latest_run.company_ir_count if latest_run else 100 }}</div>
            <div class="health-metric-sub">Official press room feeds</div>
          </div>
          <div class="health-metric-card">
            <div class="health-metric-title">Total Unique Yield</div>
            <div class="health-metric-val" style="color:#7c3aed;">{{ latest_run.total_unique if latest_run else stats.total }}</div>
            <div class="health-metric-sub">After deduplication</div>
          </div>
          <div class="health-metric-card">
            <div class="health-metric-title">High Priority Stories</div>
            <div class="health-metric-val" style="color:#b45309;">{{ latest_run.high_impact_count if latest_run else stats.high_priority_count }}</div>
            <div class="health-metric-sub">Score ≥ 7.0 / 10.0</div>
          </div>
        </div>
      </section>
    </main>
  </div>

  <!-- Ask AI Assistant Interactive Modal -->
  <div class="ai-modal-backdrop" id="aiModal" onclick="closeAiModal(event)">
    <div class="ai-modal-card" onclick="event.stopPropagation()">
      <div class="ai-modal-header">
        <div style="display:flex; align-items:center; gap:0.65rem;">
          <div class="ai-modal-icon-badge">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m12 3-1.9 5.8a2 2 0 0 1-1.3 1.3L3 12l5.8 1.9a2 2 0 0 1 1.3 1.3L12 21l1.9-5.8a2 2 0 0 1 1.3-1.3L21 12l-5.8-1.9a2 2 0 0 1-1.3-1.3Z"/></svg>
          </div>
          <div>
            <h3 style="font-size:1.05rem; font-weight:800; color:var(--text-primary);">StockPulse AI Assistant</h3>
            <p style="font-size:0.75rem; color:var(--text-muted);">Query corporate disclosures, executive takeaways &amp; macroeconomic sensitivities</p>
          </div>
        </div>
        <button class="ai-modal-close" onclick="closeAiModal()">&times;</button>
      </div>

      <div class="ai-modal-body">
        <div class="ai-input-wrap">
          <input type="text" id="aiQueryInput" placeholder="Ask e.g. 'What did NVIDIA disclose?', 'Interest rate sensitivity'..." onkeydown="handleAiKeydown(event)">
          <button class="btn-primary" style="padding:0.45rem 0.9rem;" onclick="runAiQuery()">Ask</button>
        </div>

        <div class="ai-chips-wrap">
          <span style="font-size:0.72rem; font-weight:700; color:var(--text-muted); text-transform:uppercase;">Quick Queries:</span>
          <button class="ai-chip" onclick="setAiQuery('NVIDIA latest disclosures')">NVIDIA Disclosures</button>
          <button class="ai-chip" onclick="setAiQuery('Interest rates sensitivity')">Interest Rate Sensitivities</button>
          <button class="ai-chip" onclick="setAiQuery('Upcoming earnings')">Upcoming Earnings</button>
          <button class="ai-chip" onclick="setAiQuery('Insider executive trades')">Insider Trades</button>
        </div>

        <div class="ai-results-container" id="aiResults">
          <div style="text-align:center; padding:1.5rem; color:var(--text-muted); font-size:0.85rem;">
            Ask any question about current filings, company events, or macroeconomic sensitivities.
          </div>
        </div>
      </div>
    </div>
  </div>

  <script>
    """ + SHARED_MOBILE_JS + """

    const allItems = {{ items|tojson|safe }};
    const calendarEvents = {{ calendar_events|tojson|safe }};
    const econIndicators = {{ economic_indicators|tojson|safe }};
    const watchlistCompanies = {{ watchlist_companies|tojson|safe }};

    function openSearchDropdown() {
      const dropdown = document.getElementById('searchDropdown');
      dropdown.classList.add('active');
      document.getElementById('globalSearchBox').classList.add('focused');
    }

    function closeSearchDropdown() {
      const dropdown = document.getElementById('searchDropdown');
      dropdown.classList.remove('active');
      document.getElementById('globalSearchBox').classList.remove('focused');
    }

    // =========================================================================
    // LIVE AUTOCOMPLETE & GUESSING SEARCH ENGINE
    // =========================================================================
    function handleSearchType(rawVal) {
      openSearchDropdown();
      const val = (rawVal || '').toLowerCase().trim();
      const defaultContent = document.getElementById('defaultDropdownContent');
      const liveResults = document.getElementById('liveSearchResults');

      if (!val) {
        defaultContent.style.display = 'block';
        liveResults.style.display = 'none';
        liveResults.innerHTML = '';
        return;
      }

      defaultContent.style.display = 'none';
      liveResults.style.display = 'block';

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

      const totalMatches = matchedCompanies.length + matchedNews.length + matchedCal.length + matchedEcon.length;

      if (totalMatches === 0) {
        liveResults.innerHTML = `
          <div class="search-no-results">
            <div class="no-results-icon">🔍</div>
            <div class="no-results-title">Sorry, what you are searching for cannot be found, try being less specific.</div>
            <div class="no-results-sub">Try searching by company ticker (e.g. <em>NVDA</em>, <em>AAPL</em>), form type (<em>8-K</em>), category, or indicator.</div>
          </div>
        `;
        return;
      }

      let html = '<div class="search-results-list">';

      // Render Company matches
      if (matchedCompanies.length > 0) {
        html += '<div class="dropdown-section-title">Matching Companies</div>';
        matchedCompanies.slice(0, 3).forEach(c => {
          html += `
            <a href="news.html?ticker=${c.symbol}" class="search-result-item">
              <div class="search-result-left">
                <span class="ticker-badge ticker-${c.symbol}">${c.symbol}</span>
                <div>
                  <div class="search-result-title">${c.name}</div>
                  <div class="search-result-sub">${c.sector}</div>
                </div>
              </div>
              <span class="action-link" style="font-size:0.75rem;">View Feed ↗</span>
            </a>
          `;
        });
      }

      // Render Calendar matches
      if (matchedCal.length > 0) {
        html += '<div class="dropdown-section-title" style="margin-top:0.6rem;">Upcoming Corporate Events</div>';
        matchedCal.slice(0, 2).forEach(ev => {
          html += `
            <a href="calendar.html" class="search-result-item">
              <div class="search-result-left">
                <span class="ticker-badge ticker-${ev.ticker}">${ev.ticker}</span>
                <div>
                  <div class="search-result-title">${ev.headline}</div>
                  <div class="search-result-sub">📅 ${ev.display_date} &bull; ${ev.event_type}</div>
                </div>
              </div>
              <span class="action-link" style="font-size:0.75rem;">Calendar ↗</span>
            </a>
          `;
        });
      }

      // Render Macroeconomic matches
      if (matchedEcon.length > 0) {
        html += '<div class="dropdown-section-title" style="margin-top:0.6rem;">Macroeconomic Indicators</div>';
        matchedEcon.slice(0, 2).forEach(ind => {
          html += `
            <a href="economic.html" class="search-result-item">
              <div class="search-result-left">
                <div class="search-result-icon">🏛️</div>
                <div>
                  <div class="search-result-title">${ind.name}: ${ind.formatted_value}</div>
                  <div class="search-result-sub">${ind.category} &bull; Relevant: ${ind.relevant_tickers}</div>
                </div>
              </div>
              <span class="action-link" style="font-size:0.75rem;">Macro ↗</span>
            </a>
          `;
        });
      }

      // Render News matches
      if (matchedNews.length > 0) {
        html += '<div class="dropdown-section-title" style="margin-top:0.6rem;">Disclosures &amp; Intelligence (' + matchedNews.length + ')</div>';
        matchedNews.slice(0, 4).forEach(it => {
          html += `
            <a href="news.html?q=${encodeURIComponent(val)}" class="search-result-item">
              <div class="search-result-left">
                <span class="ticker-badge ticker-${it.ticker}">${it.ticker}</span>
                <div>
                  <div class="search-result-title">${it.clean_headline}</div>
                  <div class="search-result-sub">${it.category} &bull; ${it.published_date} &bull; ★ ${it.score}</div>
                </div>
              </div>
              <span class="action-link" style="font-size:0.75rem;">Feed ↗</span>
            </a>
          `;
        });
      }

      html += '</div>';
      liveResults.innerHTML = html;
    }

    // Modal AI Controls
    function openAiModal() {
      document.getElementById('aiModal').classList.add('active');
      setTimeout(() => document.getElementById('aiQueryInput')?.focus(), 50);
    }

    function closeAiModal(e) {
      if (!e || e.target.id === 'aiModal' || e.target.classList.contains('ai-modal-close')) {
        document.getElementById('aiModal').classList.remove('active');
      }
    }

    function setAiQuery(q) {
      const input = document.getElementById('aiQueryInput');
      if (input) {
        input.value = q;
        runAiQuery();
      }
    }

    function handleAiKeydown(e) {
      if (e.key === 'Enter') {
        runAiQuery();
      }
    }

    function runAiQuery() {
      const q = (document.getElementById('aiQueryInput').value || '').toLowerCase().trim();
      const container = document.getElementById('aiResults');
      if (!q) return;

      let matchedItems = allItems.filter(it => 
        (it.clean_headline || '').toLowerCase().includes(q) ||
        (it.ticker || '').toLowerCase().includes(q) ||
        (it.llm_summary || '').toLowerCase().includes(q) ||
        (it.category || '').toLowerCase().includes(q)
      );

      let matchedEcon = econIndicators.filter(ind =>
        (ind.name || '').toLowerCase().includes(q) ||
        (ind.relevant_tickers || '').toLowerCase().includes(q) ||
        (ind.category || '').toLowerCase().includes(q)
      );

      let matchedCal = calendarEvents.filter(ev =>
        (ev.headline || '').toLowerCase().includes(q) ||
        (ev.ticker || '').toLowerCase().includes(q) ||
        (ev.event_type || '').toLowerCase().includes(q)
      );

      if (matchedItems.length === 0 && matchedEcon.length === 0 && matchedCal.length === 0) {
        container.innerHTML = `<div style="text-align:center; padding:1.25rem; color:var(--text-muted); font-size:0.85rem;">No direct disclosures found for "<strong>${q}</strong>". Try searching for a specific company (e.g. <em>NVDA</em>, <em>AAPL</em>) or category.</div>`;
        return;
      }

      let html = '<div style="display:flex; flex-direction:column; gap:0.65rem;">';
      
      if (matchedEcon.length > 0) {
        html += '<div style="font-size:0.75rem; font-weight:800; color:var(--text-muted); text-transform:uppercase;">Macroeconomic Indicators:</div>';
        matchedEcon.forEach(ind => {
          html += `
            <div style="background:#ffffff; border:1px solid var(--border-card); border-radius:6px; padding:0.65rem;">
              <div style="display:flex; justify-content:space-between; align-items:center;">
                <span style="font-weight:700; font-size:0.85rem;">${ind.name}</span>
                <span style="font-family:'JetBrains Mono'; font-weight:800; color:var(--accent-blue);">${ind.formatted_value}</span>
              </div>
              <div style="font-size:0.78rem; color:var(--text-secondary); margin-top:0.25rem;">${ind.context_note}</div>
            </div>`;
        });
      }

      if (matchedCal.length > 0) {
        html += '<div style="font-size:0.75rem; font-weight:800; color:var(--text-muted); text-transform:uppercase; margin-top:0.35rem;">Upcoming Scheduled Events:</div>';
        matchedCal.slice(0, 3).forEach(ev => {
          html += `
            <div style="background:#ffffff; border:1px solid var(--border-card); border-radius:6px; padding:0.65rem;">
              <div style="display:flex; justify-content:space-between; align-items:center;">
                <span style="font-weight:700; font-size:0.85rem;">[${ev.ticker}] ${ev.headline}</span>
                <span style="font-size:0.72rem; color:var(--accent-blue); font-weight:700;">${ev.display_date}</span>
              </div>
            </div>`;
        });
      }

      if (matchedItems.length > 0) {
        html += '<div style="font-size:0.75rem; font-weight:800; color:var(--text-muted); text-transform:uppercase; margin-top:0.35rem;">Recent Company Disclosures:</div>';
        matchedItems.slice(0, 4).forEach(it => {
          html += `
            <div style="background:#ffffff; border:1px solid var(--border-card); border-radius:6px; padding:0.65rem;">
              <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:0.25rem;">
                <span style="font-family:'JetBrains Mono'; font-weight:700; font-size:0.75rem; background:#f1f5f9; padding:0.1rem 0.35rem; border-radius:3px;">${it.ticker}</span>
                <span style="font-family:'JetBrains Mono'; font-weight:800; font-size:0.75rem; color:#15803d;">★ ${it.score}</span>
              </div>
              <div style="font-size:0.85rem; font-weight:700; color:var(--text-primary); margin-bottom:0.25rem;">${it.clean_headline}</div>
              ${it.llm_summary ? `<div style="font-size:0.78rem; color:#1e3a8a; background:#eff6ff; padding:0.35rem 0.5rem; border-radius:4px;">💡 ${it.llm_summary}</div>` : ''}
              <div style="margin-top:0.4rem; text-align:right;">
                <a href="${it.url}" target="_blank" rel="noopener noreferrer" style="font-size:0.75rem; color:var(--accent-blue); font-weight:600; text-decoration:none;">View Source ↗</a>
              </div>
            </div>`;
        });
      }

      html += '</div>';
      container.innerHTML = html;
    }

    // Click outside search wrapper to close dropdown
    document.addEventListener('click', function(e) {
      const wrapper = document.querySelector('.search-wrapper');
      if (wrapper && !wrapper.contains(e.target)) {
        closeSearchDropdown();
      }
    });

    // Keyboard Shortcuts: ⌘K or Ctrl+K
    document.addEventListener('keydown', function(e) {
      if ((e.metaKey || e.ctrlKey) && (e.key === 'k' || e.key === 'K')) {
        e.preventDefault();
        const input = document.getElementById('globalSearchInput');
        if (input) {
          input.focus();
          openSearchDropdown();
        }
      } else if (e.key === 'Escape') {
        closeSearchDropdown();
        closeAiModal();
        closeMobileNav();
      }
    });

    const searchInput = document.getElementById('globalSearchInput');
    if (searchInput) {
      searchInput.addEventListener('keydown', function(e) {
        if (e.key === 'Enter') {
          e.preventDefault();
          const val = this.value.trim();
          if (val) {
            window.location.href = `news.html?q=${encodeURIComponent(val)}`;
          }
        }
      });
    }

    // =========================================================================
    // RESPONSIVE RICH CHARTS INITIALIZATION
    // =========================================================================
    const chartData = {{ chart_data_json|safe }};
    const isNarrowViewport = window.innerWidth < 640;

    // 1. Line Chart: Multi-Gradient Curve with adaptive ticks and responsive styling
    if (document.getElementById('timelineChart') && chartData.timeline_dates) {
      const canvasEl = document.getElementById('timelineChart');
      const ctxTimeline = canvasEl.getContext('2d');

      const palette = [
        { stroke: '#2563eb', fillTop: 'rgba(37, 99, 235, 0.28)', fillBot: 'rgba(37, 99, 235, 0.0)' },
        { stroke: '#10b981', fillTop: 'rgba(16, 185, 129, 0.22)', fillBot: 'rgba(16, 185, 129, 0.0)' },
        { stroke: '#7c3aed', fillTop: 'rgba(124, 58, 237, 0.20)', fillBot: 'rgba(124, 58, 237, 0.0)' },
        { stroke: '#f59e0b', fillTop: 'rgba(245, 158, 11, 0.20)', fillBot: 'rgba(245, 158, 11, 0.0)' },
      ];

      const presentTickers = Object.keys(chartData.timeline_series || {}).slice(0, 4);
      const datasets = presentTickers.map((ticker, idx) => {
        const theme = palette[idx % palette.length];
        const grad = ctxTimeline.createLinearGradient(0, 0, 0, 220);
        grad.addColorStop(0, theme.fillTop);
        grad.addColorStop(1, theme.fillBot);

        return {
          label: ticker,
          data: chartData.timeline_series[ticker] || [],
          borderColor: theme.stroke,
          backgroundColor: grad,
          fill: true,
          borderWidth: isNarrowViewport ? 2.0 : 2.5,
          tension: 0.38,
          pointBackgroundColor: '#ffffff',
          pointBorderColor: theme.stroke,
          pointBorderWidth: 1.5,
          pointRadius: isNarrowViewport ? 2.5 : 3.5,
          pointHoverRadius: 5,
          pointHoverBackgroundColor: theme.stroke,
          pointHoverBorderColor: '#ffffff',
          pointHoverBorderWidth: 2,
        };
      });

      new Chart(ctxTimeline, {
        type: 'line',
        data: { labels: chartData.timeline_dates, datasets: datasets },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          interaction: {
            mode: 'index',
            intersect: false,
          },
          plugins: {
            legend: {
              position: isNarrowViewport ? 'bottom' : 'top',
              align: isNarrowViewport ? 'center' : 'end',
              labels: {
                boxWidth: 8,
                boxHeight: 8,
                usePointStyle: true,
                pointStyle: 'circle',
                font: { family: 'Inter', size: isNarrowViewport ? 10 : 11, weight: '600' },
                color: '#475569',
                padding: isNarrowViewport ? 8 : 14
              }
            },
            tooltip: {
              backgroundColor: '#0f172a',
              titleColor: '#f8fafc',
              bodyColor: '#e2e8f0',
              padding: 8,
              cornerRadius: 6,
              bodyFont: { family: 'JetBrains Mono', size: 11 },
              titleFont: { family: 'Inter', size: 11, weight: '700' }
            }
          },
          scales: {
            x: {
              grid: { color: 'rgba(226, 232, 240, 0.6)', drawBorder: false },
              ticks: { 
                color: '#64748b', 
                font: { family: 'JetBrains Mono', size: isNarrowViewport ? 9 : 10 },
                maxTicksLimit: isNarrowViewport ? 5 : 8,
                autoSkip: true,
                maxRotation: 0
              }
            },
            y: {
              grid: { color: 'rgba(226, 232, 240, 0.6)', drawBorder: false },
              ticks: { color: '#64748b', font: { family: 'JetBrains Mono', size: isNarrowViewport ? 9 : 10 }, stepSize: 1 },
              beginAtZero: true
            }
          }
        }
      });
    }

    // 2. Donut Chart with Responsive Leader Line Callout Badges & Stacked Legend
    const catLabels = chartData.categories || chartData.category_labels || [];
    const catCounts = chartData.category_counts || [];
    if (document.getElementById('categoryChart') && catLabels.length > 0) {
      const ctxCat = document.getElementById('categoryChart').getContext('2d');
      const sliceColors = ['#2563eb', '#10b981', '#7c3aed', '#f59e0b', '#0284c7'];
      const topLabels = catLabels.slice(0, 5);
      const topCounts = catCounts.slice(0, 5);
      const totalCount = topCounts.reduce((a, b) => a + b, 0);

      // Custom Leader-line & Data Callout Plugin (Adaptive for mobile)
      const donutCalloutPlugin = {
        id: 'donutCallouts',
        afterDraw(chart) {
          if (chart.width < 340) return; // Prevent horizontal canvas clipping on small phones
          const { ctx } = chart;
          const meta = chart.getDatasetMeta(0);
          if (!meta || !meta.data) return;

          ctx.save();
          meta.data.forEach((element, i) => {
            const { x, y, startAngle, endAngle, outerRadius } = element;
            const midAngle = startAngle + (endAngle - startAngle) / 2;
            const val = chart.data.datasets[0].data[i];
            const pct = Math.round((val / totalCount) * 100);
            if (pct < 7) return;

            const r1 = outerRadius + 4;
            const r2 = outerRadius + 12;
            const sx = x + Math.cos(midAngle) * r1;
            const sy = y + Math.sin(midAngle) * r1;
            const ex = x + Math.cos(midAngle) * r2;
            const ey = y + Math.sin(midAngle) * r2;

            const isRight = Math.cos(midAngle) >= 0;
            const endHorizontalX = ex + (isRight ? 10 : -10);

            ctx.beginPath();
            ctx.moveTo(sx, sy);
            ctx.lineTo(ex, ey);
            ctx.lineTo(endHorizontalX, ey);
            ctx.strokeStyle = '#94a3b8';
            ctx.lineWidth = 1.0;
            ctx.stroke();

            ctx.textAlign = isRight ? 'left' : 'right';
            ctx.textBaseline = 'middle';
            ctx.font = 'bold 10px Inter, sans-serif';
            ctx.fillStyle = '#0f172a';
            ctx.fillText(`${pct}%`, endHorizontalX + (isRight ? 3 : -3), ey);
          });
          ctx.restore();
        }
      };

      new Chart(ctxCat, {
        type: 'doughnut',
        data: {
          labels: topLabels,
          datasets: [{
            data: topCounts,
            backgroundColor: sliceColors,
            borderColor: '#ffffff',
            borderWidth: 2.0,
            hoverOffset: 3
          }]
        },
        plugins: [donutCalloutPlugin],
        options: {
          responsive: true,
          maintainAspectRatio: false,
          layout: {
            padding: { top: 10, bottom: 10, left: 15, right: 15 }
          },
          plugins: {
            legend: { display: false },
            tooltip: {
              backgroundColor: '#0f172a',
              titleColor: '#f8fafc',
              bodyColor: '#e2e8f0',
              padding: 8,
              cornerRadius: 6,
              bodyFont: { family: 'JetBrains Mono', size: 11 },
              callbacks: {
                label: function(context) {
                  const val = context.parsed || 0;
                  const pct = ((val / totalCount) * 100).toFixed(1);
                  return ` ${context.label}: ${val} items (${pct}%)`;
                }
              }
            }
          },
          cutout: '60%'
        }
      });

      const legendListEl = document.getElementById('categoryLegendList');
      if (legendListEl) {
        let legendHtml = '';
        topLabels.forEach((label, i) => {
          const count = topCounts[i];
          const pct = ((count / totalCount) * 100).toFixed(1);
          const color = sliceColors[i % sliceColors.length];
          legendHtml += `
            <div class="category-legend-pill">
              <span class="category-legend-dot" style="background:${color};"></span>
              <strong style="color:var(--text-primary);">${label}</strong>
              <span style="font-family:'JetBrains Mono'; font-weight:700; color:var(--text-muted);">${count} (${pct}%)</span>
            </div>
          `;
        });
        legendListEl.innerHTML = legendHtml;
      }
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
  <meta name="description" content="Full intelligence feed of scored stock news and SEC filings with interactive filtering and AI takeaways.">
  <title>StockPulse — Full Intelligence Feed</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600;700&display=swap" rel="stylesheet">
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
          <h1 class="hero-title" style="font-size:1.85rem; text-align:left; margin-bottom:0.25rem;">Full Intelligence Feed</h1>
          <p style="font-size:0.9rem; color:var(--text-muted);">Deduplicated, scored disclosures with transparent arithmetic and supply-chain cross-references</p>
        </div>
        <div style="display:flex; align-items:center; gap:0.5rem;">
          <span class="section-time-pill">
            <span class="pulse-dot" style="background:#10b981;"></span> {{ items|length }} Total Items
          </span>
        </div>
      </header>

      <!-- Priority Panel -->
      {% if priority_items %}
      <section class="priority-section">
        <div class="priority-header">
          <div class="priority-title-wrap">
            <span class="priority-badge-icon">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>
              PRIORITY
            </span>
            <div>
              <h2 style="font-size:1.15rem; font-weight:800; color:var(--text-primary);">Top Impact Disclosures</h2>
              <p style="font-size:0.8rem; color:var(--text-muted);">Top {{ priority_items|length }} highest scored stories with investor takeaways</p>
            </div>
          </div>
          <div style="font-family:'JetBrains Mono', monospace; font-size:0.8rem; color:#15803d; font-weight:700; background:#dcfce7; padding:0.35rem 0.75rem; border-radius:6px; border:1px solid #86efac; width:fit-content;">
            SCORES: {{ priority_items[0].score }} &ndash; {{ priority_items[-1].score }} / 10.0
          </div>
        </div>

        <div class="priority-grid">
          {% for item in priority_items %}
          <div class="priority-card">
            <div>
              <div class="priority-card-top">
                <div style="display:flex; align-items:center; gap:0.45rem; flex-wrap:wrap;">
                  <span class="priority-rank-pill">#{{ loop.index }}</span>
                  <span class="ticker-badge ticker-{{ item.ticker }}">{{ item.ticker }}</span>
                  {% if item.form_or_type %}
                  <span class="form-type-pill">{{ item.form_or_type }}</span>
                  {% endif %}
                </div>
                <span class="priority-score-pill" title="{{ item.score_breakdown }}">
                  ★ {{ item.score }}
                </span>
              </div>

              <div style="margin-top:0.4rem; display:flex; align-items:center; flex-wrap:wrap; gap:0.4rem;">
                <span class="category-badge">{{ item.category }}</span>
                <span class="source-tag">{{ item.source_label }}</span>
              </div>

              <h3 class="priority-card-headline">{{ item.clean_headline }}</h3>
              
              {% if item.cross_references_list %}
                {% if item.cross_references_list|length == 1 %}
                  {% set ref = item.cross_references_list[0] %}
                  <div class="crossref-badges-wrap">
                    <span class="crossref-badge" title="{{ ref.impact_note }}">
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/></svg>
                      <span class="crossref-rel-pill {% if ref.relation_type == 'Customer' %}crossref-customer{% else %}crossref-supplier{% endif %}">{{ ref.relation_type }}</span>
                      <strong class="ticker-badge" style="font-size:0.65rem; padding:0.05rem 0.35rem;">{{ ref.related_ticker }}</strong>
                      ({{ ref.matched_entity }})
                    </span>
                  </div>
                {% else %}
                  <div class="crossref-badges-wrap">
                    <details class="crossref-accordion">
                      <summary class="crossref-summary-pill">
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/></svg>
                        Also relevant to {{ item.cross_references_list|length }} companies <span class="accordion-arrow">▾</span>
                      </summary>
                      <div class="crossref-dropdown-content">
                        {% for ref in item.cross_references_list %}
                        <div class="crossref-dropdown-item" title="{{ ref.impact_note }}">
                          <span class="crossref-rel-pill {% if ref.relation_type == 'Customer' %}crossref-customer{% else %}crossref-supplier{% endif %}">{{ ref.relation_type }}</span>
                          <strong class="ticker-badge" style="font-size:0.65rem; padding:0.05rem 0.35rem;">{{ ref.related_ticker }}</strong>
                          <span style="font-size:0.75rem; color:var(--text-secondary);">${ref.impact_note}</span>
                        </div>
                        {% endfor %}
                      </div>
                    </details>
                  </div>
                {% endif %}
              {% endif %}

              {% if item.llm_summary %}
              <div class="why-matters-box">
                <span class="why-tag">
                  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M15 14c.2-1 .7-1.7 1.5-2.5 1-.9 1.5-2.2 1.5-3.5A6 6 0 0 0 6 8c0 1 .2 2.2 1.5 3.5.7.7 1.3 1.5 1.5 2.5"/><path d="M9 18h6"/><path d="M10 22h4"/></svg>
                  Takeaway:
                </span>
                {{ item.llm_summary }}
              </div>
              {% endif %}

              <p class="priority-card-summary">{{ item.summary[:150] }}{% if item.summary|length > 150 %}...{% endif %}</p>
            </div>

            <div class="priority-card-footer">
              <span class="date-cell">{{ item.published_date }}</span>
              <a href="{{ item.url }}" target="_blank" rel="noopener noreferrer" class="action-link">
                View Source
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" x2="21" y1="14" y2="3"/></svg>
              </a>
            </div>
          </div>
          {% endfor %}
        </div>
      </section>
      {% endif %}

      <!-- Controls & Filters Panel -->
      <div class="controls-panel">
        <div class="filter-row">
          <span class="filter-label">Ticker:</span>
          <button class="filter-btn active" data-filter-type="ticker" data-val="ALL" onclick="setTickerFilter('ALL', this)">
            All Tickers <span class="pill-count">{{ items|length }}</span>
          </button>
          {% for ticker, count in stats.by_ticker.items() %}
          <button class="filter-btn" data-filter-type="ticker" data-val="{{ ticker }}" onclick="setTickerFilter('{{ ticker }}', this)">
            {{ ticker }} <span class="pill-count">{{ count }}</span>
          </button>
          {% endfor %}
        </div>

        <div class="filter-row">
          <span class="filter-label">Category:</span>
          <button class="filter-btn active" data-filter-type="category" data-val="ALL" onclick="setCategoryFilter('ALL', this)">
            All Categories
          </button>
          {% for cat, count in stats.by_category.items() %}
          <button class="filter-btn" data-filter-type="category" data-val="{{ cat }}" onclick="setCategoryFilter('{{ cat }}', this)">
            {{ cat }} <span class="pill-count">{{ count }}</span>
          </button>
          {% endfor %}
        </div>

        <div class="filter-row">
          <span class="filter-label">Source:</span>
          <button class="filter-btn active" data-filter-type="source" data-val="ALL" onclick="setSourceFilter('ALL', this)">
            All Sources
          </button>
          <button class="filter-btn" data-filter-type="source" data-val="sec_edgar" onclick="setSourceFilter('sec_edgar', this)">
            SEC EDGAR
          </button>
          <button class="filter-btn" data-filter-type="source" data-val="company_ir" onclick="setSourceFilter('company_ir', this)">
            Company IR
          </button>
        </div>

        <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:0.75rem; margin-top:1rem; padding-top:1rem; border-top:1px solid var(--border-card);">
          <div style="display:flex; align-items:center; gap:0.4rem; flex-wrap:wrap;">
            <span class="filter-label">Sort:</span>
            <button class="filter-btn active" id="sortScoreBtn" onclick="sortRows('score')">Highest Score</button>
            <button class="filter-btn" id="sortDateBtn" onclick="sortRows('date')">Newest Date</button>
          </div>
          <div style="display:flex; align-items:center; gap:0.5rem; width:100%; max-width:280px;">
            <input type="text" id="searchInput" placeholder="Search headlines, takeaways..." oninput="filterItems()" 
                   style="background:var(--bg-base); border:1px solid var(--border-card); color:var(--text-primary); padding:0.45rem 0.85rem; border-radius:var(--radius-sm); font-size:0.85rem; width:100%;">
          </div>
        </div>
      </div>

      <!-- News Feed Table -->
      <div class="table-container">
        <table>
          <thead>
            <tr>
              <th style="width: 75px;">Score</th>
              <th>Company</th>
              <th>Category &amp; Source</th>
              <th>Date</th>
              <th>Headline, Cross-References &amp; Takeaways</th>
              <th>Source</th>
            </tr>
          </thead>
          <tbody id="newsBody">
            {% for item in items %}
            <tr class="news-row" 
                data-score="{{ item.score }}"
                data-date="{{ item.published_date }}"
                data-ticker="{{ item.ticker }}"
                data-tickers="{{ item.ticker }}{% if item.related_tickers_list %},{{ item.related_tickers_list|join(',') }}{% endif %}"
                data-source="{{ item.source }}" 
                data-category="{{ item.category }}"
                data-text="{{ item.ticker }} {{ item.company_name }} {{ item.category }} {{ item.source_label }} {{ item.form_or_type }} {{ item.clean_headline }} {{ item.headline }} {{ item.cross_ref_summary or '' }} {{ item.llm_summary or '' }} {{ item.summary or '' }}">
              <td>
                <span class="score-badge {% if item.score >= 7.0 %}score-high{% elif item.score >= 4.0 %}score-med{% else %}score-low{% endif %}" title="{{ item.score_breakdown }}">
                  {{ item.score }}
                </span>
              </td>
              <td>
                <div>
                  <span class="ticker-badge ticker-{{ item.ticker }}">{{ item.ticker }}</span>
                  <div class="summary-text" style="margin-top: 0.25rem;">{{ item.company_name }}</div>
                </div>
              </td>
              <td>
                <div>
                  <span class="category-badge">{{ item.category }}</span>
                  <div class="source-tag" style="margin-top: 0.35rem;">
                    {{ item.source_label }}
                  </div>
                </div>
              </td>
              <td class="date-cell">
                {{ item.published_date }}
              </td>
              <td>
                <div class="headline-text">{{ item.clean_headline }}</div>
                
                <div style="display:flex; align-items:center; flex-wrap:wrap; gap:0.4rem; margin-top:0.25rem;">
                  {% if item.form_or_type %}
                  <span class="form-type-pill">{{ item.form_or_type }}</span>
                  {% endif %}
                  
                  {% if item.cross_references_list %}
                    {% if item.cross_references_list|length == 1 %}
                      {% set ref = item.cross_references_list[0] %}
                      <span class="crossref-badge" title="{{ ref.impact_note }}">
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/></svg>
                        <span class="crossref-rel-pill {% if ref.relation_type == 'Customer' %}crossref-customer{% else %}crossref-supplier{% endif %}">{{ ref.relation_type }}</span>
                        <strong class="ticker-badge" style="font-size:0.65rem; padding:0.05rem 0.35rem;">{{ ref.related_ticker }}</strong>
                        ({{ ref.matched_entity }})
                      </span>
                    {% else %}
                      <details class="crossref-accordion">
                        <summary class="crossref-summary-pill">
                          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/></svg>
                          Also relevant to {{ item.cross_references_list|length }} companies <span class="accordion-arrow">▾</span>
                        </summary>
                        <div class="crossref-dropdown-content">
                          {% for ref in item.cross_references_list %}
                          <div class="crossref-dropdown-item" title="{{ ref.impact_note }}">
                            <span class="crossref-rel-pill {% if ref.relation_type == 'Customer' %}crossref-customer{% else %}crossref-supplier{% endif %}">{{ ref.relation_type }}</span>
                            <strong class="ticker-badge" style="font-size:0.65rem; padding:0.05rem 0.35rem;">{{ ref.related_ticker }}</strong>
                            <span style="font-size:0.75rem; color:var(--text-secondary);">{{ ref.impact_note }}</span>
                          </div>
                          {% endfor %}
                        </div>
                      </details>
                    {% endif %}
                  {% endif %}
                </div>

                {% if item.llm_summary %}
                <div class="why-matters-box">
                  <span class="why-tag">
                    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M15 14c.2-1 .7-1.7 1.5-2.5 1-.9 1.5-2.2 1.5-3.5A6 6 0 0 0 6 8c0 1 .2 2.2 1.5 3.5.7.7 1.3 1.5 1.5 2.5"/><path d="M9 18h6"/><path d="M10 22h4"/></svg>
                    Why it matters:
                  </span>
                  {{ item.llm_summary }}
                </div>
                {% endif %}

                <div class="summary-text">{{ item.summary }}</div>
              </td>
              <td>
                <a href="{{ item.url }}" target="_blank" rel="noopener noreferrer" class="action-link">
                  View
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" x2="21" y1="14" y2="3"/></svg>
                </a>
              </td>
            </tr>
            {% endfor %}
          </tbody>
        </table>
        <div id="noResults" style="display:none; padding:2rem; text-align:center; color:var(--text-muted);">
          No intelligence items match your active filter criteria.
        </div>
      </div>
    </main>
  </div>

  <script>
    """ + SHARED_MOBILE_JS + """

    let activeTickerFilter = 'ALL';
    let activeCategoryFilter = 'ALL';
    let activeSourceFilter = 'ALL';

    window.addEventListener('DOMContentLoaded', () => {
      const urlParams = new URLSearchParams(window.location.search);
      const tickerParam = urlParams.get('ticker');
      const qParam = urlParams.get('q');
      if (tickerParam) {
        const btn = document.querySelector(`[data-filter-type="ticker"][data-val="${tickerParam}"]`);
        setTickerFilter(tickerParam, btn);
      }
      if (qParam) {
        const input = document.getElementById('searchInput');
        if (input) {
          input.value = qParam;
          filterItems();
        }
      }
    });

    function setTickerFilter(val, btn) {
      activeTickerFilter = val;
      document.querySelectorAll('[data-filter-type="ticker"]').forEach(b => b.classList.remove('active'));
      if (btn) btn.classList.add('active');
      filterItems();
    }

    function setCategoryFilter(val, btn) {
      activeCategoryFilter = val;
      document.querySelectorAll('[data-filter-type="category"]').forEach(b => b.classList.remove('active'));
      if (btn) btn.classList.add('active');
      filterItems();
    }

    function setSourceFilter(val, btn) {
      activeSourceFilter = val;
      document.querySelectorAll('[data-filter-type="source"]').forEach(b => b.classList.remove('active'));
      if (btn) btn.classList.add('active');
      filterItems();
    }

    function sortRows(criteria) {
      document.getElementById('sortScoreBtn').classList.toggle('active', criteria === 'score');
      document.getElementById('sortDateBtn').classList.toggle('active', criteria === 'date');
      const tbody = document.getElementById('newsBody');
      const rows = Array.from(tbody.querySelectorAll('.news-row'));

      rows.sort((a, b) => {
        if (criteria === 'score') {
          return (parseFloat(b.getAttribute('data-score')) || 0) - (parseFloat(a.getAttribute('data-score')) || 0);
        } else {
          return (b.getAttribute('data-date') || '').localeCompare(a.getAttribute('data-date') || '');
        }
      });
      rows.forEach(r => tbody.appendChild(r));
    }

    function filterItems() {
      const query = (document.getElementById('searchInput').value || '').toLowerCase().trim();
      const rows = document.querySelectorAll('.news-row');
      let visibleCount = 0;

      rows.forEach(row => {
        const rowTicker = row.getAttribute('data-ticker');
        const rowTickers = (row.getAttribute('data-tickers') || rowTicker || '').split(',').map(t => t.trim());
        const rowSource = row.getAttribute('data-source');
        const rowCategory = row.getAttribute('data-category');
        const rowText = (row.getAttribute('data-text') || '').toLowerCase();

        const matchesTicker = (activeTickerFilter === 'ALL' || rowTickers.includes(activeTickerFilter));
        const matchesSource = (activeSourceFilter === 'ALL' || rowSource === activeSourceFilter);
        const matchesCategory = (activeCategoryFilter === 'ALL' || rowCategory === activeCategoryFilter);
        const matchesSearch = (!query || rowText.includes(query));

        if (matchesTicker && matchesSource && matchesCategory && matchesSearch) {
          row.style.display = '';
          visibleCount++;
        } else {
          row.style.display = 'none';
        }
      });

      document.getElementById('noResults').style.display = (visibleCount === 0) ? 'block' : 'none';
    }
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
  <meta name="description" content="Forthcoming corporate calendar showing upcoming earnings dates, dividend ex-dates, and statutory SEC filing deadlines.">
  <title>StockPulse — Forthcoming Corporate Calendar</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600;700&display=swap" rel="stylesheet">
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
          <h1 class="hero-title" style="font-size:1.85rem; text-align:left; margin-bottom:0.25rem;">Corporate Calendar</h1>
          <p style="font-size:0.9rem; color:var(--text-muted);">Upcoming earnings calls, dividend dates, conferences &amp; statutory SEC Form 10-Q/10-K deadlines</p>
        </div>
        <div style="display:flex; align-items:center; gap:0.45rem; flex-wrap:wrap;">
          <span class="calendar-origin-badge origin-sourced">SOURCED</span>
          <span class="calendar-origin-badge origin-estimated">COMPUTED (40D RULE)</span>
        </div>
      </header>

      <!-- Calendar Controls -->
      <div class="controls-panel">
        <div class="filter-row">
          <span class="filter-label">Filter:</span>
          <button class="filter-btn active cal-filter-btn" data-val="ALL" onclick="filterCalendar('ALL', this)">All Events ({{ calendar_events|length }})</button>
          <button class="filter-btn cal-filter-btn" data-val="Earnings" onclick="filterCalendar('Earnings', this)">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 3v18h18"/><path d="m19 9-5 5-4-4-3 3"/></svg>
            Earnings Calls
          </button>
          <button class="filter-btn cal-filter-btn" data-val="Dividend" onclick="filterCalendar('Dividend', this)">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M16 8h-6a2 2 0 1 0 0 4h4a2 2 0 1 1 0 4H8"/><path d="M12 18V6"/></svg>
            Dividend Dates
          </button>
          <button class="filter-btn cal-filter-btn" data-val="SEC" onclick="filterCalendar('SEC', this)">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m16 16 3-8 3 8c-.87.65-1.92 1-3 1s-2.13-.35-3-1Z"/><path d="m2 16 3-8 3 8c-.87.65-1.92 1-3 1s-2.13-.35-3-1Z"/><path d="M7 21h10"/><path d="M12 3v18"/><path d="M3 7h2c2 0 5-1 7-2 2 1 5 2 7 2h2"/></svg>
            SEC Filing Deadlines
          </button>
          <button class="filter-btn cal-filter-btn" data-val="Conference" onclick="filterCalendar('Conference', this)">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/><line x1="12" x2="12" y1="19" y2="22"/></svg>
            Conferences
          </button>
        </div>
      </div>

      <!-- Calendar Grid -->
      <div class="calendar-grid" id="calendarGrid">
        {% for ev in calendar_events %}
        <div class="calendar-card {% if ev.source_type == 'ESTIMATED_RULE' %}calendar-card-estimated{% endif %}"
             data-event-type="{{ ev.event_type }}"
             data-source-type="{{ ev.source_type }}">
          <div>
            <div class="calendar-card-top">
              <div style="display:flex; flex-direction:column; gap:0.35rem;">
                <div style="display:flex; align-items:center; gap:0.4rem; flex-wrap:wrap;">
                  <span class="ticker-badge ticker-{{ ev.ticker }}">{{ ev.ticker }}</span>
                  {% if ev.source_type == 'ESTIMATED_RULE' %}
                  <span class="calendar-origin-badge origin-estimated">COMPUTED (40D RULE)</span>
                  {% else %}
                  <span class="calendar-origin-badge origin-sourced">SOURCED</span>
                  {% endif %}
                </div>
                <span class="calendar-type-pill {% if 'Earnings' in ev.event_type %}cal-type-earnings{% elif 'Dividend' in ev.event_type %}cal-type-dividend{% elif 'SEC' in ev.event_type or 'Statutory' in ev.event_type %}cal-type-sec{% else %}cal-type-conference{% endif %}">
                  {% if 'Earnings' in ev.event_type %}Earnings Call
                  {% elif 'Dividend' in ev.event_type %}Dividend
                  {% elif 'SEC' in ev.event_type or 'Statutory' in ev.event_type %}SEC Deadline (Estimated)
                  {% else %}Conference{% endif %}
                </span>
              </div>
              <div class="calendar-date-box">
                <div class="calendar-date-month">{{ ev.event_date[5:7] | replace('01','JAN') | replace('02','FEB') | replace('03','MAR') | replace('04','APR') | replace('05','MAY') | replace('06','JUN') | replace('07','JUL') | replace('08','AUG') | replace('09','SEP') | replace('10','OCT') | replace('11','NOV') | replace('12','DEC') }}</div>
                <div class="calendar-date-day">{{ ev.event_date[8:10] }}</div>
              </div>
            </div>

            <h4 class="calendar-card-headline">{{ ev.headline }}</h4>
            <p class="calendar-card-details">{{ ev.details }}</p>
          </div>

          <div class="calendar-card-bottom">
            <span class="relative-badge">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
              <strong>{{ ev.relative_badge }}</strong> ({{ ev.display_date }})
            </span>
            {% if ev.source_url %}
            <a href="{{ ev.source_url }}" target="_blank" rel="noopener noreferrer" class="action-link" style="font-size:0.75rem;">
              {% if ev.source_type == 'ESTIMATED_RULE' %}SEC Filings{% else %}Source{% endif %}
              <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" x2="21" y1="14" y2="3"/></svg>
            </a>
            {% endif %}
          </div>
        </div>
        {% endfor %}
      </div>
    </main>
  </div>

  <script>
    """ + SHARED_MOBILE_JS + """

    function filterCalendar(type, btn) {
      document.querySelectorAll('.cal-filter-btn').forEach(b => b.classList.remove('active'));
      if (btn) btn.classList.add('active');

      const cards = document.querySelectorAll('.calendar-card');
      cards.forEach(card => {
        const evType = card.getAttribute('data-event-type') || '';
        if (type === 'ALL') {
          card.style.display = 'flex';
        } else if (type === 'Earnings' && evType.includes('Earnings')) {
          card.style.display = 'flex';
        } else if (type === 'Dividend' && evType.includes('Dividend')) {
          card.style.display = 'flex';
        } else if (type === 'SEC' && (evType.includes('SEC') || evType.includes('Statutory'))) {
          card.style.display = 'flex';
        } else if (type === 'Conference' && evType.includes('Conference')) {
          card.style.display = 'flex';
        } else {
          card.style.display = 'none';
        }
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
  <meta name="description" content="Macroeconomic intelligence panel mapping Federal Reserve (FRED) interest rates, CPI inflation, and unemployment to company sensitivities.">
  <title>StockPulse — Macroeconomic Snapshot &amp; Sensitivities</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600;700&display=swap" rel="stylesheet">
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
          <h1 class="hero-title" style="font-size:1.85rem; text-align:left; margin-bottom:0.25rem;">Macroeconomic Intelligence</h1>
          <p style="font-size:0.9rem; color:var(--text-muted);">Federal Reserve Bank of St. Louis (FRED) live indicators mapped to individual watchlist company sensitivities</p>
        </div>
        <div style="display:flex; align-items:center; gap:0.5rem;">
          <span class="section-time-pill" style="color:var(--accent-blue); font-weight:700;">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="20" x2="12" y2="10"/><line x1="18" y1="20" x2="18" y2="4"/><line x1="6" y1="20" x2="6" y2="16"/></svg>
            St. Louis Fed (FRED) Feed
          </span>
        </div>
      </header>

      <!-- Ticker Filter for Sensitivities -->
      <div class="controls-panel">
        <div class="filter-row">
          <span class="filter-label">Filter Company:</span>
          <button class="filter-btn active econ-filter-btn" data-val="ALL" onclick="filterEconomicByTicker('ALL', this)">All Watchlist Tickers</button>
          {% for sym in ['NVDA', 'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'TSLA', 'JPM', 'JNJ', 'XOM', 'WMT', 'DIS', 'KO', 'PFE', 'BA'] %}
          <button class="filter-btn econ-filter-btn" data-val="{{ sym }}" onclick="filterEconomicByTicker('{{ sym }}', this)">{{ sym }}</button>
          {% endfor %}
        </div>
      </div>

      <!-- Economic Indicator Cards -->
      <div class="economic-grid" id="economicCardsGrid" style="margin-bottom:2.5rem;">
        {% for ind in economic_indicators %}
        <div class="economic-card" 
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

            <div class="economic-val">{{ ind.formatted_value }}</div>
            <h4 class="economic-series-name">{{ ind.name }}</h4>
            <p class="economic-context">{{ ind.context_note }}</p>
          </div>

          <div class="economic-tickers-wrap">
            <div class="economic-tickers-label">Direct Watchlist Sensitivities ({{ ind.tickers_list|length }} Companies):</div>
            <div class="economic-tickers-list">
              {% for sym in ind.tickers_list %}
              <span class="ticker-badge ticker-{{ sym }}">{{ sym }}</span>
              {% endfor %}
            </div>
          </div>
        </div>
        {% endfor %}
      </div>

      <!-- Watchlist Sensitivity Matrix Table -->
      <section style="background:#ffffff; border:1px solid var(--border-card); border-radius:var(--radius-lg); padding:1.75rem; box-shadow:var(--shadow-card);">
        <h3 style="font-size:1.15rem; font-weight:800; color:var(--text-primary); margin-bottom:0.35rem;">Watchlist Sensitivity Matrix</h3>
        <p style="font-size:0.85rem; color:var(--text-secondary); margin-bottom:1.5rem;">Documented sensitivities driving company-specific macroeconomic exposure</p>

        <div class="table-container">
          <table>
            <thead>
              <tr>
                <th>Ticker</th>
                <th>Company Name</th>
                <th>Sector</th>
                <th>Interest Rates Sensitivity</th>
                <th>Inflation Sensitivity</th>
                <th>Unemployment Sensitivity</th>
              </tr>
            </thead>
            <tbody>
              {% for co in watchlist_companies %}
              <tr>
                <td><span class="ticker-badge ticker-{{ co.symbol }}">{{ co.symbol }}</span></td>
                <td style="font-weight:600; color:var(--text-primary);">{{ co.name }}</td>
                <td><span class="category-badge">{{ co.sector }}</span></td>
                <td>
                  {% if 'interest_rates' in co.economic_sensitivities %}
                  <span style="color:#15803d; font-weight:700;">● Active</span>
                  {% else %}
                  <span style="color:var(--text-muted);">&mdash;</span>
                  {% endif %}
                </td>
                <td>
                  {% if 'inflation' in co.economic_sensitivities %}
                  <span style="color:#b45309; font-weight:700;">● Active</span>
                  {% else %}
                  <span style="color:var(--text-muted);">&mdash;</span>
                  {% endif %}
                </td>
                <td>
                  {% if 'unemployment' in co.economic_sensitivities %}
                  <span style="color:#1d4ed8; font-weight:700;">● Active</span>
                  {% else %}
                  <span style="color:var(--text-muted);">&mdash;</span>
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

    function filterEconomicByTicker(ticker, btn) {
      document.querySelectorAll('.econ-filter-btn').forEach(b => b.classList.remove('active'));
      if (btn) btn.classList.add('active');

      const cards = document.querySelectorAll('.economic-card');
      cards.forEach(card => {
        if (ticker === 'ALL') {
          card.style.display = 'flex';
        } else {
          const relTickers = (card.getAttribute('data-relevant-tickers') || '').split(',').map(t => t.trim());
          if (relTickers.includes(ticker)) {
            card.style.display = 'flex';
          } else {
            card.style.display = 'none';
          }
        }
      });
    }
  </script>
</body>
</html>
"""


# ==============================================================================
# RENDER DISPATCHER
# ==============================================================================
def render_dashboard(
    output_path: Optional[str] = None,
    db_path: Optional[str] = None,
) -> str:
    """Render all static site pages (index.html, news.html, calendar.html, economic.html)."""
    if output_path is None:
        site_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "site")
        os.makedirs(site_dir, exist_ok=True)
        primary_output = os.path.join(site_dir, "index.html")
    elif os.path.isdir(output_path):
        site_dir = output_path
        primary_output = os.path.join(site_dir, "index.html")
    else:
        site_dir = os.path.dirname(os.path.abspath(output_path))
        primary_output = output_path

    os.makedirs(site_dir, exist_ok=True)

    # 1. Fetch data from SQLite
    raw_items = get_all_news_items(order_by="score", db_path=db_path)
    priority_items = get_top_priority_items(limit=8, db_path=db_path)
    stats = get_news_stats(db_path=db_path)
    chart_data = get_chart_data(db_path=db_path)
    economic_indicators = get_economic_indicators(db_path=db_path)
    calendar_events = get_forthcoming_calendar(limit=30, db_path=db_path)
    recent_runs = get_recent_pipeline_runs(limit=5, db_path=db_path)
    latest_run = recent_runs[0] if recent_runs else None
    now_str = datetime.now().strftime("%b %d, %Y %H:%M:%S")

    # 2. Enrich items with human-readable headlines
    items = []
    for it in raw_items:
        it_copy = dict(it)
        it_copy["clean_headline"] = format_human_headline(it_copy)
        items.append(it_copy)

    enriched_priority = []
    for it in priority_items:
        it_copy = dict(it)
        it_copy["clean_headline"] = format_human_headline(it_copy)
        enriched_priority.append(it_copy)

    # 3. Load watchlist for sensitivity matrix
    watchlist_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "watchlist.yaml")
    watchlist_companies: List[Dict[str, Any]] = []
    if os.path.exists(watchlist_path):
        with open(watchlist_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
            watchlist_companies = cfg.get("tickers", [])

    common_context = {
        "items": items,
        "priority_items": enriched_priority,
        "stats": stats,
        "chart_data_json": json.dumps(chart_data),
        "economic_indicators": economic_indicators,
        "calendar_events": calendar_events,
        "recent_runs": recent_runs,
        "latest_run": latest_run,
        "generated_at": now_str,
        "watchlist_companies": watchlist_companies,
    }

    # 4. Render and save all 4 pages
    pages = [
        ("index.html", INDEX_TEMPLATE, "home"),
        ("news.html", NEWS_TEMPLATE, "news"),
        ("calendar.html", CALENDAR_TEMPLATE, "calendar"),
        ("economic.html", ECONOMIC_TEMPLATE, "economic"),
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
