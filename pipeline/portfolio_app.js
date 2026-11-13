// The portfolio page: holdings kept in this browser, priced from the site's own price files.
//
// What leaves the browser: for a company StockPulse follows, nothing but the request for a static
// file. For any other ticker, that ticker alone goes to this site's /api/history, at most once
// every six hours. Shares, dollars, dates and costs are never sent anywhere.
const PORTFOLIO_KEY = 'stockpulse_portfolio';
const PRICES_KEY = 'stockpulse_prices';
const PRICE_CACHE_MS = 6 * 60 * 60 * 1000;
const PRICE_CACHE_MAX = 40;
const OLD_PRICE_DAYS = 4;
const FIRST_ROWS = 5;
const SECTOR_NAMES = new Set(PF_DATA.sectors);

const PF = {
  holdings: [],
  dropped: 0,
  index: null,        // symbols that have a static price file
  indexFailed: false,
  demo: false,
  info: new Map(),    // ticker -> { status: 'loading' | 'ok' | 'missing' | 'failed', ... }
  waiting: new Map(), // ticker -> promise for its info
  saved: true,
  showAll: false,
  editing: null,
  pending: null,      // a pasted or imported list waiting for "Add these"
  mode: 'shares',
  view: 'overview',   // which part of the page is showing, once there are holdings
  sort: 'value',
  before: [],         // run before the holdings are drawn
  listeners: [],
};

// ---- Small helpers ----------------------------------------------------------------------------

// Builds an element. Text only ever goes in through textContent, so nothing typed, pasted or
// imported can become markup.
function pfEl(tag, props, children) {
  const node = document.createElement(tag);
  Object.keys(props || {}).forEach(key => {
    const value = props[key];
    if (value === null || value === undefined || value === false) return;
    if (key === 'class') node.className = value;
    else if (key === 'text') node.textContent = value;
    else if (key === 'data') Object.keys(value).forEach(k => { node.dataset[k] = value[k]; });
    else if (key === 'hidden' || key === 'disabled' || key === 'selected') node[key] = Boolean(value);
    else node.setAttribute(key, value === true ? '' : String(value));
  });
  (children || []).forEach(child => {
    if (child === null || child === undefined || child === false) return;
    node.append(child.nodeType ? child : document.createTextNode(String(child)));
  });
  return node;
}

const MONEY = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' });
const MONEY_WHOLE = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 });

function pfMoney(value) {
  if (!Number.isFinite(value)) return '';
  return Math.abs(value) >= 100000 ? MONEY_WHOLE.format(value) : MONEY.format(value);
}

function pfShares(value) {
  return new Intl.NumberFormat('en-US', { maximumFractionDigits: value < 100 ? 4 : 2 }).format(value);
}

function pfPercent(fraction, digits) {
  if (!Number.isFinite(fraction)) return '';
  const pct = fraction * 100;
  // One decimal below 10%, none from 10% up (so 9.96% reads "10%", not "10.0%").
  const places = digits !== undefined ? digits : Math.abs(Number(pct.toFixed(1))) < 10 ? 1 : 0;
  return `${pct.toFixed(places)}%`;
}

function pfSigned(fraction) {
  if (!Number.isFinite(fraction)) return '';
  return (fraction > 0 ? '+' : fraction < 0 ? '−' : '') + pfPercent(Math.abs(fraction));
}

// "2026-11-10" as "Nov 10", with the year when it isn't this one.
function pfDay(iso) {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(iso || ''));
  if (!m) return '';
  const when = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
  const sameYear = Number(m[1]) === new Date().getFullYear();
  return when.toLocaleDateString('en-US', sameYear ? { month: 'short', day: 'numeric' } : { month: 'short', day: 'numeric', year: 'numeric' });
}

// "2021-10" as "October 2021".
function pfMonth(month) {
  const m = /^(\d{4})-(\d{2})$/.exec(String(month || ''));
  if (!m) return '';
  return new Date(Number(m[1]), Number(m[2]) - 1, 1).toLocaleDateString('en-US', { month: 'long', year: 'numeric' });
}

function pfDaysOld(iso) {
  const days = daysFromToday(iso);
  return Number.isNaN(days) ? 0 : -days;
}

function pfSay(text, tone) {
  const box = document.getElementById('pfStatus');
  if (!box) return;
  box.textContent = text || '';
  box.className = 'pf-status' + (tone ? ` pf-status-${tone}` : '');
}

// The watchlist company a ticker belongs to: itself, or the listed share class of the same company.
function pfCompany(ticker) {
  if (KNOWN_SYMBOLS.has(ticker)) return ticker;
  const same = PF_DATA.other[ticker];
  return same && KNOWN_SYMBOLS.has(same) ? same : '';
}

function pfName(ticker) {
  const info = PF.info.get(ticker);
  return COMPANY_NAMES[ticker] || (info && info.name) || COMPANY_NAMES[pfCompany(ticker)] || '';
}

function pfIsFund(ticker) {
  const info = PF.info.get(ticker);
  return Boolean(info && info.kind === 'fund');
}

// A holding's sector: the watchlist's, else the one set by hand, else the one the price service gave.
function pfSector(holding) {
  if (pfIsFund(holding.t)) return 'Funds';
  const company = pfCompany(holding.t);
  if (company) return COMPANY_SECTOR[company];
  if (holding.sector) return holding.sector;
  const info = PF.info.get(holding.t);
  return info && info.sector && SECTOR_NAMES.has(info.sector) ? info.sector : '';
}

