"""Multi-page static HTML dashboard generator with shared sidebar navigation (Phase 6).

Generates:
1. site/index.html    - Home / Overview: Clickable widget preview cards linking to full subpages
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

# ==============================================================================
# SHARED BASE CSS & DESIGN SYSTEM
# ==============================================================================
SHARED_CSS = """
    :root {
      --bg-base: #080c14;
      --bg-surface: #0f172a;
      --bg-surface-elevated: #1e293b;
      --bg-surface-highlight: #243048;
      --bg-hover: #334155;
      --border-subtle: #1e293b;
      --border-card: #283548;
      --border-accent: #3b82f6;
      --text-primary: #f8fafc;
      --text-secondary: #94a3b8;
      --text-muted: #64748b;
      --accent-blue: #3b82f6;
      --accent-indigo: #6366f1;
      --accent-emerald: #10b981;
      --accent-amber: #f59e0b;
      --accent-purple: #8b5cf6;
      --accent-rose: #f43f5e;
      --accent-cyan: #06b6d4;
      --radius-sm: 6px;
      --radius-md: 10px;
      --radius-lg: 14px;
      --radius-xl: 18px;
      --shadow-card: 0 4px 20px -2px rgba(0, 0, 0, 0.5);
      --transition-fast: 0.15s ease;
      --transition-normal: 0.25s ease;
    }

    * {
      box-sizing: border-box;
      margin: 0;
      padding: 0;
    }

    body {
      background-color: var(--bg-base);
      color: var(--text-primary);
      font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      min-height: 100vh;
      line-height: 1.5;
    }

    /* Layout with Persistent Sidebar */
    .app-layout {
      display: flex;
      min-height: 100vh;
    }

    .app-sidebar {
      width: 270px;
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
      padding: 1.75rem 1.25rem;
    }

    .app-main {
      flex: 1;
      margin-left: 270px;
      padding: 2.25rem 3rem;
      max-width: 1480px;
      width: calc(100% - 270px);
    }

    @media (max-width: 1080px) {
      .app-sidebar {
        width: 230px;
        padding: 1.25rem 1rem;
      }
      .app-main {
        margin-left: 230px;
        width: calc(100% - 230px);
        padding: 1.75rem 1.5rem;
      }
    }

    @media (max-width: 768px) {
      .app-layout {
        flex-direction: column;
      }
      .app-sidebar {
        position: relative;
        width: 100%;
        height: auto;
        border-right: none;
        border-bottom: 1px solid var(--border-card);
      }
      .app-main {
        margin-left: 0;
        width: 100%;
        padding: 1.5rem 1rem;
      }
    }

    /* Sidebar Components */
    .sidebar-brand {
      display: flex;
      align-items: center;
      gap: 0.85rem;
      padding-bottom: 1.5rem;
      border-bottom: 1px solid var(--border-card);
      margin-bottom: 1.5rem;
      text-decoration: none;
      color: inherit;
    }

    .logo-badge {
      width: 42px;
      height: 42px;
      border-radius: var(--radius-md);
      background: linear-gradient(135deg, #2563eb, #7c3aed);
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 1.4rem;
      box-shadow: 0 0 15px rgba(59, 130, 246, 0.4);
      flex-shrink: 0;
    }

    .brand-title {
      font-size: 1.15rem;
      font-weight: 800;
      letter-spacing: -0.02em;
      color: var(--text-primary);
      line-height: 1.2;
    }

    .brand-subtitle {
      font-size: 0.72rem;
      color: var(--accent-cyan);
      font-weight: 600;
      letter-spacing: 0.05em;
      text-transform: uppercase;
    }

    .nav-section-title {
      font-size: 0.68rem;
      font-weight: 800;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      color: var(--text-muted);
      margin-bottom: 0.65rem;
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
      padding: 0.75rem 0.85rem;
      border-radius: var(--radius-md);
      color: var(--text-secondary);
      text-decoration: none;
      font-size: 0.9rem;
      font-weight: 600;
      transition: all var(--transition-fast);
      border: 1px solid transparent;
    }

    .nav-link:hover {
      background: var(--bg-surface-elevated);
      color: var(--text-primary);
      border-color: var(--border-card);
    }

    .nav-link.active {
      background: rgba(59, 130, 246, 0.14);
      color: #93c5fd;
      border-color: rgba(59, 130, 246, 0.35);
      box-shadow: 0 0 12px rgba(59, 130, 246, 0.15);
    }

    .nav-item-left {
      display: flex;
      align-items: center;
      gap: 0.75rem;
    }

    .nav-icon {
      font-size: 1.15rem;
      width: 24px;
      text-align: center;
    }

    .nav-count {
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.72rem;
      font-weight: 700;
      background: var(--bg-surface-highlight);
      color: var(--text-secondary);
      padding: 0.15rem 0.45rem;
      border-radius: 999px;
      border: 1px solid var(--border-card);
    }

    .nav-link.active .nav-count {
      background: rgba(59, 130, 246, 0.25);
      color: #bfdbfe;
      border-color: rgba(59, 130, 246, 0.4);
    }

    .sidebar-footer {
      padding-top: 1.5rem;
      border-top: 1px solid var(--border-card);
      margin-top: 1.5rem;
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

    /* Page Header */
    .page-header {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      flex-wrap: wrap;
      gap: 1.25rem;
      padding-bottom: 1.75rem;
      border-bottom: 1px solid var(--border-card);
      margin-bottom: 2rem;
    }

    .page-title {
      font-size: 1.85rem;
      font-weight: 800;
      letter-spacing: -0.03em;
      color: var(--text-primary);
      margin-bottom: 0.35rem;
    }

    .page-subtitle {
      font-size: 0.95rem;
      color: var(--text-secondary);
      line-height: 1.4;
    }

    .top-status-group {
      display: flex;
      align-items: center;
      gap: 0.75rem;
      flex-wrap: wrap;
    }

    .status-pill {
      font-size: 0.8rem;
      font-weight: 600;
      padding: 0.35rem 0.75rem;
      border-radius: 999px;
      border: 1px solid var(--border-card);
      background: var(--bg-surface-elevated);
      display: inline-flex;
      align-items: center;
      gap: 0.45rem;
    }

    /* Stats Grid */
    .stats-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 1rem;
      margin-bottom: 2.25rem;
    }

    .stat-card {
      background: var(--bg-surface);
      border: 1px solid var(--border-card);
      border-radius: var(--radius-lg);
      padding: 1.25rem;
      box-shadow: var(--shadow-card);
      position: relative;
      overflow: hidden;
    }

    .stat-label {
      font-size: 0.75rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: var(--text-muted);
      margin-bottom: 0.4rem;
    }

    .stat-value {
      font-family: 'JetBrains Mono', monospace;
      font-size: 1.85rem;
      font-weight: 800;
      color: var(--text-primary);
      line-height: 1.1;
      margin-bottom: 0.3rem;
    }

    .stat-subtext {
      font-size: 0.75rem;
      color: var(--text-secondary);
    }

    /* Ticker Badges */
    .ticker-badge {
      font-family: 'JetBrains Mono', monospace;
      font-weight: 700;
      font-size: 0.78rem;
      padding: 0.2rem 0.55rem;
      border-radius: 4px;
      display: inline-block;
      letter-spacing: 0.02em;
    }

    .ticker-NVDA  { background: rgba(16, 185, 129, 0.15); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.3); }
    .ticker-AAPL  { background: rgba(59, 130, 246, 0.15); color: #60a5fa; border: 1px solid rgba(59, 130, 246, 0.3); }
    .ticker-MSFT  { background: rgba(139, 92, 246, 0.15); color: #a78bfa; border: 1px solid rgba(139, 92, 246, 0.3); }
    .ticker-GOOGL { background: rgba(99, 102, 241, 0.15); color: #818cf8; border: 1px solid rgba(99, 102, 241, 0.3); }
    .ticker-AMZN  { background: rgba(245, 158, 11, 0.15); color: #fbbf24; border: 1px solid rgba(245, 158, 11, 0.3); }
    .ticker-META  { background: rgba(6, 182, 212, 0.15); color: #22d3ee; border: 1px solid rgba(6, 182, 212, 0.3); }
    .ticker-TSLA  { background: rgba(239, 68, 68, 0.15); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.3); }
    .ticker-JPM   { background: rgba(20, 184, 166, 0.15); color: #2dd4bf; border: 1px solid rgba(20, 184, 166, 0.3); }
    .ticker-JNJ   { background: rgba(244, 63, 94, 0.15); color: #fb7185; border: 1px solid rgba(244, 63, 94, 0.3); }
    .ticker-XOM   { background: rgba(234, 88, 12, 0.15); color: #fb923c; border: 1px solid rgba(234, 88, 12, 0.3); }
    .ticker-WMT   { background: rgba(234, 179, 8, 0.15); color: #facc15; border: 1px solid rgba(234, 179, 8, 0.3); }
    .ticker-DIS   { background: rgba(14, 165, 233, 0.15); color: #38bdf8; border: 1px solid rgba(14, 165, 233, 0.3); }
    .ticker-KO    { background: rgba(220, 38, 38, 0.15); color: #fca5a5; border: 1px solid rgba(220, 38, 38, 0.3); }
    .ticker-PFE   { background: rgba(37, 99, 235, 0.15); color: #93c5fd; border: 1px solid rgba(37, 99, 235, 0.3); }
    .ticker-BA    { background: rgba(100, 116, 139, 0.2); color: #cbd5e1; border: 1px solid rgba(100, 116, 139, 0.35); }

    /* Category Badges */
    .category-badge {
      font-size: 0.72rem;
      font-weight: 700;
      padding: 0.2rem 0.55rem;
      border-radius: var(--radius-sm);
      display: inline-block;
      background: var(--bg-surface-highlight);
      color: var(--text-secondary);
      border: 1px solid var(--border-card);
      white-space: nowrap;
    }

    .source-tag {
      font-size: 0.7rem;
      color: var(--text-muted);
      font-weight: 500;
    }

    /* Score Badges */
    .score-badge {
      font-family: 'JetBrains Mono', monospace;
      font-weight: 800;
      font-size: 0.85rem;
      padding: 0.25rem 0.6rem;
      border-radius: var(--radius-sm);
      display: inline-flex;
      align-items: center;
      gap: 0.2rem;
    }

    .score-high {
      background: rgba(16, 185, 129, 0.15);
      color: #34d399;
      border: 1px solid rgba(16, 185, 129, 0.35);
      box-shadow: 0 0 10px rgba(16, 185, 129, 0.15);
    }

    .score-med {
      background: rgba(245, 158, 11, 0.15);
      color: #fbbf24;
      border: 1px solid rgba(245, 158, 11, 0.3);
    }

    .score-low {
      background: rgba(148, 163, 184, 0.1);
      color: #94a3b8;
      border: 1px solid rgba(148, 163, 184, 0.2);
    }

    /* Supply-Chain Cross-Reference Badges */
    .crossref-badges-wrap {
      display: flex;
      flex-wrap: wrap;
      gap: 0.35rem;
      margin-top: 0.45rem;
    }

    .crossref-badge {
      display: inline-flex;
      align-items: center;
      gap: 0.25rem;
      font-size: 0.7rem;
      font-weight: 600;
      padding: 0.2rem 0.55rem;
      border-radius: var(--radius-sm);
      background: rgba(99, 102, 241, 0.12);
      color: #c7d2fe;
      border: 1px solid rgba(99, 102, 241, 0.35);
      line-height: 1.35;
    }

    .crossref-rel-pill {
      font-size: 0.62rem;
      font-weight: 800;
      text-transform: uppercase;
      letter-spacing: 0.04em;
      padding: 0.1rem 0.35rem;
      border-radius: 3px;
      margin: 0 0.15rem;
    }

    .crossref-customer {
      background: rgba(16, 185, 129, 0.2);
      color: #34d399;
      border: 1px solid rgba(16, 185, 129, 0.4);
    }

    .crossref-supplier {
      background: rgba(245, 158, 11, 0.2);
      color: #fbbf24;
      border: 1px solid rgba(245, 158, 11, 0.4);
    }

    /* Why It Matters Callout Box */
    .why-matters-box {
      margin-top: 0.45rem;
      background: rgba(59, 130, 246, 0.08);
      border-left: 3px solid var(--accent-blue);
      padding: 0.5rem 0.75rem;
      border-radius: 0 var(--radius-sm) var(--radius-sm) 0;
      font-size: 0.85rem;
      color: #bfdbfe;
      line-height: 1.4;
    }

    .why-tag {
      font-weight: 700;
      color: #60a5fa;
      font-size: 0.75rem;
      text-transform: uppercase;
      letter-spacing: 0.03em;
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
    }

    .action-link:hover {
      color: #93c5fd;
      text-decoration: underline;
    }

    /* Buttons */
    .btn-primary {
      background: linear-gradient(135deg, #2563eb, #3b82f6);
      color: #ffffff;
      padding: 0.6rem 1.15rem;
      border-radius: var(--radius-md);
      font-weight: 700;
      font-size: 0.85rem;
      text-decoration: none;
      display: inline-flex;
      align-items: center;
      gap: 0.4rem;
      border: 1px solid rgba(255, 255, 255, 0.15);
      transition: all var(--transition-fast);
    }

    .btn-primary:hover {
      transform: translateY(-1px);
      box-shadow: 0 4px 15px rgba(37, 99, 235, 0.4);
    }

    /* Filter Controls */
    .controls-panel {
      background: var(--bg-surface);
      border: 1px solid var(--border-card);
      border-radius: var(--radius-lg);
      padding: 1.35rem;
      margin-bottom: 1.75rem;
      box-shadow: var(--shadow-card);
    }

    .filter-row {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 0.5rem;
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
      min-width: 80px;
    }

    .filter-btn {
      background: var(--bg-surface-elevated);
      border: 1px solid var(--border-card);
      color: var(--text-secondary);
      font-size: 0.78rem;
      font-weight: 600;
      padding: 0.35rem 0.75rem;
      border-radius: var(--radius-sm);
      cursor: pointer;
      transition: all var(--transition-fast);
      display: inline-flex;
      align-items: center;
      gap: 0.35rem;
    }

    .filter-btn:hover {
      background: var(--bg-hover);
      color: var(--text-primary);
      border-color: var(--border-accent);
    }

    .filter-btn.active {
      background: var(--accent-blue);
      color: #ffffff;
      border-color: var(--accent-blue);
      box-shadow: 0 0 10px rgba(59, 130, 246, 0.4);
    }

    .pill-count {
      font-size: 0.7rem;
      opacity: 0.85;
      font-family: 'JetBrains Mono', monospace;
    }

    /* Table Styles */
    .table-container {
      background: var(--bg-surface);
      border: 1px solid var(--border-card);
      border-radius: var(--radius-lg);
      overflow-x: auto;
      box-shadow: var(--shadow-card);
    }

    table {
      width: 100%;
      border-collapse: collapse;
      text-align: left;
      font-size: 0.875rem;
    }

    th {
      background: var(--bg-surface-elevated);
      color: var(--text-muted);
      font-size: 0.75rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      padding: 0.85rem 1rem;
      border-bottom: 1px solid var(--border-card);
    }

    td {
      padding: 1.1rem 1rem;
      border-bottom: 1px solid var(--border-card);
      vertical-align: top;
    }

    tr.news-row:hover td {
      background: rgba(255, 255, 255, 0.015);
    }

    .headline-text {
      font-weight: 700;
      color: var(--text-primary);
      margin-bottom: 0.25rem;
      font-size: 0.95rem;
      line-height: 1.35;
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

    /* Priority Section & Grid */
    .priority-section {
      background: linear-gradient(180deg, rgba(15, 23, 42, 0.95) 0%, rgba(10, 16, 30, 0.95) 100%);
      border: 1px solid rgba(59, 130, 246, 0.25);
      border-radius: var(--radius-lg);
      padding: 1.75rem;
      margin-bottom: 2.25rem;
      box-shadow: 0 10px 30px rgba(0, 0, 0, 0.3);
    }

    .priority-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 1rem;
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
      background: rgba(245, 158, 11, 0.15);
      color: #fbbf24;
      border: 1px solid rgba(245, 158, 11, 0.3);
      padding: 0.3rem 0.65rem;
      border-radius: var(--radius-sm);
      font-size: 0.75rem;
      font-weight: 800;
      letter-spacing: 0.05em;
    }

    .priority-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
      gap: 1.25rem;
    }

    .priority-card {
      background: var(--bg-surface-elevated);
      border: 1px solid var(--border-card);
      border-radius: var(--radius-md);
      padding: 1.35rem;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      transition: transform var(--transition-fast), border-color var(--transition-fast), box-shadow var(--transition-fast);
      position: relative;
    }

    .priority-card:hover {
      transform: translateY(-2px);
      border-color: var(--border-accent);
      box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4);
    }

    .priority-card-top {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 0.75rem;
    }

    .priority-rank-pill {
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.72rem;
      font-weight: 800;
      color: var(--text-muted);
      background: var(--bg-surface);
      padding: 0.15rem 0.45rem;
      border-radius: 4px;
      border: 1px solid var(--border-card);
    }

    .priority-score-pill {
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.82rem;
      font-weight: 800;
      color: #34d399;
      background: rgba(16, 185, 129, 0.15);
      border: 1px solid rgba(16, 185, 129, 0.35);
      padding: 0.2rem 0.55rem;
      border-radius: 4px;
    }

    .priority-card-headline {
      font-size: 0.98rem;
      font-weight: 700;
      color: var(--text-primary);
      margin: 0.5rem 0;
      line-height: 1.35;
    }

    .priority-why-box {
      background: rgba(59, 130, 246, 0.1);
      border-left: 3px solid var(--accent-blue);
      padding: 0.5rem 0.75rem;
      border-radius: 0 var(--radius-sm) var(--radius-sm) 0;
      font-size: 0.8rem;
      color: #bfdbfe;
      margin: 0.65rem 0;
      line-height: 1.4;
    }

    .priority-card-summary {
      font-size: 0.8rem;
      color: var(--text-secondary);
      line-height: 1.4;
    }

    .priority-card-footer {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding-top: 0.85rem;
      border-top: 1px solid var(--border-subtle);
      margin-top: 1rem;
    }

    /* Forthcoming Corporate Calendar Grid */
    .calendar-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
      gap: 1.25rem;
    }

    .calendar-card {
      background: var(--bg-surface-elevated);
      border: 1px solid var(--border-card);
      border-radius: var(--radius-md);
      padding: 1.35rem;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      transition: transform var(--transition-fast), border-color var(--transition-fast), box-shadow var(--transition-fast);
      position: relative;
    }

    .calendar-card:hover {
      transform: translateY(-2px);
      border-color: var(--border-accent);
      box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4);
    }

    .calendar-card-estimated {
      border: 1px dashed rgba(148, 163, 184, 0.4);
      background: rgba(30, 41, 59, 0.6);
    }

    .calendar-card-top {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      margin-bottom: 0.85rem;
    }

    .calendar-origin-badge {
      font-size: 0.62rem;
      font-weight: 800;
      padding: 0.15rem 0.4rem;
      border-radius: 4px;
      letter-spacing: 0.04em;
    }

    .origin-sourced {
      background: rgba(16, 185, 129, 0.15);
      color: #34d399;
      border: 1px solid rgba(16, 185, 129, 0.35);
    }

    .origin-estimated {
      background: rgba(148, 163, 184, 0.15);
      color: #cbd5e1;
      border: 1px solid rgba(148, 163, 184, 0.35);
    }

    .calendar-type-pill {
      font-size: 0.72rem;
      font-weight: 700;
      padding: 0.2rem 0.5rem;
      border-radius: 4px;
      display: inline-block;
    }

    .cal-type-earnings   { background: rgba(59, 130, 246, 0.15); color: #60a5fa; border: 1px solid rgba(59, 130, 246, 0.3); }
    .cal-type-dividend   { background: rgba(16, 185, 129, 0.15); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.3); }
    .cal-type-sec        { background: rgba(139, 92, 246, 0.15); color: #a78bfa; border: 1px solid rgba(139, 92, 246, 0.3); }
    .cal-type-conference { background: rgba(245, 158, 11, 0.15); color: #fbbf24; border: 1px solid rgba(245, 158, 11, 0.3); }

    .calendar-date-box {
      background: var(--bg-surface);
      border: 1px solid var(--border-card);
      border-radius: var(--radius-md);
      padding: 0.4rem 0.65rem;
      text-align: center;
      min-width: 58px;
    }

    .calendar-date-month {
      font-size: 0.65rem;
      font-weight: 800;
      color: var(--accent-cyan);
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
    }

    .calendar-card-details {
      font-size: 0.8rem;
      color: var(--text-secondary);
      margin: 0 0 1rem 0;
      line-height: 1.45;
    }

    .calendar-card-bottom {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding-top: 0.75rem;
      border-top: 1px solid var(--border-subtle);
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
      grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
      gap: 1.25rem;
    }

    .economic-card {
      background: var(--bg-surface-elevated);
      border: 1px solid var(--border-card);
      border-radius: var(--radius-md);
      padding: 1.35rem;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      transition: transform var(--transition-fast), border-color var(--transition-fast), box-shadow var(--transition-fast);
      position: relative;
    }

    .economic-card:hover {
      transform: translateY(-2px);
      border-color: var(--border-accent);
      box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4);
    }

    .economic-card-top {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      margin-bottom: 0.85rem;
    }

    .economic-category-badge {
      font-size: 0.65rem;
      font-weight: 800;
      letter-spacing: 0.06em;
      text-transform: uppercase;
      color: var(--text-muted);
      background: var(--bg-surface-highlight);
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

    .trend-up   { background: rgba(239, 68, 68, 0.12); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.3); }
    .trend-down { background: rgba(16, 185, 129, 0.12); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.3); }
    .trend-flat { background: rgba(148, 163, 184, 0.12); color: #94a3b8; border: 1px solid rgba(148, 163, 184, 0.3); }

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
    }

    .economic-context {
      font-size: 0.8rem;
      color: var(--text-secondary);
      line-height: 1.45;
      margin-bottom: 1rem;
    }

    .economic-tickers-wrap {
      border-top: 1px solid var(--border-subtle);
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

    /* Home Overview Widgets Grid */
    .home-widgets-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(380px, 1fr));
      gap: 1.5rem;
      margin-bottom: 2.5rem;
    }

    .widget-card {
      background: var(--bg-surface);
      border: 1px solid var(--border-card);
      border-radius: var(--radius-lg);
      padding: 1.5rem;
      box-shadow: var(--shadow-card);
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      transition: all var(--transition-fast);
    }

    .widget-card:hover {
      border-color: rgba(59, 130, 246, 0.4);
      box-shadow: 0 8px 25px rgba(0, 0, 0, 0.4);
    }

    .widget-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding-bottom: 1rem;
      border-bottom: 1px solid var(--border-card);
      margin-bottom: 1.25rem;
    }

    .widget-title {
      font-size: 1.15rem;
      font-weight: 800;
      color: var(--text-primary);
      display: flex;
      align-items: center;
      gap: 0.5rem;
    }

    .widget-footer {
      padding-top: 1.25rem;
      border-top: 1px solid var(--border-card);
      margin-top: 1.25rem;
      display: flex;
      justify-content: flex-end;
    }

    /* Charts Section */
    .charts-grid {
      display: grid;
      grid-template-columns: 2fr 1fr;
      gap: 1.5rem;
      margin-bottom: 2rem;
    }

    @media (max-width: 960px) {
      .charts-grid {
        grid-template-columns: 1fr;
      }
    }

    .chart-card {
      background: var(--bg-surface);
      border: 1px solid var(--border-card);
      border-radius: var(--radius-lg);
      padding: 1.5rem;
      box-shadow: var(--shadow-card);
    }

    .chart-header {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      margin-bottom: 1.25rem;
    }

    .chart-title {
      font-size: 1.05rem;
      font-weight: 700;
      color: var(--text-primary);
    }

    .chart-subtitle {
      font-size: 0.78rem;
      color: var(--text-secondary);
    }

    .chart-canvas-container {
      position: relative;
      height: 240px;
      width: 100%;
    }

    .chart-legend-wrap {
      display: flex;
      flex-wrap: wrap;
      gap: 0.4rem;
    }

    .chart-legend-item {
      font-size: 0.72rem;
      font-weight: 600;
      color: var(--text-secondary);
      background: var(--bg-surface-elevated);
      padding: 0.15rem 0.45rem;
      border-radius: 4px;
      border: 1px solid var(--border-card);
      display: inline-flex;
      align-items: center;
      gap: 0.3rem;
    }

    .legend-dot {
      width: 6px;
      height: 6px;
      border-radius: 50%;
    }

    /* Health Section */
    .health-section {
      background: var(--bg-surface);
      border: 1px solid var(--border-card);
      border-radius: var(--radius-lg);
      padding: 1.75rem;
      box-shadow: var(--shadow-card);
      margin-top: 2.5rem;
    }

    .health-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 1rem;
      padding-bottom: 1.25rem;
      border-bottom: 1px solid var(--border-card);
      margin-bottom: 1.5rem;
    }

    .health-title-group {
      display: flex;
      align-items: center;
      gap: 0.85rem;
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

    .health-badge-healthy  { background: rgba(16, 185, 129, 0.15); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.4); }
    .health-badge-warning  { background: rgba(245, 158, 11, 0.15); color: #fbbf24; border: 1px solid rgba(245, 158, 11, 0.4); }
    .health-badge-critical { background: rgba(239, 68, 68, 0.15); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.4); }

    .health-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
      gap: 1rem;
      margin-bottom: 1.5rem;
    }

    .health-metric-card {
      background: var(--bg-surface-elevated);
      border: 1px solid var(--border-card);
      border-radius: var(--radius-md);
      padding: 1.1rem;
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
"""

# ==============================================================================
# SIDEBAR NAVIGATION MACRO
# ==============================================================================
SIDEBAR_HTML = """
<aside class="app-sidebar">
  <a href="index.html" class="sidebar-brand">
    <div class="logo-badge">⚡</div>
    <div>
      <div class="brand-title">StockPulse</div>
      <div class="brand-subtitle">Intelligence System</div>
    </div>
  </a>

  <div class="nav-section-title">Navigation</div>
  <nav class="sidebar-nav">
    <a href="index.html" class="nav-link {% if active_page == 'home' %}active{% endif %}">
      <div class="nav-item-left">
        <span class="nav-icon">🏠</span>
        <span class="nav-text">Home / Overview</span>
      </div>
    </a>
    <a href="news.html" class="nav-link {% if active_page == 'news' %}active{% endif %}">
      <div class="nav-item-left">
        <span class="nav-icon">⚡</span>
        <span class="nav-text">Intelligence Feed</span>
      </div>
      <span class="nav-count">{{ stats.total }}</span>
    </a>
    <a href="calendar.html" class="nav-link {% if active_page == 'calendar' %}active{% endif %}">
      <div class="nav-item-left">
        <span class="nav-icon">📅</span>
        <span class="nav-text">Corporate Calendar</span>
      </div>
      <span class="nav-count">{{ calendar_events|length }}</span>
    </a>
    <a href="economic.html" class="nav-link {% if active_page == 'economic' %}active{% endif %}">
      <div class="nav-item-left">
        <span class="nav-icon">🏛️</span>
        <span class="nav-text">Economic Snapshot</span>
      </div>
      <span class="nav-count">{{ economic_indicators|length }}</span>
    </a>
  </nav>

  <div class="sidebar-footer">
    <div class="sidebar-health-box">
      <div style="display:flex; align-items:center; gap:0.5rem; margin-bottom:0.35rem;">
        <span class="pulse-dot" style="background:#10b981; box-shadow:0 0 6px #10b981;"></span>
        <span style="font-size:0.75rem; font-weight:700; color:var(--accent-emerald);">SYSTEM HEALTHY</span>
      </div>
      <div style="font-size:0.7rem; color:var(--text-muted); line-height:1.4;">
        15 Watchlist Companies<br>
        Updated: {{ generated_at }}
      </div>
    </div>
  </div>
</aside>
"""

# ==============================================================================
# 1. HOME / OVERVIEW TEMPLATE (site/index.html)
# ==============================================================================
INDEX_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="description" content="Personal stock news dashboard overview with widget preview cards linking to full subpages.">
  <title>StockPulse Intelligence — Home &amp; Overview</title>
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
    """ + SIDEBAR_HTML + """

    <main class="app-main">
      <header class="page-header">
        <div>
          <h1 class="page-title">Executive Briefing &amp; Overview</h1>
          <p class="page-subtitle">Multi-source SEC EDGAR filings, company announcements, corporate calendar &amp; FRED economic indicators</p>
        </div>
        <div class="top-status-group">
          <span class="status-pill">
            <span class="pulse-dot" style="background:#10b981; box-shadow:0 0 6px #10b981;"></span> Live System
          </span>
          <span class="status-pill" style="font-family:'JetBrains Mono', monospace; font-size:0.75rem;">
            Updated: {{ generated_at }}
          </span>
        </div>
      </header>

      <!-- Stats Summary -->
      <div class="stats-grid">
        <div class="stat-card">
          <div class="stat-label">High Impact Stories (≥ 7.0)</div>
          <div class="stat-value" style="color: var(--accent-emerald);">{{ stats.high_priority_count }}</div>
          <div class="stat-subtext">Priority queue items</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">Total Disclosures In Database</div>
          <div class="stat-value">{{ stats.total }}</div>
          <div class="stat-subtext">Deduplicated across sources</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">Average Importance Score</div>
          <div class="stat-value">{{ stats.avg_score }} / 10</div>
          <div class="stat-subtext">Rule-based scoring</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">Active Watchlist</div>
          <div class="stat-value">{{ stats.by_ticker|length }}</div>
          <div class="stat-subtext">US Large-Cap Core Focus</div>
        </div>
      </div>

      <!-- Clickable Widget Preview Cards Grid -->
      <div class="home-widgets-grid">
        <!-- Widget 1: Priority News Preview -->
        <div class="widget-card">
          <div>
            <div class="widget-header">
              <h3 class="widget-title">⚡ Top Priority News</h3>
              <span class="category-badge">{{ priority_items|length }} Top Items</span>
            </div>
            
            <div style="display:flex; flex-direction:column; gap:0.85rem;">
              {% for it in priority_items[:3] %}
              <div style="background:var(--bg-surface-elevated); border:1px solid var(--border-card); border-radius:var(--radius-md); padding:0.85rem;">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:0.35rem;">
                  <span class="ticker-badge ticker-{{ it.ticker }}">{{ it.ticker }}</span>
                  <span class="score-badge score-high" style="font-size:0.75rem; padding:0.15rem 0.45rem;">★ {{ it.score }}</span>
                </div>
                <div style="font-size:0.88rem; font-weight:700; color:var(--text-primary); line-height:1.3; margin-bottom:0.25rem;">
                  {{ it.headline }}
                </div>
                {% if it.llm_summary %}
                <div style="font-size:0.78rem; color:#bfdbfe; background:rgba(59,130,246,0.08); padding:0.35rem 0.55rem; border-radius:4px; border-left:2px solid var(--accent-blue);">
                  💡 {{ it.llm_summary[:110] }}{% if it.llm_summary|length > 110 %}...{% endif %}
                </div>
                {% endif %}
              </div>
              {% endfor %}
            </div>
          </div>

          <div class="widget-footer">
            <a href="news.html" class="btn-primary">View Full Intelligence Feed ({{ stats.total }} Items) &rarr;</a>
          </div>
        </div>

        <!-- Widget 2: Forthcoming Calendar Preview -->
        <div class="widget-card">
          <div>
            <div class="widget-header">
              <h3 class="widget-title">📅 Forthcoming Calendar</h3>
              <span class="category-badge">{{ calendar_events|length }} Scheduled Events</span>
            </div>

            <div style="display:flex; flex-direction:column; gap:0.85rem;">
              {% for ev in calendar_events[:3] %}
              <div style="background:var(--bg-surface-elevated); border:1px solid var(--border-card); border-radius:var(--radius-md); padding:0.85rem; display:flex; justify-content:space-between; align-items:center; gap:0.75rem;">
                <div>
                  <div style="display:flex; align-items:center; gap:0.4rem; margin-bottom:0.25rem;">
                    <span class="ticker-badge ticker-{{ ev.ticker }}">{{ ev.ticker }}</span>
                    <span style="font-size:0.72rem; font-weight:700; color:var(--text-muted);">{{ ev.event_type }}</span>
                  </div>
                  <div style="font-size:0.85rem; font-weight:700; color:var(--text-primary); line-height:1.3;">
                    {{ ev.headline[:55] }}{% if ev.headline|length > 55 %}...{% endif %}
                  </div>
                </div>
                <div class="calendar-date-box" style="padding:0.3rem 0.5rem; min-width:50px;">
                  <div class="calendar-date-month" style="font-size:0.6rem;">{{ ev.event_date[5:7] | replace('01','JAN') | replace('02','FEB') | replace('03','MAR') | replace('04','APR') | replace('05','MAY') | replace('06','JUN') | replace('07','JUL') | replace('08','AUG') | replace('09','SEP') | replace('10','OCT') | replace('11','NOV') | replace('12','DEC') }}</div>
                  <div class="calendar-date-day" style="font-size:1.15rem;">{{ ev.event_date[8:10] }}</div>
                </div>
              </div>
              {% endfor %}
            </div>
          </div>

          <div class="widget-footer">
            <a href="calendar.html" class="btn-primary">View Full Corporate Calendar &rarr;</a>
          </div>
        </div>

        <!-- Widget 3: Economic Snapshot Preview -->
        <div class="widget-card">
          <div>
            <div class="widget-header">
              <h3 class="widget-title">🏛️ Macroeconomic Snapshot</h3>
              <span class="category-badge">FRED API</span>
            </div>

            <div style="display:flex; flex-direction:column; gap:0.75rem;">
              {% for ind in economic_indicators %}
              <div style="background:var(--bg-surface-elevated); border:1px solid var(--border-card); border-radius:var(--radius-md); padding:0.85rem; display:flex; justify-content:space-between; align-items:center;">
                <div>
                  <div style="font-size:0.72rem; font-weight:700; text-transform:uppercase; color:var(--text-muted); margin-bottom:0.15rem;">{{ ind.name }}</div>
                  <div style="font-family:'JetBrains Mono', monospace; font-size:1.4rem; font-weight:800; color:var(--text-primary);">{{ ind.formatted_value }}</div>
                </div>
                <span class="economic-trend-badge {% if ind.change_direction == 'up' %}trend-up{% elif ind.change_direction == 'down' %}trend-down{% else %}trend-flat{% endif %}">
                  {% if ind.change_direction == 'up' %}▲ +{{ ind.change_value }}{% elif ind.change_direction == 'down' %}▼ {{ ind.change_value }}{% else %}■ Steady{% endif %}
                </span>
              </div>
              {% endfor %}
            </div>
          </div>

          <div class="widget-footer">
            <a href="economic.html" class="btn-primary">View Full Economic Intelligence &rarr;</a>
          </div>
        </div>
      </div>

      <!-- Charts & Visual Analytics Section -->
      <section class="charts-section">
        <div class="charts-grid">
          <div class="chart-card">
            <div class="chart-header">
              <div>
                <h3 class="chart-title">📈 Filing &amp; News Frequency Over Time</h3>
                <p class="chart-subtitle">Recent daily disclosure volume per company</p>
              </div>
              <div class="chart-legend-wrap" id="chartLegendBadges"></div>
            </div>
            <div class="chart-canvas-container">
              <canvas id="timelineChart"></canvas>
            </div>
          </div>

          <div class="chart-card">
            <div class="chart-header">
              <div>
                <h3 class="chart-title">📊 Intelligence by Category</h3>
                <p class="chart-subtitle">Distribution across 24 core categories</p>
              </div>
            </div>
            <div class="chart-canvas-container">
              <canvas id="categoryChart"></canvas>
            </div>
          </div>
        </div>
      </section>

      <!-- Health Section -->
      <section class="health-section" id="health">
        <div class="health-header">
          <div class="health-title-group">
            <h3 class="health-title">🛡️ Pipeline Health &amp; Collector Safeguards</h3>
            <span class="health-status-badge health-badge-healthy">
              <span class="pulse-dot" style="background:#10b981; box-shadow:0 0 6px #10b981;"></span>
              HEALTHY · ALL COLLECTORS OPERATIONAL
            </span>
          </div>
          <div style="font-size:0.75rem; color:var(--text-muted);">
            Moving Avg Baseline: {{ latest_run.moving_avg_raw if latest_run else 570 }} items/run
          </div>
        </div>

        <div class="health-grid">
          <div class="health-metric-card">
            <div class="health-metric-title">SEC EDGAR Filings</div>
            <div class="health-metric-val" style="color:var(--accent-emerald);">{{ latest_run.edgar_count if latest_run else 450 }}</div>
            <div class="health-metric-sub">15 companies queried</div>
          </div>
          <div class="health-metric-card">
            <div class="health-metric-title">Company IR Releases</div>
            <div class="health-metric-val" style="color:var(--accent-blue);">{{ latest_run.company_ir_count if latest_run else 100 }}</div>
            <div class="health-metric-sub">Official press room feeds</div>
          </div>
          <div class="health-metric-card">
            <div class="health-metric-title">Total Unique Yield</div>
            <div class="health-metric-val" style="color:var(--accent-purple);">{{ latest_run.total_unique if latest_run else stats.total }}</div>
            <div class="health-metric-sub">After deduplication</div>
          </div>
          <div class="health-metric-card">
            <div class="health-metric-title">High Priority Stories</div>
            <div class="health-metric-val" style="color:var(--accent-amber);">{{ latest_run.high_impact_count if latest_run else stats.high_priority_count }}</div>
            <div class="health-metric-sub">Score ≥ 7.0 / 10.0</div>
          </div>
        </div>
      </section>
    </main>
  </div>

  <script>
    const chartData = {{ chart_data_json|safe }};
    if (document.getElementById('timelineChart') && chartData.timeline_dates) {
      const ctxTimeline = document.getElementById('timelineChart').getContext('2d');
      const tickerColors = {
        'NVDA':  { border: '#10b981', bg: 'rgba(16, 185, 129, 0.14)' },
        'AAPL':  { border: '#3b82f6', bg: 'rgba(59, 130, 246, 0.14)' },
        'MSFT':  { border: '#8b5cf6', bg: 'rgba(139, 92, 246, 0.14)' },
        'GOOGL': { border: '#6366f1', bg: 'rgba(99, 102, 241, 0.14)' },
        'AMZN':  { border: '#f59e0b', bg: 'rgba(245, 158, 11, 0.14)' },
        'META':  { border: '#06b6d4', bg: 'rgba(6, 182, 212, 0.14)' },
        'TSLA':  { border: '#ef4444', bg: 'rgba(239, 68, 68, 0.14)' },
        'JPM':   { border: '#14b8a6', bg: 'rgba(20, 184, 166, 0.14)' },
        'JNJ':   { border: '#f43f5e', bg: 'rgba(244, 63, 94, 0.14)' },
        'XOM':   { border: '#ea580c', bg: 'rgba(234, 88, 12, 0.14)' },
        'WMT':   { border: '#eab308', bg: 'rgba(234, 179, 8, 0.14)' },
        'DIS':   { border: '#0ea5e9', bg: 'rgba(14, 165, 233, 0.14)' },
        'KO':    { border: '#dc2626', bg: 'rgba(220, 38, 38, 0.14)' },
        'PFE':   { border: '#2563eb', bg: 'rgba(37, 99, 235, 0.14)' },
        'BA':    { border: '#64748b', bg: 'rgba(100, 116, 139, 0.18)' }
      };

      const presentTickers = Object.keys(chartData.timeline_series).slice(0, 6);
      const legendBadgesEl = document.getElementById('chartLegendBadges');
      if (legendBadgesEl) {
        legendBadgesEl.innerHTML = presentTickers.map(ticker => {
          const col = tickerColors[ticker]?.border || '#06b6d4';
          return `<span class="chart-legend-item"><span class="legend-dot" style="background:${col};"></span> ${ticker}</span>`;
        }).join('');
      }

      const datasets = presentTickers.map(ticker => {
        const col = tickerColors[ticker] || { border: '#06b6d4', bg: 'rgba(6, 182, 212, 0.1)' };
        return {
          label: ticker,
          data: chartData.timeline_series[ticker] || [],
          borderColor: col.border,
          backgroundColor: col.bg,
          borderWidth: 2,
          pointRadius: 2.5,
          tension: 0.35,
          fill: true
        };
      });

      new Chart(ctxTimeline, {
        type: 'line',
        data: { labels: chartData.timeline_dates, datasets: datasets },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: { legend: { display: false } },
          scales: {
            x: { grid: { color: 'rgba(51, 65, 85, 0.3)' }, ticks: { color: '#94a3b8', font: { size: 10 } } },
            y: { grid: { color: 'rgba(51, 65, 85, 0.3)' }, ticks: { color: '#94a3b8', font: { size: 10 }, stepSize: 1 }, beginAtZero: true }
          }
        }
      });
    }

    const catLabels = chartData.categories || chartData.category_labels || [];
    const catCounts = chartData.category_counts || [];
    if (document.getElementById('categoryChart') && catLabels.length > 0) {
      const ctxCat = document.getElementById('categoryChart').getContext('2d');
      new Chart(ctxCat, {
        type: 'doughnut',
        data: {
          labels: catLabels,
          datasets: [{
            data: catCounts,
            backgroundColor: ['#10b981', '#3b82f6', '#8b5cf6', '#f59e0b', '#06b6d4', '#ef4444', '#14b8a6', '#f43f5e', '#ea580c', '#eab308'],
            borderColor: '#0f172a',
            borderWidth: 2
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: { legend: { position: 'right', labels: { boxWidth: 10, font: { size: 11 }, color: '#cbd5e1', padding: 8 } } }
        }
      });
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
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
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
    """ + SIDEBAR_HTML + """

    <main class="app-main">
      <header class="page-header">
        <div>
          <h1 class="page-title">⚡ Full Intelligence Feed</h1>
          <p class="page-subtitle">Deduplicated, scored disclosures with transparent arithmetic and supply-chain cross-references</p>
        </div>
        <div class="top-status-group">
          <span class="status-pill">
            <span class="pulse-dot" style="background:#10b981;"></span> {{ items|length }} Total Items
          </span>
        </div>
      </header>

      <!-- Priority Panel -->
      {% if priority_items %}
      <section class="priority-section">
        <div class="priority-header">
          <div class="priority-title-wrap">
            <span class="priority-badge-icon">⚡ PRIORITY</span>
            <div>
              <h2 class="priority-title">Top Impact Disclosures</h2>
              <p class="priority-subtitle">Top {{ priority_items|length }} highest scored stories with plain-English investor takeaways</p>
            </div>
          </div>
          <div style="font-family:'JetBrains Mono', monospace; font-size:0.8rem; color:var(--accent-emerald); font-weight:700; background:rgba(16,185,129,0.12); padding:0.35rem 0.75rem; border-radius:6px; border:1px solid rgba(16,185,129,0.3);">
            ⚡ SCORES: {{ priority_items[0].score }} &ndash; {{ priority_items[-1].score }} / 10.0
          </div>
        </div>

        <div class="priority-grid">
          {% for item in priority_items %}
          <div class="priority-card">
            <div>
              <div class="priority-card-top">
                <div style="display:flex; align-items:center; gap:0.45rem;">
                  <span class="priority-rank-pill">#{{ loop.index }}</span>
                  <span class="ticker-badge ticker-{{ item.ticker }}">{{ item.ticker }}</span>
                </div>
                <span class="priority-score-pill" title="{{ item.score_breakdown }}">
                  ★ {{ item.score }}
                </span>
              </div>

              <div style="margin-top:0.65rem;">
                <span class="category-badge">{{ item.category }}</span>
                <span class="source-tag" style="margin-left:0.4rem;">{{ item.source_label }}</span>
              </div>

              <h3 class="priority-card-headline">{{ item.headline }}</h3>
              
              {% if item.cross_references_list %}
              <div class="crossref-badges-wrap">
                {% for ref in item.cross_references_list %}
                <span class="crossref-badge" title="{{ ref.impact_note }}">
                  🔗 <span class="crossref-rel-pill {% if ref.relation_type == 'Customer' %}crossref-customer{% else %}crossref-supplier{% endif %}">{{ ref.relation_type }}</span>
                  <strong class="ticker-badge ticker-{{ ref.related_ticker }}" style="font-size:0.65rem; padding:0.1rem 0.35rem;">{{ ref.related_ticker }}</strong>
                  ({{ ref.matched_entity }})
                </span>
                {% endfor %}
              </div>
              {% endif %}

              {% if item.llm_summary %}
              <div class="priority-why-box">
                <span class="why-tag">💡 Takeaway:</span> {{ item.llm_summary }}
              </div>
              {% endif %}

              <p class="priority-card-summary">{{ item.summary[:150] }}{% if item.summary|length > 150 %}...{% endif %}</p>
            </div>

            <div class="priority-card-footer">
              <span class="date-cell">{{ item.published_date }}</span>
              <a href="{{ item.url }}" target="_blank" rel="noopener noreferrer" class="action-link">
                View Source ↗
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

        <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:1rem; margin-top:1rem; padding-top:1rem; border-top:1px solid var(--border-card);">
          <div style="display:flex; align-items:center; gap:0.5rem;">
            <span class="filter-label">Sort:</span>
            <button class="filter-btn active" id="sortScoreBtn" onclick="sortRows('score')">Highest Score First</button>
            <button class="filter-btn" id="sortDateBtn" onclick="sortRows('date')">Newest Date First</button>
          </div>
          <div style="display:flex; align-items:center; gap:0.5rem;">
            <input type="text" id="searchInput" placeholder="Search headlines, takeaways, suppliers..." oninput="filterItems()" 
                   style="background:var(--bg-surface-elevated); border:1px solid var(--border-card); color:var(--text-primary); padding:0.45rem 0.85rem; border-radius:var(--radius-sm); font-size:0.85rem; width:280px;">
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
                data-text="{{ item.ticker }} {{ item.company_name }} {{ item.category }} {{ item.source_label }} {{ item.form_or_type }} {{ item.headline }} {{ item.cross_ref_summary or '' }} {{ item.llm_summary or '' }} {{ item.summary or '' }}">
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
                    {{ item.source_label }} &bull; {{ item.form_or_type }}
                  </div>
                </div>
              </td>
              <td class="date-cell">
                {{ item.published_date }}
              </td>
              <td>
                <div class="headline-text">{{ item.headline }}</div>
                
                {% if item.cross_references_list %}
                <div class="crossref-badges-wrap">
                  {% for ref in item.cross_references_list %}
                  <span class="crossref-badge" title="{{ ref.impact_note }}">
                    🔗 <span class="crossref-rel-pill {% if ref.relation_type == 'Customer' %}crossref-customer{% else %}crossref-supplier{% endif %}">{{ ref.relation_type }}</span>
                    <strong class="ticker-badge ticker-{{ ref.related_ticker }}" style="font-size:0.65rem; padding:0.1rem 0.35rem;">{{ ref.related_ticker }}</strong>
                    ({{ ref.matched_entity }})
                  </span>
                  {% endfor %}
                </div>
                {% endif %}

                {% if item.llm_summary %}
                <div class="why-matters-box">
                  <span class="why-tag">💡 Why it matters:</span> {{ item.llm_summary }}
                </div>
                {% endif %}

                <div class="summary-text">{{ item.summary }}</div>
              </td>
              <td>
                <a href="{{ item.url }}" target="_blank" rel="noopener noreferrer" class="action-link">
                  View ↗
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
    let activeTickerFilter = 'ALL';
    let activeCategoryFilter = 'ALL';
    let activeSourceFilter = 'ALL';

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
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
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
    """ + SIDEBAR_HTML + """

    <main class="app-main">
      <header class="page-header">
        <div>
          <h1 class="page-title">📅 Forthcoming Corporate Calendar</h1>
          <p class="page-subtitle">Upcoming earnings calls, dividend dates, conferences &amp; statutory SEC Form 10-Q/10-K deadlines</p>
        </div>
        <div class="top-status-group">
          <span class="calendar-origin-badge origin-sourced">📢 SOURCED FROM IR / PR</span>
          <span class="calendar-origin-badge origin-estimated">⚙️ COMPUTED (40D STATUTORY RULE)</span>
        </div>
      </header>

      <!-- Calendar Controls -->
      <div class="controls-panel">
        <div class="filter-row">
          <span class="filter-label">Filter:</span>
          <button class="filter-btn active cal-filter-btn" data-val="ALL" onclick="filterCalendar('ALL', this)">All Events ({{ calendar_events|length }})</button>
          <button class="filter-btn cal-filter-btn" data-val="Earnings" onclick="filterCalendar('Earnings', this)">📊 Earnings Calls</button>
          <button class="filter-btn cal-filter-btn" data-val="Dividend" onclick="filterCalendar('Dividend', this)">💰 Dividend Dates</button>
          <button class="filter-btn cal-filter-btn" data-val="SEC" onclick="filterCalendar('SEC', this)">⚖️ SEC Filing Deadlines</button>
          <button class="filter-btn cal-filter-btn" data-val="Conference" onclick="filterCalendar('Conference', this)">🎤 Conferences</button>
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
                <div style="display:flex; align-items:center; gap:0.4rem;">
                  <span class="ticker-badge ticker-{{ ev.ticker }}">{{ ev.ticker }}</span>
                  {% if ev.source_type == 'ESTIMATED_RULE' %}
                  <span class="calendar-origin-badge origin-estimated">⚙️ COMPUTED (40D RULE)</span>
                  {% else %}
                  <span class="calendar-origin-badge origin-sourced">📢 SOURCED</span>
                  {% endif %}
                </div>
                <span class="calendar-type-pill {% if 'Earnings' in ev.event_type %}cal-type-earnings{% elif 'Dividend' in ev.event_type %}cal-type-dividend{% elif 'SEC' in ev.event_type or 'Statutory' in ev.event_type %}cal-type-sec{% else %}cal-type-conference{% endif %}">
                  {% if 'Earnings' in ev.event_type %}📊 Earnings Call
                  {% elif 'Dividend' in ev.event_type %}💰 Dividend
                  {% elif 'SEC' in ev.event_type or 'Statutory' in ev.event_type %}⚖️ SEC Deadline (Estimated)
                  {% else %}🎤 Conference{% endif %}
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
              ⏳ <strong>{{ ev.relative_badge }}</strong> ({{ ev.display_date }})
            </span>
            {% if ev.source_url %}
            <a href="{{ ev.source_url }}" target="_blank" rel="noopener noreferrer" class="action-link" style="font-size:0.75rem;">
              {% if ev.source_type == 'ESTIMATED_RULE' %}SEC Filings ↗{% else %}Source ↗{% endif %}
            </a>
            {% endif %}
          </div>
        </div>
        {% endfor %}
      </div>
    </main>
  </div>

  <script>
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
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
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
    """ + SIDEBAR_HTML + """

    <main class="app-main">
      <header class="page-header">
        <div>
          <h1 class="page-title">🏛️ Macroeconomic Intelligence</h1>
          <p class="page-subtitle">Federal Reserve Bank of St. Louis (FRED) live indicators mapped to individual watchlist company sensitivities</p>
        </div>
        <div class="top-status-group">
          <span class="status-pill" style="color:var(--accent-indigo); font-weight:700;">
            📈 St. Louis Fed (FRED) Feed
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
      <section style="background:var(--bg-surface); border:1px solid var(--border-card); border-radius:var(--radius-lg); padding:1.75rem; box-shadow:var(--shadow-card);">
        <h3 style="font-size:1.15rem; font-weight:800; color:var(--text-primary); margin-bottom:0.35rem;">📊 Watchlist Sensitivity Matrix</h3>
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
                  <span style="color:#34d399; font-weight:700;">● Active</span>
                  {% else %}
                  <span style="color:var(--text-muted);">&mdash;</span>
                  {% endif %}
                </td>
                <td>
                  {% if 'inflation' in co.economic_sensitivities %}
                  <span style="color:#fbbf24; font-weight:700;">● Active</span>
                  {% else %}
                  <span style="color:var(--text-muted);">&mdash;</span>
                  {% endif %}
                </td>
                <td>
                  {% if 'unemployment' in co.economic_sensitivities %}
                  <span style="color:#60a5fa; font-weight:700;">● Active</span>
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
    items = get_all_news_items(order_by="score", db_path=db_path)
    priority_items = get_top_priority_items(limit=8, db_path=db_path)
    stats = get_news_stats(db_path=db_path)
    chart_data = get_chart_data(db_path=db_path)
    economic_indicators = get_economic_indicators(db_path=db_path)
    calendar_events = get_forthcoming_calendar(limit=30, db_path=db_path)
    recent_runs = get_recent_pipeline_runs(limit=5, db_path=db_path)
    latest_run = recent_runs[0] if recent_runs else None
    now_str = datetime.now().strftime("%b %d, %Y %H:%M:%S")

    # 2. Load watchlist for sensitivity matrix
    watchlist_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "watchlist.yaml")
    watchlist_companies: List[Dict[str, Any]] = []
    if os.path.exists(watchlist_path):
        with open(watchlist_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
            watchlist_companies = cfg.get("tickers", [])

    common_context = {
        "items": items,
        "priority_items": priority_items,
        "stats": stats,
        "chart_data_json": json.dumps(chart_data),
        "economic_indicators": economic_indicators,
        "calendar_events": calendar_events,
        "recent_runs": recent_runs,
        "latest_run": latest_run,
        "generated_at": now_str,
        "watchlist_companies": watchlist_companies,
    }

    # 3. Render and save all 4 pages
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
