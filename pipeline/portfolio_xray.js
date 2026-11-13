// The X-ray: what the holdings add up to. Everything here is worked out in the browser from the
// holdings, the site's price files and what the watchlist says about each company. It states
// what is there ("62% of your money is in Technology") and never what to do about it.
const PF_SPY = 'SPY';
const XRAY = { showAllOverlap: false, showAllGains: false };

// Plain words for every theme in the watchlist (`themes:` in data/watchlist.yaml). Each one finishes
// the sentence "X% of your portfolio is sensitive to ...". tests/test_portfolio_page.py keeps the
// two lists in step.
const THEME_WORDS = {
  data_center_spending: 'spending on AI and data centers',
  china_export_controls: 'US export controls on China',
  pc_demand: 'demand for PCs',
  smartphone_demand: 'demand for smartphones',
  memory_chip_prices: 'memory chip prices',
  bank_interest_income: 'what banks earn on loans as interest rates move',
  dealmaking: 'how many mergers and share sales are being done',
  card_spending: 'how much people spend on cards',
  market_levels: 'how high stock and bond markets are, which sets the fees they earn',
  oil_prices: 'crude oil prices',
  drug_pricing_rules: 'US rules on drug prices',
  medical_procedures: 'how many operations and procedures hospitals do',
  health_insurance_rules: 'Medicare and health insurance rules',
  lab_research_spending: 'spending on drug research and lab work',
  defense_budgets: 'government defense budgets',
  air_travel: 'how much people fly',
  housing_market: 'the housing market and mortgage rates',
  online_ads: 'spending on online ads',
  cloud_computing: 'business spending on cloud computing',
  business_tech_spending: 'how much businesses spend on software and IT',
  streaming: 'the streaming business',
  electric_cars: 'the electric car market',
  electricity_demand: 'growing demand for electricity',
  tobacco_rules: 'rules on tobacco and nicotine',
  strong_dollar: 'a strong dollar, which shrinks what overseas sales are worth',
  shipping_volumes: 'how much freight is being shipped',
  heavy_machinery_demand: 'demand for heavy machinery',
};
const ECONOMY_WORDS = {
  inflation: 'inflation',
  interest_rates: 'interest rates',
  unemployment: 'unemployment',
  treasury_10y: 'the 10-year Treasury yield',
  crude_oil: 'the price of oil',
};

function pfSvg(tag, attrs, children) {
  const node = document.createElementNS('http://www.w3.org/2000/svg', tag);
  Object.keys(attrs || {}).forEach(key => node.setAttribute(key, String(attrs[key])));
  (children || []).forEach(child => node.append(child));
  return node;
}

function pfBar(fraction) {
  const width = Math.max(0, Math.min(100, fraction * 100));
  return pfSvg('svg', { class: 'pf-bar', viewBox: '0 0 100 4', preserveAspectRatio: 'none', 'aria-hidden': 'true' }, [
    pfSvg('rect', { class: 'pf-bar-track', x: 0, y: 0, width: 100, height: 4 }),
    pfSvg('rect', { class: 'pf-bar-fill', x: 0, y: 0, width: width.toFixed(2), height: 4 }),
  ]);
}

// "NVIDIA Corporation" as "NVIDIA", for use mid-sentence. A name we don't follow is shown as written.
function pfShortName(entity) {
  const full = COMPANY_NAMES[entity];
  if (!full) return String(entity);
  return full.replace(/,? (Inc\.?|Incorporated|Corporation|Corp\.?|Company|Co\.|Holdings|Group|plc|N\.V\.|Ltd\.?|& Co\.?)$/i, '').replace(/,? (Inc\.?|Corporation)$/i, '') || full;
}

function pfList(names) {
  if (names.length <= 1) return names.join('');
  return names.slice(0, -1).join(', ') + ' and ' + names[names.length - 1];
}

// Priced holdings only, in the shape PortfolioMath works on.
function pfMathRows() {
  return pfRows().rows.filter(r => r.priced).map(r => ({
    t: r.h.t, company: r.company, value: r.value, fund: r.fund, sector: r.fund ? 'Funds' : r.sector, paid: r.h.paid, bought: r.h.bought,
  }));
}

