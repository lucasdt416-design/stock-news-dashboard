// The top of the page: what the portfolio is worth, a chart of what today's shares were worth at
// the end of each month, and how many dollars each holding added or took away over the chosen
// range. Everything is real month-end prices times the shares held now; nothing is estimated.
const SUM = {
  range: 12,          // months back; 0 is all the history there is
  picked: false,      // true once the visitor chooses a range themselves
  showNumbers: false,
  showAllMoves: false,
  asked: new Set(),   // tickers whose monthly prices have been asked for
  noHistory: new Set(),
  hover: null,
};
const SUM_RANGES = [[12, '1Y', 'in the past year', 'a year ago'], [36, '3Y', 'in the past 3 years', '3 years ago'],
  [60, '5Y', 'in the past 5 years', '5 years ago'], [0, 'All', '', '']];
const MOVES_FIRST = 8;

function pfSignedMoney(value) {
  return `${value > 0 ? '+' : value < 0 ? '−' : ''}${pfMoney(Math.abs(value))}`;
}

function pfTone(value) {
  return value > 0 ? 'pos' : value < 0 ? 'neg' : '';
}

// Priced holdings that have their monthly prices, in the shape PortfolioMath.valueSeries works on.
function pfSeriesItems() {
  return pfRows().rows
    .filter(r => r.priced && Array.isArray(r.info.months) && r.info.months.length)
    .map(r => ({ t: r.h.t, sh: r.h.sh, months: r.info.months, price: r.info.price.value, date: r.info.price.date }));
}

// Monthly prices are one file (or one request for one ticker) per holding, fetched once.
function pfAskForHistory() {
  pfRows().rows.forEach(row => {
    const ticker = row.h.t;
    if (!row.priced || row.info.months || SUM.asked.has(ticker)) return;
    SUM.asked.add(ticker);
    const before = row.info;
    pfInfo(ticker, true).then(info => {
      if (info.status !== 'ok' || !info.months || !info.months.length) {
        // No history is not a reason to lose the price that was already there.
        PF.info.set(ticker, before);
        SUM.noHistory.add(ticker);
      }
      pfRender();
    });
  });
}

// The range in use: the one chosen, or the longest shorter one the prices can fill.
function pfRangeState() {
  const series = PortfolioMath.valueSeries(pfSeriesItems());
  const available = SUM_RANGES.filter(([months]) => PortfolioMath.lastMonths(series, months));
  let range = available.find(([months]) => months === SUM.range);
  if (!range) range = available.find(([months]) => months === 12) || available[available.length - 1] || null;
  const points = range ? PortfolioMath.lastMonths(series, range[0]) : null;
  return { series, available, range, points };
}

// "in the past year", or "since the end of March 2021" for all of it.
function pfRangeWords(state) {
  if (!state.range) return '';
  return state.range[2] || `since the end of ${pfMonth(state.points[0][0])}`;
}

function pfPointLabel(point, last) {
  return last ? `Now (${pfDay(point[0])})` : `End of ${pfMonth(point[0])}`;
}