// ---- Storage ----------------------------------------------------------------------------------

function pfLoad() {
  let text = null;
  try { text = localStorage.getItem(PORTFOLIO_KEY); } catch (e) { text = null; }
  const stored = PortfolioInput.readStored(text, SECTOR_NAMES);
  PF.holdings = stored.holdings;
  PF.dropped = stored.dropped;
}

function pfSave() {
  try {
    if (PF.holdings.length) localStorage.setItem(PORTFOLIO_KEY, PortfolioInput.toStored(PF.holdings));
    else localStorage.removeItem(PORTFOLIO_KEY);
    PF.saved = true;
  } catch (e) {
    // Storage may be blocked or full. The list still works for this visit.
    PF.saved = false;
  }
}

function pfReadPriceCache() {
  let raw = {};
  try { raw = JSON.parse(localStorage.getItem(PRICES_KEY) || '{}') || {}; } catch (e) { raw = {}; }
  const out = {};
  if (!raw || typeof raw !== 'object') return out;
  Object.keys(raw).slice(0, PRICE_CACHE_MAX * 2).forEach(key => {
    const entry = raw[key];
    const ticker = PortfolioInput.normalizeTicker(key);
    if (!ticker || ticker !== key || !entry || typeof entry !== 'object') return;
    const record = pfCheckRecord(ticker, entry.rec);
    if (record && Number.isFinite(entry.at)) out[ticker] = { at: entry.at, rec: record };
  });
  return out;
}

function pfWritePriceCache(ticker, record) {
  const cache = pfReadPriceCache();
  cache[ticker] = { at: Date.now(), rec: record };
  const keep = Object.keys(cache).sort((a, b) => cache[b].at - cache[a].at).slice(0, PRICE_CACHE_MAX);
  const trimmed = {};
  keep.forEach(key => { trimmed[key] = cache[key]; });
  try { localStorage.setItem(PRICES_KEY, JSON.stringify(trimmed)); } catch (e) { /* not cached; asked again next visit */ }
}

// ---- Prices -----------------------------------------------------------------------------------

// A price record from a file, the server or the cache is checked before anything uses it.
function pfCheckRecord(ticker, raw) {
  if (!raw || typeof raw !== 'object' || raw.symbol !== ticker) return null;
  const price = raw.price;
  if (!price || !Number.isFinite(price.value) || price.value <= 0 || !/^\d{4}-\d{2}-\d{2}$/.test(String(price.date))) return null;
  if (raw.kind !== 'stock' && raw.kind !== 'fund') return null;
  const months = [];
  if (Array.isArray(raw.months)) {
    let last = '';
    for (const pair of raw.months.slice(0, 2000)) {
      if (!Array.isArray(pair) || !PortfolioInput.MONTH.test(String(pair[0])) || !Number.isFinite(pair[1]) || pair[1] <= 0 || pair[0] <= last) return null;
      last = pair[0];
      months.push([pair[0], pair[1]]);
    }
  }
  return {
    symbol: ticker,
    name: String(raw.name || '').slice(0, 120),
    kind: raw.kind,
    price: { value: price.value, date: price.date },
    first_month: months.length ? months[0][0] : null,
    months: Array.isArray(raw.months) ? months : null,
    sector: typeof raw.sector === 'string' && SECTOR_NAMES.has(raw.sector) ? raw.sector : null,
    industry: typeof raw.industry === 'string' ? raw.industry.slice(0, 80) : null,
    demo: raw.demo === true,
  };
}

async function pfLoadIndex() {
  try {
    const res = await fetch('data/prices/index.json', { cache: 'no-cache' });
    if (!res.ok) throw new Error('index');
    const body = await res.json();
    PF.index = body && typeof body.symbols === 'object' && body.symbols ? body.symbols : {};
    PF.demo = body.demo === true;
  } catch (e) {
    PF.index = {};
    PF.indexFailed = true;
  }
  const banner = document.getElementById('pfDemo');
  if (banner) banner.hidden = !PF.demo;
}

function pfHasFile(ticker) {
  return Boolean(PF.index && Object.prototype.hasOwnProperty.call(PF.index, ticker));
}

let pfActive = 0;
const pfQueue = [];
function pfLimit(task) {
  return new Promise(resolve => {
    const run = async () => {
      pfActive += 1;
      try { resolve(await task()); } finally {
        pfActive -= 1;
        const next = pfQueue.shift();
        if (next) next();
      }
    };
    if (pfActive < 3) run(); else pfQueue.push(run);
  });
}