function pfRenderSectors(rows) {
  const sectors = PortfolioMath.sectors(rows);
  const list = document.getElementById('pfSectors');
  list.replaceChildren();
  const real = sectors.filter(s => s.name !== 'Funds' && s.name !== 'Sector unknown');
  const all = PortfolioMath.total(rows);
  document.getElementById('pfSectorLead').textContent = real.length
    ? `${pfMoney(real[0].weight * all)} of your ${pfMoney(all)} is in ${real[0].name} (${pfPercent(real[0].weight, 0)})${real.length > 1 ? `, across ${real.length} sectors in all` : ''}.`
    : 'None of your money is in a stock with a known sector.';
  sectors.forEach(sector => {
    const label = sector.name === 'Funds' ? 'Funds (contents not broken out)' : sector.name;
    list.append(pfEl('li', { class: 'pf-sector' }, [
      pfEl('span', { class: 'pf-sector-name', text: label }),
      pfBar(sector.weight),
      pfEl('span', { class: 'pf-sector-money', text: pfMoney(sector.weight * all) }),
      pfEl('span', { class: 'pf-sector-pct', text: pfPercent(sector.weight) }),
      pfEl('span', { class: 'pf-sector-tickers', text: sector.tickers.join(', ') }),
    ]));
  });
}

function pfRenderConcentration(rows) {
  const c = PortfolioMath.concentration(rows);
  const list = document.getElementById('pfConcentration');
  const lead = document.getElementById('pfConcentrationLead');
  const note = document.getElementById('pfConcentrationNote');
  list.replaceChildren();
  const fundsNote = c.fundWeight > 0
    ? `Funds are ${pfPercent(c.fundWeight, 0)} of your portfolio and aren’t counted here: a fund is many stocks, so counting it as one would make you look more concentrated than you are.`
    : '';
  if (!c.stocks) {
    lead.textContent = 'Everything here is a fund, so there’s nothing to measure stock by stock.';
    note.textContent = '';
    return;
  }
  const stat = (label, value, detail) => pfEl('div', { class: 'pf-stat' }, [
    pfEl('dt', { class: 'pf-stat-label', text: label }),
    pfEl('dd', { class: 'pf-stat-value', text: value }),
    pfEl('dd', { class: 'pf-stat-detail', text: detail }),
  ]);
  const base = c.fundWeight > 0 ? 'of the money you have in individual stocks' : 'of your portfolio';
  const inStocks = PortfolioMath.total(rows.filter(r => !r.fund));
  const part = (names, weight) => `${names}: ${pfPercent(weight, 0)} ${base}`;
  list.append(stat('Largest holding', pfMoney(c.largest.weight * inStocks), part(c.largest.name, c.largest.weight)));
  if (c.stocks > 3) list.append(stat('Top three together', pfMoney(c.topThree.weight * inStocks), part(c.topThree.names.join(', '), c.topThree.weight)));
  list.append(stat('Largest sector', pfMoney(c.largestSector.weight * inStocks), part(c.largestSector.name, c.largestSector.weight)));
  const effective = c.effective < 9.95 ? c.effective.toFixed(1).replace(/\.0$/, '') : String(Math.round(c.effective));
  if (c.stocks === 1) {
    lead.textContent = 'You hold one stock, so all of it rides on that one.';
  } else if (c.effective / c.stocks > 0.95) {
    lead.textContent = `Your ${c.stocks} stocks are close to equal in size.`;
  } else {
    lead.textContent = `Your ${c.stocks} stocks behave like about ${effective} equal-sized ones.`;
    list.append(stat('Effective number of holdings', effective,
      'A few big holdings count for more than many small ones. This is how many equal-sized holdings would be as concentrated as yours.'));
  }
  note.textContent = fundsNote;
}

function pfOverlapWords(line) {
  const pct = pfPercent(line.weight, 0);
  const n = line.tickers.length;
  const names = pfList(line.tickers);
  if (line.kind === 'theme') {
    const words = THEME_WORDS[line.subject] || String(line.subject).replace(/_/g, ' ');
    return `${pct} of your portfolio is sensitive to ${words}: ${names}.`;
  }
  if (line.kind === 'economy') {
    const words = ECONOMY_WORDS[line.subject] || String(line.subject).replace(/_/g, ' ');
    return `${n} of your holdings, ${pct} of your portfolio, are marked as sensitive to ${words}: ${names}.`;
  }
  if (line.kind === 'customers') {
    const count = line.others.length === 1 ? 'one of its key customers' : `${line.others.length} of its key customers`;
    return `You hold ${line.subjectLabel} and ${count} (${pfList(line.others)}). Together they’re ${pct} of your portfolio.`;
  }
  if (line.kind === 'sameCustomer') return `${n} of your holdings count ${pfShortName(line.subject)} as a key customer: ${names} (${pct} of your portfolio).`;
  if (line.kind === 'sameSupplier') return `${n} of your holdings rely on ${pfShortName(line.subject)} as a key supplier: ${names} (${pct} of your portfolio).`;
  return line.others.length === 1
    ? `${line.subjectLabel} and its competitor ${line.others[0]} are both in your portfolio: ${pct}.`
    : `${line.subjectLabel} and ${line.others.length} of its competitors (${pfList(line.others)}) are all in your portfolio: ${pct}.`;
}

