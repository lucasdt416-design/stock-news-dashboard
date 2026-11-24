// The Briefing: what was published, what moved and what's coming for the things someone holds,
// ranked by how much of their money each one touches. Plain functions with no page or network
// access, so tests/node/portfolio_brief.test.mjs runs the same source the page uses.
//
// It says what happened and how much of the portfolio it concerns. It never says what to do.
const PortfolioBrief = (() => {
  const ISO = /^\d{4}-\d{2}-\d{2}$/;
  // How much a kind of item is worth reading, before the money it touches is counted.
  const KIND_WEIGHT = { results: 1.6, filing: 1.0, release: 1.1, news: 1.0 };
  const RELATED_SHARE = 0.4;   // news about a customer or supplier counts for less than news about the company
  const READ_FIRST = 5;
  const SOON_DAYS = 14;
  const WEEK_DAYS = 7;

  function dayNumber(iso) {
    if (!ISO.test(String(iso || ''))) return NaN;
    const [y, m, d] = iso.split('-').map(Number);
    return Date.UTC(y, m - 1, d) / 86400000;
  }

  function daysBetween(from, to) {
    return dayNumber(to) - dayNumber(from);
  }

  // A story's own importance: its score (0-10 or so), the kind of item, and how recent it is.
  function importance(story, today) {
    const age = Math.max(0, daysBetween(story.d, today));
    const fresh = Number.isFinite(age) ? 1 / (1 + age / 5) : 0.3;
    return Math.max(0, Number(story.s) || 0) * (KIND_WEIGHT[story.k] || 1) * fresh;
  }

  // holdings: [{ t, company, weight, fund }]. company is the watchlist symbol ('' if not followed).
  // seen: the day the briefing was last marked read ('' for never). today: 'YYYY-MM-DD'.
  function build(data, holdings, seen, today) {
    const stories = Array.isArray(data && data.stories) ? data.stories : [];
    const events = Array.isArray(data && data.events) ? data.events : [];
    const days = Array.isArray(data && data.days) ? data.days : [];
    const since = ISO.test(String(seen || '')) ? seen : '';
    // With no visit on record, "new" means the past week.
    const from = since || (() => {
      const n = dayNumber(today) - WEEK_DAYS;
      return new Date(n * 86400000).toISOString().slice(0, 10);
    })();

    // A company can be held twice (GOOGL and GOOG): its weight is the sum.
    const byCompany = new Map();
    holdings.forEach(h => {
      if (!h.company) return;
      const entry = byCompany.get(h.company) || { company: h.company, tickers: [], weight: 0 };
      entry.tickers.push(h.t);
      entry.weight += Math.max(0, Number(h.weight) || 0);
      byCompany.set(h.company, entry);
    });

    const items = [];
    stories.forEach(story => {
      if (!ISO.test(String(story.d || '')) || story.d > today) return;
      const own = byCompany.get(story.t);
      if (own) {
        items.push({ story, company: own.company, weight: own.weight, how: 'own', why: '',
          rank: importance(story, today) * (0.25 + own.weight), isNew: story.d > from });
        return;
      }
      // A story filed under another company that names one held as a customer, supplier or peer.
      const touched = (story.rel || []).map(t => byCompany.get(t)).filter(Boolean)
        .sort((a, b) => b.weight - a.weight)[0];
      if (touched) {
        items.push({ story, company: touched.company, weight: touched.weight, how: 'related',
          why: (story.why && story.why[touched.company]) || '',
          rank: importance(story, today) * (0.25 + touched.weight) * RELATED_SHARE, isNew: story.d > from });
      }
    });
    items.sort((a, b) => b.rank - a.rank || (a.story.d < b.story.d ? 1 : -1));

    const fresh = items.filter(i => i.isNew);
    // "Read these first": the best of what's new, at most one per company so one busy name can't fill it.
    const first = [];
    const used = new Set();
    fresh.forEach(item => {
      if (first.length >= READ_FIRST || used.has(item.company)) return;
      if (item.rank < 0.6) return;
      used.add(item.company);
      first.push(item);
    });

    const moves = days.filter(d => byCompany.has(d.t) && d.d > from && d.d <= today)
      .map(d => Object.assign({ weight: byCompany.get(d.t).weight }, d))
      .sort((a, b) => Math.abs(b.m) * (0.25 + b.weight) - Math.abs(a.m) * (0.25 + a.weight));

    const coming = events.filter(e => byCompany.has(e.t) && e.d >= today)
      .map(e => Object.assign({ weight: byCompany.get(e.t).weight, inDays: daysBetween(today, e.d) }, e));
    const soonResults = coming.filter(e => e.k === 'results' && e.inDays <= SOON_DAYS);
    const soonShare = [...new Set(soonResults.map(e => e.t))].reduce((sum, t) => sum + byCompany.get(t).weight, 0);

    // Companies with nothing new, no big day and nothing due soon: the ones that can be skipped today.
    const busy = new Set([...fresh.map(i => i.company), ...moves.map(m => m.t),
      ...coming.filter(e => e.inDays <= SOON_DAYS).map(e => e.t)]);
    const quiet = [...byCompany.values()].filter(c => !busy.has(c.company))
      .sort((a, b) => b.weight - a.weight).map(c => c.company);
    const quietShare = quiet.reduce((sum, c) => sum + byCompany.get(c).weight, 0);

    const counts = new Map();
    fresh.forEach(i => counts.set(i.company, (counts.get(i.company) || 0) + 1));

    return {
      since,
      from,
      newCount: fresh.length,
      first,
      rest: fresh.filter(i => !first.includes(i)),
      older: items.filter(i => !i.isNew).slice(0, 20),
      moves,
      coming,
      soonResults,
      soonShare,
      quiet,
      quietShare,
      counts,
      covered: byCompany.size,
      uncovered: holdings.filter(h => !h.company && !h.fund).map(h => h.t),
      funds: holdings.filter(h => h.fund).map(h => h.t),
    };
  }

  // The briefing as plain text, to paste into notes or an email. Holdings' amounts are left out.
  function asText(brief, names, todayLabel) {
    const name = t => names[t] || t;
    const lines = [`StockPulse briefing, ${todayLabel}`, ''];
    if (brief.first.length) {
      lines.push('Read first');
      brief.first.forEach(i => lines.push(`- ${name(i.company)}: ${i.story.h}${i.story.u ? ` (${i.story.u})` : ''}`));
      lines.push('');
    }
    if (brief.moves.length) {
      lines.push('Big days');
      brief.moves.forEach(m => lines.push(`- ${name(m.t)} ${m.m > 0 ? '+' : ''}${m.m}% on ${m.d}${m.v === 'own' ? ', on its own' : m.v === 'market' ? ', with the market' : m.v === 'peers' ? ', with its peers' : ''}`));
      lines.push('');
    }
    const soon = brief.coming.filter(e => e.inDays <= SOON_DAYS);
    if (soon.length) {
      lines.push('Coming up');
      soon.forEach(e => lines.push(`- ${e.d} ${name(e.t)}: ${e.h}`));
      lines.push('');
    }
    if (brief.quiet.length) lines.push(`Nothing new: ${brief.quiet.map(name).join(', ')}`);
    return lines.join('\n').trim();
  }

  return { build, asText, importance, daysBetween, READ_FIRST, SOON_DAYS };
})();