function pfWait(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

// One ticker from this site's own server. Only the ticker is sent.
async function pfAskServer(ticker) {
  for (let attempt = 0; attempt < 3; attempt += 1) {
    let res;
    try {
      res = await fetch('/api/history?ticker=' + encodeURIComponent(ticker));
    } catch (e) {
      return { status: 'failed' };
    }
    if (res.status === 429 && attempt < 2) {
      const wait = Math.min(20, Math.max(1, Number(res.headers.get('Retry-After')) || 5));
      await pfWait(wait * 1000);
      continue;
    }
    let body = null;
    try { body = await res.json(); } catch (e) { body = null; }
    if (res.status === 404) {
      const foreign = body && /only prices US-listed/.test(String(body.error || ''));
      return { status: 'missing', why: foreign ? 'foreign' : 'unknown' };
    }
    if (!res.ok || !body || body.found !== true) return { status: 'failed' };
    const record = pfCheckRecord(ticker, body);
    return record ? Object.assign({ status: 'ok' }, record) : { status: 'failed' };
  }
  return { status: 'failed' };
}

async function pfFetchInfo(ticker, wantMonths) {
  if (pfHasFile(ticker)) {
    if (!wantMonths) {
      const entry = PF.index[ticker];
      const record = pfCheckRecord(ticker, { symbol: ticker, name: entry.name, kind: entry.kind, price: entry.price });
      if (record) {
        record.first_month = PortfolioInput.MONTH.test(String(entry.first_month)) ? entry.first_month : null;
        return Object.assign({ status: 'ok', local: true }, record);
      }
    }
    try {
      const res = await fetch('data/prices/' + encodeURIComponent(ticker) + '.json', { cache: 'no-cache' });
      const record = res.ok ? pfCheckRecord(ticker, await res.json()) : null;
      return record ? Object.assign({ status: 'ok', local: true }, record) : { status: 'failed' };
    } catch (e) {
      return { status: 'failed' };
    }
  }
  const cached = pfReadPriceCache()[ticker];
  if (cached && Date.now() - cached.at < PRICE_CACHE_MS) return Object.assign({ status: 'ok' }, cached.rec);
  const answer = await pfLimit(() => pfAskServer(ticker));
  if (answer.status === 'ok') {
    const { status, ...record } = answer;
    pfWritePriceCache(ticker, record);
  } else if (answer.status === 'failed' && cached) {
    // The server couldn't be reached: the last real reading, with its own date, is better than nothing.
    return Object.assign({ status: 'ok' }, cached.rec);
  }
  return answer;
}

// What is known about a ticker: its name, whether it's a fund, its latest price and (when asked)
// its monthly history. Asked for once, then remembered for this visit.
function pfInfo(ticker, wantMonths) {
  const known = PF.info.get(ticker);
  if (known && known.status !== 'loading' && (!wantMonths || known.months || known.status !== 'ok')) return Promise.resolve(known);
  const key = ticker + (wantMonths ? ':months' : '');
  if (PF.waiting.has(key)) return PF.waiting.get(key);
  if (!known) PF.info.set(ticker, { status: 'loading' });
  const promise = (async () => {
    if (!PF.index) await pfLoadIndex();
    const info = await pfFetchInfo(ticker, wantMonths);
    PF.info.set(ticker, info);
    PF.waiting.delete(key);
    return info;
  })();
  PF.waiting.set(key, promise);
  return promise;
}

// ---- Changing the list ------------------------------------------------------------------------

function pfChanged() {
  pfSave();
  pfRender();
}

// Dollar entries become shares the first time a real price is known for them.
function pfConvertDollars() {
  let changed = false;
  PF.holdings = PF.holdings.map(h => {
    if (h.sh !== null || h.usd === null) return h;
    const info = PF.info.get(h.t);
    if (!info || info.status !== 'ok') return h;
    const shares = PortfolioInput.sharesFromDollars(h.usd, info.price.value);
    if (shares === null) return h;
    changed = true;
    return Object.assign({}, h, { sh: shares, usd: null });
  });
  if (changed) pfSave();
}

async function pfPriceAll() {
  const tickers = PF.holdings.map(h => h.t);
  await Promise.all(tickers.map(async t => {
    await pfInfo(t);
    pfConvertDollars();
    pfRender();
  }));
}

// Turns what was typed in the ticker box into a ticker: a symbol, or a company's name.
async function pfResolve(text) {
  const typed = String(text || '').trim();
  if (!typed) return { error: 'Type a ticker, like NVDA.' };
  const ticker = PortfolioInput.normalizeTicker(typed);
  if (!PF.index) await pfLoadIndex();
  if (ticker && (KNOWN_SYMBOLS.has(ticker) || pfHasFile(ticker))) return { ticker };
  const lower = typed.toLowerCase();
  const byName = Object.keys(COMPANY_NAMES).filter(sym => COMPANY_NAMES[sym].toLowerCase() === lower);
  const starts = lower.length >= 3 ? Object.keys(COMPANY_NAMES).filter(sym => COMPANY_NAMES[sym].toLowerCase().startsWith(lower)) : [];
  if (byName.length === 1) return { ticker: byName[0] };
  if (starts.length === 1) return { ticker: starts[0] };
  if (ticker) {
    const info = await pfInfo(ticker);
    if (info.status === 'ok' || info.status === 'failed') return { ticker };
    if (info.why === 'foreign') return { error: 'StockPulse only prices US-listed stocks and funds in dollars.' };
  }
  // Not a ticker we can find: ask the existing lookup, which also knows company names.
  if (/^[A-Za-z0-9][A-Za-z0-9 .,&'-]{0,59}$/.test(typed)) {
    try {
      const res = await fetch('/api/lookup?q=' + encodeURIComponent(typed));
      const body = res.ok ? await res.json() : null;
      const found = body && body.found ? PortfolioInput.normalizeTicker(body.symbol) : '';
      if (found) {
        const info = await pfInfo(found);
        if (info.status === 'ok') return { ticker: found };
      }
    } catch (e) { /* the lookup isn't available; fall through to "couldn't find" */ }
  }
  return { error: `We couldn’t find “${typed.slice(0, 40)}”.` };
}

function pfSetMode(mode) {
  PF.mode = mode === 'dollars' ? 'dollars' : 'shares';
  document.querySelectorAll('[data-pf-mode]').forEach(btn => {
    btn.setAttribute('aria-pressed', String(btn.dataset.pfMode === PF.mode));
  });
  const amount = document.getElementById('pfAmount');
  if (amount) {
    amount.placeholder = PF.mode === 'dollars' ? 'Dollars, e.g. 2000' : 'Shares, e.g. 10';
    amount.setAttribute('aria-label', PF.mode === 'dollars' ? 'What it is worth today, in dollars' : 'Number of shares');
  }
}

function pfToggle(id, button) {
  const box = document.getElementById(id);
  if (!box) return;
  box.hidden = !box.hidden;
  if (button) button.setAttribute('aria-expanded', String(!box.hidden));
  if (!box.hidden) {
    const first = box.querySelector('input, textarea');
    if (first) first.focus();
  }
}

async function pfAddOne() {
  const tickerBox = document.getElementById('pfTicker');
  const amountBox = document.getElementById('pfAmount');
  const boughtBox = document.getElementById('pfBought');
  const paidBox = document.getElementById('pfPaid');
  const amount = PortfolioInput.parseAmount(amountBox.value);
  if (!(amount > 0) || amount >= 1e12) {
    pfSay(PF.mode === 'dollars' ? 'Type what it is worth today, in dollars.' : 'Type how many shares you hold.', 'bad');
    amountBox.focus();
    return;
  }
  let paid = null;
  if (paidBox.value.trim()) {
    paid = PortfolioInput.parseAmount(paidBox.value);
    if (!(paid > 0) || paid >= 1e12) { pfSay('“Paid” is the total you paid, in dollars.', 'bad'); paidBox.focus(); return; }
  }
  const bought = PortfolioInput.MONTH.test(boughtBox.value) ? boughtBox.value : null;
  pfSay('Checking…');
  const found = await pfResolve(tickerBox.value);
  if (found.error) { pfSay(found.error, 'bad'); tickerBox.focus(); return; }
  const row = { ticker: found.ticker, shares: PF.mode === 'shares' ? amount : null, usd: PF.mode === 'dollars' ? amount : null, paid, bought };
  const result = PortfolioInput.addRow(PF.holdings, row);
  if (!result.added) { pfSay(result.reason, 'bad'); return; }
  PF.holdings = result.holdings;
  tickerBox.value = ''; amountBox.value = ''; boughtBox.value = ''; paidBox.value = '';
  const info = await pfInfo(found.ticker);
  pfConvertDollars();
  pfChanged();
  const now = PF.holdings.find(h => h.t === found.ticker);
  const unpriced = info.status !== 'ok' ? ' We couldn’t get its price right now.' : '';
  pfSay(result.merged && now && now.sh !== null
    ? `Added to ${found.ticker}. You now have ${pfShares(now.sh)} shares.${unpriced}`
    : `Added ${found.ticker}.${unpriced}`, PF.saved ? 'good' : 'bad');
  if (!PF.saved) pfSay(`Added ${found.ticker}, but this browser wouldn’t save it. It will be gone when you leave the page.`, 'bad');
  tickerBox.focus();
}

// ---- Pasted and imported lists ----------------------------------------------------------------

function pfOfferRows(result, source) {
  if (result.error) { pfSay(result.error, 'bad'); return; }
  if (!result.rows.length && !result.unread.length) { pfSay('There was nothing to read.', 'bad'); return; }
  PF.pending = { rows: result.rows.slice(0, PortfolioInput.MAX_HOLDINGS), unread: result.unread.slice(0, 200), source };
  pfSay('');
  pfRenderPreview();
  document.getElementById('pfPreview').scrollIntoView({ block: 'nearest' });
  [...new Set(PF.pending.rows.map(r => r.ticker))].forEach(async ticker => {
    await pfInfo(ticker);
    if (PF.pending) pfRenderPreview();
  });
}

function pfReadPaste() {
  const box = document.getElementById('pfPasteText');
  pfOfferRows(PortfolioInput.parsePaste(box.value), 'paste');
}

function pfReadFile(input) {
  const file = input.files && input.files[0];
  input.value = '';
  if (!file) return;
  if (file.size > 1024 * 1024) { pfSay('That file is too big. The limit is 1 MB.', 'bad'); return; }
  const reader = new FileReader();
  // The file is read here, in the browser. It isn't uploaded anywhere.
  reader.onload = () => pfOfferRows(PortfolioInput.readCsv(String(reader.result || '')), 'file');
  reader.onerror = () => pfSay('That file couldn’t be read.', 'bad');
  reader.readAsText(file);
}

function pfRowWords(row, info) {
  if (row.shares !== null) return `${pfShares(row.shares)} ${row.shares === 1 ? 'share' : 'shares'}`;
  const shares = info && info.status === 'ok' ? PortfolioInput.sharesFromDollars(row.usd, info.price.value) : null;
  return shares === null ? `${pfMoney(row.usd)} today` : `${pfMoney(row.usd)} today, about ${pfShares(shares)} shares at the ${pfDay(info.price.date)} price`;
}

function pfRenderPreview() {
  const box = document.getElementById('pfPreview');
  box.replaceChildren();
  const pending = PF.pending;
  box.hidden = !pending;
  if (!pending) return;
  let ready = 0;
  let checking = 0;
  const list = pfEl('ul', { class: 'pf-preview-rows' });
  pending.rows.forEach(row => {
    const info = PF.info.get(row.ticker) || { status: 'loading' };
    const have = PF.holdings.find(h => h.t === row.ticker);
    let note = '';
    let bad = false;
    if (info.status === 'loading') { note = 'checking…'; checking += 1; }
    else if (info.status === 'missing') { note = info.why === 'foreign' ? 'not a US-listed stock or fund, so it won’t be added' : 'we couldn’t find this ticker, so it won’t be added'; bad = true; }
    else {
      ready += 1;
      if (info.status === 'failed') note = 'we couldn’t get its price right now; it will be added without one';
      else if (have && have.sh !== null && row.shares !== null) note = `adds to the ${pfShares(have.sh)} you have`;
      else if (have && have.sh !== null) { note = 'already here in shares, so this dollar amount won’t be added'; bad = true; ready -= 1; }
    }
    list.append(pfEl('li', { class: 'pf-preview-row' + (bad ? ' pf-preview-bad' : '') }, [
      pfEl('span', { class: 'pf-ticker', text: row.ticker }),
      pfEl('span', { class: 'pf-preview-name', text: pfName(row.ticker) }),
      pfEl('span', { class: 'pf-preview-what', text: pfRowWords(row, info) + (row.paid !== null ? `, paid ${pfMoney(row.paid)}` : '') }),
      note ? pfEl('span', { class: 'pf-preview-note', text: note }) : null,
    ]));
  });
  box.append(pfEl('h2', { class: 'settings-heading', text: pending.source === 'file' ? 'From your file' : 'From what you pasted' }));
  if (pending.rows.length) box.append(list);
  if (pending.unread.length) {
    box.append(pfEl('p', { class: 'pf-preview-unread-head', text: `${plural(pending.unread.length, 'line', 'lines')} couldn’t be read:` }));
    box.append(pfEl('ul', { class: 'pf-preview-unread' }, pending.unread.map(u =>
      pfEl('li', {}, [pfEl('span', { class: 'pf-unread-text', text: u.text }), pfEl('span', { class: 'pf-unread-why', text: u.reason })]))));
  }
  box.append(pfEl('div', { class: 'pf-preview-actions' }, [
    pfEl('button', { type: 'button', class: 'setup-yes', data: { click: 'pfAcceptPreview' }, disabled: checking > 0 || ready === 0,
      text: checking > 0 ? 'Checking…' : ready === 0 ? 'Nothing to add' : `Add ${ready === 1 ? 'this one' : `these ${ready}`}` }),
    pfEl('button', { type: 'button', class: 'setup-no', data: { click: 'pfCancelPreview' }, text: 'Cancel' }),
  ]));
}

function pfAcceptPreview() {
  if (!PF.pending) return;
  let added = 0;
  let refused = '';
  PF.pending.rows.forEach(row => {
    const info = PF.info.get(row.ticker);
    if (!info || info.status === 'missing' || info.status === 'loading') return;
    const result = PortfolioInput.addRow(PF.holdings, row);
    if (result.added) { PF.holdings = result.holdings; added += 1; } else if (!refused) refused = result.reason;
  });
  PF.pending = null;
  pfRenderPreview();
  const paste = document.getElementById('pfPasteText');
  if (paste) paste.value = '';
  const pasteBox = document.getElementById('pfPasteBox');
  if (pasteBox) pasteBox.hidden = true;
  pfConvertDollars();
  pfChanged();
  pfSay(!PF.saved ? 'Added, but this browser wouldn’t save it. It will be gone when you leave the page.'
    : `Added ${plural(added, 'holding', 'holdings')}.${refused ? ' ' + refused : ''}`, PF.saved ? 'good' : 'bad');
}

function pfCancelPreview() {
  PF.pending = null;
  pfRenderPreview();
}

// ---- The list ---------------------------------------------------------------------------------

// Each holding with what is known about it now, largest first.
function pfRows() {
  const rows = PF.holdings.map(h => {
    const info = PF.info.get(h.t) || { status: 'loading' };
    const priced = info.status === 'ok' && h.sh !== null;
    const value = priced ? h.sh * info.price.value : h.sh === null && h.usd !== null ? h.usd : null;
    return { h, info, priced, value, sector: pfSector(h), fund: pfIsFund(h.t), company: pfCompany(h.t) };
  });
  const total = rows.reduce((sum, r) => sum + (r.value || 0), 0);
  rows.forEach(r => { r.weight = r.value !== null && total > 0 ? r.value / total : null; });
  rows.sort((a, b) => (b.value || 0) - (a.value || 0) || a.h.t.localeCompare(b.h.t));
  return { rows, total };
}

function pfMeta(row) {
  const { h, info } = row;
  if (h.sh === null) {
    if (info.status === 'loading') return `${pfMoney(h.usd)} entered · getting its price…`;
    return `${pfMoney(h.usd)} entered · not priced yet, so not turned into shares`;
  }
  const shares = `${pfShares(h.sh)} ${h.sh === 1 ? 'share' : 'shares'}`;
  if (info.status === 'loading') return `${shares} · getting its price…`;
  if (info.status === 'missing') return `${shares} · ${info.why === 'foreign' ? 'not a US-listed stock or fund' : 'we couldn’t find this ticker'}, so it isn’t counted`;
  if (info.status === 'failed') return `${shares} · we couldn’t get its price right now, so it isn’t counted`;
  return `${shares} · ${pfMoney(info.price.value)} on ${pfDay(info.price.date)}`;
}

function pfEditForm(row) {
  const { h } = row;
  const needsSector = !row.fund && !row.company;
  const field = (label, input) => pfEl('label', { class: 'pf-field' }, [pfEl('span', { class: 'pf-field-label', text: label }), input]);
  const sectorSelect = needsSector ? pfEl('select', { class: 'pf-input', id: 'pfEditSector' },
    [pfEl('option', { value: '', text: row.info.sector ? `${row.info.sector} (from the price service)` : 'Sector unknown' })].concat(
      PF_DATA.sectors.filter(s => s !== 'Other').map(s => pfEl('option', { value: s, text: s, selected: h.sector === s })))) : null;
  return pfEl('div', { class: 'pf-edit', id: 'pfEdit' }, [
    field('Shares', pfEl('input', { class: 'pf-input', id: 'pfEditShares', type: 'text', inputmode: 'decimal', value: h.sh !== null ? String(h.sh) : '' })),
    field('Bought (month)', pfEl('input', { class: 'pf-input', id: 'pfEditBought', type: 'month', value: h.bought || '', max: todayKey().slice(0, 7) })),
    field('Paid in total ($)', pfEl('input', { class: 'pf-input', id: 'pfEditPaid', type: 'text', inputmode: 'decimal', value: h.paid !== null ? String(h.paid) : '' })),
    sectorSelect ? field('Sector', sectorSelect) : null,
    pfEl('div', { class: 'pf-edit-actions' }, [
      pfEl('button', { type: 'button', class: 'setup-yes', data: { click: 'pfSaveEdit', ticker: h.t }, text: 'Save' }),
      pfEl('button', { type: 'button', class: 'setup-no', data: { click: 'pfCancelEdit' }, text: 'Cancel' }),
      pfEl('button', { type: 'button', class: 'pf-link pf-danger', data: { click: 'pfRemoveOne', ticker: h.t }, text: `Remove ${h.t}` }),
    ]),
  ]);
}

function pfRenderHoldings() {
  const { rows, total } = pfRows();
  const section = document.getElementById('pfHoldings');
  const list = document.getElementById('pfList');
  const empty = document.getElementById('pfEmpty');
  section.hidden = rows.length === 0;
  empty.hidden = rows.length !== 0;
  list.replaceChildren();
  if (!rows.length) return;

  const sorter = document.getElementById('pfSortBox');
  sorter.hidden = rows.length < 4;
  if (PF.sort === 'name') rows.sort((a, b) => a.h.t.localeCompare(b.h.t));
  else if (PF.sort === 'change') {
    const change = r => { const m = SUM.moves && SUM.moves.get(r.h.t); return m ? m.change : -Infinity; };
    rows.sort((a, b) => change(b) - change(a) || a.h.t.localeCompare(b.h.t));
  }
  const anyPaid = rows.some(r => r.h.paid !== null && r.priced);
  const shown = PF.showAll || rows.length <= FIRST_ROWS + 1 ? rows : rows.slice(0, FIRST_ROWS);
  shown.forEach(row => {
    const { h, info } = row;
    const name = pfName(h.t);
    const old = row.priced && pfDaysOld(info.price.date) > OLD_PRICE_DAYS;
    const gain = row.priced && h.paid !== null ? row.value - h.paid : null;
    const title = row.company
      ? pfEl('a', { class: 'pf-ticker', href: companyHref(row.company), text: h.t })
      : pfEl('span', { class: 'pf-ticker', text: h.t });
    const tags = [];
    if (row.fund) tags.push('Fund');
    else if (row.sector) tags.push(row.sector + (h.sector && !row.company ? ' (set by you)' : ''));
    else if (info.status === 'ok') tags.push('Sector unknown');
    const share = row.weight !== null
      ? pfEl('span', {}, [tags.length ? ' · ' : '', pfEl('span', { class: 'pf-row-weight', text: pfPercent(row.weight) }), ' of your portfolio'])
      : null;
    const paidGain = gain !== null ? pfEl('div', { class: 'pf-gain ' + (gain > 0 ? 'pos' : gain < 0 ? 'neg' : ''),
      text: `${gain > 0 ? '+' : gain < 0 ? '−' : ''}${pfMoney(Math.abs(gain))} since you bought` }) : null;
    const item = pfEl('li', { class: 'pf-row' + (row.priced || h.sh === null ? '' : ' pf-row-out'), data: { ticker: h.t } }, [
      pfEl('div', { class: 'pf-row-main' }, [
        pfEl('div', { class: 'pf-row-title' }, [title, name ? pfEl('span', { class: 'pf-row-name', text: name }) : null]),
        pfEl('div', { class: 'pf-row-meta' + (old ? ' pf-old' : ''), text: pfMeta(row) + (old ? ' (an old price)' : '') }),
        tags.length || share ? pfEl('div', { class: 'pf-row-meta' }, [tags.join(' · '), share]) : null,
      ]),
      pfEl('div', { class: 'pf-row-spark' }, [row.priced ? pfSparkline(info) : null]),
      pfEl('div', { class: 'pf-row-value' }, [
        pfEl('div', { class: 'pf-value', text: row.value !== null ? pfMoney(row.value) : '—' }),
        row.priced ? pfRowMove(h.t) : null,
        paidGain,
      ]),
      pfEl('button', { type: 'button', class: 'pf-link', data: { click: 'pfEditOne', ticker: h.t }, 'aria-label': `Edit ${h.t}`,
        'aria-expanded': String(PF.editing === h.t), text: 'Edit' }),
    ]);
    list.append(item);
    if (PF.editing === h.t) list.append(pfEl('li', { class: 'pf-row-edit' }, [pfEditForm(row)]));
  });

  const more = document.getElementById('pfShowAll');
  more.hidden = shown.length === rows.length && !PF.showAll;
  more.textContent = PF.showAll ? 'Show fewer' : `Show all ${rows.length}`;
  if (rows.length <= FIRST_ROWS + 1) more.hidden = true;

  const priced = rows.filter(r => r.priced);
  const dates = priced.map(r => r.info.price.date).sort();
  const out = rows.filter(r => r.value === null).map(r => r.h.t);
  const stale = priced.filter(r => pfDaysOld(r.info.price.date) > OLD_PRICE_DAYS).map(r => r.h.t);
  document.getElementById('pfTotal').textContent = pfMoney(total);
  const notes = [];
  if (dates.length) {
    notes.push(dates[0] === dates[dates.length - 1] ? `Prices from ${pfDay(dates[0])}.` : `Prices from ${pfDay(dates[0])} to ${pfDay(dates[dates.length - 1])}.`);
  }
  if (stale.length) notes.push(`Old ${stale.length === 1 ? 'price' : 'prices'}: ${stale.join(', ')}.`);
  if (out.length) notes.push(`Not counted: ${out.join(', ')}.`);
  if (rows.some(r => r.info.status === 'loading')) notes.push('Still getting some prices…');
  if (anyPaid) notes.push('“Since you bought” is today’s value against what you paid.');
  document.getElementById('pfTotalNote').textContent = notes.join(' ');
}

// ---- The parts of the page --------------------------------------------------------------------

// With holdings, the page shows one part at a time. With none, it is just the form to add some.
const PF_VIEWS = ['overview', 'holdings', 'exposure', 'what-if'];

function pfViewFromAddress() {
  const hash = String(location.hash || '').slice(1);
  if (PF_VIEWS.includes(hash)) return hash;
  return /[?&]t=/.test(location.search) ? 'what-if' : null;
}

function pfSyncView() {
  const tabs = document.getElementById('pfTabs');
  const has = PF.holdings.length > 0;
  if (has && PF.wasEmpty) PF.view = 'holdings'; // just added the first one: show it
  PF.wasEmpty = !has;
  tabs.hidden = !has;
  if (has) document.body.dataset.view = PF.view; else delete document.body.dataset.view;
  tabs.querySelectorAll('button').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.view === PF.view)));
}