function pfRenderOverlap(rows) {
  const result = PortfolioMath.overlap(rows, PF_DATA.companies);
  const list = document.getElementById('pfOverlap');
  const more = document.getElementById('pfOverlapAll');
  list.replaceChildren();
  const shown = XRAY.showAllOverlap ? result.lines : result.lines.slice(0, FIRST_ROWS);
  const all = PortfolioMath.total(rows);
  shown.forEach(line => list.append(pfEl('li', { class: 'pf-overlap-line' }, [
    pfEl('strong', { class: 'pf-line-amount', text: pfMoney(line.weight * all) }),
    pfEl('span', { class: 'pf-line-words', text: pfOverlapWords(line) }),
  ])));
  document.getElementById('pfOverlapLead').textContent = result.lines.length
    ? 'Where several of your holdings depend on the same thing. These overlap, so they don’t add up.'
    : result.covered >= 2
      ? 'Nothing stands out. None of your holdings share a theme, a key customer or supplier, or compete with each other, as far as StockPulse’s notes go.'
      : 'This needs at least two companies StockPulse follows.';
  more.hidden = result.lines.length <= FIRST_ROWS;
  more.textContent = XRAY.showAllOverlap ? 'Show fewer' : `Show all ${result.lines.length}`;
  const parts = [`StockPulse only has these notes for the ${KNOWN_SYMBOLS.size} companies it follows, and not every company has all of them.`];
  if (result.outside.length) {
    parts.push(`${plural(result.outside.length, 'of your holdings isn’t', 'of your holdings aren’t')} among them (${pfPercent(result.outsideWeight, 0)} of your portfolio): ${result.outside.join(', ')}.`);
  }
  if (rows.some(r => r.fund)) parts.push('Funds aren’t looked into.');
  document.getElementById('pfOverlapNote').textContent = parts.join(' ');
}

function pfRenderFunds(rows) {
  const funds = rows.filter(r => r.fund);
  const section = document.getElementById('pfFundsSection');
  section.hidden = funds.length === 0;
  if (!funds.length) return;
  const all = PortfolioMath.total(rows);
  const weight = funds.reduce((a, r) => a + r.value, 0) / all;
  document.getElementById('pfFunds').textContent =
    `${pfPercent(weight, 0)} of your portfolio is in ${funds.length === 1 ? 'a fund' : 'funds'}: ${funds.map(r => r.t).join(', ')}. ` +
    'StockPulse doesn’t look inside funds, so what they hold isn’t in the sector, concentration or shared-bets figures above.';
}

