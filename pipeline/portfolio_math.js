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

  return { total, positions, sectors, concentration, monthAtOrBefore, gains, overlap };
})();
