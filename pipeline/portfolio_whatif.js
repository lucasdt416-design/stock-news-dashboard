// "What if I'd invested": what an amount put into a stock would be worth now, beside the same
// money in the S&P 500 fund. Uses the same price histories as the rest of the page: a static file
// for a company StockPulse follows, and for any other ticker one request carrying that ticker only.
// A result can be shared as a link (?t=NVDA&a=1000&from=2021-10). A whole-portfolio result can't,
// so holdings never end up in an address.
const WI = { result: null, showNumbers: false, busy: false };
const WI_MAX = 1e9;

function wiSay(text, tone) {
  const box = document.getElementById('wiStatus');
  box.replaceChildren(text || '');
  box.className = 'pf-status' + (tone ? ` pf-status-${tone}` : '');
}

function wiToday() {
  return todayKey();
}

function wiPick(years) {
  const month = document.getElementById('wiFrom');
  if (years === 'first') {
    month.value = '';
    month.dataset.first = '1';
    month.placeholder = 'the first month';
    document.querySelectorAll('[data-wi-years]').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.wiYears === 'first')));
    return;
  }
  delete month.dataset.first;
  month.value = PortfolioMath.monthYearsAgo(wiToday(), Number(years));
  document.querySelectorAll('[data-wi-years]').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.wiYears === String(years))));
}

function wiClearPicks() {
  const month = document.getElementById('wiFrom');
  delete month.dataset.first;
  document.querySelectorAll('[data-wi-years]').forEach(b => b.setAttribute('aria-pressed', 'false'));
}

function wiHistory(info) {
  return { months: info.months || [], price: info.price.value, date: info.price.date };
}

function wiYears(years) {
  if (years < 1) return `${Math.max(1, Math.round(years * 12))} months`;
  const rounded = Math.round(years * 10) / 10;
  return `${String(rounded).replace(/\.0$/, '')} ${rounded === 1 ? 'year' : 'years'}`;
}

function wiRate(result) {
  return result.perYear === null ? '' : `, about ${pfSigned(result.perYear)} a year`;
}

// Reads the form. Returns null (after saying why) if something is missing or out of range.
function wiRead() {
  const amount = PortfolioInput.parseAmount(document.getElementById('wiAmount').value);
  if (!(amount > 0) || amount > WI_MAX) { wiSay('Type an amount in dollars, like 1000.', 'bad'); return null; }
  const monthlyText = document.getElementById('wiMonthly').value.trim();
  let monthly = 0;
  if (monthlyText) {
    monthly = PortfolioInput.parseAmount(monthlyText);
    if (!(monthly > 0) || monthly > WI_MAX) { wiSay('The monthly amount has to be a number above zero, or left empty.', 'bad'); return null; }
  }
  const box = document.getElementById('wiFrom');
  const first = box.dataset.first === '1';
  if (!first && !PortfolioInput.MONTH.test(box.value)) { wiSay('Pick the month to start from, or one of the quick picks.', 'bad'); return null; }
  if (!first && box.value >= wiToday().slice(0, 7)) { wiSay('The start has to be a month that has finished.', 'bad'); return null; }
  return { amount, monthly, from: first ? null : box.value };
}

async function wiRun() {
  if (WI.busy) return;
  const input = wiRead();
  if (!input) return;
  WI.busy = true;
  wiSay('Getting prices…');
  try {
    const found = await pfResolve(document.getElementById('wiTicker').value);
    if (found.error) { wiSay(found.error, 'bad'); return; }
    const [info, spyInfo] = await Promise.all([pfInfo(found.ticker, true), pfInfo(PF_SPY, true)]);
    if (info.status !== 'ok' || !info.months) {
      wiSay(info.status === 'missing' ? `We couldn’t find ${found.ticker}.` : `Couldn’t get prices for ${found.ticker} right now. Try again in a little while.`, 'bad');
      return;
    }
    if (!info.months.length) { wiSay(`${found.ticker} hasn’t finished its first month of trading, so there’s nothing to work out yet.`, 'bad'); return; }
    const from = input.from || info.months[0][0];
    const run = PortfolioMath.whatIf(wiHistory(info), input.amount, from, input.monthly);
    if (run.error === 'before') {
      const box = document.getElementById('wiStatus');
      wiSay('');
      box.className = 'pf-status';
      box.replaceChildren(`${found.ticker} started trading in ${pfMonth(run.first)}, after the month you picked. `,
        pfEl('button', { type: 'button', class: 'pf-link', data: { click: 'wiUseFirst', month: run.first }, text: `Use ${pfMonth(run.first)}` }));
      return;
    }
    let spy = null;
    if (spyInfo.status === 'ok' && spyInfo.months && found.ticker !== PF_SPY) {
      const same = PortfolioMath.whatIf(wiHistory(spyInfo), input.amount, run.from, input.monthly);
      if (!same.error && same.from === run.from) spy = same;
    }
    WI.result = { kind: 'one', ticker: found.ticker, name: pfName(found.ticker), input, run, spy, demo: info.demo };
    wiSay('');
    wiRender();
    wiWriteLink();
  } finally {
    WI.busy = false;
  }
}