function pfRenderGains(rows) {
  const section = document.getElementById('pfGainSection');
  const spyInfo = PF.info.get(PF_SPY);
  const spy = spyInfo && spyInfo.status === 'ok' && spyInfo.months ? { months: spyInfo.months, price: spyInfo.price.value } : null;
  const g = PortfolioMath.gains(rows, spy);
  section.hidden = !g;
  if (!g) return;
  const signed = v => `${v > 0 ? '+' : v < 0 ? '−' : ''}${pfMoney(Math.abs(v))}`;
  const lead = document.getElementById('pfGainLead');
  lead.replaceChildren(
    `The ${g.count === 1 ? 'holding' : `${g.count} holdings`} you gave a cost for cost ${pfMoney(g.paid)} and ${g.count === 1 ? 'is' : 'are'} worth ${pfMoney(g.value)} now: `,
    pfEl('span', { class: g.gain > 0 ? 'pos' : g.gain < 0 ? 'neg' : '', text: `${signed(g.gain)} (${pfSigned(g.pct)})` }),
    '.' + (g.without ? ` ${plural(g.without, 'holding has', 'holdings have')} no cost, so ${g.without === 1 ? 'it isn’t' : 'they aren’t'} in this.` : ''));

  // Paid, worth now and (once the comparison is known) the same money in the S&P 500, as bars.
  const bars = document.getElementById('pfGainBars');
  bars.replaceChildren();
  const drawBars = items => {
    const top = Math.max(...items.map(i => i[1]));
    items.forEach(([label, amount, cls]) => bars.append(pfEl('li', { class: 'pf-money-row' }, [
      pfEl('span', { class: 'pf-money-label', text: label }),
      pfSvg('svg', { class: 'pf-bar', viewBox: '0 0 100 4', preserveAspectRatio: 'none', 'aria-hidden': 'true' },
        [pfSvg('rect', { class: cls, x: 0, y: 0, width: ((amount / top) * 100).toFixed(2), height: 4 })]),
      pfEl('span', { class: 'pf-money-amount', text: pfMoney(amount) }),
    ])));
  };
  const versus = document.getElementById('pfGainSpy');
  const list = document.getElementById('pfGainRows');
  const more = document.getElementById('pfGainAll');
  const note = document.getElementById('pfGainNote');
  list.replaceChildren();
  const wantsSpy = rows.some(r => r.paid && r.bought);
  if (!g.spy) {
    drawBars([['You paid', g.paid, 'pf-bar-quiet'], ['Worth now', g.value, 'pf-bar-fill']]);
    more.hidden = true;
    versus.textContent = !wantsSpy
      ? 'Add the month you bought to compare with the S&P 500 over the same time. Without a date there’s no period to compare.'
      : !spy ? (spyInfo && spyInfo.status !== 'loading' ? 'The S&P 500’s prices couldn’t be loaded, so there’s no comparison right now.' : 'Getting the S&P 500’s prices…')
        : 'The S&P 500 fund has no price for the months you bought, so there’s no comparison.';
    note.textContent = '';
    return;
  }
  const s = g.spy;
  drawBars([['You paid', s.paid, 'pf-bar-quiet'], ['Worth now', s.value, 'pf-bar-fill'], ['Same money in the S&P 500', s.same, 'pf-bar-other']]);
  versus.textContent = `For the ${s.rows.length === 1 ? 'one' : s.rows.length} with a buy month: the same ${pfMoney(s.paid)} put into the S&P 500 in ${s.rows.length === 1 ? 'that month' : 'those months'} would be worth ${pfMoney(s.same)} now (${pfSigned(s.spyPct)}). Yours ${s.rows.length === 1 ? 'is' : 'are'} worth ${pfMoney(s.value)} (${pfSigned(s.pct)}).`;
  const ordered = s.rows.slice().sort((a, b) => b.value - a.value);
  (XRAY.showAllGains ? ordered : ordered.slice(0, FIRST_ROWS)).forEach(r => {
    list.append(pfEl('li', { class: 'pf-overlap-line',
      text: `${r.t}: paid ${pfMoney(r.paid)} in ${pfMonth(r.from)}, worth ${pfMoney(r.value)} now. The same money in the S&P 500: ${pfMoney(r.same)}.` }));
  });
  more.hidden = ordered.length <= FIRST_ROWS;
  more.textContent = XRAY.showAllGains ? 'Show fewer' : `Show all ${ordered.length}`;
  note.textContent = 'The S&P 500 figure is the SPY fund at the end of the month you bought, with dividends reinvested. Yours is today’s value against what you paid, so dividends you were paid aren’t in it. Buy dates are to the month.'
    + (s.skipped ? ` ${plural(s.skipped, 'holding with a cost has', 'holdings with a cost have')} no usable buy month and ${s.skipped === 1 ? 'isn’t' : 'aren’t'} compared.` : '');
}

function pfRenderXray() {
  const rows = pfMathRows();
  const box = document.getElementById('pfXray');
  box.hidden = rows.length === 0;
  if (!rows.length) return;
  pfRenderSectors(rows);
  pfRenderConcentration(rows);
  pfRenderOverlap(rows);
  pfRenderFunds(rows);
  pfRenderGains(rows);
  // The comparison needs the S&P 500 fund's history: one static file, fetched only when it's needed.
  if (rows.some(r => r.paid && r.bought) && !PF.info.has(PF_SPY + ':asked')) {
    PF.info.set(PF_SPY + ':asked', { status: 'ok' });
    pfInfo(PF_SPY, true).then(() => pfRenderXray());
  }
}

PF.listeners.push(pfRenderXray);
Object.assign(PAGE_ACTIONS.click, {
  pfOverlapAll: () => { XRAY.showAllOverlap = !XRAY.showAllOverlap; pfRenderXray(); },
  pfGainAll: () => { XRAY.showAllGains = !XRAY.showAllGains; pfRenderXray(); },
});
