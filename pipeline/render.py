"""Static HTML dashboard generator."""

import os
from datetime import datetime
from typing import Optional
from jinja2 import Template
from pipeline.persist import get_all_filings, get_filing_stats

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="description" content="Personal stock news and SEC EDGAR filings dashboard for watchlist companies.">
  <title>Stock News Dashboard — SEC Filings</title>
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
      max-width: 1280px;
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
      font-size: 1.25rem;
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
      margin-bottom: 2.5rem;
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
      flex-wrap: wrap;
      gap: 1.25rem;
      align-items: center;
      justify-content: space-between;
    }

    .ticker-filters {
      display: flex;
      flex-wrap: wrap;
      gap: 0.5rem;
      align-items: center;
    }

    .filter-btn {
      background: var(--bg-surface-elevated);
      color: var(--text-secondary);
      border: 1px solid var(--border-subtle);
      border-radius: var(--radius-sm);
      padding: 0.45rem 0.9rem;
      font-size: 0.85rem;
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

    .search-box {
      position: relative;
      min-width: 260px;
      flex-grow: 1;
      max-width: 380px;
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

    /* Filings Table / Cards */
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

    .form-badge {
      display: inline-block;
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.78rem;
      font-weight: 600;
      padding: 0.2rem 0.5rem;
      border-radius: var(--radius-sm);
      background: var(--bg-surface-elevated);
      color: var(--text-primary);
      border: 1px solid var(--border-subtle);
    }

    .form-10-K, .form-10-Q {
      background: rgba(16, 185, 129, 0.15);
      color: #10b981;
      border-color: rgba(16, 185, 129, 0.3);
    }

    .form-8-K {
      background: rgba(59, 130, 246, 0.15);
      color: #3b82f6;
      border-color: rgba(59, 130, 246, 0.3);
    }

    .form-4 {
      background: rgba(245, 158, 11, 0.15);
      color: #f59e0b;
      border-color: rgba(245, 158, 11, 0.3);
    }

    .filing-title {
      font-weight: 500;
      color: var(--text-primary);
      margin-bottom: 0.15rem;
    }

    .filing-desc {
      font-size: 0.8rem;
      color: var(--text-muted);
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
      .controls-panel { flex-direction: column; align-items: stretch; }
      .search-box { max-width: none; }
      table { display: block; overflow-x: auto; }
    }
  </style>
</head>
<body>

  <div class="container">
    <header>
      <div class="brand">
        <div class="logo-badge">SEC</div>
        <div class="brand-text">
          <h1>Stock News Dashboard</h1>
          <p>Automated SEC EDGAR Disclosures & Filings Feed</p>
        </div>
      </div>
      <div class="header-meta">
        <div><span class="status-indicator"></span> <strong>EDGAR Live Sync</strong></div>
        <div>Updated: <span id="generated-time">{{ generated_at }}</span></div>
      </div>
    </header>

    <!-- Summary Stats -->
    <div class="stats-grid">
      <div class="stat-card">
        <div class="stat-label">Total Filings Tracked</div>
        <div class="stat-value">{{ stats.total }}</div>
        <div class="stat-subtext">Across active watchlist</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Latest Filing Date</div>
        <div class="stat-value" style="font-size: 1.35rem; margin-top: 0.3rem;">{{ stats.latest_date or "N/A" }}</div>
        <div class="stat-subtext">Most recent disclosure</div>
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
        <div class="stat-label">Filing Form Types</div>
        <div class="stat-value">{{ stats.by_form|length }}</div>
        <div class="stat-subtext">
          {% for form, count in stats.by_form.items()|batch(3)|first %}
            <span style="font-family:'JetBrains Mono', monospace; margin-right: 0.35rem;">{{ form }}: {{ count }}</span>
          {% endfor %}
        </div>
      </div>
    </div>

    <!-- Controls / Filters -->
    <div class="controls-panel">
      <div class="ticker-filters">
        <button class="filter-btn active" data-ticker="ALL" onclick="filterByTicker('ALL', this)">
          All Tickers <span class="pill-count" id="count-all">{{ filings|length }}</span>
        </button>
        {% for ticker, count in stats.by_ticker.items() %}
        <button class="filter-btn" data-ticker="{{ ticker }}" onclick="filterByTicker('{{ ticker }}', this)">
          {{ ticker }} <span class="pill-count">{{ count }}</span>
        </button>
        {% endfor %}
      </div>

      <div class="search-box">
        <span class="search-icon">🔍</span>
        <input type="text" id="searchInput" placeholder="Search forms, accession #, or details..." onkeyup="filterFilings()">
      </div>
    </div>

    <!-- Filings Table -->
    <div class="table-container">
      <table id="filingsTable">
        <thead>
          <tr>
            <th>Ticker / Company</th>
            <th>Form Type</th>
            <th>Filing Date</th>
            <th>Report Date</th>
            <th>Primary Document & Accession</th>
            <th>Source Document</th>
          </tr>
        </thead>
        <tbody id="filingsBody">
          {% for filing in filings %}
          <tr class="filing-row" data-ticker="{{ filing.ticker }}" data-form="{{ filing.form }}" data-text="{{ filing.ticker }} {{ filing.company_name }} {{ filing.form }} {{ filing.accession_number }} {{ filing.primary_doc_name }} {{ filing.primary_doc_description }}">
            <td>
              <div>
                <span class="ticker-badge ticker-{{ filing.ticker }}">{{ filing.ticker }}</span>
                <div class="filing-desc" style="margin-top: 0.25rem;">{{ filing.company_name }}</div>
              </div>
            </td>
            <td>
              <span class="form-badge form-{{ filing.form|replace(' ', '-') }}">{{ filing.form }}</span>
            </td>
            <td class="date-cell">
              {{ filing.filing_date }}
            </td>
            <td class="date-cell">
              {{ filing.report_date or "—" }}
            </td>
            <td>
              <div class="filing-title">{{ filing.primary_doc_description or filing.primary_doc_name or "Official SEC Submission" }}</div>
              <div class="filing-desc" style="font-family:'JetBrains Mono', monospace; font-size:0.75rem;">Acc: {{ filing.accession_number }}</div>
            </td>
            <td>
              <a href="{{ filing.url }}" target="_blank" rel="noopener noreferrer" class="action-link">
                View on SEC ↗
              </a>
            </td>
          </tr>
          {% endfor %}
        </tbody>
      </table>
      <div id="noResults" class="no-results" style="display: none;">
        <p>No filings matching the current filter criteria.</p>
      </div>
    </div>

    <footer>
      <p>Data provided directly via official <a href="https://www.sec.gov/edgar" target="_blank" rel="noopener">SEC EDGAR Submissions API</a>. This dashboard is for informational and research purposes only and does not constitute financial advice.</p>
    </footer>
  </div>

  <script>
    let currentTickerFilter = 'ALL';

    function filterByTicker(ticker, btnElement) {
      currentTickerFilter = ticker;
      document.querySelectorAll('.filter-btn').forEach(btn => btn.classList.remove('active'));
      if (btnElement) {
        btnElement.classList.add('active');
      }
      filterFilings();
    }

    function filterFilings() {
      const query = (document.getElementById('searchInput').value || '').toLowerCase().trim();
      const rows = document.querySelectorAll('.filing-row');
      let visibleCount = 0;

      rows.forEach(row => {
        const rowTicker = row.getAttribute('data-ticker');
        const rowText = (row.getAttribute('data-text') || '').toLowerCase();

        const matchesTicker = (currentTickerFilter === 'ALL' || rowTicker === currentTickerFilter);
        const matchesSearch = (!query || rowText.includes(query));

        if (matchesTicker && matchesSearch) {
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
    """Render the dashboard HTML file from SQLite data and return the destination path."""
    if output_path is None:
        site_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "site")
        os.makedirs(site_dir, exist_ok=True)
        output_path = os.path.join(site_dir, "index.html")

    filings = get_all_filings(db_path=db_path)
    stats = get_filing_stats(db_path=db_path)
    now_str = datetime.now().strftime("%b %d, %Y %H:%M:%S")

    template = Template(HTML_TEMPLATE)
    rendered_html = template.render(
        filings=filings,
        stats=stats,
        generated_at=now_str,
    )

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(rendered_html)

    return output_path