function pfSetView(view) {
  if (!PF_VIEWS.includes(view)) return;
  PF.view = view;
  try { history.replaceState(null, '', '#' + view); } catch (e) { /* the address just isn't updated */ }
  pfRender();
  window.scrollTo(0, 0);
}

function pfRender() {
  pfSyncView();
  PF.before.forEach(fn => { try { fn(); } catch (e) { /* the holdings still show */ } });
  pfRenderHoldings();
  const note = document.getElementById('pfDropped');
  note.hidden = PF.dropped === 0;
  note.textContent = PF.dropped ? `${plural(PF.dropped, 'saved holding', 'saved holdings')} couldn’t be read and ${PF.dropped === 1 ? 'was' : 'were'} left out.` : '';
  const failed = document.getElementById('pfPricesFailed');
  failed.hidden = !PF.indexFailed;
  pfSyncFollow();
  PF.listeners.forEach(fn => { try { fn(); } catch (e) { /* one section failing must not blank the page */ } });
}

// "Follow these companies": the companies held that StockPulse follows go into the existing For you
// settings. Only which companies, never how much: the same list the Follow buttons elsewhere keep.
function pfUnfollowedHeld() {
  const direct = new Set(followState().symbols);
  return [...new Set(PF.holdings.map(h => pfCompany(h.t)).filter(sym => sym && !direct.has(sym)))];
}

