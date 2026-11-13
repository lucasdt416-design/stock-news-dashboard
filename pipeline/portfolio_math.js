// The portfolio page's arithmetic: weights, sectors, concentration, shared bets and gain or loss.
// Plain functions with no page or network access, so tests/node/portfolio_math.test.mjs checks
// the same source the page runs against numbers worked out by hand.
//
// A "row" is one priced holding: { t, company, value, fund, sector, paid, bought }.
//   company  the watchlist company it belongs to ('' if StockPulse doesn't follow it). Two share
//            classes of one company (GOOG and GOOGL) have the same company and count as one.
//   value    shares times the latest real price, in dollars
const PortfolioMath = (() => {
  function sum(list) {
    return list.reduce((a, b) => a + b, 0);
  }

  function total(rows) {
    return sum(rows.map(r => r.value));
  }

  // The same company held under two tickers is one position.
  function positions(rows) {
    const byKey = new Map();
    rows.forEach(r => {
      const key = r.company || r.t;
      const have = byKey.get(key);
      if (have) { have.value += r.value; have.tickers.push(r.t); } else {
        byKey.set(key, { key, value: r.value, tickers: [r.t], sector: r.sector, fund: r.fund, company: r.company });
      }
    });
    return [...byKey.values()].sort((a, b) => b.value - a.value || a.key.localeCompare(b.key));
  }

  // Each sector's share of the whole portfolio. Funds are their own group, because their contents
  // aren't looked into, and a stock with no known sector is "Sector unknown".
  function sectors(rows) {
    const all = total(rows);
    if (!(all > 0)) return [];
    const groups = new Map();
    rows.forEach(r => {
      const name = r.fund ? 'Funds' : r.sector || 'Sector unknown';
      const group = groups.get(name) || { name, value: 0, tickers: [] };
      group.value += r.value;
      group.tickers.push(r.t);
      groups.set(name, group);
    });
    const last = name => (name === 'Sector unknown' ? 2 : name === 'Funds' ? 1 : 0);
    return [...groups.values()]
      .map(g => ({ name: g.name, weight: g.value / all, tickers: g.tickers }))
      .sort((a, b) => last(a.name) - last(b.name) || b.weight - a.weight || a.name.localeCompare(b.name));
  }

  // How concentrated the individual stocks are. Funds are left out: a fund is hundreds of stocks,
  // so counting it as one holding would make a spread-out portfolio look concentrated.
  //   effective = 1 / (sum of squared weights): 50%, 30%, 20% gives 1 / 0.38 = 2.63.
  function concentration(rows) {
    const all = total(rows);
    const stocks = positions(rows.filter(r => !r.fund));
    const funds = rows.filter(r => r.fund);
    const stockTotal = sum(stocks.map(p => p.value));
    const fundWeight = all > 0 ? sum(funds.map(r => r.value)) / all : 0;
    if (!(stockTotal > 0)) return { stocks: 0, fundWeight, fundTickers: funds.map(r => r.t) };
    const weights = stocks.map(p => p.value / stockTotal);
    const bySector = new Map();
    stocks.forEach((p, i) => {
      const name = p.sector || 'Sector unknown';
      bySector.set(name, (bySector.get(name) || 0) + weights[i]);
    });
    const [sectorName, sectorWeight] = [...bySector.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))[0];
    return {
      stocks: stocks.length,
      fundWeight,
      fundTickers: funds.map(r => r.t),
      largest: { name: stocks[0].tickers.join(' + '), weight: weights[0] },
      topThree: { names: stocks.slice(0, 3).map(p => p.tickers.join(' + ')), weight: sum(weights.slice(0, 3)) },
      largestSector: { name: sectorName, weight: sectorWeight },
      effective: 1 / sum(weights.map(w => w * w)),
    };
  }

  // The adjusted close for the given month, or the nearest earlier month that has one.
  function monthAtOrBefore(months, month) {
    let found = null;
    for (const pair of months || []) {
      if (pair[0] > month) break;
      found = pair;
    }
    return found;
  }

  // Gain or loss against what was paid, and the same money in the S&P 500 fund where a buy month
  // is known. Without a buy month there is no period to compare over, so there is no comparison.
  //   same money in the fund = paid x (fund's latest price / fund's adjusted close for the buy month)
  function gains(rows, spy) {
    const withCost = rows.filter(r => Number.isFinite(r.paid) && r.paid > 0);
    if (!withCost.length) return null;
    const paid = sum(withCost.map(r => r.paid));
    const value = sum(withCost.map(r => r.value));
    const out = { count: withCost.length, without: rows.length - withCost.length, paid, value, gain: value - paid, pct: (value - paid) / paid, spy: null };
    if (!spy || !Array.isArray(spy.months) || !(spy.price > 0)) return out;
    const compared = [];
    withCost.forEach(r => {
      if (!r.bought) return;
      const start = monthAtOrBefore(spy.months, r.bought);
      if (!start || start[0] !== r.bought) return; // before the fund existed, or a month it has no price for
      compared.push({ t: r.t, paid: r.paid, value: r.value, from: start[0], same: r.paid * spy.price / start[1] });
    });
    if (compared.length) {
      const cPaid = sum(compared.map(c => c.paid));
      const cValue = sum(compared.map(c => c.value));
      const cSame = sum(compared.map(c => c.same));
      out.spy = { rows: compared, paid: cPaid, value: cValue, same: cSame, pct: (cValue - cPaid) / cPaid, spyPct: (cSame - cPaid) / cPaid,
        skipped: withCost.length - compared.length };
    }
    return out;
  }

  // Bets several holdings share, from what the watchlist says about each company. Every line names
  // its holdings, and its percentage is the sum of those holdings' shares of the whole portfolio,
  // each counted once. Lines overlap, so they are never added together.
  //   details: { SYM: { th: [themes], ec: [economy links], cu: [customers], su: [suppliers], co: [competitors] } }
  function overlap(rows, details) {
    const all = total(rows);
    if (!(all > 0)) return { lines: [], covered: 0, outside: [], outsideWeight: 0 };
    const held = positions(rows.filter(r => !r.fund && r.company && details[r.company]));
    const weightOf = new Map(held.map(p => [p.key, p.value / all]));
    const label = key => held.find(p => p.key === key).tickers.join(' + ');
    const line = (kind, subject, keys, extra) => {
      const unique = [...new Set(keys)].sort((a, b) => weightOf.get(b) - weightOf.get(a) || a.localeCompare(b));
      return Object.assign({ kind, subject, tickers: unique.map(label), weight: sum(unique.map(k => weightOf.get(k))) }, extra || {});
    };
    const lines = [];

    const shared = field => {
      const groups = new Map();
      held.forEach(p => (details[p.key][field] || []).forEach(tag => {
        groups.set(tag, (groups.get(tag) || []).concat([p.key]));
      }));
      return [...groups.entries()].filter(([, keys]) => keys.length >= 2);
    };
    shared('th').forEach(([tag, keys]) => lines.push(line('theme', tag, keys)));
    shared('ec').forEach(([tag, keys]) => lines.push(line('economy', tag, keys)));

    // Who sells to whom, inside the portfolio. A lists B as a customer, or B lists A as a supplier.
    const sellsTo = new Map();
    const add = (seller, buyer) => {
      if (seller === buyer || !weightOf.has(seller) || !weightOf.has(buyer)) return;
      sellsTo.set(seller, (sellsTo.get(seller) || new Set()).add(buyer));
    };
    held.forEach(p => {
      (details[p.key].cu || []).forEach(buyer => add(p.key, buyer));
      (details[p.key].su || []).forEach(seller => add(seller, p.key));
    });
    sellsTo.forEach((buyers, seller) => {
      lines.push(line('customers', seller, [seller, ...buyers], { subjectLabel: label(seller), others: [...buyers].map(label).sort() }));
    });

    // The same customer or supplier named by several holdings, whether or not it is held too.
    const named = field => {
      const groups = new Map();
      held.forEach(p => (details[p.key][field] || []).forEach(name => {
        if (name !== p.key) groups.set(name, (groups.get(name) || []).concat([p.key]));
      }));
      return [...groups.entries()].filter(([, keys]) => keys.length >= 2);
    };
    named('cu').forEach(([name, keys]) => lines.push(line('sameCustomer', name, keys)));
    named('su').forEach(([name, keys]) => lines.push(line('sameSupplier', name, keys)));

    // A holding and the competitors of its that are also held. The same group reached from two
    // of its members is one line.
    const rivals = new Map(held.map(p => [p.key, new Set()]));
    held.forEach(p => (details[p.key].co || []).forEach(other => {
      if (other !== p.key && weightOf.has(other)) { rivals.get(p.key).add(other); rivals.get(other).add(p.key); }
    }));
    const seen = new Set();
    held.forEach(p => {
      const others = rivals.get(p.key);
      if (!others.size) return;
      const group = [p.key, ...others].sort();
      const id = group.join('|');
      if (seen.has(id)) return;
      seen.add(id);
      lines.push(line('competitors', p.key, group, { subjectLabel: label(p.key), others: [...others].map(label).sort() }));
    });

    lines.sort((a, b) => b.weight - a.weight || b.tickers.length - a.tickers.length || String(a.subject).localeCompare(String(b.subject)));
    const outside = rows.filter(r => !r.fund && !(r.company && details[r.company]));
    return {
      lines,
      covered: held.length,
      outside: outside.map(r => r.t),
      outsideWeight: sum(outside.map(r => r.value)) / all,
    };
  }

  // ---- "What if I'd invested" --------------------------------------------------------------
  // Prices are month-end adjusted closes, so every date here is a month. Nothing is estimated
  // between two real readings.

  function addMonths(month, n) {
    const index = Number(month.slice(0, 4)) * 12 + Number(month.slice(5, 7)) - 1 + n;
    return `${String(Math.floor(index / 12)).padStart(4, '0')}-${String((index % 12) + 1).padStart(2, '0')}`;
  }

  function monthsApart(from, to) {
    return (Number(to.slice(0, 4)) - Number(from.slice(0, 4))) * 12 + Number(to.slice(5, 7)) - Number(from.slice(5, 7));
  }

  // Days from the last day of a month to a date, as years.
  function yearsSince(month, isoDate) {
    const end = Date.UTC(Number(month.slice(0, 4)), Number(month.slice(5, 7)), 0);
    const then = Date.UTC(Number(isoDate.slice(0, 4)), Number(isoDate.slice(5, 7)) - 1, Number(isoDate.slice(8, 10)));
    return (then - end) / 86400000 / 365.25;
  }

  // The last finished month on or before the day n years before a date: for 2026-11-11 and
  // 5 years, the day is 2021-11-11 and the month is 2021-10.
  function monthYearsAgo(isoDate, years) {
    return addMonths(isoDate.slice(0, 7), -12 * years - 1);
  }

  // The yearly rate that turns the money put in, when it was put in, into the value today.
  // flows: [{ months: how long ago in months, amount }]. Found by bisection on the monthly rate.
  function yearlyRate(flows, value) {
    const worth = rate => sum(flows.map(f => f.amount * Math.pow(1 + rate, f.months)));
    let low = -0.99;
    let high = 1;
    if (!(value > 0) || !flows.length || worth(high) < value) return null;
    for (let i = 0; i < 200; i += 1) {
      const mid = (low + high) / 2;
      if (worth(mid) < value) low = mid; else high = mid;
    }
    return Math.pow(1 + (low + high) / 2, 12) - 1;
  }

  // What an amount put in at the end of a month, plus an optional amount at the end of every
  // finished month after it, is worth at the latest price.
  //   history: { months: [[month, adjusted close]], price: latest price, date: its date }
  //   value = shares x latest price, where shares = amount / close(start) + sum(monthly / close(m))
  function whatIf(history, amount, fromMonth, monthly) {
    const months = history.months || [];
    if (!months.length) return { error: 'noHistory' };
    if (fromMonth < months[0][0]) return { error: 'before', first: months[0][0] };
    const start = monthAtOrBefore(months, fromMonth);
    const extra = monthly > 0 ? monthly : 0;
    let shares = amount / start[1];
    let putIn = amount;
    const totalMonths = yearsSince(start[0], history.date) * 12;
    const flows = [{ months: totalMonths, amount }];
    const series = [[start[0], amount]];
    let contributions = 0;
    months.forEach(([month, close]) => {
      if (month <= start[0]) return;
      if (extra) {
        shares += extra / close;
        putIn += extra;
        contributions += 1;
        flows.push({ months: Math.max(0, totalMonths - monthsApart(start[0], month)), amount: extra });
      }
      series.push([month, shares * close]);
    });
    const value = shares * history.price;
    series.push([history.date, value]);
    const years = totalMonths / 12;
    let perYear = null;
    if (years >= 1) perYear = extra ? yearlyRate(flows, value) : Math.pow(value / amount, 1 / years) - 1;
    return { from: start[0], asked: fromMonth, value, putIn, gain: value - putIn, pct: (value - putIn) / putIn, years, perYear, contributions, series };
  }

  // The same amount split across a portfolio by today's weights, each part bought at the end of
  // the same month. A holding that wasn't trading yet is left out and named, and the others'
  // weights are rescaled to add to 100%.
  //   parts: [{ t, weight, months, price, date }]
  function whatIfPortfolio(parts, amount, fromMonth) {
    const included = [];
    const leftOut = [];
    parts.forEach(p => {
      const months = p.months || [];
      if (!months.length || fromMonth < months[0][0]) leftOut.push(p.t); else included.push(p);
    });
    const weight = sum(included.map(p => p.weight));
    if (!included.length || !(weight > 0)) return { error: 'none', leftOut };
    const runs = included.map(p => ({ t: p.t, share: p.weight / weight, run: whatIf(p, amount * p.weight / weight, fromMonth, 0) }));
    const from = runs.map(r => r.run.from).sort()[0];
    const value = sum(runs.map(r => r.run.value));
    const date = included.map(p => p.date).sort()[0];
    const years = yearsSince(from, date);
    // One point per month from the start to the latest finished month any part has.
    const lastMonth = included.map(p => p.months[p.months.length - 1][0]).sort().pop();
    const series = [];
    for (let month = from; month <= lastMonth; month = addMonths(month, 1)) {
      series.push([month, sum(runs.map(r => {
        const at = monthAtOrBefore(r.run.series.slice(0, -1), month);
        return at ? at[1] : amount * r.share;
      }))]);
    }
    series.push([date, value]);
    return {
      from, asked: fromMonth, value, putIn: amount, gain: value - amount, pct: (value - amount) / amount, years,
      perYear: years >= 1 ? Math.pow(value / amount, 1 / years) - 1 : null,
      included: runs.map(r => ({ t: r.t, share: r.share, value: r.run.value })), leftOut, series,
    };
  }

  // ---- Value over time ----------------------------------------------------------------------
  // What the shares held today were worth at the end of each month: shares x that month's adjusted
  // close, added up. A month is only shown if every holding has a real price for it, so the line
  // starts when the youngest holding began trading, and nothing is filled in. The last point is
  // today's prices.
  //   items: [{ t, sh, months: [[YYYY-MM, adjusted close]], price, date }]
  function valueSeries(items) {
    const usable = (items || []).filter(i => i.sh > 0 && i.price > 0 && Array.isArray(i.months) && i.months.length);
    if (!usable.length) return null;
    const start = usable.map(i => i.months[0][0]).sort().pop();
    const earliest = usable.map(i => i.months[0][0]).sort()[0];
    const lookups = usable.map(i => ({ sh: i.sh, byMonth: new Map(i.months) }));
    const points = [];
    usable[0].months.forEach(([month]) => {
      if (month < start || !lookups.every(l => l.byMonth.has(month))) return;
      points.push([month, sum(lookups.map(l => l.sh * l.byMonth.get(month)))]);
    });
    const date = usable.map(i => i.date).sort().pop();
    points.push([date, sum(usable.map(i => i.sh * i.price))]);
    return {
      points,
      from: points[0][0],
      // The holdings that set where the line starts, when others go back further.
      limitedBy: start > earliest ? usable.filter(i => i.months[0][0] === start).map(i => i.t) : [],
    };
  }

  // The last `months` finished months of a series, plus today. Null when there aren't that many,
  // so a "5 years" view is never drawn from 3 years of prices. No `months` means all of it.
  function lastMonths(series, months) {
    if (!series || series.points.length < 2) return null;
    if (!months) return series.points;
    if (series.points.length - 1 < months) return null;
    return series.points.slice(series.points.length - 1 - months);
  }

  // How much each holding's shares gained or lost in dollars since the end of a month:
  //   shares x (today's price - that month's adjusted close). They add up to the whole change.
  function changeSince(items, month) {
    const out = [];
    (items || []).forEach(i => {
      if (!(i.sh > 0) || !(i.price > 0) || !Array.isArray(i.months)) return;
      const then = i.months.find(pair => pair[0] === month);
      if (!then) return;
      out.push({ t: i.t, then: i.sh * then[1], now: i.sh * i.price, change: i.sh * (i.price - then[1]) });
    });
    return out.sort((a, b) => b.change - a.change || a.t.localeCompare(b.t));
  }

  // The same starting money put into a fund instead, for the same months: the first point's value
  // x (the fund's price that month / its price in the first month). Null if the fund has no real
  // price for any of the months, so the comparison is never drawn from a guess.
  function sameMoneyIn(points, months, price) {
    if (!points || points.length < 2 || !Array.isArray(months) || !(price > 0)) return null;
    const byMonth = new Map(months);
    const start = byMonth.get(points[0][0]);
    if (!start) return null;
    const out = [];
    for (let i = 0; i < points.length; i += 1) {
      const at = i === points.length - 1 ? price : byMonth.get(points[i][0]);
      if (!at) return null;
      out.push([points[i][0], points[0][1] * at / start]);
    }
    return out;
  }

  // ---- The latest day's change and dividends --------------------------------------------------

  // How many dollars the holdings moved on the latest trading day: shares x (latest price - the
  // close of the trading day before). Only holdings priced on the latest date, with a real close
  // before it, are counted. The rest are named, so the figure never passes for the whole
  // portfolio when it isn't.
  //   items: [{ t, sh, price, date, previous: { value, date } or null }]
  function dayChange(items) {
    const usable = (items || []).filter(i => i.sh > 0 && i.price > 0 && i.date);
    if (!usable.length) return null;
    const date = usable.map(i => i.date).sort().pop();
    const rows = [];
    const missing = [];
    usable.forEach(i => {
      const p = i.previous;
      if (i.date !== date || !p || !(p.value > 0) || !(p.date < date)) { missing.push(i.t); return; }
      rows.push({ t: i.t, before: i.sh * p.value, change: i.sh * (i.price - p.value), each: i.price - p.value });
    });
    if (!rows.length) return null;
    const before = sum(rows.map(r => r.before));
    const change = sum(rows.map(r => r.change));
    return { date, change, before, pct: change / before, missing: missing.sort(),
      rows: rows.sort((a, b) => b.change - a.change || a.t.localeCompare(b.t)) };
  }

  // What the shares held now earned in dividends over the past year: shares x each dividend per
  // share. A holding with an empty list paid nothing, which is known; one with no list isn't
  // known and is named rather than counted as zero. The yield is the year's dividends over
  // today's value of the holdings whose dividends are known.
  //   items: [{ t, sh, value, dividends: [[YYYY-MM-DD, per share]] or null }]
  function dividendIncome(items) {
    const usable = (items || []).filter(i => i.sh > 0 && i.value > 0);
    const known = usable.filter(i => Array.isArray(i.dividends));
    if (!known.length) return null;
    const rows = known.map(i => {
      const perShare = sum(i.dividends.map(d => d[1]));
      return { t: i.t, amount: i.sh * perShare, perShare, payments: i.dividends.length, yield: i.sh * perShare / i.value };
    });
    const total = sum(rows.map(r => r.amount));
    return {
      total,
      yield: total / sum(known.map(i => i.value)),
      rows: rows.filter(r => r.amount > 0).sort((a, b) => b.amount - a.amount || a.t.localeCompare(b.t)),
      none: rows.filter(r => !(r.amount > 0)).map(r => r.t).sort(),
      unknown: usable.filter(i => !Array.isArray(i.dividends)).map(i => i.t).sort(),
    };
  }

  return { total, positions, sectors, concentration, monthAtOrBefore, gains, overlap, sameMoneyIn, dayChange, dividendIncome,
    addMonths, monthsApart, yearsSince, monthYearsAgo, yearlyRate, whatIf, whatIfPortfolio,
    valueSeries, lastMonths, changeSince };
})();