async function wiRunPortfolio(skip) {
  if (WI.busy) return;
  const input = wiRead();
  if (!input) return;
  if (!input.from) { wiSay('Pick a month to start from. “From its first month” only works for one ticker.', 'bad'); return; }
  const rows = pfRows().rows.filter(r => r.priced);
  if (!rows.length) { wiSay('Add some holdings first.', 'bad'); return; }
  WI.busy = true;
  wiSay('Getting prices…');
  try {
    const infos = await Promise.all(rows.map(r => pfInfo(r.h.t, true)));
    const spyInfo = await pfInfo(PF_SPY, true);
    const missing = rows.filter((r, i) => infos[i].status !== 'ok' || !infos[i].months).map(r => r.h.t);
    if (missing.length && !skip) {
      const box = document.getElementById('wiStatus');
      box.className = 'pf-status pf-status-bad';
      box.replaceChildren(`Couldn’t get the price history for ${pfList(missing)}, so there’s no total to show. `,
        pfEl('button', { type: 'button', class: 'pf-link', data: { click: 'wiPortfolioSkip' }, text: 'Run it without them' }));
      return;
    }
    const usable = rows.map((r, i) => ({ r, info: infos[i] })).filter(x => x.info.status === 'ok' && x.info.months);
    const total = usable.reduce((a, x) => a + x.r.value, 0);
    const parts = usable.map(x => ({ t: x.r.h.t, weight: x.r.value / total, months: x.info.months, price: x.info.price.value, date: x.info.price.date }));
    const run = PortfolioMath.whatIfPortfolio(parts, input.amount, input.from);
    if (run.error) { wiSay(`None of your holdings were trading in ${pfMonth(input.from)}.`, 'bad'); return; }
    let spy = null;
    if (spyInfo.status === 'ok' && spyInfo.months) {
      const same = PortfolioMath.whatIf(wiHistory(spyInfo), input.amount, run.from, 0);
      if (!same.error && same.from === run.from) spy = same;
    }
    WI.result = { kind: 'portfolio', input, run, spy, skipped: skip ? missing : [], hadMonthly: input.monthly > 0 };
    wiSay('');
    wiRender();
    wiClearLink();
  } finally {
    WI.busy = false;
  }
}

// ---- The chart ----------------------------------------------------------------------------------