function pfValueChart(points) {
  const host = document.getElementById('pfValueChart');
  const W = Math.max(280, Math.round(host.clientWidth || 640));
  const H = W < 480 ? 200 : 260;
  const left = 8, right = 62, top = 12, bottom = 24;
  const values = points.map(p => p[1]);
  const hi = Math.max(...values), lo = Math.min(...values);
  const pad = (hi - lo || hi || 1) * 0.08;
  const max = hi + pad, min = Math.max(0, lo - pad);
  const x = i => left + (points.length <= 1 ? 0 : (i / (points.length - 1)) * (W - left - right));
  const y = v => top + (1 - (v - min) / (max - min)) * (H - top - bottom);
  const svg = pfSvg('svg', { class: 'pf-chart-svg', viewBox: `0 0 ${W} ${H}`, width: W, height: H, role: 'img',
    'aria-label': 'What the shares you hold now were worth at the end of each month. The numbers are in the table below.' });
  [0, 0.5, 1].forEach(f => {
    const value = min + (max - min) * f;
    svg.append(pfSvg('line', { class: 'wi-grid', x1: left, x2: W - right, y1: y(value).toFixed(1), y2: y(value).toFixed(1) }));
    const label = pfSvg('text', { class: 'wi-axis', x: W - right + 8, y: (y(value) + 4).toFixed(1) });
    label.textContent = MONEY_WHOLE.format(value);
    svg.append(label);
  });
  const stamp = i => (i === points.length - 1 ? 'Now' : new Date(Number(points[i][0].slice(0, 4)), Number(points[i][0].slice(5, 7)) - 1, 1)
    .toLocaleDateString('en-US', { month: 'short', year: 'numeric' }));
  [[0, 'start'], [points.length - 1, 'end']].forEach(([i, anchor]) => {
    const label = pfSvg('text', { class: 'wi-axis', x: x(i).toFixed(1), y: H - 6, 'text-anchor': anchor });
    label.textContent = stamp(i);
    svg.append(label);
  });
  svg.append(pfSvg('path', { class: 'pf-line', d: points.map((p, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(p[1]).toFixed(1)}`).join('') }));
  const cross = pfSvg('line', { class: 'pf-cross', y1: top, y2: H - bottom, x1: 0, x2: 0, visibility: 'hidden' });
  const dot = pfSvg('circle', { class: 'pf-dot', r: 4.5, cx: x(points.length - 1).toFixed(1), cy: y(values[values.length - 1]).toFixed(1) });
  svg.append(cross, dot);

  // Move along the line and the big number above follows.
  const show = index => {
    SUM.hover = index;
    const at = index === null ? points.length - 1 : index;
    dot.setAttribute('cx', x(at).toFixed(1));
    dot.setAttribute('cy', y(values[at]).toFixed(1));
    cross.setAttribute('visibility', index === null ? 'hidden' : 'visible');
    cross.setAttribute('x1', x(at).toFixed(1));
    cross.setAttribute('x2', x(at).toFixed(1));
    pfRenderHeadline();
  };
  const nearest = event => {
    const box = svg.getBoundingClientRect();
    const px = (event.clientX - box.left) * (W / (box.width || W));
    const index = Math.round(((px - left) / (W - left - right)) * (points.length - 1));
    return Math.max(0, Math.min(points.length - 1, index));
  };
  svg.addEventListener('pointermove', event => show(nearest(event)));
  svg.addEventListener('pointerdown', event => show(nearest(event)));
  svg.addEventListener('pointerleave', () => show(null));
  return svg;
}

// The big number and the line under it. While a point on the chart is under the pointer they
// describe that month; otherwise they describe today.
function pfRenderHeadline() {
  const { total } = pfRows();
  const state = SUM.state;
  const label = document.getElementById('pfHeroLabel');
  const value = document.getElementById('pfHeroValue');
  const change = document.getElementById('pfHeroChange');
  const points = state && state.points;
  if (points && SUM.hover !== null && SUM.hover < points.length - 1) {
    const point = points[SUM.hover];
    const diff = points[points.length - 1][1] - point[1];
    label.textContent = `What your shares were worth at the end of ${pfMonth(point[0])}`;
    value.textContent = pfMoney(point[1]);
    change.replaceChildren(pfEl('span', { class: pfTone(diff), text: pfSignedMoney(diff) }), ' between then and now');
    return;
  }
  label.textContent = 'Your portfolio is worth';
  value.textContent = pfMoney(total);
  if (!points) {
    change.textContent = pfRows().rows.some(r => r.priced && !r.info.months && !SUM.noHistory.has(r.h.t)) ? 'Getting price history…' : '';
    return;
  }
  const first = points[0][1], last = points[points.length - 1][1];
  const diff = last - first;
  change.replaceChildren(
    pfEl('span', { class: pfTone(diff), text: `${pfSignedMoney(diff)} (${pfSigned(diff / first)})` }),
    ` ${pfRangeWords(state)}`);
}

function pfTile(label, value, detail, tone) {
  return pfEl('div', { class: 'pf-tile' }, [
    pfEl('dt', { class: 'pf-tile-label', text: label }),
    pfEl('dd', { class: 'pf-tile-value' + (tone ? ' ' + tone : ''), text: value }),
    detail ? pfEl('dd', { class: 'pf-tile-detail', text: detail }) : null,
  ]);
}

function pfRenderTiles(state, moves) {
  const tiles = document.getElementById('pfTiles');
  tiles.replaceChildren();
  const g = PortfolioMath.gains(pfMathRows(), null);
  if (g) {
    const some = g.without ? ` for the ${g.count === 1 ? 'one holding' : `${g.count} holdings`} with a cost` : '';
    tiles.append(pfTile('You paid', pfMoney(g.paid), some.trim()));
    tiles.append(pfTile(g.gain < 0 ? 'Loss since you bought' : 'Gain since you bought', pfSignedMoney(g.gain), pfSigned(g.pct), pfTone(g.gain)));
  }
  if (moves.length >= 2) {
    const words = pfRangeWords(state);
    const best = moves[0], worst = moves[moves.length - 1];
    tiles.append(pfTile(best.change >= 0 ? 'Added the most' : 'Lost the least', `${best.t} ${pfSignedMoney(best.change)}`, words, pfTone(best.change)));
    tiles.append(pfTile(worst.change < 0 ? 'Lost the most' : 'Added the least', `${worst.t} ${pfSignedMoney(worst.change)}`, words, pfTone(worst.change)));
  }
  tiles.hidden = !tiles.children.length;
}

// One bar per holding, growing right from the zero line for a gain and left for a loss.
function pfMoveBar(change, min, max) {
  const span = max - min || 1;
  const zero = ((0 - min) / span) * 100;
  const end = ((change - min) / span) * 100;
  return pfSvg('svg', { class: 'pf-movebar', viewBox: '0 0 100 10', preserveAspectRatio: 'none', 'aria-hidden': 'true' }, [
    pfSvg('rect', { class: change < 0 ? 'pf-bar-neg' : 'pf-bar-pos', x: Math.min(zero, end).toFixed(2), y: 1, width: Math.max(0.6, Math.abs(end - zero)).toFixed(2), height: 8, rx: 1 }),
    pfSvg('line', { class: 'pf-zero', x1: zero.toFixed(2), x2: zero.toFixed(2), y1: 0, y2: 10 }),
  ]);
}

function pfRenderMoves(state, moves) {
  const section = document.getElementById('pfMovesSection');
  section.hidden = moves.length < 2;
  if (moves.length < 2) return;
  const list = document.getElementById('pfMoves');
  const more = document.getElementById('pfMovesAll');
  list.replaceChildren();
  const whole = moves.reduce((a, m) => a + m.change, 0);
  document.getElementById('pfMovesLead').replaceChildren(
    'Your shares are worth ', pfEl('span', { class: pfTone(whole), text: pfSignedMoney(whole).replace(/^[+−]/, '') + (whole < 0 ? ' less' : ' more') }),
    ` than ${state.range[3] || `at the end of ${pfMonth(state.points[0][0])}`}. Here’s where that came from.`);
  const min = Math.min(0, ...moves.map(m => m.change));
  const max = Math.max(0, ...moves.map(m => m.change));
  // The biggest moves either way come first, so the short list shows what mattered most.
  const ordered = moves.slice().sort((a, b) => Math.abs(b.change) - Math.abs(a.change) || a.t.localeCompare(b.t));
  const shown = (SUM.showAllMoves ? ordered : ordered.slice(0, MOVES_FIRST)).sort((a, b) => b.change - a.change || a.t.localeCompare(b.t));
  shown.forEach(m => {
    list.append(pfEl('li', { class: 'pf-move' }, [
      pfEl('span', { class: 'pf-ticker', text: m.t }),
      pfMoveBar(m.change, min, max),
      pfEl('span', { class: 'pf-move-amount ' + pfTone(m.change), text: pfSignedMoney(m.change) }),
      pfEl('span', { class: 'pf-move-detail', text: `${pfMoney(m.then)} then, ${pfMoney(m.now)} now` }),
    ]));
  });
  more.hidden = ordered.length <= MOVES_FIRST;
  more.textContent = SUM.showAllMoves ? 'Show fewer' : `Show all ${ordered.length}`;
}

function pfRenderSummary() {
  const { rows } = pfRows();
  const box = document.getElementById('pfSummary');
  const any = rows.some(r => r.value !== null);
  box.hidden = !any;
  if (!any) { document.getElementById('pfMovesSection').hidden = true; return; }
  pfAskForHistory();

  const state = pfRangeState();
  SUM.state = state;
  SUM.hover = null;
  const items = pfSeriesItems();
  const moves = state.points ? PortfolioMath.changeSince(items, state.points[0][0]) : [];
  SUM.moves = new Map(moves.map(m => [m.t, m]));

  const ranges = document.getElementById('pfRanges');
  ranges.hidden = !state.range;
  ranges.querySelectorAll('button').forEach(button => {
    const months = Number(button.dataset.months);
    const ok = state.available.some(([m]) => m === months);
    button.disabled = !ok;
    button.setAttribute('aria-pressed', String(Boolean(state.range) && state.range[0] === months));
  });

  const host = document.getElementById('pfValueChart');
  host.replaceChildren();
  const numbers = document.getElementById('pfValueNumbers');
  const table = document.getElementById('pfValueTable');
  table.replaceChildren();
  numbers.hidden = !state.points;
  numbers.textContent = SUM.showNumbers ? 'Hide the numbers' : 'Show the numbers';
  numbers.setAttribute('aria-expanded', String(SUM.showNumbers));
  table.hidden = !(state.points && SUM.showNumbers);
  if (state.points) {
    host.append(pfValueChart(state.points));
    if (SUM.showNumbers) table.append(wiTable([{ label: 'Your shares were worth', points: state.points }]));
  }
  pfRenderHeadline();
  pfRenderTiles(state, moves);
  pfRenderMoves(state, moves);

  const notes = [];
  if (state.points) {
    notes.push('The line is the shares you hold now, priced at the end of each month, with dividends counted as reinvested. You may have held something different then.');
    if (!state.range[0] && state.series.limitedBy.length) {
      notes.push(`It starts in ${pfMonth(state.series.from)}, when ${pfList(state.series.limitedBy)} began trading.`);
    }
    const priced = rows.filter(r => r.priced).map(r => r.h.t);
    const charted = new Set(items.map(i => i.t));
    const left = priced.filter(t => !charted.has(t) && SUM.noHistory.has(t));
    if (left.length) notes.push(`Not in the line, because their price history couldn’t be loaded: ${pfList(left)}.`);
    const short = SUM_RANGES.filter(([months]) => months && !state.available.some(([m]) => m === months)).map(r => r[1]);
    if (short.length && state.series.limitedBy.length) notes.push(`${pfList(short)} ${short.length === 1 ? 'isn’t' : 'aren’t'} offered because ${pfList(state.series.limitedBy)} ${state.series.limitedBy.length === 1 ? 'hasn’t' : 'haven’t'} traded that long.`);
    if (PF.demo) notes.push('These are demo prices, not real ones.');
  } else if (rows.some(r => r.priced) && rows.filter(r => r.priced).every(r => SUM.noHistory.has(r.h.t))) {
    notes.push('Price history couldn’t be loaded just now, so there’s no chart.');
  }
  document.getElementById('pfValueNote').textContent = notes.join(' ');
}

// A small line of the past year's month-end prices, for a holding's row.
function pfSparkline(info) {
  const months = Array.isArray(info.months) ? info.months.slice(-12) : [];
  if (months.length < 3) return null;
  const values = months.map(m => m[1]).concat([info.price.value]);
  const min = Math.min(...values), max = Math.max(...values);
  const W = 96, H = 30;
  const x = i => 2 + (i / (values.length - 1)) * (W - 4);
  const y = v => 3 + (1 - (max === min ? 0.5 : (v - min) / (max - min))) * (H - 6);
  const up = values[values.length - 1] >= values[0];
  return pfSvg('svg', { class: 'pf-spark ' + (up ? 'pf-spark-up' : 'pf-spark-down'), viewBox: `0 0 ${W} ${H}`, width: W, height: H, role: 'img',
    'aria-label': `Its price over the past year: ${up ? 'up' : 'down'}` },
  [pfSvg('path', { d: values.map((v, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join('') })]);
}

// What a holding's shares gained or lost over the chosen range, for its row.
function pfRowMove(ticker) {
  const move = SUM.moves && SUM.moves.get(ticker);
  if (!move || !SUM.state || !SUM.state.range) return null;
  // Short words, because a row is narrow: "past year", or "since Jan 2019" for all of it.
  const from = SUM.state.points[0][0];
  const words = SUM.state.range[0] ? SUM.state.range[2].replace(/^in the /, '')
    : `since ${new Date(Number(from.slice(0, 4)), Number(from.slice(5, 7)) - 1, 1).toLocaleDateString('en-US', { month: 'short', year: 'numeric' })}`;
  return pfEl('div', { class: 'pf-gain ' + pfTone(move.change), text: `${pfSignedMoney(move.change)} ${words}` });
}

// The summary works out the range first, because the holdings' rows show the same range.
PF.before.push(pfRenderSummary);
Object.assign(PAGE_ACTIONS.click, {
  pfSetRange: el => { SUM.range = Number(el.dataset.months); SUM.picked = true; pfRender(); },
  pfValueNumbers: () => { SUM.showNumbers = !SUM.showNumbers; pfRenderSummary(); },
  pfMovesAll: () => { SUM.showAllMoves = !SUM.showAllMoves; pfRenderSummary(); },
});

let pfResizeTimer = null;
let pfLastWidth = 0;
window.addEventListener('resize', () => {
  const host = document.getElementById('pfValueChart');
  if (!host || host.clientWidth === pfLastWidth) return;
  pfLastWidth = host.clientWidth;
  clearTimeout(pfResizeTimer);
  pfResizeTimer = setTimeout(pfRenderSummary, 150);
});