function pfSyncFollow() {
  const box = document.getElementById('pfFollowBox');
  const held = [...new Set(PF.holdings.map(h => pfCompany(h.t)).filter(Boolean))];
  const todo = pfUnfollowedHeld();
  box.hidden = held.length === 0;
  document.getElementById('pfFollow').hidden = todo.length === 0;
  document.getElementById('pfFollowNote').textContent = todo.length
    ? `Adds ${todo.length === 1 ? todo[0] : `${todo.length} companies`} to For you, so their stories come first. It doesn’t share what you hold.`
    : `You follow ${held.length === 1 ? 'this company' : `all ${held.length} of these companies`} in For you.`;
}

function pfFollowHeld() {
  const todo = pfUnfollowedHeld();
  if (!todo.length) return;
  updateFollowState({ symbols: [...new Set([...followState().symbols, ...todo])] });
  pfSay(`Now following ${todo.length <= 4 ? todo.join(', ') : `${todo.length} more companies`}. Change this any time in Your feed.`, 'good');
}

function pfEditOne(ticker) {
  PF.editing = PF.editing === ticker ? null : ticker;
  pfRenderHoldings();
  const first = document.getElementById('pfEditShares');
  if (first) first.focus();
}

function pfSaveEdit(ticker) {
  const current = PF.holdings.find(h => h.t === ticker);
  if (!current) return;
  const sharesText = document.getElementById('pfEditShares').value.trim();
  const paidText = document.getElementById('pfEditPaid').value.trim();
  const bought = document.getElementById('pfEditBought').value;
  const sector = document.getElementById('pfEditSector');
  const next = Object.assign({}, current);
  if (sharesText || current.sh !== null) {
    const shares = PortfolioInput.parseAmount(sharesText);
    if (!(shares > 0) || shares >= 1e12) { pfSay('Shares has to be a number above zero.', 'bad'); return; }
    next.sh = shares;
    next.usd = null;
  }
  if (paidText) {
    const paid = PortfolioInput.parseAmount(paidText);
    if (!(paid > 0) || paid >= 1e12) { pfSay('“Paid” is the total you paid, in dollars.', 'bad'); return; }
    next.paid = paid;
  } else next.paid = null;
  next.bought = PortfolioInput.MONTH.test(bought) ? bought : null;
  if (sector) next.sector = SECTOR_NAMES.has(sector.value) ? sector.value : null;
  PF.holdings = PF.holdings.map(h => (h.t === ticker ? next : h));
  PF.editing = null;
  pfChanged();
  pfSay(`Saved ${ticker}.`, 'good');
}

