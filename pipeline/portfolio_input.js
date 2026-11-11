// Reading holdings that someone typed, pasted or imported, and checking what was stored.
// Plain functions with no page or network access, so tests/node/portfolio_input.test.mjs can run
// the same source the page uses. pipeline/portfolio_page.py puts this file into portfolio.html.
const PortfolioInput = (() => {
  const TICKER = /^[A-Z][A-Z0-9]{0,5}(?:-[A-Z]{1,2})?$/;
  const MONTH = /^(19|20)\d{2}-(0[1-9]|1[0-2])$/;
  const MAX_HOLDINGS = 200;
  const MAX_AMOUNT = 1e12;
  const MAX_FILE_BYTES = 1024 * 1024;
  const MAX_FILE_LINES = 2000;
  // Words that sit next to a number in a pasted list and are never tickers.
  const FILLER = new Set(['SHARES', 'SHARE', 'SH', 'SHS', 'UNITS', 'UNIT', 'X', 'OF', 'AT', 'IN', 'STOCK', 'STOCKS',
    'USD', 'DOLLARS', 'DOLLAR', 'WORTH', 'AND', 'OWN', 'I', 'HAVE', 'ABOUT', 'APPROX', 'EACH', 'TOTAL', 'PAID', 'FOR']);

  // "brk.b", "BRK/B" and "$nvda" become BRK-B and NVDA. Anything that isn't a US ticker gives ''.
  function normalizeTicker(value) {
    const text = String(value === null || value === undefined ? '' : value).trim().toUpperCase()
      .replace(/^\$/, '').replace(/[./]/g, '-');
    return TICKER.test(text) ? text : '';
  }

  // "2,000", "$2k", "1.5m", "(12)" and " 10 " as numbers. NaN for anything else.
  function parseAmount(value) {
    let text = String(value === null || value === undefined ? '' : value).trim().replace(/[$\s]/g, '').replace(/,/g, '');
    if (/^\(.*\)$/.test(text)) text = '-' + text.slice(1, -1);
    const m = /^(-?\d*\.?\d+)([KM])?$/i.exec(text);
    if (!m) return NaN;
    const scale = !m[2] ? 1 : m[2].toUpperCase() === 'K' ? 1e3 : 1e6;
    return Number(m[1]) * scale;
  }

  function usable(n) {
    return typeof n === 'number' && Number.isFinite(n) && n > 0 && n < MAX_AMOUNT;
  }

  function unread(text, reason) {
    return { text: String(text).slice(0, 200), reason };
  }

  // One piece of a pasted list, like "NVDA 10", "10 shares of AAPL", "VOO $2000" or "AAPL 5 @ 150".
  function parsePiece(piece) {
    const original = piece.trim();
    if (!original) return null;
    let text = ' ' + original + ' ';
    let perShare = null;
    let dollars = null;

    const at = /@\s*\$?\s*(\d[\d,]*\.?\d*|\.\d+)\s*([KkMm])?(?![A-Za-z0-9])/.exec(text);
    if (at) {
      perShare = parseAmount(at[1] + (at[2] || ''));
      text = text.replace(at[0], ' ');
    }
    const money = [];
    text = text.replace(/\$\s*(\d[\d,]*\.?\d*|\.\d+)\s*([KkMm])?(?![A-Za-z0-9])/g, (all, n, scale) => {
      money.push(parseAmount(n + (scale || '')));
      return ' ';
    });
    text = text.replace(/(^|\s)(\d[\d,]*\.?\d*|\.\d+)([KkMm])?\s*(USD|dollars?)(?![A-Za-z0-9])/gi, (all, lead, n, scale) => {
      money.push(parseAmount(n + (scale || '')));
      return ' ';
    });
    if (money.length > 1) return unread(original, 'more than one dollar amount');
    if (money.length === 1) dollars = money[0];

    const tickers = [];
    const numbers = [];
    for (const raw of text.split(/[\s:=|()]+/)) {
      // A leading minus is kept, so "-5" is refused rather than read as 5.
      const token = raw.replace(/^[^A-Za-z0-9$.\-]+|[^A-Za-z0-9]+$/g, '');
      if (!token) continue;
      const numeric = /^[xX×]?(\d[\d,]*\.?\d*|\.\d+)([KkMm])?[xX×]?$/.exec(token);
      if (numeric) {
        numbers.push(parseAmount(numeric[1] + (numeric[2] || '')));
        continue;
      }
      if (FILLER.has(token.toUpperCase())) continue;
      const ticker = normalizeTicker(token);
      if (!ticker) return unread(original, `"${token.slice(0, 20)}" isn't a ticker or a number`);
      tickers.push(ticker);
    }

    if (tickers.length === 0) return unread(original, 'no ticker');
    if (tickers.length > 1) return unread(original, 'more than one ticker');
    if (numbers.length > 1) return unread(original, 'more than one number');
    if (numbers.length === 1 && dollars !== null) return unread(original, 'both a number of shares and a dollar amount');
    if (numbers.length === 0 && dollars === null) return unread(original, 'no amount');

    const row = { ticker: tickers[0], shares: null, usd: null, paid: null, bought: null };
    if (dollars !== null) {
      if (!usable(dollars)) return unread(original, 'the amount has to be more than zero');
      row.usd = dollars;
    } else {
      if (!usable(numbers[0])) return unread(original, 'the number of shares has to be more than zero');
      row.shares = numbers[0];
      if (perShare !== null) {
        if (!usable(perShare)) return unread(original, 'the price paid has to be more than zero');
        row.paid = Math.round(perShare * row.shares * 100) / 100;
      }
    }
    return row;
  }

  // A pasted list: pieces are separated by new lines, semicolons, or commas that aren't inside a number.
  function parsePaste(text) {
    const rows = [];
    const notRead = [];
    let source = String(text || '').slice(0, 20000);
    let before;
    do {
      before = source;
      source = source.replace(/(\d),(\d{3})(?!\d)/g, '$1$2');
    } while (source !== before);
    for (const piece of source.split(/[\n\r;,]+/)) {
      const result = parsePiece(piece);
      if (!result) continue;
      if (result.ticker) rows.push(result);
      else notRead.push(result);
    }
    return { rows, unread: notRead };
  }

  // CSV text as rows of cells: quoted cells, doubled quotes, commas and new lines inside quotes.
  function parseCsv(text, delimiter) {
    const rows = [];
    let row = [];
    let cell = '';
    let quoted = false;
    const src = String(text || '').replace(/^﻿/, '');
    for (let i = 0; i < src.length; i += 1) {
      const c = src[i];
      if (quoted) {
        if (c === '"') {
          if (src[i + 1] === '"') { cell += '"'; i += 1; } else quoted = false;
        } else cell += c;
      } else if (c === '"' && cell.trim() === '') {
        quoted = true;
        cell = '';
      } else if (c === delimiter) {
        row.push(cell); cell = '';
      } else if (c === '\n' || c === '\r') {
        if (c === '\r' && src[i + 1] === '\n') i += 1;
        row.push(cell); cell = '';
        rows.push(row); row = [];
      } else cell += c;
    }
    if (cell !== '' || row.length) { row.push(cell); rows.push(row); }
    return rows;
  }

  const COLUMNS = {
    ticker: ['symbol', 'ticker', 'tickersymbol', 'instrument', 'security', 'securitysymbol'],
    shares: ['quantity', 'qty', 'shares', 'units', 'sharesowned', 'numberofshares', 'currentquantity'],
    paid: ['costbasis', 'costbasistotal', 'totalcost', 'totalcostbasis', 'bookcost', 'cost'],
    perShare: ['averagecost', 'avgcost', 'avgprice', 'averageprice', 'costpershare', 'purchaseprice', 'averagecostbasis',
      'avgcostshare', 'costbasispershare'],
    value: ['marketvalue', 'currentvalue', 'value', 'totalvalue'],
  };

  function headerKey(cell) {
    return String(cell || '').toLowerCase().replace(/[^a-z]/g, '');
  }

  function findColumns(cells) {
    const keys = cells.map(headerKey);
    const found = {};
    Object.keys(COLUMNS).forEach(name => {
      const at = keys.findIndex(k => COLUMNS[name].includes(k));
      if (at >= 0) found[name] = at;
    });
    return found;
  }

  // A broker's export. Columns are matched by name, whatever their order or spelling.
  function readCsv(text) {
    const source = String(text || '');
    if (source.length > MAX_FILE_BYTES) return { rows: [], unread: [], error: 'That file is too big. The limit is 1 MB.' };
    const firstLines = source.split(/\r?\n/, 16).join('\n');
    const count = ch => firstLines.split(ch).length - 1;
    const delimiter = count('\t') > count(',') && count('\t') > count(';') ? '\t' : count(';') > count(',') ? ';' : ',';
    const table = parseCsv(source, delimiter);
    if (table.length > MAX_FILE_LINES) return { rows: [], unread: [], error: 'That file has too many lines. The limit is 2,000.' };

    let headerAt = -1;
    let columns = {};
    for (let i = 0; i < Math.min(table.length, 15); i += 1) {
      const found = findColumns(table[i]);
      if (found.ticker !== undefined && (found.shares !== undefined || found.value !== undefined)) {
        headerAt = i;
        columns = found;
        break;
      }
    }
    if (headerAt < 0) {
      return { rows: [], unread: [], error: "Couldn't find a column for the ticker and one for the number of shares." };
    }

    const rows = [];
    const notRead = [];
    for (let i = headerAt + 1; i < table.length; i += 1) {
      const cells = table[i];
      const line = cells.join(', ').trim();
      if (!cells.some(c => String(c).trim())) continue;
      const cell = name => (columns[name] === undefined ? '' : String(cells[columns[name]] || '').trim());
      const ticker = normalizeTicker(cell('ticker'));
      if (!ticker) { notRead.push(unread(line, 'no ticker')); continue; }
      const row = { ticker, shares: null, usd: null, paid: null, bought: null };
      const shares = parseAmount(cell('shares'));
      if (columns.shares !== undefined && cell('shares') !== '') {
        if (!usable(shares)) { notRead.push(unread(line, 'the number of shares has to be more than zero')); continue; }
        row.shares = shares;
      } else {
        const value = parseAmount(cell('value'));
        if (!usable(value)) { notRead.push(unread(line, 'no number of shares')); continue; }
        row.usd = value;
      }
      const paid = parseAmount(cell('paid'));
      const perShare = parseAmount(cell('perShare'));
      if (usable(paid)) row.paid = Math.round(paid * 100) / 100;
      else if (usable(perShare) && row.shares) row.paid = Math.round(perShare * row.shares * 100) / 100;
      rows.push(row);
    }
    return { rows, unread: notRead };
  }

  // What is kept in the browser: checked field by field on the way in and on the way out.
  function cleanHolding(raw, knownSectors) {
    if (!raw || typeof raw !== 'object') return null;
    const t = normalizeTicker(raw.t);
    if (!t || t !== raw.t) return null;
    const out = { t, sh: null, paid: null, bought: null, sector: null, usd: null };
    if (usable(raw.sh)) out.sh = raw.sh;
    if (usable(raw.usd)) out.usd = raw.usd;
    if (out.sh === null && out.usd === null) return null;
    if (out.sh !== null) out.usd = null;
    if (usable(raw.paid)) out.paid = raw.paid;
    if (typeof raw.bought === 'string' && MONTH.test(raw.bought)) out.bought = raw.bought;
    if (typeof raw.sector === 'string' && knownSectors && knownSectors.has(raw.sector)) out.sector = raw.sector;
    return out;
  }

  // Parses stored text. Bad rows are dropped and counted, never guessed at.
  function readStored(text, knownSectors) {
    let raw = null;
    try { raw = JSON.parse(text || 'null'); } catch (e) { raw = null; }
    const list = raw && typeof raw === 'object' && Array.isArray(raw.holdings) ? raw.holdings : [];
    const holdings = [];
    const seen = new Set();
    let dropped = 0;
    for (const item of list.slice(0, MAX_HOLDINGS * 2)) {
      const clean = cleanHolding(item, knownSectors);
      if (!clean || seen.has(clean.t) || holdings.length >= MAX_HOLDINGS) { dropped += 1; continue; }
      seen.add(clean.t);
      holdings.push(clean);
    }
    dropped += Math.max(0, list.length - MAX_HOLDINGS * 2);
    return { holdings, dropped };
  }

  function toStored(holdings) {
    return JSON.stringify({ v: 1, holdings: holdings.slice(0, MAX_HOLDINGS) });
  }

  // Adds a parsed row to the list. The same ticker twice is one holding: shares and cost add up,
  // and the earlier buy date and hand-set sector are kept.
  function addRow(holdings, row) {
    const existing = holdings.find(h => h.t === row.ticker);
    if (!existing) {
      if (holdings.length >= MAX_HOLDINGS) return { holdings, added: false, reason: `The limit is ${MAX_HOLDINGS} holdings.` };
      const fresh = { t: row.ticker, sh: row.shares, paid: row.paid, bought: row.bought, sector: null, usd: row.usd };
      return { holdings: holdings.concat([fresh]), added: true, merged: false };
    }
    const next = Object.assign({}, existing);
    if (row.shares !== null && next.sh !== null) next.sh = Math.round((next.sh + row.shares) * 1e6) / 1e6;
    else if (row.shares !== null) { next.sh = row.shares; next.usd = null; }
    else if (next.sh === null) next.usd = Math.round(((next.usd || 0) + row.usd) * 100) / 100;
    else return { holdings, added: false, reason: `${row.ticker} is already here in shares. Add shares, not dollars.` };
    if (row.paid !== null) next.paid = Math.round(((next.paid || 0) + row.paid) * 100) / 100;
    if (!next.bought && row.bought) next.bought = row.bought;
    return { holdings: holdings.map(h => (h.t === row.ticker ? next : h)), added: true, merged: true };
  }

  // A dollar entry becomes shares once there is a real price: dollars divided by that price.
  function sharesFromDollars(usd, price) {
    if (!usable(usd) || !usable(price)) return null;
    return Math.round((usd / price) * 1e6) / 1e6;
  }

  return { normalizeTicker, parseAmount, parsePaste, parseCsv, readCsv, readStored, toStored, addRow, sharesFromDollars,
    cleanHolding, MAX_HOLDINGS, MONTH };
})();
