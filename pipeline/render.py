"""Static HTML dashboard generator with Priority Panel, Score Ranking, and 'Why It Matters' Takeaways."""

import os
from datetime import datetime
from typing import Optional
from jinja2 import Template
from pipeline.persist import get_all_news_items, get_news_stats, get_top_priority_items

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="description" content="Personal stock news dashboard with rule-based scoring, plain-English 'Why It Matters' explanations, and multi-source intelligence.">
  <title>Stock News Dashboard — Priority Intelligence</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600;700&display=swap" rel="stylesheet">
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
      margin-bottom: 2.75rem;
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

    .ticker-NVDA { background: rgba(16, 185, 129, 0.15); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.3); }
    .ticker-AAPL { background: rgba(59, 130, 246, 0.15); color: #60a5fa; border: 1px solid rgba(59, 130, 246, 0.3); }
    .ticker-MSFT { background: rgba(139, 92, 246, 0.15); color: #a78bfa; border: 1px solid rgba(139, 92, 246, 0.3); }
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
          <p>AI-Powered Intelligence & Multi-Source Research Engine</p>
        </div>
      </div>
      <div class="header-meta">
        <div><span class="status-indicator"></span> <strong>AI & Scoring Active</strong></div>
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
              data-source="{{ item.source }}" 
              data-category="{{ item.category }}"
              data-text="{{ item.ticker }} {{ item.company_name }} {{ item.category }} {{ item.source_label }} {{ item.form_or_type }} {{ item.headline }} {{ item.llm_summary }} {{ item.summary }} {{ item.score_breakdown }}">
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

    <footer>
      <p>Multi-source financial intelligence engine powered by Gemini AI and transparent scoring arithmetic. Deduplicated across official SEC EDGAR and Company Newsrooms.</p>
    </footer>
  </div>

  <script>
    let activeTickerFilter = 'ALL';
    let activeCategoryFilter = 'ALL';
    let activeSourceFilter = 'ALL';
    let currentSort = 'score';

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
        const rowSource = row.getAttribute('data-source');
        const rowCategory = row.getAttribute('data-category');
        const rowText = (row.getAttribute('data-text') || '').toLowerCase();

        const matchesTicker = (activeTickerFilter === 'ALL' || rowTicker === activeTickerFilter);
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
  </script>
</body>
</html>
"""


def render_dashboard(
    output_path: Optional[str] = None,
    db_path: Optional[str] = None,
) -> str:
    """Render the dashboard HTML file with priority panel, scoring, and 'Why It Matters' summaries."""
    if output_path is None:
        site_dir = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "site"
        )
        os.makedirs(site_dir, exist_ok=True)
        output_path = os.path.join(site_dir, "index.html")

    items = get_all_news_items(order_by="score", db_path=db_path)
    priority_items = get_top_priority_items(limit=8, db_path=db_path)
    stats = get_news_stats(db_path=db_path)
    now_str = datetime.now().strftime("%b %d, %Y %H:%M:%S")

    template = Template(HTML_TEMPLATE)
    rendered_html = template.render(
        items=items,
        priority_items=priority_items,
        stats=stats,
        generated_at=now_str,
    )

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(rendered_html)

    return output_path