function pfRemoveOne(ticker) {
  PF.holdings = PF.holdings.filter(h => h.t !== ticker);
  PF.editing = null;
  pfChanged();
  pfSay(`Removed ${ticker}.`, 'good');
}

function pfRemoveAll() {
  if (!window.confirm('Remove every holding from this browser? This can’t be undone.')) return;
  PF.holdings = [];
  PF.editing = null;
  PF.pending = null;
  try { localStorage.removeItem(PORTFOLIO_KEY); localStorage.removeItem(PRICES_KEY); } catch (e) { /* nothing stored */ }
  pfRenderPreview();
  pfRender();
  pfSay('Everything was removed from this browser.', 'good');
}

Object.assign(PAGE_ACTIONS.click, {
  pfAddOne: () => pfAddOne(),
  pfSetMode: el => pfSetMode(el.dataset.pfMode),
  pfToggleDetails: el => pfToggle('pfDetails', el),
  pfTogglePaste: el => pfToggle('pfPasteBox', el),
  pfPickFile: () => document.getElementById('pfFile').click(),
  pfReadPaste: () => pfReadPaste(),
  pfAcceptPreview: () => pfAcceptPreview(),
  pfCancelPreview: () => pfCancelPreview(),
  pfEditOne: el => pfEditOne(el.dataset.ticker),
  pfSaveEdit: el => pfSaveEdit(el.dataset.ticker),
  pfCancelEdit: () => { PF.editing = null; pfRenderHoldings(); },
  pfRemoveOne: el => pfRemoveOne(el.dataset.ticker),
  pfRemoveAll: () => pfRemoveAll(),
  pfShowAll: () => { PF.showAll = !PF.showAll; pfRenderHoldings(); },
  pfFollowHeld: () => pfFollowHeld(),
  pfView: el => pfSetView(el.dataset.view),
});
Object.assign(PAGE_ACTIONS.change, {
  pfReadFile: el => pfReadFile(el),
  pfSort: el => { PF.sort = el.value; PF.showAll = false; pfRenderHoldings(); },
});

document.addEventListener('keydown', event => {
  if (event.key !== 'Enter' || !event.target.closest) return;
  if (event.target.closest('#pfAddRow')) { event.preventDefault(); pfAddOne(); }
  else if (event.target.closest('#pfEdit') && event.target.tagName === 'INPUT') {
    event.preventDefault();
    const save = document.querySelector('#pfEdit [data-click="pfSaveEdit"]');
    if (save) pfSaveEdit(save.dataset.ticker);
  }
});

document.addEventListener('followchange', () => pfSyncFollow());

// Another tab changed the list: pick that up here too.
window.addEventListener('storage', event => {
  if (event.key !== PORTFOLIO_KEY) return;
  pfLoad();
  pfRender();
  pfPriceAll();
});

window.addEventListener('hashchange', () => {
  const view = pfViewFromAddress();
  if (view && view !== PF.view) { PF.view = view; pfRender(); }
});

document.addEventListener('DOMContentLoaded', async () => {
  pfLoad();
  PF.view = pfViewFromAddress() || 'overview';
  PF.wasEmpty = false;
  pfSetMode('shares');
  pfRender();
  await pfLoadIndex();
  pfRender();
  pfPriceAll();
});