function wiChart(lines) {
  const W = 640, H = 260, left = 58, right = 8, top = 12, bottom = 26;
  const all = lines.flatMap(l => l.points.map(p => p[1]));
  const max = Math.max(...all);
  const min = Math.min(...all, 0);
  const span = max - min || 1;
  const count = Math.max(...lines.map(l => l.points.length));
  const x = i => left + (count <= 1 ? 0 : (i / (count - 1)) * (W - left - right));
  const y = v => top + (1 - (v - min) / span) * (H - top - bottom);
  const svg = pfSvg('svg', { class: 'wi-chart', viewBox: `0 0 ${W} ${H}`, role: 'img', 'aria-label': 'Value over time. The numbers are in the table below.' });
  [0, 0.5, 1].forEach(f => {
    const value = min + span * f;
    svg.append(pfSvg('line', { class: 'wi-grid', x1: left, x2: W - right, y1: y(value).toFixed(1), y2: y(value).toFixed(1) }));
    // Labels sit in their own gutter to the left, so a line never runs through one.
    const label = pfSvg('text', { class: 'wi-axis', x: left - 6, y: (y(value) + 4).toFixed(1), 'text-anchor': 'end' });
    label.textContent = MONEY_WHOLE.format(value);
    svg.append(label);
  });
  const first = lines[0].points;
  [[0, 'start'], [first.length - 1, 'end']].forEach(([i, anchor]) => {
    const label = pfSvg('text', { class: 'wi-axis', x: x(i).toFixed(1), y: H - 6, 'text-anchor': anchor });
    label.textContent = String(first[i][0]).slice(0, 4);
    svg.append(label);
  });
  lines.slice().reverse().forEach(l => {
    const path = l.points.map((p, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(p[1]).toFixed(1)}`).join('');
    svg.append(pfSvg('path', { class: `wi-line ${l.cls}`, d: path }));
  });
  return svg;
}

function wiTable(lines) {
  const main = lines[0].points;
  const other = lines[1] ? new Map(lines[1].points) : null;
  const head = pfEl('tr', {}, [pfEl('th', { scope: 'col', text: 'End of' }), pfEl('th', { scope: 'col', text: lines[0].label })]
    .concat(other ? [pfEl('th', { scope: 'col', text: lines[1].label })] : []));
  const body = main.map(([when, value], i) => pfEl('tr', {}, [
    pfEl('td', { text: i === main.length - 1 ? `Now (${pfDay(when)})` : pfMonth(when) }),
    pfEl('td', { text: pfMoney(value) }),
  ].concat(other ? [pfEl('td', { text: other.has(when) ? pfMoney(other.get(when)) : '' })] : [])));
  return pfEl('table', { class: 'wi-table' }, [pfEl('thead', {}, [head]), pfEl('tbody', {}, body)]);
}

function wiRender() {
  const box = document.getElementById('wiResult');
  box.replaceChildren();
  const res = WI.result;
  box.hidden = !res;
  if (!res) return;
  const { run, spy, input } = res;
  const what = res.kind === 'one' ? res.ticker : 'your portfolio as it is today';
  const monthly = res.kind === 'one' && input.monthly ? ` and ${pfMoney(input.monthly)} at the end of every month since` : '';
  const tone = run.gain > 0 ? 'pos' : run.gain < 0 ? 'neg' : '';
  box.append(pfEl('p', { class: 'wi-answer' }, [
    `${pfMoney(input.amount)} put into ${what} at the end of ${pfMonth(run.from)}${monthly} would be worth `,
    pfEl('strong', { class: 'wi-value', text: pfMoney(run.value) }), ' now.',
  ]));
  box.append(pfEl('p', { class: 'pf-lead' }, [
    run.contributions ? `You’d have put in ${pfMoney(run.putIn)} over ${wiYears(run.years)}. That’s ` : `That’s `,
    pfEl('span', { class: tone, text: `${pfSigned(run.pct)}${wiRate(run)}` }),
    run.contributions ? '.' : ` over ${wiYears(run.years)}.`,
  ]));
  if (spy) {
    box.append(pfEl('p', { class: 'pf-lead', text: `The same money in the S&P 500 (the SPY fund) would be worth ${pfMoney(spy.value)}: ${pfSigned(spy.pct)}${wiRate(spy)}.` }));
  } else if (res.kind === 'portfolio' || res.ticker !== PF_SPY) {
    box.append(pfEl('p', { class: 'pf-note', text: 'The S&P 500 comparison isn’t available for this start month.' }));
  }
  const notes = [];
  if (run.asked !== run.from) notes.push(`There’s no price for ${pfMonth(run.asked)}, so this starts from ${pfMonth(run.from)}, the nearest earlier month that has one.`);
  if (res.kind === 'portfolio') {
    notes.push('Uses today’s mix of holdings. You may have held something different then.');
    if (run.leftOut.length) notes.push(`${pfList(run.leftOut)} ${run.leftOut.length === 1 ? 'wasn’t' : 'weren’t'} trading yet, so ${run.leftOut.length === 1 ? 'it is' : 'they are'} left out and the rest is scaled up to 100%.`);
    if (res.skipped.length) notes.push(`Left out because prices couldn’t be loaded: ${pfList(res.skipped)}.`);
    if (res.hadMonthly) notes.push('The monthly amount isn’t used for a whole portfolio.');
  }
  if (res.demo || PF.demo) notes.push('These are demo prices, not real ones.');
  if (notes.length) box.append(pfEl('p', { class: 'pf-note', text: notes.join(' ') }));

  const lines = [{ label: res.kind === 'one' ? res.ticker : 'Your portfolio', cls: 'wi-line-main', points: run.series }];
  if (spy) lines.push({ label: 'S&P 500', cls: 'wi-line-spy', points: spy.series });
  if (run.series.length > 2) {
    box.append(wiChart(lines));
    box.append(pfEl('p', { class: 'wi-legend' }, lines.map(l => pfEl('span', { class: `wi-key ${l.cls}`, text: l.label }))));
  }
  box.append(pfEl('button', { type: 'button', class: 'pf-link', data: { click: 'wiToggleNumbers' }, 'aria-expanded': String(WI.showNumbers),
    text: WI.showNumbers ? 'Hide the numbers' : 'Show the numbers' }));
  if (WI.showNumbers) box.append(pfEl('div', { class: 'wi-table-wrap' }, [wiTable(lines)]));
  box.append(pfEl('p', { class: 'pf-note', text: 'Uses prices adjusted for splits and dividends, so it assumes dividends were reinvested. Ignores taxes and fees. Prices are month-end, so dates are to the month. What happened before says nothing about what happens next.' }));
  if (res.kind === 'one') {
    box.append(pfEl('button', { type: 'button', class: 'pf-link', data: { click: 'wiCopyLink' }, text: 'Copy a link to this result' }));
  }
}

// ---- The link -----------------------------------------------------------------------------------

function wiLink() {
  const res = WI.result;
  if (!res || res.kind !== 'one') return '';
  const params = new URLSearchParams({ t: res.ticker, a: String(res.input.amount), from: res.run.from });
  if (res.input.monthly) params.set('m', String(res.input.monthly));
  return `${window.location.pathname}?${params}#what-if`;
}

function wiWriteLink() {
  try { history.replaceState(null, '', wiLink()); } catch (e) { /* the address just doesn't update */ }
}

function wiClearLink() {
  try { history.replaceState(null, '', window.location.pathname + '#what-if'); } catch (e) { /* nothing to clear */ }
}

function wiCopyLink(button) {
  const url = new URL(wiLink(), window.location.href).href;
  const done = text => { button.textContent = text; setTimeout(() => { button.textContent = 'Copy a link to this result'; }, 2400); };
  if (navigator.clipboard && window.isSecureContext) navigator.clipboard.writeText(url).then(() => done('Link copied'), () => window.prompt('Copy this link:', url));
  else window.prompt('Copy this link:', url);
}

// A shared link fills the form and runs it. Every field is checked; anything odd is ignored.
function wiFromLink() {
  const params = new URLSearchParams(window.location.search);
  const ticker = PortfolioInput.normalizeTicker(params.get('t'));
  const amount = PortfolioInput.parseAmount(params.get('a'));
  const from = String(params.get('from') || '');
  if (!ticker || !(amount > 0) || amount > WI_MAX || !PortfolioInput.MONTH.test(from)) return false;
  document.getElementById('wiTicker').value = ticker;
  document.getElementById('wiAmount').value = String(amount);
  document.getElementById('wiFrom').value = from;
  const monthly = PortfolioInput.parseAmount(params.get('m'));
  if (monthly > 0 && monthly <= WI_MAX) document.getElementById('wiMonthly').value = String(monthly);
  return true;
}

function wiSyncPortfolioButton() {
  const button = document.getElementById('wiPortfolio');
  if (button) button.hidden = !pfRows().rows.some(r => r.priced);
}

PF.listeners.push(wiSyncPortfolioButton);
Object.assign(PAGE_ACTIONS.click, {
  wiRun: () => wiRun(),
  wiRunPortfolio: () => wiRunPortfolio(false),
  wiPortfolioSkip: () => wiRunPortfolio(true),
  wiPick: el => wiPick(el.dataset.wiYears),
  wiUseFirst: el => { wiClearPicks(); document.getElementById('wiFrom').value = el.dataset.month; wiRun(); },
  wiToggleNumbers: () => { WI.showNumbers = !WI.showNumbers; wiRender(); },
  wiCopyLink: el => wiCopyLink(el),
});
Object.assign(PAGE_ACTIONS.input, {
  wiClearPicks: () => wiClearPicks(),
});

document.addEventListener('keydown', event => {
  if (event.key === 'Enter' && event.target.closest && event.target.closest('#wiForm')) { event.preventDefault(); wiRun(); }
});

document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('wiFrom').max = PortfolioMath.addMonths(wiToday().slice(0, 7), -1);
  if (wiFromLink()) {
    wiRun().then(() => document.getElementById('what-if').scrollIntoView());
  } else {
    wiPick(5);
  }
});
