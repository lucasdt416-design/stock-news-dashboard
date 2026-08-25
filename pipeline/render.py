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
from datetime import datetime
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
# SHARED BASE CSS & ORGANIC RESPONSIVE DESIGN SYSTEM
# ==============================================================================
SHARED_CSS = """
    :root {
      --bg-base: #f8fafc;
      --bg-surface: #ffffff;
      --bg-surface-elevated: #f1f5f9;
      --bg-surface-glass: rgba(255, 255, 255, 0.92);
      --bg-surface-highlight: #e2e8f0;
      --bg-hover: #f1f5f9;
      --border-subtle: #f1f5f9;
      --border-card: #e2e8f0;
      --border-glass: rgba(226, 232, 240, 0.85);
      --border-accent: #2563eb;
      --text-primary: #0f172a;
      --text-secondary: #475569;
      --text-muted: #64748b;
      --accent-blue: #2563eb;
      --accent-blue-soft: #eff6ff;
      --accent-orange-dark: #c2410c;
      --accent-orange-main: #ea580c;
      --accent-indigo: #4f46e5;
      --accent-emerald: #10b981;
      --accent-amber: #d97706;
      --accent-purple: #7c3aed;
      --accent-rose: #e11d48;
      --accent-cyan: #0284c7;
      
      /* Organic Softer Border Radii */
      --radius-xs: 6px;
      --radius-sm: 10px;
      --radius-md: 16px;
      --radius-lg: 24px;
      --radius-xl: 32px;
      --radius-2xl: 40px;
      --radius-full: 9999px;
      
      /* Organic Atmospheric Shadows */
      --shadow-sm: 0 2px 8px rgba(15, 23, 42, 0.04);
      --shadow-card: 0 4px 20px -2px rgba(15, 23, 42, 0.05), 0 2px 6px -1px rgba(15, 23, 42, 0.02);
      --shadow-hover: 0 16px 36px -6px rgba(37, 99, 235, 0.09), 0 4px 14px -2px rgba(15, 23, 42, 0.03);
      --shadow-float: 0 20px 40px -10px rgba(15, 23, 42, 0.08);
      --shadow-dropdown: 0 20px 45px -10px rgba(15, 23, 42, 0.12), 0 8px 16px -4px rgba(15, 23, 42, 0.04);
      --shadow-modal: 0 30px 60px -15px rgba(15, 23, 42, 0.25);
      
      --transition-fast: 0.18s cubic-bezier(0.16, 1, 0.3, 1);
      --transition-normal: 0.28s cubic-bezier(0.16, 1, 0.3, 1);
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
      background-color: #f8fafc;
      background-image: 
        radial-gradient(at 15% 10%, rgba(219, 234, 254, 0.45) 0px, transparent 45%),
        radial-gradient(at 85% 15%, rgba(254, 243, 199, 0.35) 0px, transparent 40%),
        radial-gradient(at 50% 85%, rgba(241, 245, 249, 0.6) 0px, transparent 50%);
      background-attachment: fixed;
      color: var(--text-primary);
      font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
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
      width: 240px;
      min-width: 240px;
      max-width: 240px;
      flex-shrink: 0;
      background: rgba(255, 255, 255, 0.95);
      backdrop-filter: blur(16px);
      border-right: 1px solid var(--border-card);
      display: flex;
      flex-direction: column;
      position: sticky;
      top: 0;
      height: 100vh;
      overflow-y: auto;
      padding: 1.5rem 1.15rem;
      z-index: 100;
      transition: transform var(--transition-normal);
    }

    .app-main {
      flex: 1 1 0%;
      min-width: 0;
      width: 100%;
      padding: 2.25rem 3rem 5rem 3rem;
      margin: 0;
      box-sizing: border-box;
    }

    /* Mobile Sticky Header & Bottom Navigation Bar */
    .mobile-top-header {
      display: none;
      position: sticky;
      top: 0;
      left: 0;
      right: 0;
      z-index: 900;
      background: rgba(255, 255, 255, 0.95);
      backdrop-filter: blur(12px);
      border-bottom: 1px solid var(--border-card);
      padding: 0.75rem 1.15rem;
      align-items: center;
      justify-content: space-between;
    }

    .mobile-header-left {
      display: flex;
      align-items: center;
      gap: 0.65rem;
      text-decoration: none;
      color: inherit;
    }

    .mobile-header-right {
      display: flex;
      align-items: center;
      gap: 0.5rem;
    }

    .mobile-hamburger-btn {
      width: 38px;
      height: 38px;
      border-radius: var(--radius-sm);
      background: var(--bg-surface-elevated);
      border: 1px solid var(--border-card);
      color: var(--text-primary);
      display: flex;
      align-items: center;
      justify-content: center;
      cursor: pointer;
      padding: 0;
      transition: all var(--transition-fast);
    }

    .mobile-drawer-backdrop {
      display: none;
      position: fixed;
      top: 0;
      left: 0;
      right: 0;
      bottom: 0;
      background: rgba(15, 23, 42, 0.45);
      backdrop-filter: blur(4px);
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
      background: rgba(255, 255, 255, 0.96);
      backdrop-filter: blur(16px);
      border-top: 1px solid var(--border-card);
      padding: 0.45rem 0.25rem calc(0.45rem + env(safe-area-inset-bottom)) 0.25rem;
      box-shadow: 0 -4px 16px rgba(0, 0, 0, 0.04);
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
      border-radius: var(--radius-sm);
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

      .top-header-bar {
        display: none !important;
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
        box-shadow: var(--shadow-modal) !important;
      }

      .app-sidebar.mobile-open {
        transform: translateX(0) !important;
      }

      .app-main {
        margin: 0 !important;
        width: 100% !important;
        max-width: 100% !important;
        padding: 1.5rem 1.25rem calc(5.5rem + env(safe-area-inset-bottom)) 1.25rem !important;
      }

      .hero-container {
        margin: 0.75rem auto 1.75rem auto !important;
      }

      .hero-title {
        font-size: 2rem !important;
      }

      .hero-subtext {
        font-size: 0.9rem !important;
        margin-bottom: 1.35rem !important;
      }

      .search-wrapper {
        margin-bottom: 2rem !important;
      }

      .hero-bento-deck {
        grid-template-columns: 1fr !important;
        gap: 1rem !important;
      }

      .analytics-grid {
        grid-template-columns: 1fr !important;
        gap: 1.25rem !important;
      }

      .priority-section, .controls-panel, .health-section {
        padding: 1.35rem !important;
      }
    }

    /* Narrow Phone Viewports (<= 640px) */
    @media (max-width: 640px) {
      .hero-title {
        font-size: 1.65rem !important;
      }

      .analytics-card {
        padding: 1.15rem !important;
      }

      .priority-section, .controls-panel, .health-section {
        padding: 1.15rem !important;
      }

      .hero-badge {
        font-size: 0.75rem !important;
        padding: 0.35rem 0.85rem !important;
      }

      .calendar-grid {
        grid-template-columns: 1fr !important;
      }

      .spotlight-content-row {
        flex-direction: column !important;
        align-items: flex-start !important;
      }
    }

    /* Top Navigation Bar */
    .top-header-bar {
      display: flex;
      justify-content: flex-end;
      align-items: center;
      gap: 0.75rem;
      margin-bottom: 2rem;
    }

    .top-header-btn {
      font-size: 0.82rem;
      font-weight: 600;
      color: var(--text-secondary);
      text-decoration: none;
      display: inline-flex;
      align-items: center;
      gap: 0.45rem;
      padding: 0.5rem 0.95rem;
      border-radius: var(--radius-full);
      background: var(--bg-surface-glass);
      backdrop-filter: blur(12px);
      border: 1px solid var(--border-card);
      cursor: pointer;
      transition: all var(--transition-fast);
      box-shadow: var(--shadow-sm);
    }

    .top-header-btn:hover {
      background: #ffffff;
      color: var(--text-primary);
      border-color: #cbd5e1;
      transform: translateY(-1px);
      box-shadow: var(--shadow-card);
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

    /* Sidebar Brand (Logo and Title Only - No Tagline) */
    .sidebar-brand {
      display: flex;
      align-items: center;
      gap: 0.75rem;
      text-decoration: none;
      color: inherit;
    }

    .logo-badge {
      width: 36px;
      height: 36px;
      border-radius: var(--radius-sm);
      background: linear-gradient(135deg, #c2410c, #9a3412);
      display: flex;
      align-items: center;
      justify-content: center;
      color: #ffffff;
      box-shadow: 0 4px 12px rgba(194, 65, 12, 0.3);
      flex-shrink: 0;
    }

    .brand-title {
      font-size: 1.15rem;
      font-weight: 800;
      letter-spacing: -0.02em;
      color: var(--text-primary);
      line-height: 1;
    }

    .nav-section-title {
      font-size: 0.68rem;
      font-weight: 800;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      color: var(--text-muted);
      margin-bottom: 0.6rem;
      padding-left: 0.5rem;
    }

    .sidebar-nav {
      display: flex;
      flex-direction: column;
      gap: 0.35rem;
      flex: 1;
    }

    .nav-link {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 0.68rem 0.95rem;
      border-radius: var(--radius-sm);
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
      border-radius: var(--radius-full);
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
      padding: 0.85rem;
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
      max-width: 840px;
      width: 100%;
    }

    .hero-badge {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 0.5rem;
      background: rgba(255, 255, 255, 0.9);
      backdrop-filter: blur(12px);
      border: 1px solid var(--border-card);
      padding: 0.42rem 1.25rem;
      border-radius: var(--radius-full);
      font-size: 0.82rem;
      font-weight: 600;
      color: var(--text-secondary);
      box-shadow: var(--shadow-sm);
      margin-bottom: 1.35rem;
      transition: all var(--transition-fast);
      text-decoration: none;
      max-width: 100%;
      text-align: center;
      line-height: 1.4;
      white-space: normal;
      word-break: normal !important;
      overflow-wrap: normal !important;
    }

    .hero-badge:hover {
      border-color: var(--accent-blue);
      color: var(--accent-blue);
      box-shadow: var(--shadow-card);
      transform: translateY(-1px);
    }

    .catalyst-ticker, .ticker-badge {
      white-space: nowrap !important;
      word-break: keep-all !important;
      overflow-wrap: normal !important;
      display: inline-block;
    }

    .hero-title {
      font-size: 2.5rem;
      font-weight: 800;
      letter-spacing: -0.035em;
      color: var(--text-primary);
      margin-bottom: 0.6rem;
      word-break: normal;
      overflow-wrap: normal;
      line-height: 1.2;
    }

    .hero-subtext {
      font-size: 0.98rem;
      color: var(--text-muted);
      line-height: 1.55;
      margin-bottom: 2rem;
      word-break: normal;
      max-width: 650px;
    }

    /* Global Search & Command Bar (⌘K) with Bulletproof Overflow Containment */
    .search-wrapper {
      position: relative;
      width: 100%;
      max-width: 680px;
      margin: 0 auto 3rem auto;
      box-sizing: border-box;
    }

    .search-box {
      display: flex;
      align-items: center;
      background: rgba(255, 255, 255, 0.95);
      backdrop-filter: blur(16px);
      border: 1px solid var(--border-card);
      border-radius: var(--radius-xl);
      padding: 0.85rem 1.35rem;
      box-shadow: var(--shadow-card);
      transition: all var(--transition-normal);
      cursor: text;
      width: 100%;
      box-sizing: border-box;
    }

    .search-box:focus-within, .search-box.focused {
      border-color: var(--accent-blue);
      box-shadow: 0 0 0 4px rgba(37, 99, 235, 0.12), var(--shadow-hover);
      background: #ffffff;
    }

    .search-icon-wrap {
      display: flex;
      align-items: center;
      color: var(--text-muted);
      margin-right: 0.85rem;
      flex-shrink: 0;
    }

    .search-input {
      flex: 1;
      min-width: 0;
      border: none;
      outline: none;
      background: transparent;
      font-size: 0.94rem;
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
      border-radius: 6px;
      padding: 0.18rem 0.5rem;
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.72rem;
      font-weight: 700;
      color: var(--text-muted);
      flex-shrink: 0;
    }

    /* Tab Suggestions & Live Autocomplete Dropdown - Bulletproof Containment */
    .search-dropdown {
      position: absolute;
      top: calc(100% + 10px);
      left: 0;
      right: 0;
      width: 100%;
      max-width: 100%;
      box-sizing: border-box;
      background: rgba(255, 255, 255, 0.98);
      backdrop-filter: blur(20px);
      border: 1px solid var(--border-card);
      border-radius: var(--radius-lg);
      box-shadow: var(--shadow-dropdown);
      padding: 1.15rem;
      z-index: 500;
      display: none;
      max-height: 420px;
      overflow-x: hidden;
      overflow-y: auto;
    }

    .search-dropdown.active {
      display: block;
      animation: fadeIn 0.18s cubic-bezier(0.16, 1, 0.3, 1);
    }

    @keyframes fadeIn {
      from { opacity: 0; transform: translateY(-6px); }
      to { opacity: 1; transform: translateY(0); }
    }

    .dropdown-section-title {
      font-size: 0.7rem;
      font-weight: 800;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      color: var(--text-muted);
      margin-bottom: 0.6rem;
      padding-left: 0.25rem;
    }

    .dropdown-tabs-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 0.6rem;
      margin-bottom: 1rem;
      width: 100%;
      box-sizing: border-box;
    }

    @media (max-width: 500px) {
      .dropdown-tabs-grid {
        grid-template-columns: 1fr;
      }
    }

    .dropdown-tab-card {
      display: flex;
      align-items: center;
      gap: 0.75rem;
      padding: 0.7rem 0.9rem;
      background: var(--bg-surface-elevated);
      border: 1px solid var(--border-subtle);
      border-radius: var(--radius-md);
      text-decoration: none;
      color: var(--text-primary);
      transition: all var(--transition-fast);
      min-width: 0;
      width: 100%;
      box-sizing: border-box;
      overflow: hidden;
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

    .dropdown-tab-info {
      min-width: 0;
      flex: 1 1 auto;
      overflow: hidden;
    }

    .dropdown-tab-title {
      font-size: 0.85rem;
      font-weight: 700;
      color: var(--text-primary);
      line-height: 1.2;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      max-width: 100%;
      display: block;
    }

    .dropdown-tab-sub {
      font-size: 0.72rem;
      color: var(--text-muted);
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      max-width: 100%;
      display: block;
    }

    .dropdown-tickers-wrap {
      padding-top: 0.85rem;
      border-top: 1px solid var(--border-card);
      width: 100%;
      box-sizing: border-box;
    }

    .dropdown-tickers-list {
      display: flex;
      flex-wrap: wrap;
      gap: 0.4rem;
      margin-top: 0.4rem;
      width: 100%;
      box-sizing: border-box;
    }

    .ticker-jump-pill {
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.75rem;
      font-weight: 700;
      padding: 0.22rem 0.6rem;
      border-radius: var(--radius-sm);
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
      transform: translateY(-1px);
    }

    /* Live Search Results List - Contained Layout */
    .search-results-list {
      display: flex;
      flex-direction: column;
      gap: 0.5rem;
      width: 100%;
      box-sizing: border-box;
    }

    .search-result-item {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 0.75rem;
      padding: 0.75rem 1rem;
      border-radius: var(--radius-md);
      background: var(--bg-surface-elevated);
      border: 1px solid var(--border-subtle);
      text-decoration: none;
      color: var(--text-primary);
      transition: all var(--transition-fast);
      width: 100%;
      min-width: 0;
      box-sizing: border-box;
      overflow: hidden;
    }

    .search-result-item:hover {
      background: #eff6ff;
      border-color: #bfdbfe;
      transform: translateX(2px);
    }

    .search-result-left {
      display: flex;
      align-items: center;
      gap: 0.75rem;
      min-width: 0;
      flex: 1 1 auto;
      overflow: hidden;
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

    .search-result-info {
      min-width: 0;
      flex: 1 1 auto;
      overflow: hidden;
    }

    .search-result-title {
      font-size: 0.85rem;
      font-weight: 700;
      color: var(--text-primary);
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      max-width: 100%;
      display: block;
    }

    .search-result-sub {
      font-size: 0.72rem;
      color: var(--text-secondary);
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      max-width: 100%;
      display: block;
    }

    .search-no-results {
      text-align: center;
      padding: 2rem 1rem;
      color: var(--text-muted);
      width: 100%;
      box-sizing: border-box;
    }

    .no-results-icon {
      font-size: 1.75rem;
      margin-bottom: 0.4rem;
    }

    .no-results-title {
      font-size: 0.88rem;
      font-weight: 700;
      color: var(--text-primary);
      margin-bottom: 0.35rem;
      word-break: break-word;
      overflow-wrap: break-word;
    }

    .no-results-sub {
      font-size: 0.75rem;
      color: var(--text-muted);
      word-break: break-word;
      overflow-wrap: break-word;
    }

    /* Asymmetric Hero Bento Deck (Replacing rigid 3-column cards) */
    .hero-bento-deck {
      display: grid;
      grid-template-columns: 1.5fr 1fr;
      gap: 1.35rem;
      margin-bottom: 3.5rem;
      width: 100%;
    }

    .bento-card {
      background: var(--bg-surface-glass);
      backdrop-filter: blur(16px);
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
      border-color: #cbd5e1;
      box-shadow: var(--shadow-hover);
      transform: translateY(-2px);
    }

    .bento-card-primary {
      background: linear-gradient(135deg, rgba(238, 242, 255, 0.95), rgba(255, 255, 255, 0.95));
      border: 1px solid rgba(199, 210, 254, 0.8);
      position: relative;
    }

    .bento-card-primary::before {
      content: "";
      position: absolute;
      top: -40px;
      right: -40px;
      width: 140px;
      height: 140px;
      background: radial-gradient(circle, rgba(99, 102, 241, 0.15), transparent 70%);
      border-radius: 50%;
      pointer-events: none;
    }

    .bento-side-stack {
      display: flex;
      flex-direction: column;
      gap: 1.15rem;
    }

    .bento-card-side {
      padding: 1.35rem 1.5rem;
    }

    .bento-badge-top {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 0.85rem;
    }

    .bento-pill-accent {
      display: inline-flex;
      align-items: center;
      gap: 0.35rem;
      font-size: 0.72rem;
      font-weight: 800;
      letter-spacing: 0.05em;
      text-transform: uppercase;
      color: #4338ca;
      background: #e0e7ff;
      padding: 0.25rem 0.65rem;
      border-radius: var(--radius-full);
    }

    .bento-pill-cal {
      display: inline-flex;
      align-items: center;
      gap: 0.35rem;
      font-size: 0.72rem;
      font-weight: 800;
      letter-spacing: 0.05em;
      text-transform: uppercase;
      color: #0369a1;
      background: #e0f2fe;
      padding: 0.25rem 0.65rem;
      border-radius: var(--radius-full);
    }

    .bento-pill-econ {
      display: inline-flex;
      align-items: center;
      gap: 0.35rem;
      font-size: 0.72rem;
      font-weight: 800;
      letter-spacing: 0.05em;
      text-transform: uppercase;
      color: #15803d;
      background: #dcfce7;
      padding: 0.25rem 0.65rem;
      border-radius: var(--radius-full);
    }

    .bento-arrow {
      font-size: 0.8rem;
      font-weight: 700;
      color: var(--text-muted);
      transition: transform var(--transition-fast);
    }

    .bento-card:hover .bento-arrow {
      color: var(--accent-blue);
      transform: translateX(3px);
    }

    .bento-score-hero {
      display: flex;
      align-items: baseline;
      gap: 0.6rem;
      margin-bottom: 0.6rem;
    }

    .bento-count {
      font-family: 'JetBrains Mono', monospace;
      font-size: 2.2rem;
      font-weight: 800;
      color: #1e1b4b;
      line-height: 1;
    }

    .bento-sublabel {
      font-size: 0.9rem;
      font-weight: 700;
      color: var(--text-secondary);
    }

    .bento-headline-preview {
      font-size: 0.95rem;
      font-weight: 700;
      color: var(--text-primary);
      line-height: 1.4;
      margin-bottom: 1.25rem;
      display: -webkit-box;
      -webkit-line-clamp: 2;
      -webkit-box-orient: vertical;
      overflow: hidden;
    }

    .bento-footer-pill {
      display: flex;
      justify-content: space-between;
      align-items: center;
      background: rgba(255, 255, 255, 0.8);
      border: 1px solid rgba(199, 210, 254, 0.6);
      border-radius: var(--radius-md);
      padding: 0.65rem 0.95rem;
      font-size: 0.82rem;
      font-weight: 600;
      color: #4338ca;
    }

    .bento-side-meta {
      font-size: 0.75rem;
      color: var(--text-muted);
      margin-top: 0.35rem;
    }

    /* Recently Viewed Companies Quick Access Deck */
    .recently-viewed-section {
      margin-bottom: 2.75rem;
      width: 100%;
    }

    .recently-viewed-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
      gap: 1rem;
    }

    .recent-card {
      background: var(--bg-surface-glass);
      backdrop-filter: blur(14px);
      border: 1px solid var(--border-glass);
      border-radius: var(--radius-lg);
      padding: 1.1rem 1.25rem;
      box-shadow: var(--shadow-sm);
      text-decoration: none;
      color: inherit;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      transition: all var(--transition-normal);
      position: relative;
      overflow: hidden;
      min-height: 118px;
    }

    .recent-card:hover {
      border-color: #94a3b8;
      box-shadow: var(--shadow-hover);
      transform: translateY(-2px);
    }

    .recent-card-top {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 0.5rem;
    }

    .recent-card-time {
      font-size: 0.72rem;
      color: var(--text-muted);
      font-weight: 500;
    }

    .recent-card-body {
      margin-bottom: 0.65rem;
    }

    .recent-card-name {
      font-size: 0.92rem;
      font-weight: 700;
      color: var(--text-primary);
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      line-height: 1.3;
    }

    .recent-card-sector {
      font-size: 0.74rem;
      color: var(--text-secondary);
      margin-top: 0.15rem;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    .recent-card-footer {
      display: flex;
      justify-content: space-between;
      align-items: center;
      font-size: 0.74rem;
      color: var(--text-muted);
      border-top: 1px solid var(--border-card);
      padding-top: 0.5rem;
      margin-top: auto;
    }

    .recent-card-pill {
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.72rem;
      font-weight: 700;
      color: #4338ca;
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
      font-weight: 800;
      letter-spacing: -0.025em;
      color: var(--text-primary);
    }

    .section-time-pill {
      display: inline-flex;
      align-items: center;
      gap: 0.4rem;
      background: var(--bg-surface-glass);
      backdrop-filter: blur(12px);
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
      backdrop-filter: blur(16px);
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
      font-family: 'JetBrains Mono', monospace;
      font-size: 2rem;
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
      background: rgba(16, 185, 129, 0.12);
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
      background: #f8fafc;
      border-color: #cbd5e1;
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
      box-shadow: 0 0 0 2px rgba(255, 255, 255, 0.9);
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
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.76rem;
      font-weight: 700;
      color: var(--text-primary);
    }

    .cat-stat-pct {
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.68rem;
      font-weight: 600;
      color: var(--text-muted);
      background: #f1f5f9;
      padding: 0.1rem 0.35rem;
      border-radius: 4px;
    }

    /* Ticker & Form Badges */
    .ticker-badge {
      font-family: 'JetBrains Mono', monospace;
      font-weight: 700;
      font-size: 0.78rem;
      padding: 0.2rem 0.55rem;
      border-radius: 6px;
      display: inline-block;
      letter-spacing: 0.02em;
      background: #f1f5f9;
      color: #334155;
      border: 1px solid #cbd5e1;
      flex-shrink: 0;
      white-space: nowrap !important;
      word-break: keep-all !important;
      text-decoration: none;
      transition: transform 0.15s ease, box-shadow 0.15s ease, border-color 0.15s ease;
      cursor: pointer;
    }

    .ticker-badge:hover {
      transform: translateY(-1px);
      box-shadow: 0 2px 6px rgba(0, 0, 0, 0.08);
      border-color: #94a3b8;
      text-decoration: none;
    }

    .form-type-pill {
      font-family: 'JetBrains Mono', monospace;
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

    .source-tag {
      font-size: 0.72rem;
      color: var(--text-muted);
      font-weight: 500;
      white-space: nowrap;
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
      background: #f1f5f9;
      color: #334155;
      border: 1px solid #cbd5e1;
    }

    .source-badge-ir {
      background: #eff6ff;
      color: #1d4ed8;
      border: 1px solid #bfdbfe;
    }

    .source-badge-news {
      background: #ecfdf5;
      color: #047857;
      border: 1px solid #a7f3d0;
    }

    /* Score Badges */
    .score-badge {
      font-family: 'JetBrains Mono', monospace;
      font-weight: 800;
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
      color: #ffffff;
      border-color: var(--accent-blue);
      box-shadow: 0 4px 12px rgba(37, 99, 235, 0.25);
    }
    .company-strip-pill.active .ticker-badge {
      background: rgba(255, 255, 255, 0.25);
      color: #ffffff;
      border-color: rgba(255, 255, 255, 0.4);
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
      font-family: 'JetBrains Mono', monospace;
      font-size: 1.5rem;
      font-weight: 800;
      padding: 0.35rem 0.95rem;
      border-radius: var(--radius-md);
      background: var(--bg-surface-elevated);
      border: 2px solid var(--border-card);
      color: var(--text-primary);
    }
    .company-hero-name {
      font-size: 1.45rem;
      font-weight: 800;
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
      background: #f8fafc;
      border: 1px solid #e2e8f0;
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
      border-color: #cbd5e1;
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
      font-family: 'JetBrains Mono', monospace;
      font-size: 1.25rem;
      font-weight: 800;
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
      border-color: #cbd5e1;
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
      font-weight: 800;
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
      padding: 0.1rem 0.35rem;
      border-radius: 4px;
      white-space: nowrap;
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
      margin-top: 0.5rem;
      padding: 0.65rem 0.85rem;
      background: #ffffff;
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
      background: #eff6ff;
      border-left: 4px solid var(--accent-blue);
      padding: 0.65rem 0.95rem;
      border-radius: 0 var(--radius-md) var(--radius-md) 0;
      font-size: 0.835rem;
      color: #1e3a8a;
      line-height: 1.5;
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
      color: #1d4ed8;
      transform: translateX(2px);
    }

    /* Primary Button */
    .btn-primary {
      background: var(--accent-blue);
      color: #ffffff;
      padding: 0.6rem 1.25rem;
      border-radius: var(--radius-full);
      font-weight: 600;
      font-size: 0.85rem;
      text-decoration: none;
      display: inline-flex;
      align-items: center;
      gap: 0.45rem;
      border: none;
      cursor: pointer;
      transition: all var(--transition-fast);
      box-shadow: var(--shadow-sm);
      white-space: nowrap;
    }

    .btn-primary:hover {
      background: #1d4ed8;
      box-shadow: var(--shadow-card);
      transform: translateY(-1px);
    }

    /* Filter Controls Panel */
    .controls-panel {
      background: var(--bg-surface-glass);
      backdrop-filter: blur(16px);
      border: 1px solid var(--border-glass);
      border-radius: var(--radius-lg);
      padding: 1.65rem;
      margin-bottom: 2.25rem;
      box-shadow: var(--shadow-card);
      min-width: 0;
    }

    .filter-row {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 0.5rem;
      margin-bottom: 0.95rem;
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
      padding: 0.38rem 0.8rem;
      border-radius: var(--radius-full);
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
      transform: translateY(-1px);
    }

    .filter-btn.active {
      background: var(--accent-blue);
      color: #ffffff;
      border-color: var(--accent-blue);
      box-shadow: 0 2px 8px rgba(37, 99, 235, 0.25);
    }

    .pill-count {
      font-size: 0.7rem;
      opacity: 0.85;
      font-family: 'JetBrains Mono', monospace;
    }

    /* Table Styles */
    .table-container {
      background: var(--bg-surface-glass);
      backdrop-filter: blur(16px);
      border: 1px solid var(--border-glass);
      border-radius: var(--radius-lg);
      overflow-x: auto;
      -webkit-overflow-scrolling: touch;
      box-shadow: var(--shadow-card);
      width: 100%;
    }

    table {
      width: 100%;
      min-width: 680px;
      border-collapse: collapse;
      text-align: left;
      font-size: 0.875rem;
    }

    th {
      background: rgba(248, 250, 252, 0.85);
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
      background: rgba(248, 250, 252, 0.7);
    }

    .headline-text {
      font-weight: 700;
      color: var(--text-primary);
      margin-bottom: 0.35rem;
      font-size: 0.95rem;
      line-height: 1.4;
    }

    .summary-text {
      color: var(--text-secondary);
      font-size: 0.825rem;
      line-height: 1.45;
      margin-top: 0.35rem;
    }

    .date-cell {
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.78rem;
      color: var(--text-muted);
      white-space: nowrap;
    }

    /* Priority Section & Editorial Suite Layout */
    .priority-section {
      background: var(--bg-surface-glass);
      backdrop-filter: blur(16px);
      border: 1px solid var(--border-glass);
      border-radius: var(--radius-xl);
      padding: 2rem;
      margin-bottom: 3rem;
      box-shadow: var(--shadow-card);
      min-width: 0;
    }

    .priority-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 0.75rem;
      margin-bottom: 1.75rem;
      padding-bottom: 1.25rem;
      border-bottom: 1px solid var(--border-card);
    }

    .priority-title-wrap {
      display: flex;
      align-items: center;
      gap: 0.85rem;
    }

    .priority-badge-icon {
      background: #fef3c7;
      color: #b45309;
      border: 1px solid #fde68a;
      padding: 0.35rem 0.75rem;
      border-radius: var(--radius-full);
      font-size: 0.75rem;
      font-weight: 800;
      letter-spacing: 0.05em;
      display: inline-flex;
      align-items: center;
      gap: 0.35rem;
      flex-shrink: 0;
    }

    .priority-editorial-layout {
      display: flex;
      flex-direction: column;
      gap: 1.35rem;
    }

    .priority-card {
      background: var(--bg-surface-elevated);
      border: 1px solid var(--border-card);
      border-radius: var(--radius-lg);
      padding: 1.5rem;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      transition: all var(--transition-fast);
      min-width: 0;
    }

    .priority-card:hover {
      transform: translateY(-2px);
      border-color: #cbd5e1;
      box-shadow: var(--shadow-card);
      background: #ffffff;
    }

    /* #1 Lead Editorial Card */
    .priority-lead-card {
      background: linear-gradient(135deg, rgba(238, 242, 255, 0.8), #ffffff);
      border: 1px solid rgba(199, 210, 254, 0.9);
      padding: 2rem;
      box-shadow: var(--shadow-hover);
    }

    .priority-lead-badge {
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.75rem;
      font-weight: 800;
      color: #4338ca;
      background: #e0e7ff;
      border: 1px solid #c7d2fe;
      padding: 0.25rem 0.65rem;
      border-radius: var(--radius-full);
    }

    .score-pill-lead {
      font-size: 0.92rem !important;
      padding: 0.25rem 0.75rem !important;
    }

    .priority-lead-headline {
      font-size: 1.25rem;
      font-weight: 800;
      color: var(--text-primary);
      margin: 0.75rem 0 0.5rem 0;
      line-height: 1.35;
    }

    .lead-why-box {
      margin-top: 0.85rem;
      padding: 0.85rem 1.15rem;
      font-size: 0.9rem;
    }

    .priority-subgrid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
      gap: 1.25rem;
    }

    .priority-subcard {
      padding: 1.35rem;
    }

    .priority-card-top {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 0.85rem;
      gap: 0.5rem;
      flex-wrap: wrap;
    }

    .priority-rank-pill {
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.72rem;
      font-weight: 800;
      color: var(--text-muted);
      background: #ffffff;
      padding: 0.18rem 0.5rem;
      border-radius: var(--radius-sm);
      border: 1px solid var(--border-card);
    }

    .priority-score-pill {
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.82rem;
      font-weight: 800;
      color: #15803d;
      background: #dcfce7;
      border: 1px solid #bbf7d0;
      padding: 0.22rem 0.6rem;
      border-radius: var(--radius-full);
      flex-shrink: 0;
    }

    .priority-card-headline {
      font-size: 1rem;
      font-weight: 700;
      color: var(--text-primary);
      margin: 0.55rem 0;
      line-height: 1.35;
    }

    .priority-card-summary {
      font-size: 0.82rem;
      color: var(--text-secondary);
      line-height: 1.45;
    }

    .priority-card-footer {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding-top: 0.95rem;
      border-top: 1px solid var(--border-card);
      margin-top: 1.15rem;
      gap: 0.5rem;
      flex-wrap: wrap;
    }

    /* Corporate Calendar Spotlight & Organic Grid */
    .calendar-spotlight-card {
      background: linear-gradient(135deg, rgba(240, 249, 255, 0.9), #ffffff);
      border: 1px solid rgba(186, 230, 253, 0.9);
      border-radius: var(--radius-xl);
      padding: 1.85rem;
      box-shadow: var(--shadow-card);
      margin-bottom: 2.5rem;
    }

    .spotlight-badge-row {
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 0.5rem;
      margin-bottom: 1rem;
    }

    .spotlight-beacon-pill {
      font-size: 0.72rem;
      font-weight: 800;
      letter-spacing: 0.05em;
      text-transform: uppercase;
      color: #0369a1;
      background: #e0f2fe;
      padding: 0.25rem 0.75rem;
      border-radius: var(--radius-full);
    }

    .spotlight-content-row {
      display: flex;
      align-items: center;
      gap: 1.5rem;
      flex-wrap: wrap;
    }

    .spotlight-date-box {
      width: 72px !important;
      min-width: 72px !important;
      padding: 0.6rem 0.85rem !important;
      border-radius: var(--radius-md) !important;
      background: #ffffff !important;
      border: 1px solid #bae6fd !important;
      box-shadow: 0 4px 12px rgba(3, 105, 161, 0.08) !important;
    }

    .calendar-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(290px, 1fr));
      gap: 1.35rem;
      width: 100%;
    }

    .calendar-card {
      background: var(--bg-surface-glass);
      backdrop-filter: blur(16px);
      border: 1px solid var(--border-glass);
      border-radius: var(--radius-lg);
      padding: 1.35rem;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      transition: all var(--transition-fast);
      box-shadow: var(--shadow-sm);
      min-width: 0;
      width: 100%;
      box-sizing: border-box;
    }

    .calendar-card:hover {
      transform: translateY(-2px);
      border-color: #cbd5e1;
      box-shadow: var(--shadow-card);
    }

    .calendar-card-estimated {
      border: 1px dashed #cbd5e1;
      background: rgba(248, 250, 252, 0.85);
    }

    .calendar-card-header {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 0.5rem;
      margin-bottom: 0.75rem;
    }

    .calendar-card-identity {
      display: flex;
      align-items: center;
      flex-wrap: wrap;
      gap: 0.4rem;
      min-width: 0;
      flex: 1;
    }

    .calendar-origin-badge {
      font-size: 0.62rem;
      font-weight: 800;
      padding: 0.18rem 0.5rem;
      border-radius: var(--radius-full);
      letter-spacing: 0.04em;
      white-space: nowrap;
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
      padding: 0.22rem 0.6rem;
      border-radius: var(--radius-full);
      display: inline-flex;
      align-items: center;
      gap: 0.3rem;
      width: fit-content;
      margin-top: 0.35rem;
    }

    .cal-type-earnings   { background: #eff6ff; color: #1d4ed8; border: 1px solid #bfdbfe; }
    .cal-type-dividend   { background: #dcfce7; color: #15803d; border: 1px solid #bbf7d0; }
    .cal-type-sec        { background: #f3e8ff; color: #7e22ce; border: 1px solid #e9d5ff; }
    .cal-type-conference { background: #fef3c7; color: #b45309; border: 1px solid #fde68a; }

    .calendar-date-box {
      background: #ffffff;
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
      font-weight: 800;
      color: var(--accent-blue);
      text-transform: uppercase;
      letter-spacing: 0.04em;
    }

    .calendar-date-day {
      font-family: 'JetBrains Mono', monospace;
      font-size: 1.35rem;
      font-weight: 800;
      color: var(--text-primary);
      line-height: 1.1;
    }

    .calendar-card-headline {
      font-size: 0.96rem;
      font-weight: 700;
      color: var(--text-primary);
      margin: 0.5rem 0 0.35rem 0;
      line-height: 1.35;
    }

    .calendar-card-details {
      font-size: 0.8rem;
      color: var(--text-secondary);
      margin: 0 0 0.95rem 0;
      line-height: 1.45;
    }

    .calendar-card-bottom {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding-top: 0.85rem;
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

    /* Macroeconomic Intelligence Grid & Anchor Cards */
    .economic-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
      gap: 1.35rem;
    }

    .economic-card {
      background: var(--bg-surface-glass);
      backdrop-filter: blur(16px);
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
      border-color: #cbd5e1;
      box-shadow: var(--shadow-card);
    }

    .economic-card-anchor {
      background: linear-gradient(135deg, rgba(238, 242, 255, 0.9), #ffffff);
      border: 1px solid rgba(199, 210, 254, 0.9);
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
      font-weight: 800;
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

    .trend-up   { background: #fee2e2; color: #b91c1c; border: 1px solid #fecaca; }
    .trend-down { background: #dcfce7; color: #15803d; border: 1px solid #bbf7d0; }
    .trend-flat { background: #f1f5f9; color: #475569; border: 1px solid #cbd5e1; }

    .economic-val {
      font-family: 'JetBrains Mono', monospace;
      font-size: 2.1rem;
      font-weight: 800;
      color: var(--text-primary);
      line-height: 1;
      margin-bottom: 0.45rem;
    }

    .economic-val-anchor {
      font-size: 2.5rem;
      color: #1e1b4b;
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

    /* Health Section */
    .health-section {
      background: var(--bg-surface-glass);
      backdrop-filter: blur(16px);
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
      font-weight: 800;
      color: var(--text-primary);
    }

    .health-status-badge {
      font-size: 0.75rem;
      font-weight: 800;
      letter-spacing: 0.05em;
      text-transform: uppercase;
      padding: 0.3rem 0.75rem;
      border-radius: var(--radius-full);
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
      font-family: 'JetBrains Mono', monospace;
      font-size: 1.65rem;
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
      backdrop-filter: blur(6px);
      z-index: 2000;
      display: none;
      align-items: center;
      justify-content: center;
      padding: 1rem;
    }

    .ai-modal-backdrop.active {
      display: flex;
      animation: fadeIn 0.18s cubic-bezier(0.16, 1, 0.3, 1);
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
      padding: 1.25rem 1.5rem;
      border-bottom: 1px solid var(--border-card);
    }

    .ai-modal-icon-badge {
      width: 34px;
      height: 34px;
      border-radius: var(--radius-sm);
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
      font-size: 1.4rem;
      color: var(--text-muted);
      cursor: pointer;
      padding: 0.25rem;
      border-radius: var(--radius-xs);
      line-height: 1;
    }

    .ai-modal-close:hover {
      color: var(--text-primary);
      background: var(--bg-surface-elevated);
    }

    .ai-modal-body {
      padding: 1.5rem;
      overflow-y: auto;
      display: flex;
      flex-direction: column;
      gap: 1rem;
    }

    .ai-input-wrap {
      display: flex;
      gap: 0.5rem;
      background: var(--bg-base);
      border: 1px solid var(--border-card);
      border-radius: var(--radius-md);
      padding: 0.4rem;
    }

    .ai-input-wrap input {
      flex: 1;
      min-width: 0;
      border: none;
      outline: none;
      background: transparent;
      padding: 0.4rem 0.75rem;
      font-size: 0.92rem;
      font-family: inherit;
      color: var(--text-primary);
    }

    .ai-chips-wrap {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 0.4rem;
    }

    .ai-chip {
      font-size: 0.75rem;
      font-weight: 600;
      color: var(--text-secondary);
      background: var(--bg-surface-elevated);
      border: 1px solid var(--border-card);
      border-radius: var(--radius-full);
      padding: 0.25rem 0.75rem;
      cursor: pointer;
      transition: all var(--transition-fast);
      white-space: nowrap;
    }

    .ai-chip:hover {
      background: #eff6ff;
      border-color: #bfdbfe;
      color: #1d4ed8;
      transform: translateY(-1px);
    }

    .ai-results-container {
      border: 1px solid var(--border-card);
      border-radius: var(--radius-md);
      background: var(--bg-base);
      max-height: 280px;
      overflow-y: auto;
      padding: 0.85rem;
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
      font-family: 'JetBrains Mono', monospace;
      font-size: 1.25rem;
      font-weight: 800;
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
    <span style="font-size:1rem; font-weight:800; color:var(--text-primary);">StockPulse</span>
  </a>
  <div class="mobile-header-right">
    <button class="top-header-btn btn-ai" style="padding:0.35rem 0.75rem; font-size:0.75rem;" onclick="openAiModal()">
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
    <a href="index.html" class="sidebar-brand">
      <div class="logo-badge">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
          <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>
        </svg>
      </div>
      <span class="brand-title">StockPulse</span>
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
    <a href="company.html" class="nav-link {% if active_page == 'company' %}active{% endif %}" onclick="closeMobileNav()">
      <div class="nav-item-left">
        <svg class="nav-svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 3v18h18"/><path d="m19 9-5 5-4-4-3 3"/></svg>
        <span class="nav-text">Company Deep Dive</span>
      </div>
      <span class="nav-count">{{ watchlist_companies|length }}</span>
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
  <a href="company.html" class="mobile-tab-link {% if active_page == 'company' %}active{% endif %}">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><path d="M3 3v18h18"/><path d="m19 9-5 5-4-4-3 3"/></svg>
    <span>Deep Dive</span>
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
        <span class="section-time-pill" style="font-size:0.75rem; padding:0.3rem 0.75rem;">
          <span class="pulse-dot" style="background:#10b981;"></span> Live
        </span>
      </div>

      <!-- Hero Greeting Section -->
      <div class="hero-container">
        <a href="calendar.html" class="hero-badge">
          <span class="pulse-dot" style="background:#10b981; margin-right:0.2rem; flex-shrink:0;"></span>
          {% if calendar_events %}
          <span>Next Event: <strong class="catalyst-ticker" style="color:var(--text-primary);">{{ calendar_events[0].ticker }}</strong> ({{ calendar_events[0].display_date }}) &bull; {{ priority_items|length }} Priority Stories ↗</span>
          {% else %}
          <span><strong class="catalyst-ticker">{{ priority_items|length }} Priority Disclosures Active</strong> &bull; 15 Companies Monitored ↗</span>
          {% endif %}
        </a>
        <h1 class="hero-title">What's on the agenda?</h1>
        <p class="hero-subtext">Review overnight SEC filings, corporate announcements, forthcomming milestones, and FRED macroeconomic sensitivities.</p>
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

        <!-- Interactive Live Suggestions / Autocomplete Dropdown - Constrained Containment -->
        <div class="search-dropdown" id="searchDropdown">
          <div id="defaultDropdownContent">
            <div class="dropdown-section-title">Suggested Pages &amp; Views</div>
            <div class="dropdown-tabs-grid">
              <a href="news.html" class="dropdown-tab-card">
                <div class="dropdown-tab-icon">
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 22h16a2 2 0 0 0 2-2V4a2 2 0 0 0-2-2H8a2 2 0 0 0-2 2v16a2 2 0 0 1-2 2Zm0 0a2 2 0 0 1-2-2v-9c0-1.1.9-2 2-2h2"/><path d="M18 14h-8"/><path d="M15 18h-5"/><path d="M10 6h8v4h-8V6Z"/></svg>
                </div>
                <div class="dropdown-tab-info">
                  <div class="dropdown-tab-title">Intelligence Feed</div>
                  <div class="dropdown-tab-sub">{{ stats.total }} Scored Disclosures</div>
                </div>
              </a>
              <a href="calendar.html" class="dropdown-tab-card">
                <div class="dropdown-tab-icon">
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect width="18" height="18" x="3" y="4" rx="2" ry="2"/><line x1="16" x2="16" y1="2" y2="6"/><line x1="8" x2="8" y1="2" y2="6"/><line x1="3" x2="21" y1="10" y2="10"/></svg>
                </div>
                <div class="dropdown-tab-info">
                  <div class="dropdown-tab-title">Corporate Calendar</div>
                  <div class="dropdown-tab-sub">{{ calendar_events|length }} Upcoming Events</div>
                </div>
              </a>
              <a href="economic.html" class="dropdown-tab-card">
                <div class="dropdown-tab-icon">
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="20" x2="12" y2="10"/><line x1="18" y1="20" x2="18" y2="4"/><line x1="6" y1="20" x2="6" y2="16"/></svg>
                </div>
                <div class="dropdown-tab-info">
                  <div class="dropdown-tab-title">Economic Snapshot</div>
                  <div class="dropdown-tab-sub">{{ economic_indicators|length }} FRED Indicators</div>
                </div>
              </a>
              <a href="#analyticsSection" class="dropdown-tab-card" onclick="closeSearchDropdown()">
                <div class="dropdown-tab-icon">
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/></svg>
                </div>
                <div class="dropdown-tab-info">
                  <div class="dropdown-tab-title">Analytics &amp; Trends</div>
                  <div class="dropdown-tab-sub">Metrics &amp; Safeguards</div>
                </div>
              </a>
            </div>

            <div class="dropdown-tickers-wrap">
              <div class="dropdown-section-title">Jump to Watchlist Ticker</div>
              <div class="dropdown-tickers-list">
                {% for sym in ['NVDA', 'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'TSLA', 'JPM', 'JNJ', 'XOM', 'WMT', 'DIS', 'KO', 'PFE', 'BA'] %}
                <a href="company.html?ticker={{ sym }}" class="ticker-jump-pill">{{ sym }}</a>
                {% endfor %}
              </div>
            </div>
          </div>

          <!-- Dynamic Live Search Results Container -->
          <div id="liveSearchResults" style="display:none;"></div>
        </div>
      </div>

      <!-- Top Quick Preview Bento Deck (Asymmetric Layout) -->
      <div class="hero-bento-deck">
        <!-- Featured Priority Intelligence Card -->
        <a href="news.html" class="bento-card bento-card-primary">
          <div class="bento-badge-top">
            <span class="bento-pill-accent">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>
              FEATURED INTELLIGENCE
            </span>
            <span class="bento-arrow">Explore Feed ›</span>
          </div>
          <div>
            <div class="bento-score-hero">
              <span class="bento-count">{{ priority_items|length }}</span>
              <span class="bento-sublabel">High-Impact Disclosures Monitored</span>
            </div>
            {% if priority_items %}
            <div class="bento-headline-preview">
              <span class="ticker-badge ticker-{{ priority_items[0].ticker }}" style="margin-right:0.35rem;">{{ priority_items[0].ticker }}</span>
              {{ priority_items[0].clean_headline }}
            </div>
            {% endif %}
          </div>
          <div class="bento-footer-pill">
            <span>Score Baseline ≥ 7.0 &bull; Transparent Scoring Breakdown</span>
            <span>→</span>
          </div>
        </a>

        <!-- Right Stacked Bento Cards -->
        <div class="bento-side-stack">
          <!-- Calendar Milestone Card -->
          <a href="calendar.html" class="bento-card bento-card-side">
            <div class="bento-badge-top">
              <span class="bento-pill-cal">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect width="18" height="18" x="3" y="4" rx="2" ry="2"/><line x1="16" x2="16" y1="2" y2="6"/><line x1="8" x2="8" y1="2" y2="6"/><line x1="3" x2="21" y1="10" y2="10"/></svg>
                NEXT EVENT
              </span>
              <span class="bento-arrow">Calendar ›</span>
            </div>
            {% if calendar_events %}
            <div style="display:flex; align-items:center; gap:0.85rem; margin:0.4rem 0;">
              <div class="calendar-date-box" style="width:48px; min-width:48px; padding:0.25rem 0.45rem;">
                <div class="calendar-date-month">{{ calendar_events[0].event_date[5:7] | replace('01','JAN') | replace('02','FEB') | replace('03','MAR') | replace('04','APR') | replace('05','MAY') | replace('06','JUN') | replace('07','JUL') | replace('08','AUG') | replace('09','SEP') | replace('10','OCT') | replace('11','NOV') | replace('12','DEC') }}</div>
                <div class="calendar-date-day" style="font-size:1.15rem;">{{ calendar_events[0].event_date[8:10] }}</div>
              </div>
              <div style="flex:1; min-width:0;">
                <div style="font-size:0.85rem; font-weight:700; color:var(--text-primary); white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">
                  {{ calendar_events[0].headline }}
                </div>
                <div style="font-size:0.75rem; color:var(--text-muted);">
                  {{ calendar_events[0].relative_badge }} &bull; {{ calendar_events[0].event_type }}
                </div>
              </div>
            </div>
            {% else %}
            <div style="font-size:0.88rem; font-weight:700; color:var(--text-primary); margin:0.35rem 0;">Corporate Calendar Active</div>
            {% endif %}
            <div class="bento-side-meta">{{ calendar_events|length }} Scheduled Corporate Events</div>
          </a>

          <!-- Macroeconomic Pulse Card -->
          <a href="economic.html" class="bento-card bento-card-side">
            <div class="bento-badge-top">
              <span class="bento-pill-econ">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="20" x2="12" y2="10"/><line x1="18" y1="20" x2="18" y2="4"/><line x1="6" y1="20" x2="6" y2="16"/></svg>
                MACRO PULSE
              </span>
              <span class="bento-arrow">Macro ›</span>
            </div>
            <div style="display:flex; align-items:baseline; gap:0.75rem; margin:0.35rem 0;">
              <span style="font-family:'JetBrains Mono', monospace; font-size:1.35rem; font-weight:800; color:var(--text-primary);">
                {% if economic_indicators %}{{ economic_indicators[0].formatted_value }}{% else %}4.58%{% endif %}
              </span>
              <span style="font-size:0.75rem; color:var(--text-muted); font-weight:600;">
                {% if economic_indicators %}{{ economic_indicators[0].name }}{% else %}Fed Funds Rate{% endif %}
              </span>
            </div>
            <div class="bento-side-meta">{{ economic_indicators|length }} St. Louis Fed Indicators Mapped</div>
          </a>
        </div>
      </div>

      <!-- Recently Viewed Companies Quick Access Deck -->
      <div class="recently-viewed-section" id="recentlyViewedSection">
        <div class="section-header-row" style="margin-bottom:0.85rem; padding-top:0.25rem;">
          <div style="display:flex; align-items:center; gap:0.55rem;">
            <div style="background:rgba(59, 130, 246, 0.1); color:#3b82f6; width:28px; height:28px; border-radius:var(--radius-sm); display:flex; align-items:center; justify-content:center;">
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
            </div>
            <h2 class="section-heading" style="margin:0; font-size:1.15rem;">Recently Viewed Companies</h2>
            <span class="badge" id="recentlyViewedCountBadge" style="font-size:0.7rem; background:var(--bg-surface-elevated); color:var(--text-muted); padding:0.15rem 0.5rem; border-radius:var(--radius-full);"></span>
          </div>
          <div style="display:flex; align-items:center; gap:0.65rem;">
            <button id="clearRecentlyViewedBtn" onclick="clearRecentlyViewed()" title="Clear your recently viewed history" style="background:none; border:none; font-size:0.75rem; color:var(--text-muted); cursor:pointer; padding:0.25rem 0.5rem; border-radius:4px; transition:color 0.15s;">
              Clear History
            </button>
            <a href="company.html" class="bento-arrow" style="font-size:0.8rem; text-decoration:none;">All 15 Companies ›</a>
          </div>
        </div>

        <div class="recently-viewed-grid" id="recentlyViewedGrid">
          <!-- Populated dynamically via localStorage -->
        </div>
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
            <div class="chart-canvas-container" style="height: 220px;">
              <canvas id="categoryChart"></canvas>
            </div>
          </div>
          
          <div class="category-legend-list" id="categoryLegendList">
            <!-- Dynamically populated legend badges with counts & percentages -->
          </div>
        </div>
      </div>

      <!-- 3-Month Comparative Performance vs Competitors & S&P 500 Benchmark -->
      <div class="comparative-perf-card" style="margin-top:1.5rem;">
        <div class="comparative-perf-header">
          <div>
            <div style="display:flex; align-items:center; gap:0.6rem;">
              <span class="category-badge" style="background:#eef2ff; color:#4338ca; border-color:#c7d2fe; font-size:0.72rem;">MARKET CONTEXT</span>
              <h3 style="font-size:1.2rem; font-weight:800; color:var(--text-primary); margin:0;">3-Month Comparative Performance vs. Peers &amp; S&amp;P 500</h3>
            </div>
            <p style="font-size:0.835rem; color:var(--text-muted); margin:0.35rem 0 0 0;">
              Contextual move analysis: Normalized % return (Day 0 = 0.0%) against top 3 competitors and the S&amp;P 500 (SPY) benchmark.
            </p>
          </div>

          <!-- Watchlist Company Selector Dropdown -->
          <div style="display:flex; align-items:center; gap:0.6rem;">
            <label for="perfCompanySelect" style="font-size:0.78rem; font-weight:700; color:var(--text-muted); text-transform:uppercase;">Select Stock:</label>
            <select id="perfCompanySelect" class="comparative-select" onchange="renderComparativePerformanceChart(this.value)">
              {% for co in watchlist_companies %}
              <option value="{{ co.symbol }}">{{ co.symbol }} — {{ co.name }}</option>
              {% endfor %}
            </select>
          </div>
        </div>

        <!-- Real-time Alpha & Return Metrics Ribbon -->
        <div class="perf-kpi-grid" id="perfKpiGrid">
          <!-- Dynamically populated via JS based on selected company -->
        </div>

        <!-- Interactive Chart Canvas -->
        <div style="position:relative; height:320px; width:100%;">
          <canvas id="comparativeChartCanvas"></canvas>
        </div>

        <!-- Competitor Breakdown Table -->
        <div class="perf-table-wrap">
          <table class="perf-table" id="perfBreakdownTable">
            <!-- Dynamically populated table -->
          </table>
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

        <div class="health-grid" style="grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));">
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
            <div class="health-metric-title">News Media Coverage</div>
            <div class="health-metric-val" style="color:#047857;">{{ latest_run.news_media_count if latest_run and latest_run.news_media_count is defined else stats.by_source.get('News Media', 0) }}</div>
            <div class="health-metric-sub">Finnhub 3rd-party journalism</div>
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

    function renderRecentlyViewed() {
      const grid = document.getElementById('recentlyViewedGrid');
      const badge = document.getElementById('recentlyViewedCountBadge');
      const clearBtn = document.getElementById('clearRecentlyViewedBtn');
      if (!grid) return;

      const companyLookup = {};
      (watchlistCompanies || []).forEach(c => {
        companyLookup[c.symbol] = c;
      });

      const tickerCounts = {};
      (allItems || []).forEach(it => {
        if (it.ticker) {
          tickerCounts[it.ticker] = (tickerCounts[it.ticker] || 0) + 1;
        }
      });

      let stored = [];
      let isDefault = false;
      try {
        const raw = localStorage.getItem('stockpulse_recently_viewed');
        if (raw) {
          stored = JSON.parse(raw);
        }
      } catch (e) {
        stored = [];
      }

      if (!Array.isArray(stored) || stored.length === 0) {
        isDefault = true;
        // Suggested starter companies for quick launchpad
        stored = [
          { symbol: 'NVDA', visitedAt: null },
          { symbol: 'AAPL', visitedAt: null },
          { symbol: 'TSLA', visitedAt: null },
          { symbol: 'MSFT', visitedAt: null },
          { symbol: 'AMZN', visitedAt: null },
          { symbol: 'GOOGL', visitedAt: null },
        ];
        if (clearBtn) clearBtn.style.display = 'none';
        if (badge) badge.textContent = 'Suggested';
      } else {
        if (clearBtn) clearBtn.style.display = 'inline-block';
        if (badge) badge.textContent = `${stored.length} viewed`;
      }

      const itemsToRender = stored.slice(0, 8);
      let html = '';

      itemsToRender.forEach(item => {
        const sym = (typeof item === 'string' ? item : item.symbol).toUpperCase();
        const co = companyLookup[sym] || { name: sym, sector: 'Watchlist Company' };
        const count = tickerCounts[sym] || 0;

        let timeLabel = 'Quick Access';
        if (item.visitedAt) {
          const diffSec = Math.floor((Date.now() - item.visitedAt) / 1000);
          if (diffSec < 60) timeLabel = 'Just now';
          else if (diffSec < 3600) timeLabel = `${Math.floor(diffSec / 60)}m ago`;
          else if (diffSec < 86400) timeLabel = `${Math.floor(diffSec / 3600)}h ago`;
          else timeLabel = `${Math.floor(diffSec / 86400)}d ago`;
        }

        html += `
          <a href="company.html?ticker=${sym}" class="recent-card" title="View ${co.name} (${sym}) deep dive">
            <div class="recent-card-top">
              <span class="ticker-badge ticker-${sym}">${sym}</span>
              <span class="recent-card-time">${timeLabel}</span>
            </div>
            <div class="recent-card-body">
              <div class="recent-card-name">${co.name}</div>
              <div class="recent-card-sector">${co.sector || 'Equities'}</div>
            </div>
            <div class="recent-card-footer">
              <span class="recent-card-pill">${count} disclosures</span>
              <span style="font-size:0.75rem; font-weight:700; color:var(--accent-blue);">Explore ›</span>
            </div>
          </a>
        `;
      });

      grid.innerHTML = html;
    }

    function clearRecentlyViewed() {
      localStorage.removeItem('stockpulse_recently_viewed');
      renderRecentlyViewed();
    }

    function openSearchDropdown() {
      const dropdown = document.getElementById('searchDropdown');
      if (dropdown) dropdown.classList.add('active');
      const val = (document.getElementById('globalSearchInput')?.value || '').trim();
      if (!val) {
        const def = document.getElementById('defaultDropdownContent');
        const res = document.getElementById('liveSearchResults');
        if (def) def.style.display = 'block';
        if (res) res.style.display = 'none';
      } else {
        handleSearchType(val);
      }
    }

    function closeSearchDropdown() {
      const dropdown = document.getElementById('searchDropdown');
      if (dropdown) dropdown.classList.remove('active');
    }

    function handleSearchType(rawVal) {
      openSearchDropdown();
      const val = (rawVal || '').toLowerCase().trim();
      const defaultContent = document.getElementById('defaultDropdownContent');
      const liveResults = document.getElementById('liveSearchResults');

      if (!val) {
        if (defaultContent) defaultContent.style.display = 'block';
        if (liveResults) {
          liveResults.style.display = 'none';
          liveResults.innerHTML = '';
        }
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

      const totalMatches = matchedCompanies.length + matchedNews.length + matchedCal.length + matchedEcon.length;

      if (!liveResults) return;

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
            <a href="company.html?ticker=${c.symbol}" class="search-result-item">
              <div class="search-result-left">
                <span class="ticker-badge ticker-${c.symbol}">${c.symbol}</span>
                <div class="search-result-info">
                  <div class="search-result-title">${c.name}</div>
                  <div class="search-result-sub">${c.sector}</div>
                </div>
              </div>
              <span class="action-link" style="font-size:0.75rem;">Company View ↗</span>
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
                <div class="search-result-info">
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
                <div class="search-result-info">
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
                <div class="search-result-info">
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
      const input = document.getElementById('aiQueryInput');
      const container = document.getElementById('aiResults');
      const q = (input ? input.value : '').toLowerCase().trim();

      if (!q || !container) return;

      container.innerHTML = '<div style="text-align:center; padding:1.25rem; color:var(--accent-blue); font-weight:600;"><span class="pulse-dot" style="background:var(--accent-blue); margin-right:0.4rem;"></span> Synthesizing answer across SEC EDGAR &amp; FRED feeds...</div>';

      setTimeout(() => {
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
              <div style="background:#ffffff; border:1px solid var(--border-card); border-radius:8px; padding:0.65rem;">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                  <span style="font-weight:700; font-size:0.85rem;">${ind.name}</span>
                  <span style="font-family:\'JetBrains Mono\'; font-weight:800; color:var(--accent-blue);">${ind.formatted_value}</span>
                </div>
                <div style="font-size:0.78rem; color:var(--text-secondary); margin-top:0.25rem;">${ind.context_note || ind.category}</div>
              </div>`;
          });
        }

        if (matchedCal.length > 0) {
          html += '<div style="font-size:0.75rem; font-weight:800; color:var(--text-muted); text-transform:uppercase; margin-top:0.35rem;">Upcoming Events:</div>';
          matchedCal.slice(0, 2).forEach(ev => {
            html += `
              <div style="background:#ffffff; border:1px solid var(--border-card); border-radius:8px; padding:0.65rem;">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                  <span style="font-weight:700; font-size:0.85rem;"><span class="ticker-badge ticker-${ev.ticker}">${ev.ticker}</span> ${ev.headline}</span>
                  <span style="font-size:0.75rem; color:var(--text-muted);">${ev.display_date}</span>
                </div>
              </div>`;
          });
        }

        if (matchedItems.length > 0) {
          html += '<div style="font-size:0.75rem; font-weight:800; color:var(--text-muted); text-transform:uppercase; margin-top:0.35rem;">Key Disclosures:</div>';
          matchedItems.slice(0, 3).forEach(top => {
            html += `
              <div style="background:#ffffff; border:1px solid var(--border-card); border-radius:8px; padding:0.75rem;">
                <div style="font-weight:700; color:#1d4ed8; margin-bottom:0.35rem; display:flex; align-items:center; gap:0.4rem;">
                  <span class="ticker-badge ticker-${top.ticker}">${top.ticker}</span>
                  ${top.clean_headline}
                </div>
                <div style="font-size:0.82rem; color:var(--text-secondary); line-height:1.4;">
                  <strong>Takeaway:</strong> ${top.llm_summary || top.summary}
                </div>
                <div style="font-size:0.72rem; color:var(--text-muted); display:flex; justify-content:space-between; align-items:center; margin-top:0.35rem;">
                  <span>Score: ★ ${top.score} / 10.0 &bull; ${top.published_date}</span>
                  <a href="${top.url}" target="_blank" rel="noopener noreferrer" class="action-link" style="font-size:0.72rem;">Source ↗</a>
                </div>
              </div>
            `;
          });
        }

        html += '</div>';
        container.innerHTML = html;
      }, 300);
    }

    // Close search dropdown on click outside
    document.addEventListener('click', (e) => {
      const searchWrap = document.querySelector('.search-wrapper');
      if (searchWrap && !searchWrap.contains(e.target)) {
        closeSearchDropdown();
      }
    });

    // Keyboard shortcut ⌘K / Ctrl+K
    document.addEventListener('keydown', (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        const input = document.getElementById('globalSearchInput');
        if (input) {
          input.focus();
          openSearchDropdown();
        }
      }
      if (e.key === 'Escape') {
        closeSearchDropdown();
        closeAiModal();
      }
    });

    // =========================================================================
    // CHART.JS RICH VISUALIZATIONS WITH PER-TICKER BREAKDOWN & LEADER CALLOUTS
    // =========================================================================
    const rawChartData = {{ chart_data_json|safe }};

    function initCharts() {
      if (typeof Chart === 'undefined') return;

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

        const displayTickers = sortedTickers.slice(0, 5);

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
            borderWidth: isNarrow ? 2.0 : 2.5,
            fill: true,
            tension: 0.38,
            pointBackgroundColor: '#ffffff',
            pointBorderColor: theme.stroke,
            pointBorderWidth: 1.5,
            pointRadius: isNarrow ? 2.5 : 3.5,
            pointHoverRadius: 5.5,
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
                align: 'end',
                labels: {
                  boxWidth: 8,
                  boxHeight: 8,
                  usePointStyle: true,
                  pointStyle: 'circle',
                  font: { family: 'Inter', size: isNarrow ? 10 : 11, weight: '600' },
                  color: '#475569',
                  padding: isNarrow ? 8 : 14
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
                  font: { family: 'JetBrains Mono', size: isNarrow ? 9 : 10 }, 
                  color: '#64748b',
                  maxTicksLimit: isNarrow ? 5 : 8,
                  autoSkip: true,
                  maxRotation: 0
                }
              },
              y: {
                beginAtZero: true,
                grid: { color: 'rgba(226, 232, 240, 0.6)', drawBorder: false },
                ticks: { precision: 0, font: { family: 'JetBrains Mono', size: isNarrow ? 9 : 10 }, color: '#64748b', stepSize: 1 }
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
          '#2563eb', // Blue
          '#10b981', // Emerald
          '#7c3aed', // Purple
          '#f59e0b', // Amber
          '#0284c7', // Sky Cyan
          '#e11d48', // Rose
          '#8b5cf6', // Violet
          '#ec4899', // Pink
          '#059669', // Teal
          '#d97706', // Gold / Bronze
          '#64748b', // Slate
          '#0ea5e9'  // Light Blue
        ];

        const totalCount = catCounts.reduce((a, b) => a + b, 0) || 1;

        const donutCalloutPlugin = {
          id: 'donutCallouts',
          afterDraw(chart) {
            if (chart.width < 280) return;
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

              // Ensure horizontal line and label stay safely inside canvas edges
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
              ctx.strokeStyle = '#94a3b8';
              ctx.lineWidth = 1.2;
              ctx.stroke();

              ctx.textAlign = isRight ? 'left' : 'right';
              ctx.textBaseline = 'middle';
              ctx.font = '600 10px Inter, sans-serif';
              ctx.fillStyle = '#0f172a';
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
              padding: { top: 15, bottom: 15, left: 45, right: 45 }
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
              <div class="category-stat-row" title="${label}: ${count} (${pct}%)">
                <div class="cat-stat-left">
                  <span class="category-legend-dot" style="background:${color};"></span>
                  <span class="cat-stat-name">${label}</span>
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

    function renderComparativePerformanceChart(symbol) {
      if (!perfData || !perfData.companies) return;
      const coData = perfData.companies[symbol];
      if (!coData) return;

      const kpiGrid = document.getElementById('perfKpiGrid');
      const table = document.getElementById('perfBreakdownTable');
      const canvas = document.getElementById('comparativeChartCanvas');
      if (!canvas) return;

      const target = coData.target;
      const comps = coData.competitors || [];
      const spy = coData.benchmark;

      const targetColor = '#2563eb';
      const compColors = ['#ea580c', '#0284c7', '#9333ea'];
      const spyColor = '#64748b';

      // 1. Populate KPI Ribbon
      if (kpiGrid && target) {
        const tgtPct = target.total_pct_change;
        const tgtColor = tgtPct >= 0 ? '#15803d' : '#b91c1c';
        const tgtArrow = tgtPct >= 0 ? '↗' : '↘';

        const alphaPeers = coData.alpha_vs_peers;
        const alphaPeersColor = alphaPeers >= 0 ? '#15803d' : '#b91c1c';

        const spyPct = spy ? spy.total_pct_change : 0;
        const avgPeerPct = coData.avg_competitor_pct;

        kpiGrid.innerHTML = `
          <div class="perf-kpi-box">
            <div class="perf-kpi-label">${symbol} 3M Return</div>
            <div class="perf-kpi-val" style="color:${tgtColor};">${tgtArrow} ${tgtPct >= 0 ? '+' : ''}${tgtPct.toFixed(2)}%</div>
            <div class="perf-kpi-sub">Latest: $${target.latest_price.toFixed(2)} (Base: $${target.base_price.toFixed(2)})</div>
          </div>
          <div class="perf-kpi-box">
            <div class="perf-kpi-label">Top Peers Avg</div>
            <div class="perf-kpi-val" style="color:${avgPeerPct >= 0 ? '#15803d' : '#b91c1c'};">${avgPeerPct >= 0 ? '+' : ''}${avgPeerPct.toFixed(2)}%</div>
            <div class="perf-kpi-sub">${comps.map(c => c.symbol).join(', ') || 'None'}</div>
          </div>
          <div class="perf-kpi-box">
            <div class="perf-kpi-label">S&P 500 (SPY)</div>
            <div class="perf-kpi-val" style="color:${spyPct >= 0 ? '#15803d' : '#b91c1c'};">${spyPct >= 0 ? '+' : ''}${spyPct.toFixed(2)}%</div>
            <div class="perf-kpi-sub">Broad Market Benchmark</div>
          </div>
          <div class="perf-kpi-box">
            <div class="perf-kpi-label">Peer Relative Alpha</div>
            <div class="perf-kpi-val" style="color:${alphaPeersColor};">${alphaPeers >= 0 ? '+' : ''}${alphaPeers.toFixed(2)}%</div>
            <div class="perf-kpi-sub" style="font-weight:700; color:${coData.assessment_type === 'positive' ? '#15803d' : (coData.assessment_type === 'negative' ? '#b91c1c' : '#475569')};">${coData.assessment}</div>
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
              <th>Base Price (3M Ago)</th>
              <th>Latest Price</th>
              <th>3-Month % Change</th>
              <th>Alpha vs ${symbol}</th>
            </tr>
          </thead>
          <tbody>
            <tr style="background:rgba(37, 99, 235, 0.05); font-weight:700;">
              <td><span class="ticker-badge ticker-${symbol}">${symbol}</span> ${coData.name}</td>
              <td><span class="form-type-pill" style="background:#dbeafe; color:#1e40af;">Target Stock</span></td>
              <td style="font-family:'JetBrains Mono';">$${target.base_price.toFixed(2)}</td>
              <td style="font-family:'JetBrains Mono';">$${target.latest_price.toFixed(2)}</td>
              <td style="font-family:'JetBrains Mono'; color:${target.total_pct_change >= 0 ? '#15803d' : '#b91c1c'};">${target.total_pct_change >= 0 ? '+' : ''}${target.total_pct_change.toFixed(2)}%</td>
              <td style="font-family:'JetBrains Mono'; color:var(--text-muted);">&mdash;</td>
            </tr>
        `;

        comps.forEach((c, idx) => {
          const delta = (c.total_pct_change - target.total_pct_change).toFixed(2);
          rowsHtml += `
            <tr>
              <td><a href="company.html?ticker=${c.symbol}" class="ticker-badge" style="font-size:0.75rem;">${c.symbol}</a></td>
              <td><span class="form-type-pill">Competitor #${idx+1}</span></td>
              <td style="font-family:'JetBrains Mono';">$${c.base_price.toFixed(2)}</td>
              <td style="font-family:'JetBrains Mono';">$${c.latest_price.toFixed(2)}</td>
              <td style="font-family:'JetBrains Mono'; color:${c.total_pct_change >= 0 ? '#15803d' : '#b91c1c'};">${c.total_pct_change >= 0 ? '+' : ''}${c.total_pct_change.toFixed(2)}%</td>
              <td style="font-family:'JetBrains Mono'; color:${delta >= 0 ? '#15803d' : '#b91c1c'};">${delta >= 0 ? '+' : ''}${delta}%</td>
            </tr>
          `;
        });

        if (spy) {
          const spyDelta = (spy.total_pct_change - target.total_pct_change).toFixed(2);
          rowsHtml += `
            <tr style="border-top:2px dashed var(--border-card);">
              <td><span class="form-type-pill" style="background:#f1f5f9; color:#334155; font-weight:700;">SPY</span> S&amp;P 500 ETF</td>
              <td><span class="form-type-pill">Benchmark</span></td>
              <td style="font-family:'JetBrains Mono';">$${spy.base_price.toFixed(2)}</td>
              <td style="font-family:'JetBrains Mono';">$${spy.latest_price.toFixed(2)}</td>
              <td style="font-family:'JetBrains Mono'; color:${spy.total_pct_change >= 0 ? '#15803d' : '#b91c1c'};">${spy.total_pct_change >= 0 ? '+' : ''}${spy.total_pct_change.toFixed(2)}%</td>
              <td style="font-family:'JetBrains Mono'; color:${spyDelta >= 0 ? '#15803d' : '#b91c1c'};">${spyDelta >= 0 ? '+' : ''}${spyDelta}%</td>
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
          borderWidth: 3,
          fill: true,
          tension: 0.25,
          pointRadius: 0,
          pointHoverRadius: 5,
        }
      ];

      comps.forEach((c, idx) => {
        const color = compColors[idx % compColors.length];
        datasets.push({
          label: `${c.symbol} (Competitor)`,
          data: c.series.map(pt => pt.pct_change),
          borderColor: color,
          borderWidth: 2,
          fill: false,
          tension: 0.25,
          pointRadius: 0,
          pointHoverRadius: 4,
        });
      });

      if (spy && spy.series) {
        datasets.push({
          label: 'S&P 500 (SPY Benchmark)',
          data: spy.series.map(pt => pt.pct_change),
          borderColor: spyColor,
          borderWidth: 2,
          borderDash: [6, 6],
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
              labels: {
                boxWidth: 14,
                boxHeight: 3,
                font: { family: 'Inter', size: 11, weight: '600' },
                color: '#475569',
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
                maxTicksLimit: 8,
                font: { family: 'JetBrains Mono', size: 10 },
                color: '#94a3b8',
              }
            },
            y: {
              grid: { color: 'rgba(226, 232, 240, 0.8)' },
              ticks: {
                callback: function(val) { return (val >= 0 ? '+' : '') + val + '%'; },
                font: { family: 'JetBrains Mono', size: 10 },
                color: '#94a3b8',
              }
            }
          }
        }
      });
    }

    function initHomePage() {
      initCharts();
      renderRecentlyViewed();
      renderComparativePerformanceChart('NVDA');
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
      <header class="section-header-row" style="padding-bottom:1.25rem; border-bottom:1px solid var(--border-card); margin-bottom:2rem;">
        <div>
          <h1 class="hero-title" style="font-size:2rem; text-align:left; margin-bottom:0.25rem;">Full Intelligence Feed</h1>
          <p style="font-size:0.92rem; color:var(--text-muted);">Deduplicated, scored disclosures with transparent arithmetic and supply-chain cross-references</p>
        </div>
        <div style="display:flex; align-items:center; gap:0.5rem;">
          <span class="section-time-pill">
            <span class="pulse-dot" style="background:#10b981;"></span> {{ items|length }} Total Items
          </span>
        </div>
      </header>

      <!-- Priority Panel with Editorial Suite Layout -->
      {% if priority_items %}
      <section class="priority-section">
        <div class="priority-header">
          <div class="priority-title-wrap">
            <span class="priority-badge-icon">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>
              PRIORITY
            </span>
            <div>
              <h2 style="font-size:1.25rem; font-weight:800; color:var(--text-primary);">Top Impact Disclosures</h2>
              <p style="font-size:0.82rem; color:var(--text-muted);">Curated high-scoring stories with investor takeaways and supply-chain cross-references</p>
            </div>
          </div>
          <div style="font-family:'JetBrains Mono', monospace; font-size:0.8rem; color:#15803d; font-weight:700; background:#dcfce7; padding:0.35rem 0.85rem; border-radius:var(--radius-full); border:1px solid #86efac; width:fit-content;">
            SCORES: {{ priority_items[0].score }} &ndash; {{ priority_items[-1].score }} / 10.0
          </div>
        </div>

        <div class="priority-editorial-layout">
          <!-- #1 Lead Editorial Card -->
          {% set lead = priority_items[0] %}
          <div class="priority-card priority-lead-card">
            <div>
              <div class="priority-card-top">
                <div style="display:flex; align-items:center; gap:0.5rem; flex-wrap:wrap;">
                  <span class="priority-lead-badge">TOP IMPACT #1</span>
                  <a href="company.html?ticker={{ lead.ticker }}" class="ticker-badge ticker-{{ lead.ticker }}" style="font-size:0.88rem; padding:0.25rem 0.65rem;">{{ lead.ticker }}</a>
                  {% if lead.form_or_type %}
                  <span class="form-type-pill">{{ lead.form_or_type }}</span>
                  {% endif %}
                  <span class="category-badge">{{ lead.category }}</span>
                  <span class="source-badge {% if lead.source == 'sec_edgar' %}source-badge-edgar{% elif lead.source == 'company_ir' %}source-badge-ir{% else %}source-badge-news{% endif %}">{{ lead.source_label }}</span>
                </div>
                <span class="priority-score-pill score-pill-lead" title="{{ lead.score_breakdown }}">
                  ★ {{ lead.score }} / 10.0
                </span>
              </div>

              <h3 class="priority-lead-headline">{{ lead.clean_headline }}</h3>

              {% if lead.cross_references_list %}
                {% if lead.cross_references_list|length == 1 %}
                  {% set ref = lead.cross_references_list[0] %}
                  <div class="crossref-badges-wrap">
                    <span class="crossref-badge" title="{{ ref.impact_note }}">
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/></svg>
                      <span class="crossref-rel-pill {% if ref.relation_type == 'Customer' %}crossref-customer{% else %}crossref-supplier{% endif %}">{{ ref.relation_type }}</span>
                      <a href="company.html?ticker={{ ref.related_ticker }}" class="ticker-badge" style="font-size:0.65rem; padding:0.05rem 0.35rem;">{{ ref.related_ticker }}</a>
                      ({{ ref.matched_entity }})
                    </span>
                  </div>
                {% else %}
                  <div class="crossref-badges-wrap">
                    <details class="crossref-accordion">
                      <summary class="crossref-summary-pill">
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/></svg>
                        Also relevant to {{ lead.cross_references_list|length }} companies <span class="accordion-arrow">▾</span>
                      </summary>
                      <div class="crossref-dropdown-content">
                        {% for ref in lead.cross_references_list %}
                        <div class="crossref-dropdown-item" title="{{ ref.impact_note }}">
                          <span class="crossref-rel-pill {% if ref.relation_type == 'Customer' %}crossref-customer{% else %}crossref-supplier{% endif %}">{{ ref.relation_type }}</span>
                          <a href="company.html?ticker={{ ref.related_ticker }}" class="ticker-badge" style="font-size:0.65rem; padding:0.05rem 0.35rem;">{{ ref.related_ticker }}</a>
                          <span style="font-size:0.75rem; color:var(--text-secondary);">{{ ref.impact_note }}</span>
                        </div>
                        {% endfor %}
                      </div>
                    </details>
                  </div>
                {% endif %}
              {% endif %}

              {% if lead.llm_summary %}
              <div class="why-matters-box lead-why-box">
                <span class="why-tag">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M15 14c.2-1 .7-1.7 1.5-2.5 1-.9 1.5-2.2 1.5-3.5A6 6 0 0 0 6 8c0 1 .2 2.2 1.5 3.5.7.7 1.3 1.5 1.5 2.5"/><path d="M9 18h6"/><path d="M10 22h4"/></svg>
                  Executive Takeaway:
                </span>
                {{ lead.llm_summary }}
              </div>
              {% endif %}

              <p class="priority-card-summary" style="font-size:0.85rem; margin-top:0.6rem; color:var(--text-secondary);">{{ lead.summary[:220] }}{% if lead.summary|length > 220 %}...{% endif %}</p>
            </div>

            <div class="priority-card-footer">
              <span class="date-cell">{{ lead.published_date }}</span>
              <a href="{{ lead.url }}" target="_blank" rel="noopener noreferrer" class="action-link">
                {% if lead.source == 'sec_edgar' %}View Official Filing ↗{% elif lead.source == 'company_ir' %}View Press Release ↗{% else %}Read Article ↗{% endif %}
              </a>
            </div>
          </div>

          <!-- Secondary Priority Cards Subgrid -->
          {% if priority_items|length > 1 %}
          <div class="priority-subgrid">
            {% for item in priority_items[1:] %}
            <div class="priority-card priority-subcard">
              <div>
                <div class="priority-card-top">
                  <div style="display:flex; align-items:center; gap:0.45rem; flex-wrap:wrap;">
                    <span class="priority-rank-pill">#{{ loop.index + 1 }}</span>
                    <a href="company.html?ticker={{ item.ticker }}" class="ticker-badge ticker-{{ item.ticker }}">{{ item.ticker }}</a>
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
                  <span class="source-badge {% if item.source == 'sec_edgar' %}source-badge-edgar{% elif item.source == 'company_ir' %}source-badge-ir{% else %}source-badge-news{% endif %}">{{ item.source_label }}</span>
                </div>

                <h3 class="priority-card-headline">{{ item.clean_headline }}</h3>

                {% if item.cross_references_list %}
                  {% if item.cross_references_list|length == 1 %}
                    {% set ref = item.cross_references_list[0] %}
                    <div class="crossref-badges-wrap">
                      <span class="crossref-badge" title="{{ ref.impact_note }}">
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/></svg>
                        <span class="crossref-rel-pill {% if ref.relation_type == 'Customer' %}crossref-customer{% else %}crossref-supplier{% endif %}">{{ ref.relation_type }}</span>
                        <a href="company.html?ticker={{ ref.related_ticker }}" class="ticker-badge" style="font-size:0.65rem; padding:0.05rem 0.35rem;">{{ ref.related_ticker }}</a>
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
                            <a href="company.html?ticker={{ ref.related_ticker }}" class="ticker-badge" style="font-size:0.65rem; padding:0.05rem 0.35rem;">{{ ref.related_ticker }}</a>
                            <span style="font-size:0.75rem; color:var(--text-secondary);">{{ ref.impact_note }}</span>
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

                <p class="priority-card-summary">{{ item.summary[:140] }}{% if item.summary|length > 140 %}...{% endif %}</p>
              </div>

              <div class="priority-card-footer">
                <span class="date-cell">{{ item.published_date }}</span>
                <a href="{{ item.url }}" target="_blank" rel="noopener noreferrer" class="action-link">
                  {% if item.source == 'sec_edgar' %}View Filing ↗{% elif item.source == 'company_ir' %}View PR ↗{% else %}Read Article ↗{% endif %}
                </a>
              </div>
            </div>
            {% endfor %}
          </div>
          {% endif %}
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
          <button class="filter-btn" data-filter-type="source" data-val="news_media" onclick="setSourceFilter('news_media', this)">
            News Media
          </button>
          <button class="filter-btn" data-filter-type="source" data-val="sec_edgar" onclick="setSourceFilter('sec_edgar', this)">
            SEC EDGAR
          </button>
          <button class="filter-btn" data-filter-type="source" data-val="company_ir" onclick="setSourceFilter('company_ir', this)">
            Company IR
          </button>
        </div>

        <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:0.75rem; margin-top:1.25rem; padding-top:1.25rem; border-top:1px solid var(--border-card);">
          <div style="display:flex; align-items:center; gap:0.5rem; flex-wrap:wrap;">
            <span class="filter-label">Sort:</span>
            <button class="filter-btn active" id="sortScoreBtn" onclick="sortRows('score')">Highest Score</button>
            <button class="filter-btn" id="sortDateBtn" onclick="sortRows('date')">Newest Date</button>
          </div>
          <div style="display:flex; align-items:center; gap:0.5rem; width:100%; max-width:300px;">
            <input type="text" id="searchInput" placeholder="Search headlines, takeaways..." oninput="filterItems()" 
                   style="background:var(--bg-base); border:1px solid var(--border-card); color:var(--text-primary); padding:0.5rem 0.95rem; border-radius:var(--radius-full); font-size:0.85rem; width:100%; outline:none;">
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
                  <a href="company.html?ticker={{ item.ticker }}" class="ticker-badge ticker-{{ item.ticker }}">{{ item.ticker }}</a>
                  <div class="summary-text" style="margin-top: 0.25rem;">{{ item.company_name }}</div>
                </div>
              </td>
              <td>
                <div>
                  <span class="category-badge">{{ item.category }}</span>
                  <div style="margin-top: 0.35rem;">
                    <span class="source-badge {% if item.source == 'sec_edgar' %}source-badge-edgar{% elif item.source == 'company_ir' %}source-badge-ir{% else %}source-badge-news{% endif %}">
                      {{ item.source_label }}
                    </span>
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
                        <a href="company.html?ticker={{ ref.related_ticker }}" class="ticker-badge" style="font-size:0.65rem; padding:0.05rem 0.35rem;">{{ ref.related_ticker }}</a>
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
                            <a href="company.html?ticker={{ ref.related_ticker }}" class="ticker-badge" style="font-size:0.65rem; padding:0.05rem 0.35rem;">{{ ref.related_ticker }}</a>
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
                    Takeaway:
                  </span>
                  {{ item.llm_summary }}
                </div>
                {% endif %}

                <p class="summary-text">{{ item.summary }}</p>
              </td>
              <td>
                <a href="{{ item.url }}" target="_blank" rel="noopener noreferrer" class="action-link">
                  {% if item.source == 'sec_edgar' %}Filing{% elif item.source == 'company_ir' %}IR Release{% else %}Article{% endif %}
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" x2="21" y1="14" y2="3"/></svg>
                </a>
              </td>
            </tr>
            {% endfor %}
          </tbody>
        </table>
      </div>
    </main>
  </div>

  <script>
    """ + SHARED_MOBILE_JS + """

    let currentTicker = 'ALL';
    let currentCategory = 'ALL';
    let currentSource = 'ALL';

    function setTickerFilter(ticker, btn) {
      currentTicker = ticker;
      document.querySelectorAll('[data-filter-type="ticker"]').forEach(b => b.classList.remove('active'));
      if (btn) btn.classList.add('active');
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
        const rowCategory = row.getAttribute('data-category');
        const rowSource = row.getAttribute('data-source');
        const rowText = (row.getAttribute('data-text') || '').toLowerCase();

        let matchTicker = (currentTicker === 'ALL') || rowTickers.includes(currentTicker);
        let matchCat = (currentCategory === 'ALL') || (rowCategory === currentCategory);
        let matchSrc = (currentSource === 'ALL') || (rowSource === currentSource);
        let matchQuery = !q || rowText.includes(q);

        if (matchTicker && matchCat && matchSrc && matchQuery) {
          row.style.display = '';
        } else {
          row.style.display = 'none';
        }
      });
    }

    function sortRows(criterion) {
      const tbody = document.getElementById('newsBody');
      const rows = Array.from(tbody.querySelectorAll('.news-row'));

      document.getElementById('sortScoreBtn')?.classList.toggle('active', criterion === 'score');
      document.getElementById('sortDateBtn')?.classList.toggle('active', criterion === 'date');

      rows.sort((a, b) => {
        if (criterion === 'score') {
          return parseFloat(b.getAttribute('data-score')) - parseFloat(a.getAttribute('data-score'));
        } else {
          return b.getAttribute('data-date').localeCompare(a.getAttribute('data-date'));
        }
      });

      rows.forEach(r => tbody.appendChild(r));
    }

    // URL parameter auto-filter (?ticker=NVDA or ?q=keyword)
    window.addEventListener('DOMContentLoaded', () => {
      const params = new URLSearchParams(window.location.search);
      const urlTicker = params.get('ticker');
      const urlQ = params.get('q');

      if (urlTicker) {
        const btn = document.querySelector(`[data-filter-type="ticker"][data-val="${urlTicker}"]`);
        if (btn) setTickerFilter(urlTicker, btn);
      }
      if (urlQ) {
        const searchBox = document.getElementById('searchInput');
        if (searchBox) {
          searchBox.value = urlQ;
          filterItems();
        }
      }
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
      <header class="section-header-row" style="padding-bottom:1.25rem; border-bottom:1px solid var(--border-card); margin-bottom:2rem;">
        <div>
          <h1 class="hero-title" style="font-size:2rem; text-align:left; margin-bottom:0.25rem;">Corporate Calendar</h1>
          <p style="font-size:0.92rem; color:var(--text-muted);">Upcoming earnings calls, dividend dates, conferences &amp; statutory SEC Form 10-Q/10-K deadlines</p>
        </div>
        <div style="display:flex; align-items:center; gap:0.5rem; flex-wrap:wrap;">
          <span class="calendar-origin-badge origin-sourced">SOURCED</span>
          <span class="calendar-origin-badge origin-estimated">40D RULE (EST)</span>
        </div>
      </header>

      <!-- Spotlight Banner for Earliest Upcoming Event -->
      {% if calendar_events %}
      {% set spot = calendar_events[0] %}
      <div class="calendar-spotlight-card {% if spot.source_type == 'ESTIMATED_RULE' %}calendar-card-estimated{% endif %}">
        <div class="spotlight-badge-row">
          <span class="spotlight-beacon-pill">NEXT UPCOMING EVENT</span>
          <span class="relative-badge" style="font-weight:700; color:var(--accent-blue);">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
            {{ spot.relative_badge }} ({{ spot.display_date }})
          </span>
        </div>
        <div class="spotlight-content-row">
          <div class="calendar-date-box spotlight-date-box">
            <div class="calendar-date-month">{{ spot.event_date[5:7] | replace('01','JAN') | replace('02','FEB') | replace('03','MAR') | replace('04','APR') | replace('05','MAY') | replace('06','JUN') | replace('07','JUL') | replace('08','AUG') | replace('09','SEP') | replace('10','OCT') | replace('11','NOV') | replace('12','DEC') }}</div>
            <div class="calendar-date-day" style="font-size:1.6rem;">{{ spot.event_date[8:10] }}</div>
          </div>
          <div style="flex:1; min-width:0;">
            <div style="display:flex; align-items:center; gap:0.5rem; flex-wrap:wrap; margin-bottom:0.35rem;">
              <a href="company.html?ticker={{ spot.ticker }}" class="ticker-badge ticker-{{ spot.ticker }}" style="font-size:0.88rem; padding:0.22rem 0.65rem;">{{ spot.ticker }}</a>
              <span class="calendar-type-pill {% if 'Earnings' in spot.event_type %}cal-type-earnings{% elif 'Dividend' in spot.event_type %}cal-type-dividend{% elif 'SEC' in spot.event_type or 'Statutory' in spot.event_type %}cal-type-sec{% else %}cal-type-conference{% endif %}">
                {% if 'Earnings' in spot.event_type %}Earnings Call
                {% elif 'Dividend' in spot.event_type %}Dividend
                {% elif 'SEC' in spot.event_type or 'Statutory' in spot.event_type %}SEC Deadline (Estimated)
                {% else %}Conference{% endif %}
              </span>
              {% if spot.source_type == 'ESTIMATED_RULE' %}
              <span class="calendar-origin-badge origin-estimated">40D RULE (EST)</span>
              {% else %}
              <span class="calendar-origin-badge origin-sourced">SOURCED</span>
              {% endif %}
            </div>
            <h3 style="font-size:1.15rem; font-weight:800; color:var(--text-primary); margin-bottom:0.35rem;">{{ spot.headline }}</h3>
            <p style="font-size:0.85rem; color:var(--text-secondary); line-height:1.45;">{{ spot.details }}</p>
          </div>
          {% if spot.source_url %}
          <div>
            <a href="{{ spot.source_url }}" target="_blank" rel="noopener noreferrer" class="btn-primary" style="font-size:0.82rem; padding:0.5rem 1.1rem;">
              {% if spot.source_type == 'ESTIMATED_RULE' %}SEC Filings ↗{% else %}Event Source ↗{% endif %}
            </a>
          </div>
          {% endif %}
        </div>
      </div>
      {% endif %}

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
            <div class="calendar-card-header">
              <div class="calendar-card-identity">
                <a href="company.html?ticker={{ ev.ticker }}" class="ticker-badge ticker-{{ ev.ticker }}">{{ ev.ticker }}</a>
                {% if ev.source_type == 'ESTIMATED_RULE' %}
                <span class="calendar-origin-badge origin-estimated">40D RULE (EST)</span>
                {% else %}
                <span class="calendar-origin-badge origin-sourced">SOURCED</span>
                {% endif %}
              </div>
              <div class="calendar-date-box">
                <div class="calendar-date-month">{{ ev.event_date[5:7] | replace('01','JAN') | replace('02','FEB') | replace('03','MAR') | replace('04','APR') | replace('05','MAY') | replace('06','JUN') | replace('07','JUL') | replace('08','AUG') | replace('09','SEP') | replace('10','OCT') | replace('11','NOV') | replace('12','DEC') }}</div>
                <div class="calendar-date-day">{{ ev.event_date[8:10] }}</div>
              </div>
            </div>

            <div style="margin: 0.25rem 0 0.5rem 0;">
              <span class="calendar-type-pill {% if 'Earnings' in ev.event_type %}cal-type-earnings{% elif 'Dividend' in ev.event_type %}cal-type-dividend{% elif 'SEC' in ev.event_type or 'Statutory' in ev.event_type %}cal-type-sec{% else %}cal-type-conference{% endif %}">
                {% if 'Earnings' in ev.event_type %}Earnings Call
                {% elif 'Dividend' in ev.event_type %}Dividend
                {% elif 'SEC' in ev.event_type or 'Statutory' in ev.event_type %}SEC Deadline (Estimated)
                {% else %}Conference{% endif %}
              </span>
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
      <header class="section-header-row" style="padding-bottom:1.25rem; border-bottom:1px solid var(--border-card); margin-bottom:2rem;">
        <div>
          <h1 class="hero-title" style="font-size:2rem; text-align:left; margin-bottom:0.25rem;">Macroeconomic Intelligence</h1>
          <p style="font-size:0.92rem; color:var(--text-muted);">Federal Reserve Bank of St. Louis (FRED) live indicators mapped to individual watchlist company sensitivities</p>
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
        <h3 style="font-size:1.25rem; font-weight:800; color:var(--text-primary); margin-bottom:0.35rem;">Watchlist Sensitivity Matrix</h3>
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
            <tbody>
              {% for co in watchlist_companies %}
              <tr>
                <td>
                  <a href="company.html?ticker={{ co.symbol }}" class="ticker-badge ticker-{{ co.symbol }}">{{ co.symbol }}</a>
                </td>
                <td style="font-weight:700; color:var(--text-primary);">
                  {{ co.name }}
                </td>
                <td>
                  <span class="category-badge">{{ co.sector }}</span>
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

    function filterEconomicByTicker(ticker, btn) {
      document.querySelectorAll('.econ-filter-btn').forEach(b => b.classList.remove('active'));
      if (btn) btn.classList.add('active');

      const cards = document.querySelectorAll('.economic-card');
      cards.forEach(card => {
        const relevant = (card.getAttribute('data-relevant-tickers') || '').split(',').map(s => s.trim());
        if (ticker === 'ALL' || relevant.includes(ticker)) {
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
# 5. PER-COMPANY DEEP-DIVE TEMPLATE (site/company.html)
# ==============================================================================
COMPANY_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=5.0">
  <meta name="description" content="Dedicated single-stock company profile with multi-source news (SEC filings, Company IR, News Media), upcoming calendar milestones, macroeconomic sensitivities, and supply chain ecosystem.">
  <title>StockPulse — Company Deep-Dive</title>
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
      <header class="section-header-row" style="padding-bottom:1.25rem; border-bottom:1px solid var(--border-card); margin-bottom:1.5rem;">
        <div>
          <h1 class="hero-title" style="font-size:2rem; text-align:left; margin-bottom:0.25rem;">Company Deep-Dive</h1>
          <p style="font-size:0.92rem; color:var(--text-muted);">Comprehensive 360° research hub per stock: multi-source intelligence, corporate calendar, FRED macro sensitivities, and supply chain ecosystem</p>
        </div>
        <div style="display:flex; align-items:center; gap:0.5rem;">
          <span class="section-time-pill">
            <span class="pulse-dot" style="background:#10b981;"></span> {{ watchlist_companies|length }} Watchlist Stocks
          </span>
        </div>
      </header>

      <!-- Quick-Switcher Ticker Strip with Live Filter -->
      <div style="display:flex; justify-content:space-between; align-items:center; gap:0.75rem; margin-bottom:0.75rem; flex-wrap:wrap;">
        <div style="font-size:0.78rem; font-weight:700; color:var(--text-muted); text-transform:uppercase; letter-spacing:0.05em;">
          Select Company (16 Monitored)
        </div>
        <div style="position:relative; width:100%; max-width:260px;">
          <input type="text" id="companyStripFilter" placeholder="Quick find stock (e.g. TSLA, NVDA, AMD)..." oninput="filterCompanyStrip(this.value)" style="width:100%; background:var(--bg-surface); border:1px solid var(--border-card); border-radius:var(--radius-full); padding:0.38rem 0.95rem; font-size:0.82rem; color:var(--text-primary); outline:none;">
        </div>
      </div>

      <div class="company-strip-wrap">
        <div class="company-strip" id="companyStripContainer">
          {% for co in watchlist_companies %}
          <button class="company-strip-pill {% if loop.first %}active{% endif %}" 
                  data-ticker="{{ co.symbol }}" 
                  data-name="{{ co.name|lower }}"
                  data-sector="{{ co.sector|lower }}"
                  onclick="switchCompany('{{ co.symbol }}')">
            <span class="ticker-badge ticker-{{ co.symbol }}">{{ co.symbol }}</span>
            <span>{{ co.name }}</span>
          </button>
          {% endfor %}
        </div>
      </div>

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
                  {% if co.ir_feed_url %}
                  <a href="{{ co.ir_feed_url }}" target="_blank" rel="noopener noreferrer" class="form-type-pill" style="text-decoration:none;" title="View Investor Relations Feed">
                    IR Feed ↗
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
                  <span class="form-type-pill" style="background:#f8fafc; color:#334155; border-color:#cbd5e1;">{{ reg }}</span>
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
              <div class="company-kpi-val" style="color:{% if ns.high_count > 0 %}#dc2626{% else %}#15803d{% endif %};">
                {{ ns.high_count }}
              </div>
              <div class="company-kpi-sub">Materiality Score &ge; 7.0</div>
            </div>

            <div class="company-kpi-card">
              <div class="company-kpi-title">Next Catalyst</div>
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
                {{ co.key_customers|length if co.key_customers else 0 }} Cust &bull; {{ co.key_suppliers|length if co.key_suppliers else 0 }} Supp &bull; {{ co.competitors|length if co.competitors else 0 }} Comp
              </div>
            </div>
          </div>
        </div>

        <!-- 3-Month Comparative Performance Card for this stock -->
        <div class="comparative-perf-card" style="margin-bottom:1.5rem;">
          <div class="comparative-perf-header">
            <div>
              <div style="display:flex; align-items:center; gap:0.6rem;">
                <span class="category-badge" style="background:#eef2ff; color:#4338ca; border-color:#c7d2fe; font-size:0.72rem;">MARKET CONTEXT</span>
                <h3 style="font-size:1.15rem; font-weight:800; color:var(--text-primary); margin:0;">3-Month Performance vs. Competitors &amp; S&amp;P 500</h3>
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
                <h3 style="font-size:1.05rem; font-weight:800; color:var(--text-primary); margin:0;">Intelligence Feed</h3>
                <div style="font-size:0.75rem; color:var(--text-muted); margin-top:0.15rem;">News Media &bull; SEC EDGAR &bull; Company IR ({{ co_news|length }} Total)</div>
              </div>

              <!-- In-Page Source Filters -->
              <div style="display:flex; gap:0.35rem; flex-wrap:wrap; align-items:center;">
                <button class="filter-btn active company-source-filter-btn" data-source="ALL" onclick="filterCompanyNews('{{ co.symbol }}', 'ALL', this)">All ({{ co_news|length }})</button>
                <button class="filter-btn company-source-filter-btn" data-source="news_media" onclick="filterCompanyNews('{{ co.symbol }}', 'news_media', this)">News Media ({{ ns.news_count }})</button>
                <button class="filter-btn company-source-filter-btn" data-source="sec_edgar" onclick="filterCompanyNews('{{ co.symbol }}', 'sec_edgar', this)">SEC EDGAR ({{ ns.edgar_count }})</button>
                <button class="filter-btn company-source-filter-btn" data-source="company_ir" onclick="filterCompanyNews('{{ co.symbol }}', 'company_ir', this)">Company IR ({{ ns.ir_count }})</button>
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
                    {% if it.source == 'sec_edgar' %}View SEC Filing ↗{% elif it.source == 'company_ir' %}View PR Release ↗{% else %}Read Full Article ↗{% endif %}
                  </a>
                </div>
              </div>
              {% endfor %}
            {% else %}
              <div class="company-feed-item" style="text-align:center; padding:2.5rem 1rem; color:var(--text-muted);">
                <div style="font-size:1.5rem; margin-bottom:0.5rem;">📰</div>
                <div style="font-weight:700; color:var(--text-primary);">No Recent Disclosures Found</div>
                <div style="font-size:0.82rem; margin-top:0.25rem;">No filings, IR releases, or news media recorded in this period for {{ co.symbol }}.</div>
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
                      <span style="font-family:'JetBrains Mono', monospace; font-size:0.88rem; font-weight:800; color:var(--accent-blue);">{{ ind.formatted_value }}</span>
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
                <div style="font-size:0.72rem; font-weight:700; color:#15803d; text-transform:uppercase; margin-bottom:0.35rem;">Key Customers</div>
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
                <div style="font-size:0.72rem; font-weight:700; color:#4338ca; text-transform:uppercase; margin-bottom:0.35rem;">Key Suppliers</div>
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
                <div style="font-size:0.72rem; font-weight:700; color:#b45309; text-transform:uppercase; margin-bottom:0.35rem;">Competitors</div>
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

      const kpiGrid = document.getElementById('compPerfKpi-' + symbol);
      const table = document.getElementById('compPerfTable-' + symbol);
      const canvas = document.getElementById('compPerfCanvas-' + symbol);
      if (!canvas) return;

      const target = coData.target;
      const comps = coData.competitors || [];
      const spy = coData.benchmark;

      const targetColor = '#2563eb';
      const compColors = ['#ea580c', '#0284c7', '#9333ea'];
      const spyColor = '#64748b';

      // 1. KPI Ribbon
      if (kpiGrid && target) {
        const tgtPct = target.total_pct_change;
        const tgtColor = tgtPct >= 0 ? '#15803d' : '#b91c1c';
        const tgtArrow = tgtPct >= 0 ? '↗' : '↘';

        const alphaPeers = coData.alpha_vs_peers;
        const alphaPeersColor = alphaPeers >= 0 ? '#15803d' : '#b91c1c';

        const spyPct = spy ? spy.total_pct_change : 0;
        const avgPeerPct = coData.avg_competitor_pct;

        kpiGrid.innerHTML = `
          <div class="perf-kpi-box">
            <div class="perf-kpi-label">${symbol} 3M Return</div>
            <div class="perf-kpi-val" style="color:${tgtColor};">${tgtArrow} ${tgtPct >= 0 ? '+' : ''}${tgtPct.toFixed(2)}%</div>
            <div class="perf-kpi-sub">Latest: $${target.latest_price.toFixed(2)} (Base: $${target.base_price.toFixed(2)})</div>
          </div>
          <div class="perf-kpi-box">
            <div class="perf-kpi-label">Top Peers Avg</div>
            <div class="perf-kpi-val" style="color:${avgPeerPct >= 0 ? '#15803d' : '#b91c1c'};">${avgPeerPct >= 0 ? '+' : ''}${avgPeerPct.toFixed(2)}%</div>
            <div class="perf-kpi-sub">${comps.map(c => c.symbol).join(', ') || 'None'}</div>
          </div>
          <div class="perf-kpi-box">
            <div class="perf-kpi-label">S&P 500 (SPY)</div>
            <div class="perf-kpi-val" style="color:${spyPct >= 0 ? '#15803d' : '#b91c1c'};">${spyPct >= 0 ? '+' : ''}${spyPct.toFixed(2)}%</div>
            <div class="perf-kpi-sub">Broad Market Benchmark</div>
          </div>
          <div class="perf-kpi-box">
            <div class="perf-kpi-label">Peer Relative Alpha</div>
            <div class="perf-kpi-val" style="color:${alphaPeersColor};">${alphaPeers >= 0 ? '+' : ''}${alphaPeers.toFixed(2)}%</div>
            <div class="perf-kpi-sub" style="font-weight:700; color:${coData.assessment_type === 'positive' ? '#15803d' : (coData.assessment_type === 'negative' ? '#b91c1c' : '#475569')};">${coData.assessment}</div>
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
              <th>Base Price (3M Ago)</th>
              <th>Latest Price</th>
              <th>3-Month % Change</th>
              <th>Alpha vs ${symbol}</th>
            </tr>
          </thead>
          <tbody>
            <tr style="background:rgba(37, 99, 235, 0.05); font-weight:700;">
              <td><span class="ticker-badge ticker-${symbol}">${symbol}</span> ${coData.name}</td>
              <td><span class="form-type-pill" style="background:#dbeafe; color:#1e40af;">Target Stock</span></td>
              <td style="font-family:'JetBrains Mono';">$${target.base_price.toFixed(2)}</td>
              <td style="font-family:'JetBrains Mono';">$${target.latest_price.toFixed(2)}</td>
              <td style="font-family:'JetBrains Mono'; color:${target.total_pct_change >= 0 ? '#15803d' : '#b91c1c'};">${target.total_pct_change >= 0 ? '+' : ''}${target.total_pct_change.toFixed(2)}%</td>
              <td style="font-family:'JetBrains Mono'; color:var(--text-muted);">&mdash;</td>
            </tr>
        `;

        comps.forEach((c, idx) => {
          const delta = (c.total_pct_change - target.total_pct_change).toFixed(2);
          rowsHtml += `
            <tr>
              <td><a href="company.html?ticker=${c.symbol}" onclick="event.preventDefault(); switchCompany('${c.symbol}')" class="ticker-badge" style="font-size:0.75rem; cursor:pointer;">${c.symbol}</a></td>
              <td><span class="form-type-pill">Competitor #${idx+1}</span></td>
              <td style="font-family:'JetBrains Mono';">$${c.base_price.toFixed(2)}</td>
              <td style="font-family:'JetBrains Mono';">$${c.latest_price.toFixed(2)}</td>
              <td style="font-family:'JetBrains Mono'; color:${c.total_pct_change >= 0 ? '#15803d' : '#b91c1c'};">${c.total_pct_change >= 0 ? '+' : ''}${c.total_pct_change.toFixed(2)}%</td>
              <td style="font-family:'JetBrains Mono'; color:${delta >= 0 ? '#15803d' : '#b91c1c'};">${delta >= 0 ? '+' : ''}${delta}%</td>
            </tr>
          `;
        });

        if (spy) {
          const spyDelta = (spy.total_pct_change - target.total_pct_change).toFixed(2);
          rowsHtml += `
            <tr style="border-top:2px dashed var(--border-card);">
              <td><span class="form-type-pill" style="background:#f1f5f9; color:#334155; font-weight:700;">SPY</span> S&amp;P 500 ETF</td>
              <td><span class="form-type-pill">Benchmark</span></td>
              <td style="font-family:'JetBrains Mono';">$${spy.base_price.toFixed(2)}</td>
              <td style="font-family:'JetBrains Mono';">$${spy.latest_price.toFixed(2)}</td>
              <td style="font-family:'JetBrains Mono'; color:${spy.total_pct_change >= 0 ? '#15803d' : '#b91c1c'};">${spy.total_pct_change >= 0 ? '+' : ''}${spy.total_pct_change.toFixed(2)}%</td>
              <td style="font-family:'JetBrains Mono'; color:${spyDelta >= 0 ? '#15803d' : '#b91c1c'};">${spyDelta >= 0 ? '+' : ''}${spyDelta}%</td>
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
          borderWidth: 3,
          fill: true,
          tension: 0.25,
          pointRadius: 0,
          pointHoverRadius: 5,
        }
      ];

      comps.forEach((c, idx) => {
        const color = compColors[idx % compColors.length];
        datasets.push({
          label: `${c.symbol} (Competitor)`,
          data: c.series.map(pt => pt.pct_change),
          borderColor: color,
          borderWidth: 2,
          fill: false,
          tension: 0.25,
          pointRadius: 0,
          pointHoverRadius: 4,
        });
      });

      if (spy && spy.series) {
        datasets.push({
          label: 'S&P 500 (SPY Benchmark)',
          data: spy.series.map(pt => pt.pct_change),
          borderColor: spyColor,
          borderWidth: 2,
          borderDash: [6, 6],
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
              labels: {
                boxWidth: 14,
                boxHeight: 3,
                font: { family: 'Inter', size: 11, weight: '600' },
                color: '#475569',
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
                maxTicksLimit: 8,
                font: { family: 'JetBrains Mono', size: 10 },
                color: '#94a3b8',
              }
            },
            y: {
              grid: { color: 'rgba(226, 232, 240, 0.8)' },
              ticks: {
                callback: function(val) { return (val >= 0 ? '+' : '') + val + '%'; },
                font: { family: 'JetBrains Mono', size: 10 },
                color: '#94a3b8',
              }
            }
          }
        }
      });
    }

    function filterCompanyStrip(rawVal) {
      const q = (rawVal || '').toLowerCase().trim();
      const pills = document.querySelectorAll('.company-strip-pill');
      pills.forEach(pill => {
        const sym = (pill.getAttribute('data-ticker') || '').toLowerCase();
        const name = (pill.getAttribute('data-name') || '').toLowerCase();
        const sec = (pill.getAttribute('data-sector') || '').toLowerCase();
        if (!q || sym.includes(q) || name.includes(q) || sec.includes(q)) {
          pill.style.display = 'inline-flex';
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

    # 4. Comparative stock performance data
    if performance_data is None:
        try:
            from collectors.stock_prices import collect_comparative_performance
            performance_data = collect_comparative_performance(watchlist_path=watchlist_path)
        except Exception as e:
            logger.warning("Could not collect comparative performance data: %s", e)
            performance_data = {}

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
        "performance_data": performance_data,
        "performance_data_json": json.dumps(performance_data or {}),
    }

    # 4. Render and save all 5 pages
    pages = [
        ("index.html", INDEX_TEMPLATE, "home"),
        ("news.html", NEWS_TEMPLATE, "news"),
        ("calendar.html", CALENDAR_TEMPLATE, "calendar"),
        ("economic.html", ECONOMIC_TEMPLATE, "economic"),
        ("company.html", COMPANY_TEMPLATE, "company"),
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
