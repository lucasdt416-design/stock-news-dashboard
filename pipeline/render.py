"""Static HTML dashboard generator with Priority Panel, Score Ranking, AI Takeaways, and Interactive Charts."""

import json
import os
from datetime import datetime
from typing import Optional
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

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="description" content="Personal stock news dashboard with rule-based scoring, plain-English 'Why It Matters' explanations, interactive charts, and multi-source intelligence.">
  <title>Stock News Dashboard — Priority Intelligence</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600;700&display=swap" rel="stylesheet">
  <!-- Chart.js CDN (lightweight, zero-build dependency) -->
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.7/dist/chart.umd.min.js"></script>
  <style>
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
      padding-bottom: 4rem;
    }

    .container {
      max-width: 1360px;
      margin: 0 auto;
      padding: 2rem 1.5rem;
    }

    header {
      display: flex;
      flex-wrap: wrap;
      justify-content: space-between;
      align-items: center;
      gap: 1.5rem;
      padding-bottom: 1.75rem;
      border-bottom: 1px solid var(--border-card);
      margin-bottom: 2rem;
    }

    .brand {
      display: flex;
      align-items: center;
      gap: 0.85rem;
    }

    .logo-badge {
      width: 44px;
      height: 44px;
      border-radius: var(--radius-md);
      background: linear-gradient(135deg, #2563eb, #7c3aed);
      display: flex;
      align-items: center;
      justify-content: center;
      font-weight: 800;
      font-size: 1.25rem;
      color: #fff;
      box-shadow: 0 0 16px rgba(59, 130, 246, 0.45);
    }

    .brand-text h1 {
      font-size: 1.45rem;
      font-weight: 700;
      letter-spacing: -0.02em;
    }

    .brand-text p {
      font-size: 0.85rem;
      color: var(--text-secondary);
    }

    .header-meta {
      display: flex;
      align-items: center;
      gap: 1rem;
      font-size: 0.85rem;
      color: var(--text-muted);
      background: var(--bg-surface);
      padding: 0.5rem 1rem;
      border-radius: var(--radius-sm);
      border: 1px solid var(--border-card);
    }

    .status-indicator {
      display: inline-block;
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background-color: var(--accent-emerald);
      box-shadow: 0 0 8px var(--accent-emerald);
    }

    /* Summary Stats Grid */
    .stats-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 1.25rem;
      margin-bottom: 2.25rem;
    }

    .stat-card {
      background: var(--bg-surface);
      border: 1px solid var(--border-card);
      border-radius: var(--radius-md);
      padding: 1.25rem;
      transition: transform 0.15s ease, border-color 0.15s ease;
      box-shadow: var(--shadow-card);
    }

    .stat-card:hover {
      border-color: var(--border-accent);
      transform: translateY(-2px);
    }

    .stat-label {
      font-size: 0.75rem;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: var(--text-muted);
      margin-bottom: 0.35rem;
    }

    .stat-value {
      font-size: 1.65rem;
      font-weight: 700;
      color: var(--text-primary);
      font-feature-settings: "tnum";
    }

    .stat-subtext {
      font-size: 0.8rem;
      color: var(--text-secondary);
      margin-top: 0.35rem;
    }

    /* ========================================================
       PRIORITY INTELLIGENCE PANEL
       ======================================================== */
    .priority-section {
      background: radial-gradient(ellipse at top, rgba(37, 99, 235, 0.15) 0%, rgba(15, 23, 42, 0.95) 70%);
      border: 1px solid rgba(59, 130, 246, 0.4);
      border-radius: var(--radius-xl);
      padding: 1.75rem;
      margin-bottom: 2.5rem;
      box-shadow: 0 12px 40px -10px rgba(0, 0, 0, 0.7), 0 0 25px rgba(59, 130, 246, 0.15);
      position: relative;
      overflow: hidden;
    }

    .priority-section::before {
      content: "";
      position: absolute;
      top: 0;
      left: 0;
      right: 0;
      height: 3px;
      background: linear-gradient(90deg, #3b82f6, #10b981, #8b5cf6, #3b82f6);
    }

    .priority-header {
      display: flex;
      flex-wrap: wrap;
      justify-content: space-between;
      align-items: center;
      gap: 1rem;
      margin-bottom: 1.35rem;
      padding-bottom: 1rem;
      border-bottom: 1px solid rgba(255, 255, 255, 0.08);
    }

    .priority-title-wrap {
      display: flex;
      align-items: center;
      gap: 0.75rem;
    }

    .priority-badge-icon {
      background: linear-gradient(135deg, #f59e0b, #ef4444);
      color: #fff;
      font-size: 0.85rem;
      font-weight: 800;
      padding: 0.25rem 0.6rem;
      border-radius: var(--radius-sm);
      display: inline-flex;
      align-items: center;
      gap: 0.3rem;
      box-shadow: 0 0 12px rgba(245, 158, 11, 0.4);
    }

    .priority-title {
      font-size: 1.2rem;
      font-weight: 800;
      color: #ffffff;
      letter-spacing: -0.01em;
    }

    .priority-subtitle {
      font-size: 0.82rem;
      color: var(--text-secondary);
    }

    .priority-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(310px, 1fr));
      gap: 1.15rem;
    }

    .priority-card {
      background: rgba(15, 23, 42, 0.85);
      border: 1px solid rgba(71, 85, 105, 0.5);
      border-radius: var(--radius-lg);
      padding: 1.25rem;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      gap: 0.85rem;
      position: relative;
      transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
      backdrop-filter: blur(8px);
    }

    .priority-card:hover {
      border-color: #34d399;
      transform: translateY(-3px);
      box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.5), 0 0 15px rgba(52, 211, 153, 0.2);
      background: rgba(24, 34, 53, 0.95);
    }

    .priority-card-top {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 0.5rem;
    }

    .priority-rank-pill {
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.72rem;
      font-weight: 700;
      color: var(--text-muted);
      background: rgba(255, 255, 255, 0.05);
      padding: 0.15rem 0.45rem;
      border-radius: 4px;
    }

    .priority-score-pill {
      display: inline-flex;
      align-items: center;
      gap: 0.25rem;
      font-family: 'JetBrains Mono', monospace;
      font-weight: 800;
      font-size: 0.92rem;
      padding: 0.25rem 0.65rem;
      border-radius: var(--radius-sm);
      background: rgba(16, 185, 129, 0.22);
      color: #34d399;
      border: 1px solid rgba(16, 185, 129, 0.5);
      box-shadow: 0 0 10px rgba(16, 185, 129, 0.25);
    }

    .priority-card-headline {
      font-size: 0.98rem;
      font-weight: 700;
      color: #ffffff;
      line-height: 1.4;
      margin-top: 0.4rem;
    }

    .priority-why-box {
      margin: 0.45rem 0;
      padding: 0.45rem 0.65rem;
      border-radius: var(--radius-sm);
      background: rgba(59, 130, 246, 0.12);
      border-left: 3px solid var(--accent-blue);
      font-size: 0.8rem;
      color: #e2e8f0;
      line-height: 1.4;
    }

    .why-matters-box {
      margin: 0.4rem 0;
      padding: 0.45rem 0.7rem;
      border-radius: var(--radius-sm);
      background: rgba(16, 185, 129, 0.08);
      border-left: 3px solid var(--accent-emerald);
      font-size: 0.82rem;
      color: #e2e8f0;
      line-height: 1.4;
    }

    .why-tag {
      font-weight: 700;
      color: #34d399;
      margin-right: 0.25rem;
    }

    .priority-why-box .why-tag {
      color: #60a5fa;
    }

    .priority-card-summary {
      font-size: 0.78rem;
      color: var(--text-muted);
      line-height: 1.35;
      margin-top: 0.25rem;
    }

    .priority-card-footer {
      display: flex;
      justify-content: space-between;
      align-items: center;
      border-top: 1px solid rgba(255, 255, 255, 0.08);
      padding-top: 0.75rem;
      margin-top: 0.5rem;
    }

    /* ========================================================
       ANALYTICS & VISUAL TRENDS SECTION (CHART.JS)
       ======================================================== */
    .charts-section {
      margin-bottom: 2.75rem;
    }

    .charts-grid {
      display: grid;
      grid-template-columns: 1.45fr 1fr;
      gap: 1.25rem;
    }

    .chart-card {
      background: var(--bg-surface);
      border: 1px solid var(--border-card);
      border-radius: var(--radius-lg);
      padding: 1.35rem;
      box-shadow: var(--shadow-card);
      display: flex;
      flex-direction: column;
      justify-content: space-between;
    }

    .chart-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 0.75rem;
      margin-bottom: 1rem;
    }

    .chart-legend-wrap {
      display: flex;
      align-items: center;
      gap: 0.75rem;
      background: var(--bg-surface-elevated);
      padding: 0.3rem 0.75rem;
      border-radius: var(--radius-sm);
      border: 1px solid var(--border-card);
    }

    .chart-legend-item {
      display: inline-flex;
      align-items: center;
      gap: 0.35rem;
      font-size: 0.76rem;
      font-weight: 700;
      font-family: 'JetBrains Mono', monospace;
      color: var(--text-primary);
    }

    .legend-dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      display: inline-block;
    }

    .chart-title {
      font-size: 0.98rem;
      font-weight: 700;
      color: var(--text-primary);
      display: flex;
      align-items: center;
      gap: 0.4rem;
    }

    .chart-subtitle {
      font-size: 0.78rem;
      color: var(--text-muted);
      margin-top: 0.2rem;
    }

    .chart-canvas-container {
      position: relative;
      width: 100%;
      height: 250px;
    }

    .chart-canvas-container.donut-container {
      height: 250px;
      display: flex;
      align-items: center;
      justify-content: center;
    }

    /* Section Divider */
    .feed-section-header {
      display: flex;
      align-items: center;
      gap: 1rem;
      margin-bottom: 1.25rem;
    }

    .feed-section-header h2 {
      font-size: 1.15rem;
      font-weight: 700;
      letter-spacing: -0.01em;
      white-space: nowrap;
    }

    .feed-divider-line {
      height: 1px;
      background: var(--border-card);
      flex-grow: 1;
    }

    /* Controls Panel */
    .controls-panel {
      background: var(--bg-surface);
      border: 1px solid var(--border-card);
      border-radius: var(--radius-lg);
      padding: 1.25rem;
      margin-bottom: 1.5rem;
      display: flex;
      flex-direction: column;
      gap: 1rem;
    }

    .filter-row {
      display: flex;
      flex-wrap: wrap;
      gap: 0.5rem;
      align-items: center;
    }

    .filter-label {
      font-size: 0.75rem;
      font-weight: 600;
      color: var(--text-muted);
      text-transform: uppercase;
      margin-right: 0.35rem;
      min-width: 65px;
    }

    .filter-btn {
      background: var(--bg-surface-elevated);
      color: var(--text-secondary);
      border: 1px solid var(--border-card);
      border-radius: var(--radius-sm);
      padding: 0.4rem 0.85rem;
      font-size: 0.82rem;
      font-weight: 500;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 0.4rem;
      transition: all 0.15s ease;
    }

    .filter-btn:hover {
      background: var(--bg-hover);
      color: var(--text-primary);
    }

    .filter-btn.active {
      background: var(--accent-blue);
      color: #ffffff;
      border-color: var(--accent-blue);
      font-weight: 600;
      box-shadow: 0 0 12px rgba(59, 130, 246, 0.35);
    }

    .pill-count {
      font-size: 0.72rem;
      padding: 0.1rem 0.4rem;
      border-radius: 999px;
      background: rgba(255, 255, 255, 0.15);
    }

    .bottom-controls {
      display: flex;
      flex-wrap: wrap;
      justify-content: space-between;
      align-items: center;
      gap: 1rem;
      border-top: 1px solid rgba(40, 53, 72, 0.5);
      padding-top: 0.85rem;
    }

    .sort-group {
      display: flex;
      align-items: center;
      gap: 0.5rem;
    }

    .search-box {
      position: relative;
      flex-grow: 1;
      max-width: 380px;
    }

    .search-box input {
      width: 100%;
      background: var(--bg-base);
      border: 1px solid var(--border-card);
      border-radius: var(--radius-sm);
      padding: 0.55rem 0.85rem 0.55rem 2.25rem;
      color: var(--text-primary);
      font-size: 0.875rem;
      outline: none;
      transition: border-color 0.15s ease;
    }

    .search-box input:focus {
      border-color: var(--accent-blue);
    }

    .search-icon {
      position: absolute;
      left: 0.75rem;
      top: 50%;
      transform: translateY(-50%);
      color: var(--text-muted);
      pointer-events: none;
      font-size: 0.9rem;
    }

    /* Table & Cards */
    .table-container {
      background: var(--bg-surface);
      border: 1px solid var(--border-card);
      border-radius: var(--radius-lg);
      overflow: hidden;
      box-shadow: var(--shadow-card);
    }

    table {
      width: 100%;
      border-collapse: collapse;
      text-align: left;
      font-size: 0.875rem;
    }

    thead th {
      background: var(--bg-surface-elevated);
      color: var(--text-muted);
      font-size: 0.75rem;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      padding: 0.85rem 1.25rem;
      border-bottom: 1px solid var(--border-card);
    }

    tbody tr {
      border-bottom: 1px solid rgba(40, 53, 72, 0.5);
      transition: background-color 0.12s ease;
    }

    tbody tr:hover {
      background-color: rgba(255, 255, 255, 0.025);
    }

    td {
      padding: 1rem 1.25rem;
      vertical-align: middle;
    }

    /* Score Badges */
    .score-badge {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-width: 44px;
      padding: 0.25rem 0.6rem;
      border-radius: var(--radius-sm);
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.85rem;
      font-weight: 700;
      cursor: help;
      position: relative;
    }

    .score-high {
      background: rgba(16, 185, 129, 0.2);
      color: #34d399;
      border: 1px solid rgba(16, 185, 129, 0.4);
      box-shadow: 0 0 10px rgba(16, 185, 129, 0.2);
    }

    .score-med {
      background: rgba(59, 130, 246, 0.2);
      color: #60a5fa;
      border: 1px solid rgba(59, 130, 246, 0.35);
    }

    .score-low {
      background: rgba(148, 163, 184, 0.15);
      color: #94a3b8;
      border: 1px solid rgba(148, 163, 184, 0.3);
    }

    .ticker-badge {
      display: inline-flex;
      align-items: center;
      font-family: 'JetBrains Mono', monospace;
      font-weight: 700;
      font-size: 0.85rem;
      padding: 0.2rem 0.55rem;
      border-radius: var(--radius-sm);
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
    .ticker-KO    { background: rgba(220, 38, 38, 0.15); color: #f87171; border: 1px solid rgba(220, 38, 38, 0.3); }
    .ticker-PFE   { background: rgba(37, 99, 235, 0.15); color: #93c5fd; border: 1px solid rgba(37, 99, 235, 0.3); }
    .ticker-BA    { background: rgba(100, 116, 139, 0.2); color: #cbd5e1; border: 1px solid rgba(100, 116, 139, 0.35); }
    .ticker-default { background: rgba(156, 163, 175, 0.15); color: #d1d5db; border: 1px solid rgba(156, 163, 175, 0.3); }

    .category-badge {
      display: inline-block;
      font-size: 0.75rem;
      font-weight: 600;
      padding: 0.2rem 0.5rem;
      border-radius: var(--radius-sm);
      background: var(--bg-surface-elevated);
      color: var(--text-secondary);
      border: 1px solid var(--border-card);
    }

    .source-tag {
      font-size: 0.72rem;
      font-weight: 600;
      text-transform: uppercase;
      color: var(--text-muted);
    }

    .headline-text {
      font-weight: 700;
      color: var(--text-primary);
      margin-bottom: 0.2rem;
      line-height: 1.4;
    }

    .summary-text {
      font-size: 0.78rem;
      color: var(--text-muted);
      line-height: 1.35;
    }

    .date-cell {
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.82rem;
      color: var(--text-secondary);
      white-space: nowrap;
    }

    .action-link {
      display: inline-flex;
      align-items: center;
      gap: 0.3rem;
      color: var(--accent-blue);
      text-decoration: none;
      font-size: 0.82rem;
      font-weight: 500;
      padding: 0.35rem 0.65rem;
      border-radius: var(--radius-sm);
      background: rgba(59, 130, 246, 0.08);
      border: 1px solid rgba(59, 130, 246, 0.2);
      transition: all 0.15s ease;
      white-space: nowrap;
    }

    .action-link:hover {
      background: rgba(59, 130, 246, 0.2);
      border-color: var(--accent-blue);
      color: #93c5fd;
    }

    .no-results {
      text-align: center;
      padding: 3.5rem 1rem;
      color: var(--text-muted);
    }

    /* Forthcoming Calendar (Category #24) Section */
    .calendar-section {
      margin-top: 3.5rem;
      background: var(--bg-surface);
      border: 1px solid var(--border-card);
      border-radius: var(--radius-lg);
      padding: 1.75rem;
      box-shadow: 0 10px 25px rgba(0, 0, 0, 0.25);
    }

    .calendar-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 1rem;
      padding-bottom: 1.25rem;
      border-bottom: 1px solid var(--border-card);
      margin-bottom: 1.5rem;
    }

    .calendar-filter-bar {
      display: flex;
      gap: 0.4rem;
      flex-wrap: wrap;
    }

    .cal-filter-btn {
      background: var(--bg-surface-elevated);
      color: var(--text-secondary);
      border: 1px solid var(--border-card);
      padding: 0.35rem 0.75rem;
      border-radius: var(--radius-sm);
      font-size: 0.8rem;
      font-weight: 600;
      cursor: pointer;
      transition: all var(--transition-fast);
    }

    .cal-filter-btn:hover {
      background: var(--bg-surface-highlight);
      color: var(--text-primary);
      border-color: var(--border-accent);
    }

    .cal-filter-btn.active {
      background: var(--accent-blue);
      color: #fff;
      border-color: var(--accent-blue);
      box-shadow: 0 0 10px rgba(59, 130, 246, 0.35);
    }

    .calendar-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
      gap: 1.25rem;
    }

    .calendar-card {
      background: var(--bg-surface-elevated);
      border: 1px solid var(--border-card);
      border-radius: var(--radius-md);
      padding: 1.25rem;
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
      border: 1px dashed rgba(6, 182, 212, 0.45);
      background: rgba(15, 23, 42, 0.55);
    }

    .calendar-card-estimated:hover {
      border-color: var(--accent-cyan);
      box-shadow: 0 8px 24px rgba(6, 182, 212, 0.18);
    }

    .calendar-card-top {
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 0.75rem;
      margin-bottom: 0.85rem;
    }

    .calendar-date-box {
      background: var(--bg-surface-highlight);
      border: 1px solid var(--border-card);
      border-radius: var(--radius-sm);
      padding: 0.35rem 0.65rem;
      text-align: center;
      min-width: 68px;
    }

    .calendar-date-month {
      font-size: 0.65rem;
      font-weight: 800;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: var(--accent-blue);
    }

    .calendar-date-day {
      font-size: 1.15rem;
      font-weight: 800;
      font-family: 'JetBrains Mono', monospace;
      color: var(--text-primary);
      line-height: 1.1;
    }

    .calendar-type-pill {
      font-size: 0.72rem;
      font-weight: 700;
      padding: 0.2rem 0.55rem;
      border-radius: var(--radius-sm);
      display: inline-flex;
      align-items: center;
      gap: 0.3rem;
    }

    .cal-type-earnings {
      background: rgba(139, 92, 246, 0.15);
      color: #c084fc;
      border: 1px solid rgba(139, 92, 246, 0.35);
    }

    .cal-type-dividend {
      background: rgba(16, 185, 129, 0.15);
      color: #34d399;
      border: 1px solid rgba(16, 185, 129, 0.35);
    }

    .cal-type-sec {
      background: rgba(6, 182, 212, 0.15);
      color: #22d3ee;
      border: 1px dashed rgba(6, 182, 212, 0.45);
    }

    .cal-type-conference {
      background: rgba(245, 158, 11, 0.15);
      color: #fbbf24;
      border: 1px solid rgba(245, 158, 11, 0.35);
    }

    .calendar-origin-badge {
      font-size: 0.62rem;
      font-weight: 800;
      letter-spacing: 0.05em;
      text-transform: uppercase;
      padding: 0.15rem 0.45rem;
      border-radius: 4px;
      display: inline-flex;
      align-items: center;
      gap: 0.2rem;
    }

    .origin-sourced {
      background: rgba(16, 185, 129, 0.12);
      color: #34d399;
      border: 1px solid rgba(16, 185, 129, 0.3);
    }

    .origin-estimated {
      background: rgba(6, 182, 212, 0.12);
      color: #22d3ee;
      border: 1px dashed rgba(6, 182, 212, 0.35);
    }

    .calendar-card-headline {
      font-size: 0.95rem;
      font-weight: 700;
      color: var(--text-primary);
      margin: 0 0 0.5rem 0;
      line-height: 1.4;
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

    /* Supplier & Customer Cross-Reference Badges (Category #12) */
    .crossref-badges-wrap {
      display: flex;
      flex-wrap: wrap;
      gap: 0.4rem;
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
      transition: all var(--transition-fast);
    }

    .crossref-badge:hover {
      background: rgba(99, 102, 241, 0.2);
      border-color: rgba(99, 102, 241, 0.55);
      color: #ffffff;
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

    /* Macroeconomic Intelligence (Category #15) Section */
    .economic-section {
      margin-top: 3.5rem;
      background: var(--bg-surface);
      border: 1px solid var(--border-card);
      border-radius: var(--radius-lg);
      padding: 1.75rem;
      box-shadow: 0 10px 25px rgba(0, 0, 0, 0.25);
    }

    .economic-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 1rem;
      padding-bottom: 1.25rem;
      border-bottom: 1px solid var(--border-card);
      margin-bottom: 1.5rem;
    }

    .economic-source-pill {
      font-size: 0.75rem;
      font-weight: 700;
      color: var(--accent-indigo);
      background: rgba(99, 102, 241, 0.12);
      border: 1px solid rgba(99, 102, 241, 0.3);
      padding: 0.3rem 0.65rem;
      border-radius: var(--radius-sm);
      display: inline-flex;
      align-items: center;
      gap: 0.35rem;
    }

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

    .economic-card.economic-hidden {
      display: none;
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

    .trend-up {
      background: rgba(239, 68, 68, 0.12);
      color: #f87171;
      border: 1px solid rgba(239, 68, 68, 0.3);
    }

    .trend-down {
      background: rgba(16, 185, 129, 0.12);
      color: #34d399;
      border: 1px solid rgba(16, 185, 129, 0.3);
    }

    .trend-flat {
      background: rgba(148, 163, 184, 0.12);
      color: #94a3b8;
      border: 1px solid rgba(148, 163, 184, 0.3);
    }

    .economic-val-row {
      display: flex;
      align-items: baseline;
      gap: 0.65rem;
      margin-bottom: 0.5rem;
    }

    .economic-val {
      font-family: 'JetBrains Mono', monospace;
      font-size: 2rem;
      font-weight: 800;
      color: var(--text-primary);
      line-height: 1;
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

    /* Health & Safeguards Section */
    .health-section {
      margin-top: 3.5rem;
      background: var(--bg-surface);
      border: 1px solid var(--border-card);
      border-radius: var(--radius-lg);
      padding: 1.75rem;
      box-shadow: 0 10px 25px rgba(0, 0, 0, 0.25);
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
      gap: 0.75rem;
      flex-wrap: wrap;
    }

    .health-title {
      font-size: 1.15rem;
      font-weight: 700;
      color: var(--text-primary);
      margin: 0;
    }

    .health-status-badge {
      display: inline-flex;
      align-items: center;
      gap: 0.45rem;
      padding: 0.3rem 0.75rem;
      border-radius: 9999px;
      font-size: 0.8rem;
      font-weight: 700;
      letter-spacing: 0.03em;
    }

    .health-badge-healthy {
      background: rgba(16, 185, 129, 0.15);
      color: #34d399;
      border: 1px solid rgba(16, 185, 129, 0.35);
    }

    .health-badge-warning {
      background: rgba(245, 158, 11, 0.15);
      color: #fbbf24;
      border: 1px solid rgba(245, 158, 11, 0.35);
    }

    .health-badge-critical {
      background: rgba(239, 68, 68, 0.2);
      color: #f87171;
      border: 1px solid rgba(239, 68, 68, 0.4);
    }

    .pulse-dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      display: inline-block;
      animation: pulseAnimation 2s infinite ease-in-out;
    }

    @keyframes pulseAnimation {
      0%, 100% { opacity: 1; transform: scale(1); }
      50% { opacity: 0.4; transform: scale(0.85); }
    }

    .health-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
      gap: 1rem;
      margin-bottom: 1.5rem;
    }

    .health-stat-card {
      background: var(--bg-surface-elevated);
      border: 1px solid var(--border-card);
      border-radius: var(--radius-md);
      padding: 1rem;
    }

    .health-stat-label {
      font-size: 0.75rem;
      color: var(--text-muted);
      text-transform: uppercase;
      letter-spacing: 0.05em;
      margin-bottom: 0.35rem;
    }

    .health-stat-val {
      font-size: 1.25rem;
      font-weight: 700;
      font-family: 'JetBrains Mono', monospace;
      color: var(--text-primary);
    }

    .health-stat-sub {
      font-size: 0.75rem;
      color: var(--text-secondary);
      margin-top: 0.2rem;
    }

    .health-runs-table {
      width: 100%;
      border-collapse: collapse;
      font-size: 0.82rem;
      margin-top: 1rem;
    }

    .health-runs-table th {
      text-align: left;
      padding: 0.6rem 0.75rem;
      color: var(--text-muted);
      font-weight: 600;
      border-bottom: 1px solid var(--border-card);
    }

    .health-runs-table td {
      padding: 0.6rem 0.75rem;
      border-bottom: 1px solid var(--border-subtle);
      color: var(--text-secondary);
    }

    footer {
      margin-top: 3.5rem;
      text-align: center;
      font-size: 0.8rem;
      color: var(--text-muted);
    }

    footer a {
      color: var(--text-secondary);
      text-decoration: none;
    }

    footer a:hover {
      text-decoration: underline;
    }

    @media (max-width: 960px) {
      .charts-grid { grid-template-columns: 1fr; }
    }

    @media (max-width: 768px) {
      .container { padding: 1rem; }
      .header-meta { width: 100%; justify-content: space-between; }
      .bottom-controls { flex-direction: column; align-items: stretch; }
      .search-box { max-width: none; }
      table { display: block; overflow-x: auto; }
    }
  </style>
</head>
<body>

  <div class="container">
    <header>
      <div class="brand">
        <div class="logo-badge">INTEL</div>
        <div class="brand-text">
          <h1>Stock News Dashboard</h1>
          <p>AI-Powered Intelligence, Scoring & Analytics Engine</p>
        </div>
      </div>
      <div class="header-meta">
        <div><span class="status-indicator"></span> <strong>Live Intelligence Feeds</strong></div>
        <div>Updated: <span id="generated-time">{{ generated_at }}</span></div>
      </div>
    </header>

    <!-- Summary Stats -->
    <div class="stats-grid">
      <div class="stat-card">
        <div class="stat-label">High Impact Stories (≥ 7.0)</div>
        <div class="stat-value" style="color: var(--accent-emerald);">{{ stats.high_priority_count }}</div>
        <div class="stat-subtext">Priority queue items</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Total Items In Database</div>
        <div class="stat-value">{{ stats.total }}</div>
        <div class="stat-subtext">Deduplicated across sources</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Average Importance Score</div>
        <div class="stat-value">{{ stats.avg_score }} / 10</div>
        <div class="stat-subtext">Transparent arithmetic</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Active Watchlist</div>
        <div class="stat-value">{{ stats.by_ticker|length }}</div>
        <div class="stat-subtext">
          {% for ticker, count in stats.by_ticker.items() %}
            <span style="font-family:'JetBrains Mono', monospace; font-weight:600; margin-right: 0.35rem;">{{ ticker }} ({{ count }})</span>
          {% endfor %}
        </div>
      </div>
    </div>

    <!-- ========================================================
         VISUALLY DISTINCT PRIORITY PANEL (TOP SCORED ITEMS)
         ======================================================== -->
    {% if priority_items %}
    <section class="priority-section">
      <div class="priority-header">
        <div class="priority-title-wrap">
          <span class="priority-badge-icon">⚡ PRIORITY</span>
          <div>
            <h2 class="priority-title">Top Impact Disclosures & News</h2>
            <p class="priority-subtitle">Top {{ priority_items|length }} highest scored stories with plain-English investor takeaways</p>
          </div>
        </div>
        <div style="font-family:'JetBrains Mono', monospace; font-size: 0.8rem; color: var(--accent-emerald); font-weight: 700; background: rgba(16, 185, 129, 0.12); padding: 0.35rem 0.75rem; border-radius: 6px; border: 1px solid rgba(16, 185, 129, 0.3);">
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

            <div style="margin-top: 0.65rem;">
              <span class="category-badge">{{ item.category }}</span>
              <span class="source-tag" style="margin-left: 0.4rem;">{{ item.source_label }}</span>
            </div>

            <h3 class="priority-card-headline">{{ item.headline }}</h3>
            
            {% if item.cross_references_list %}
            <div class="crossref-badges-wrap">
              {% for ref in item.cross_references_list %}
              <span class="crossref-badge" title="{{ ref.impact_note }}">
                🔗 Context: <span class="crossref-rel-pill {% if ref.relation_type == 'Customer' %}crossref-customer{% else %}crossref-supplier{% endif %}">{{ ref.relation_type }}</span>
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

    <!-- ========================================================
         ANALYTICS & VISUAL TRENDS SECTION (CHART.JS)
         ======================================================== -->
    <section class="charts-section">
      <div class="charts-grid">
        <!-- Chart 1: Frequency Over Time -->
        <div class="chart-card">
          <div class="chart-header">
            <div>
              <h3 class="chart-title">📈 Filing & News Frequency Over Time</h3>
              <p class="chart-subtitle">Recent daily disclosure volume per company</p>
            </div>
            <div class="chart-legend-wrap" id="chartLegendBadges">
              <!-- Dynamically populated by JS for all active tickers -->
            </div>
          </div>
          <div class="chart-canvas-container">
            <canvas id="timelineChart"></canvas>
          </div>
        </div>

        <!-- Chart 2: Category Breakdown -->
        <div class="chart-card">
          <div class="chart-header">
            <div>
              <h3 class="chart-title">📊 Intelligence by Category</h3>
              <p class="chart-subtitle">Distribution of disclosures across active categories</p>
            </div>
          </div>
          <div class="chart-canvas-container donut-container">
            <canvas id="categoryChart"></canvas>
          </div>
        </div>
      </div>
    </section>

    <!-- ========================================================
         MACROECONOMIC INTELLIGENCE & SENSITIVITIES (CATEGORY #15)
         ======================================================== -->
    {% if economic_indicators %}
    <section class="economic-section" id="economicSection">
      <div class="economic-header">
        <div class="section-header" style="margin-bottom:0;">
          <h2>🏛️ Macroeconomic Intelligence &amp; Sensitivities</h2>
          <p style="font-size:0.85rem; color:var(--text-secondary); margin:0.2rem 0 0 0;">Key Federal Reserve &amp; St. Louis Fed (FRED) economic indicators mapped to watchlist company sensitivities</p>
        </div>
        <div style="display:flex; align-items:center; gap:0.6rem;">
          <span class="economic-source-pill">📈 St. Louis Fed (FRED) API</span>
        </div>
      </div>

      <div class="economic-grid" id="economicGrid">
        {% for ind in economic_indicators %}
        <div class="economic-card" 
             data-indicator-id="{{ ind.indicator_id }}"
             data-relevant-tickers="{{ ind.relevant_tickers }}">
          <div>
            <div class="economic-card-top">
              <span class="economic-category-badge">{{ ind.category }}</span>
              <span class="economic-trend-badge {% if ind.change_direction == 'up' %}trend-up{% elif ind.change_direction == 'down' %}trend-down{% else %}trend-flat{% endif %}">
                {% if ind.change_direction == 'up' %}▲ +{{ ind.change_value }}
                {% elif ind.change_direction == 'down' %}▼ {{ ind.change_value }}
                {% else %}■ Steady{% endif %}
              </span>
            </div>

            <div class="economic-val-row">
              <div class="economic-val">{{ ind.formatted_value }}</div>
            </div>

            <h4 class="economic-series-name">{{ ind.name }}</h4>
            <p class="economic-context">{{ ind.context_note }}</p>
          </div>

          <div class="economic-tickers-wrap">
            <div class="economic-tickers-label">Direct Watchlist Sensitivities ({{ ind.tickers_list|length }}):</div>
            <div class="economic-tickers-list">
              {% for sym in ind.tickers_list %}
              <span class="ticker-badge ticker-{{ sym }}" style="font-size:0.68rem; padding: 0.15rem 0.45rem;">{{ sym }}</span>
              {% endfor %}
            </div>
          </div>
        </div>
        {% endfor %}
      </div>
    </section>
    {% endif %}

    <!-- ========================================================
         FORTHCOMING CORPORATE CALENDAR (CATEGORY #24)
         ======================================================== -->
    {% if calendar_events %}
    <section class="calendar-section">
      <div class="calendar-header">
        <div class="section-header" style="margin-bottom:0;">
          <h2>📅 Forthcoming Corporate Calendar</h2>
          <p style="font-size:0.85rem; color:var(--text-secondary); margin:0.2rem 0 0 0;">Upcoming earnings calls, dividend dates, conferences &amp; statutory SEC filing deadlines</p>
        </div>
        <div class="calendar-filter-bar">
          <button class="cal-filter-btn active" onclick="filterCalendar('ALL', this)">All ({{ calendar_events|length }})</button>
          <button class="cal-filter-btn" onclick="filterCalendar('SOURCED', this)">📢 Sourced Events</button>
          <button class="cal-filter-btn" onclick="filterCalendar('Earnings', this)">📊 Earnings</button>
          <button class="cal-filter-btn" onclick="filterCalendar('Conference', this)">🎤 Conferences</button>
          <button class="cal-filter-btn" onclick="filterCalendar('Dividend', this)">💰 Dividends</button>
          <button class="cal-filter-btn" onclick="filterCalendar('ESTIMATED', this)">⚙️ SEC Deadlines (Estimated)</button>
        </div>
      </div>

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
    </section>
    {% endif %}

    <!-- ========================================================
         FULL FEED / CONTROLS & TABLE
         ======================================================== -->
    <div class="feed-section-header">
      <h2>Full Intelligence Feed</h2>
      <div class="feed-divider-line"></div>
    </div>

    <!-- Controls / Filters -->
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

      <div class="bottom-controls">
        <div class="sort-group">
          <span class="filter-label" style="min-width:auto;">Sort By:</span>
          <button class="filter-btn active" id="sortScoreBtn" onclick="sortRows('score')">
            Highest Score First
          </button>
          <button class="filter-btn" id="sortDateBtn" onclick="sortRows('date')">
            Newest Date First
          </button>
        </div>

        <div class="search-box">
          <span class="search-icon">🔍</span>
          <input type="text" id="searchInput" placeholder="Search headlines, takeaways, or keywords..." onkeyup="filterItems()">
        </div>
      </div>
    </div>

    <!-- News Table -->
    <div class="table-container">
      <table id="newsTable">
        <thead>
          <tr>
            <th style="width: 75px;">Score</th>
            <th>Company</th>
            <th>Category & Source</th>
            <th>Date</th>
            <th>Headline & 'Why It Matters' Takeaway</th>
            <th>Source Link</th>
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
                  🔗 Cross-Ref: <strong class="ticker-badge ticker-{{ ref.related_ticker }}" style="font-size:0.65rem; padding:0.1rem 0.35rem; margin:0 0.2rem;">{{ ref.related_ticker }}</strong>
                  <span class="crossref-rel-pill {% if ref.relation_type == 'Customer' %}crossref-customer{% else %}crossref-supplier{% endif %}">{{ ref.relation_type }}</span>
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
      <div id="noResults" class="no-results" style="display: none;">
        <p>No items matching the current filter criteria.</p>
      </div>
    </div>

    <!-- ========================================================
         HEALTH MONITORING & COLLECTOR SAFEGUARDS (SECTION 10)
         ======================================================== -->
    <section class="health-section">
      <div class="health-header">
        <div class="health-title-group">
          <h3 class="health-title">🛡️ Pipeline Health & Collector Safeguards</h3>
          {% if latest_run %}
            {% if latest_run.status == 'HEALTHY' %}
            <span class="health-status-badge health-badge-healthy">
              <span class="pulse-dot" style="background:#10b981; box-shadow:0 0 6px #10b981;"></span>
              HEALTHY · ALL COLLECTORS OPERATIONAL
            </span>
            {% elif latest_run.status == 'WARNING' %}
            <span class="health-status-badge health-badge-warning">
              <span class="pulse-dot" style="background:#f59e0b; box-shadow:0 0 6px #f59e0b;"></span>
              DEGRADED · ANOMALY DETECTED
            </span>
            {% else %}
            <span class="health-status-badge health-badge-critical">
              <span class="pulse-dot" style="background:#ef4444; box-shadow:0 0 6px #ef4444;"></span>
              CRITICAL OUTAGE
            </span>
            {% endif %}
          {% else %}
          <span class="health-status-badge health-badge-healthy">
            <span class="pulse-dot" style="background:#10b981;"></span> OPERATIONAL
          </span>
          {% endif %}
        </div>
        <div style="font-size:0.8rem; color:var(--text-muted);">
          Last telemetry sync: <strong>{{ latest_run.run_timestamp if latest_run else generated_at }}</strong>
        </div>
      </div>

      <div class="health-grid">
        <div class="health-stat-card">
          <div class="health-stat-label">SEC EDGAR Filings</div>
          <div class="health-stat-val" style="color:#60a5fa;">{{ latest_run.edgar_count if latest_run else stats.by_source.get('SEC EDGAR', 0) }}</div>
          <div class="health-stat-sub">Official Submissions Ingested</div>
        </div>
        <div class="health-stat-card">
          <div class="health-stat-label">Company IR Newsrooms</div>
          <div class="health-stat-val" style="color:#34d399;">{{ latest_run.company_ir_count if latest_run else stats.by_source.get('Company IR', 0) }}</div>
          <div class="health-stat-sub">Direct Press Releases</div>
        </div>
        <div class="health-stat-card">
          <div class="health-stat-label">Total Ingestion Volume</div>
          <div class="health-stat-val" style="color:#a78bfa;">{{ latest_run.total_raw if latest_run else stats.total }}</div>
          <div class="health-stat-sub">Historical avg: {{ latest_run.moving_avg_raw|round(0)|int if latest_run and latest_run.moving_avg_raw > 0 else 'Baseline established' }} items</div>
        </div>
        <div class="health-stat-card">
          <div class="health-stat-label">Anomaly Safeguard</div>
          <div class="health-stat-val" style="color:#22d3ee;">33% Threshold</div>
          <div class="health-stat-sub">Automatic CI Failure on Outages</div>
        </div>
      </div>

      {% if latest_run and latest_run.health_message %}
      <div style="font-size:0.85rem; color:var(--text-secondary); background:var(--bg-surface-elevated); padding:0.75rem 1rem; border-radius:var(--radius-sm); border:1px solid var(--border-card); margin-bottom:1.25rem;">
        <strong>Diagnostic Summary:</strong> {{ latest_run.health_message }}
      </div>
      {% endif %}

      {% if recent_runs|length > 1 %}
      <details style="font-size:0.85rem; color:var(--text-muted); cursor:pointer;">
        <summary style="font-weight:600; color:var(--text-secondary); padding:0.25rem 0;">📋 View Recent Pipeline Run Audit Logs (Last {{ recent_runs|length }} Runs)</summary>
        <table class="health-runs-table">
          <thead>
            <tr>
              <th>Run Timestamp (UTC)</th>
              <th>Status</th>
              <th>SEC EDGAR</th>
              <th>Company IR</th>
              <th>Total Raw</th>
              <th>Survivors</th>
              <th>High Impact</th>
            </tr>
          </thead>
          <tbody>
            {% for run in recent_runs %}
            <tr>
              <td>{{ run.run_timestamp }}</td>
              <td>
                <span class="health-status-badge {% if run.status == 'HEALTHY' %}health-badge-healthy{% elif run.status == 'WARNING' %}health-badge-warning{% else %}health-badge-critical{% endif %}" style="padding:0.15rem 0.5rem; font-size:0.72rem;">
                  {{ run.status }}
                </span>
              </td>
              <td>{{ run.edgar_count }}</td>
              <td>{{ run.company_ir_count }}</td>
              <td>{{ run.total_raw }}</td>
              <td>{{ run.total_unique }}</td>
              <td>{{ run.high_impact_count }}</td>
            </tr>
            {% endfor %}
          </tbody>
        </table>
      </details>
      {% endif %}
    </section>

    <footer>
      <p>Multi-source financial intelligence engine powered by Gemini AI and transparent scoring arithmetic. Deduplicated across official SEC EDGAR and Company Newsrooms.</p>
    </footer>
  </div>

  <script>
    let activeTickerFilter = 'ALL';
    let activeCategoryFilter = 'ALL';
    let activeSourceFilter = 'ALL';
    let currentSort = 'score';

    // Chart.js Data Injected from Python SQLite Query
    const chartData = {{ chart_data_json|safe }};

    // Initialize Chart.js Dark Mode Defaults
    Chart.defaults.color = '#94a3b8';
    Chart.defaults.font.family = "'Inter', sans-serif";

    // 1. Initialize Frequency Timeline Sparkline/Line Chart
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

      // Explicitly sort tickers in order of watchlist priority
      const tickerOrder = [
        'NVDA', 'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'TSLA',
        'JPM', 'JNJ', 'XOM', 'WMT', 'DIS', 'KO', 'PFE', 'BA'
      ];
      const presentTickers = Object.keys(chartData.timeline_series).sort((a, b) => {
        const idxA = tickerOrder.indexOf(a);
        const idxB = tickerOrder.indexOf(b);
        if (idxA !== -1 && idxB !== -1) return idxA - idxB;
        if (idxA !== -1) return -1;
        if (idxB !== -1) return 1;
        return a.localeCompare(b);
      });

      // Populate header legend badges dynamically
      const legendBadgesEl = document.getElementById('chartLegendBadges');
      if (legendBadgesEl) {
        legendBadgesEl.innerHTML = presentTickers.map(ticker => {
          const col = tickerColors[ticker]?.border || '#06b6d4';
          return `<span class="chart-legend-item"><span class="legend-dot" style="background:${col}; box-shadow:0 0 6px ${col};"></span> ${ticker}</span>`;
        }).join('');
      }

      const datasets = presentTickers.map(ticker => {
        const colors = tickerColors[ticker] || { border: '#06b6d4', bg: 'rgba(6, 182, 212, 0.1)' };
        return {
          label: ticker,
          data: chartData.timeline_series[ticker],
          borderColor: colors.border,
          backgroundColor: colors.bg,
          borderWidth: 2.2,
          pointRadius: 3,
          pointHoverRadius: 6,
          pointBackgroundColor: colors.border,
          tension: 0.35,
          fill: true
        };
      });

      new Chart(ctxTimeline, {
        type: 'line',
        data: {
          labels: chartData.timeline_dates,
          datasets: datasets
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          interaction: {
            mode: 'index',
            intersect: false
          },
          plugins: {
            legend: {
              display: false
            },
            tooltip: {
              backgroundColor: '#1e293b',
              titleColor: '#f8fafc',
              bodyColor: '#e2e8f0',
              borderColor: '#334155',
              borderWidth: 1,
              padding: 10,
              boxPadding: 4,
              usePointStyle: true
            }
          },
          scales: {
            x: {
              grid: { color: 'rgba(255, 255, 255, 0.04)' },
              ticks: { font: { size: 10 } }
            },
            y: {
              beginAtZero: true,
              grid: { color: 'rgba(255, 255, 255, 0.04)' },
              ticks: { stepSize: 1, font: { size: 10 } }
            }
          }
        }
      });
    }

    // 2. Initialize Category Distribution Donut Chart
    if (document.getElementById('categoryChart') && chartData.categories) {
      const ctxCat = document.getElementById('categoryChart').getContext('2d');
      
      const palette = [
        '#3b82f6', '#10b981', '#f59e0b', '#8b5cf6', 
        '#06b6d4', '#ec4899', '#6366f1', '#64748b'
      ];

      new Chart(ctxCat, {
        type: 'doughnut',
        data: {
          labels: chartData.categories,
          datasets: [{
            data: chartData.category_counts,
            backgroundColor: palette.slice(0, chartData.categories.length),
            borderColor: '#0f172a',
            borderWidth: 2,
            hoverOffset: 6
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          cutout: '68%',
          plugins: {
            legend: {
              position: 'right',
              labels: {
                boxWidth: 10,
                boxHeight: 10,
                useBorderRadius: true,
                borderRadius: 2,
                font: { size: 10.5 },
                padding: 8
              }
            },
            tooltip: {
              backgroundColor: '#1e293b',
              titleColor: '#f8fafc',
              bodyColor: '#e2e8f0',
              borderColor: '#334155',
              borderWidth: 1,
              padding: 10
            }
          }
        }
      });
    }

    function setTickerFilter(val, btn) {
      activeTickerFilter = val;
      document.querySelectorAll('[data-filter-type="ticker"]').forEach(b => b.classList.remove('active'));
      if (btn) btn.classList.add('active');
      filterItems();
      filterEconomicCards(val);
    }

    function filterEconomicCards(ticker) {
      const econCards = document.querySelectorAll('.economic-card');
      econCards.forEach(card => {
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
      currentSort = criteria;
      document.getElementById('sortScoreBtn').classList.toggle('active', criteria === 'score');
      document.getElementById('sortDateBtn').classList.toggle('active', criteria === 'date');

      const tbody = document.getElementById('newsBody');
      const rows = Array.from(tbody.querySelectorAll('.news-row'));

      rows.sort((a, b) => {
        if (criteria === 'score') {
          const scoreA = parseFloat(a.getAttribute('data-score')) || 0;
          const scoreB = parseFloat(b.getAttribute('data-score')) || 0;
          if (scoreB !== scoreA) return scoreB - scoreA;
          return (b.getAttribute('data-date') || '').localeCompare(a.getAttribute('data-date') || '');
        } else {
          const dateComp = (b.getAttribute('data-date') || '').localeCompare(a.getAttribute('data-date') || '');
          if (dateComp !== 0) return dateComp;
          return (parseFloat(b.getAttribute('data-score')) || 0) - (parseFloat(a.getAttribute('data-score')) || 0);
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

      const noResults = document.getElementById('noResults');
      if (visibleCount === 0) {
        noResults.style.display = 'block';
      } else {
        noResults.style.display = 'none';
      }
    }

    function filterCalendar(type, btn) {
      document.querySelectorAll('.cal-filter-btn').forEach(b => b.classList.remove('active'));
      if (btn) btn.classList.add('active');

      const cards = document.querySelectorAll('.calendar-card');
      cards.forEach(card => {
        const evType = (card.getAttribute('data-event-type') || '').toLowerCase();
        const srcType = (card.getAttribute('data-source-type') || '').toLowerCase();

        if (type === 'ALL') {
          card.style.display = 'flex';
        } else if (type === 'SOURCED' && srcType === 'sourced') {
          card.style.display = 'flex';
        } else if (type === 'ESTIMATED' && srcType === 'estimated_rule') {
          card.style.display = 'flex';
        } else if (evType.includes(type.toLowerCase())) {
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


def render_dashboard(
    output_path: Optional[str] = None,
    db_path: Optional[str] = None,
) -> str:
    """Render the dashboard HTML file with priority panel, scoring, AI summaries, charts, and calendar."""
    if output_path is None:
        site_dir = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "site"
        )
        os.makedirs(site_dir, exist_ok=True)
        output_path = os.path.join(site_dir, "index.html")

    items = get_all_news_items(order_by="score", db_path=db_path)
    priority_items = get_top_priority_items(limit=8, db_path=db_path)
    stats = get_news_stats(db_path=db_path)
    chart_data = get_chart_data(db_path=db_path)
    economic_indicators = get_economic_indicators(db_path=db_path)
    calendar_events = get_forthcoming_calendar(limit=24, db_path=db_path)
    recent_runs = get_recent_pipeline_runs(limit=5, db_path=db_path)
    latest_run = recent_runs[0] if recent_runs else None
    now_str = datetime.now().strftime("%b %d, %Y %H:%M:%S")

    template = Template(HTML_TEMPLATE, autoescape=True)
    rendered_html = template.render(
        items=items,
        priority_items=priority_items,
        stats=stats,
        chart_data_json=json.dumps(chart_data),
        economic_indicators=economic_indicators,
        calendar_events=calendar_events,
        recent_runs=recent_runs,
        latest_run=latest_run,
        generated_at=now_str,
    )

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(rendered_html)

    return output_path
