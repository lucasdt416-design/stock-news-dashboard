"""Static HTML dashboard generator for multi-source stock news and filings."""

import os
from datetime import datetime
from typing import Optional
from jinja2 import Template
from pipeline.persist import get_all_news_items, get_news_stats

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="description" content="Personal stock news dashboard: SEC EDGAR filings and official company IR press releases.">
  <title>Stock News Dashboard</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg-base: #0b0f19;
      --bg-surface: #111827;
      --bg-surface-elevated: #1f2937;
      --bg-hover: #374151;
      --border-subtle: #2d3748;
      --border-accent: #3b82f6;
      --text-primary: #f9fafb;
      --text-secondary: #9ca3af;
      --text-muted: #6b7280;
      --accent-blue: #3b82f6;
      --accent-emerald: #10b981;
      --accent-amber: #f59e0b;
      --accent-purple: #8b5cf6;
      --accent-rose: #f43f5e;
      --accent-cyan: #06b6d4;
      --radius-sm: 6px;
      --radius-md: 10px;
      --radius-lg: 14px;
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
      max-width: 1320px;
      margin: 0 auto;
      padding: 2rem 1.5rem;
    }

    header {
      display: flex;
      flex-wrap: wrap;
      justify-content: space-between;
      align-items: center;
      gap: 1.5rem;
      padding-bottom: 2rem;
      border-bottom: 1px solid var(--border-subtle);
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
      font-weight: 700;
      font-size: 1.15rem;
      color: #fff;
      box-shadow: 0 0 15px rgba(59, 130, 246, 0.4);
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
      border: 1px solid var(--border-subtle);
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
      border: 1px solid var(--border-subtle);
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

    /* Controls Bar */
    .controls-panel {
      background: var(--bg-surface);
      border: 1px solid var(--border-subtle);
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
      margin-right: 0.5rem;
      min-width: 60px;
    }

    .filter-btn {
      background: var(--bg-surface-elevated);
      color: var(--text-secondary);
      border: 1px solid var(--border-subtle);
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

    .search-row {
      display: flex;
      justify-content: flex-end;
      margin-top: 0.25rem;
    }

    .search-box {
      position: relative;
      width: 100%;
      max-width: 400px;
    }

    .search-box input {
      width: 100%;
      background: var(--bg-base);
      border: 1px solid var(--border-subtle);
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

    /* Table Styling */
    .table-container {
      background: var(--bg-surface);
      border: 1px solid var(--border-subtle);
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
      border-bottom: 1px solid var(--border-subtle);
    }

    tbody tr {
      border-bottom: 1px solid rgba(45, 55, 72, 0.6);
      transition: background-color 0.12s ease;
    }

    tbody tr:hover {
      background-color: rgba(255, 255, 255, 0.025);
    }

    td {
      padding: 1rem 1.25rem;
      vertical-align: middle;
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

    .source-badge {
      display: inline-flex;
      align-items: center;
      font-size: 0.72rem;
      font-weight: 600;
      text-transform: uppercase;
      padding: 0.2rem 0.5rem;
      border-radius: var(--radius-sm);
      letter-spacing: 0.03em;
    }

    .source-sec_edgar {
      background: rgba(59, 130, 246, 0.15);
      color: #93c5fd;
      border: 1px solid rgba(59, 130, 246, 0.3);
    }

    .source-company_ir {
      background: rgba(139, 92, 246, 0.15);
      color: #c4b5fd;
      border: 1px solid rgba(139, 92, 246, 0.3);
    }

    .form-badge {
      display: inline-block;
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.75rem;
      font-weight: 600;
      padding: 0.15rem 0.45rem;
      border-radius: var(--radius-sm);
      background: var(--bg-surface-elevated);
      color: var(--text-primary);
      border: 1px solid var(--border-subtle);
      margin-left: 0.35rem;
    }

    .form-PRESS_RELEASE {
      background: rgba(6, 182, 212, 0.15);
      color: #22d3ee;
      border-color: rgba(6, 182, 212, 0.3);
    }

    .headline-text {
      font-weight: 600;
      color: var(--text-primary);
      margin-bottom: 0.25rem;
      line-height: 1.4;
    }

    .summary-text {
      font-size: 0.8rem;
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
      table { display: block; overflow-x: auto; }
    }
  </style>
</head>
<body>

  <div class="container">
    <header>
      <div class="brand">
        <div class="logo-badge">FEED</div>
        <div class="brand-text">
          <h1>Stock News Dashboard</h1>
          <p>Multi-Source Intel: SEC EDGAR Filings & Company Investor Relations Feeds</p>
        </div>
      </div>
      <div class="header-meta">
        <div><span class="status-indicator"></span> <strong>Multi-Source Live Sync</strong></div>
        <div>Updated: <span id="generated-time">{{ generated_at }}</span></div>
      </div>
    </header>

    <!-- Summary Stats -->
    <div class="stats-grid">
      <div class="stat-card">
        <div class="stat-label">Total Unique Stories</div>
        <div class="stat-value">{{ stats.total }}</div>
        <div class="stat-subtext">Deduplicated across sources</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Latest Publication</div>
        <div class="stat-value" style="font-size: 1.35rem; margin-top: 0.3rem;">{{ stats.latest_date or "N/A" }}</div>
        <div class="stat-subtext">Most recent announcement</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Tracked Companies</div>
        <div class="stat-value">{{ stats.by_ticker|length }}</div>
        <div class="stat-subtext">
          {% for ticker, count in stats.by_ticker.items() %}
            <span style="font-family:'JetBrains Mono', monospace; font-weight:600; margin-right: 0.35rem;">{{ ticker }} ({{ count }})</span>
          {% endfor %}
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Active Sources</div>
        <div class="stat-value">{{ stats.by_source|length }}</div>
        <div class="stat-subtext">
          {% for src, count in stats.by_source.items() %}
            <span style="font-family:'JetBrains Mono', monospace; margin-right: 0.35rem;">{{ src }}: {{ count }}</span>
          {% endfor %}
        </div>
      </div>
    </div>

    <!-- Controls / Filters -->
    <div class="controls-panel">
      <div class="filter-row">
        <span class="filter-label">Tickers:</span>
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
        <span class="filter-label">Source:</span>
        <button class="filter-btn active" data-filter-type="source" data-val="ALL" onclick="setSourceFilter('ALL', this)">
          All Sources
        </button>
        <button class="filter-btn" data-filter-type="source" data-val="sec_edgar" onclick="setSourceFilter('sec_edgar', this)">
          SEC EDGAR
        </button>
        <button class="filter-btn" data-filter-type="company_ir" onclick="setSourceFilter('company_ir', this)">
          Company IR
        </button>
      </div>

      <div class="search-row">
        <div class="search-box">
          <span class="search-icon">🔍</span>
          <input type="text" id="searchInput" placeholder="Search headlines, forms, or summary..." onkeyup="filterItems()">
        </div>
      </div>
    </div>

    <!-- News Table -->
    <div class="table-container">
      <table id="newsTable">
        <thead>
          <tr>
            <th>Company</th>
            <th>Source / Type</th>
            <th>Date</th>
            <th>Headline & Excerpt</th>
            <th>Source Link</th>
          </tr>
        </thead>
        <tbody id="newsBody">
          {% for item in items %}
          <tr class="news-row" data-ticker="{{ item.ticker }}" data-source="{{ item.source }}" data-text="{{ item.ticker }} {{ item.company_name }} {{ item.source_label }} {{ item.form_or_type }} {{ item.headline }} {{ item.summary }}">
            <td>
              <div>
                <span class="ticker-badge ticker-{{ item.ticker }}">{{ item.ticker }}</span>
                <div class="summary-text" style="margin-top: 0.25rem;">{{ item.company_name }}</div>
              </div>
            </td>
            <td>
              <div>
                <span class="source-badge source-{{ item.source }}">{{ item.source_label }}</span>
                <span class="form-badge form-{{ item.form_or_type|replace(' ', '-') }}">{{ item.form_or_type }}</span>
              </div>
            </td>
            <td class="date-cell">
              {{ item.published_date }}
            </td>
            <td>
              <div class="headline-text">{{ item.headline }}</div>
              <div class="summary-text">{{ item.summary }}</div>
            </td>
            <td>
              <a href="{{ item.url }}" target="_blank" rel="noopener noreferrer" class="action-link">
                View Source ↗
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
      <p>Data aggregated from official SEC EDGAR Submissions API and Company Newsroom feeds. For informational research purposes only.</p>
    </footer>
  </div>

  <script>
    let activeTickerFilter = 'ALL';
    let activeSourceFilter = 'ALL';

    function setTickerFilter(val, btn) {
      activeTickerFilter = val;
      document.querySelectorAll('[data-filter-type="ticker"]').forEach(b => b.classList.remove('active'));
      if (btn) btn.classList.add('active');
      filterItems();
    }

    function setSourceFilter(val, btn) {
      activeSourceFilter = val;
      document.querySelectorAll('[data-filter-type="source"]').forEach(b => b.classList.remove('active'));
      if (btn) btn.classList.add('active');
      filterItems();
    }

    function filterItems() {
      const query = (document.getElementById('searchInput').value || '').toLowerCase().trim();
      const rows = document.querySelectorAll('.news-row');
      let visibleCount = 0;

      rows.forEach(row => {
        const rowTicker = row.getAttribute('data-ticker');
        const rowSource = row.getAttribute('data-source');
        const rowText = (row.getAttribute('data-text') || '').toLowerCase();

        const matchesTicker = (activeTickerFilter === 'ALL' || rowTicker === activeTickerFilter);
        const matchesSource = (activeSourceFilter === 'ALL' || rowSource === activeSourceFilter);
        const matchesSearch = (!query || rowText.includes(query));

        if (matchesTicker && matchesSource && matchesSearch) {
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
    """Render the multi-source dashboard HTML file from SQLite data and return the destination path."""
    if output_path is None:
        site_dir = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "site"
        )
        os.makedirs(site_dir, exist_ok=True)
        output_path = os.path.join(site_dir, "index.html")

    items = get_all_news_items(db_path=db_path)
    stats = get_news_stats(db_path=db_path)
    now_str = datetime.now().strftime("%b %d, %Y %H:%M:%S")

    template = Template(HTML_TEMPLATE)
    rendered_html = template.render(
        items=items,
        stats=stats,
        generated_at=now_str,
    )

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(rendered_html)

    return output_path
