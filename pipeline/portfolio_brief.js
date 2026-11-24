// The Briefing tab: what was published, what moved and what's coming for what this browser holds.
// The page fetches data/brief.json, the same static file for every visitor, and matches it against
// the holdings here. Nothing about the holdings is sent anywhere.
const BRIEF_SEEN_KEY = 'stockpulse_brief_seen';
const BRIEF = {
  data: null,
  status: 'idle',   // 'idle' | 'loading' | 'ok' | 'failed'
  showRest: false,
  showQuietNames: false,
  last: null,       // the last brief worked out, for "Copy as text"
};

function brToday() {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;
}

function brSeen() {
  try {
    const value = localStorage.getItem(BRIEF_SEEN_KEY) || '';
    return /^\d{4}-\d{2}-\d{2}$/.test(value) ? value : '';
  } catch (e) { return ''; }
}

function brHttp(url) {
  return /^https?:\/\//i.test(String(url || '')) ? String(url) : null;
}

function brWeekday(iso) {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(iso || ''));
  if (!m) return '';
  return new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3])).toLocaleDateString('en-US', { weekday: 'long' });
}

// "since Thursday" within the week, "since Nov 12" before that.
function brSinceWords(brief) {
  if (!brief.since) return 'In the past week';
  const gap = PortfolioBrief.daysBetween(brief.since, brToday());
  if (gap <= 0) return 'Since earlier today';
  if (gap === 1) return 'Since yesterday';
  if (gap < 7) return `Since ${brWeekday(brief.since)}`;
  return `Since ${pfDay(brief.since)}`;
}

function brShare(weight) {
  return `${pfPercent(weight, weight >= 0.1 ? 0 : 1)} of your money`;
}

const BR_KIND = { results: 'Results', filing: 'Filing', release: 'Press release', news: 'News' };
const BR_EVENT = { results: 'Results', dividend: 'Dividend', filing: 'Filing due', event: 'Event' };
const BR_VERDICT = {
  own: 'on its own',
  market: 'with the market',
  peers: 'with its peers',
};

async function brLoad() {
  if (BRIEF.status !== 'idle') return;
  BRIEF.status = 'loading';
  try {
    const res = await fetch('data/brief.json', { cache: 'no-cache' });
    if (!res.ok) throw new Error(String(res.status));
    const data = await res.json();
    BRIEF.data = data && typeof data === 'object' ? data : null;
    BRIEF.status = BRIEF.data ? 'ok' : 'failed';
  } catch (e) {
    BRIEF.status = 'failed';
  }
  brRender();
}

// Holdings as the briefing needs them: the company each one is, and its share of the money.
function brHoldings() {
  const rows = pfRows().rows;
  const total = rows.reduce((sum, r) => sum + (Number.isFinite(r.value) ? r.value : 0), 0);
  return rows.map(r => ({
    t: r.h.t,
    company: r.fund ? '' : r.company,
    fund: r.fund,
    weight: total > 0 && Number.isFinite(r.value) ? r.value / total : 0,
  }));
}

function brStoryRow(item, n) {
  const s = item.story;
  const href = brHttp(s.u);
  const meta = [
    pfEl('a', { class: 'br-ticker', href: companyHref(item.company), text: item.company }),
    pfEl('span', { text: brShare(item.weight) }),
    pfEl('span', { text: item.how === 'related' ? `via ${s.t}` : BR_KIND[s.k] || 'News' }),
    pfEl('span', { text: pfDay(s.d) }),
  ];
  const children = [
    n ? pfEl('span', { class: 'br-n', text: String(n), 'aria-hidden': 'true' }) : null,
    pfEl('div', { class: 'br-story-body' }, [
      pfEl('p', { class: 'br-meta' }, meta),
      pfEl('h3', { class: 'br-headline' }, [href
        ? pfEl('a', { href, target: '_blank', rel: 'noopener noreferrer', text: s.h })
        : s.h]),
      item.how === 'related'
        ? pfEl('p', { class: 'br-why', text: item.why || `Filed under ${COMPANY_NAMES[s.t] || s.t}, which names ${pfShortName(item.company)}.` })
        : s.x ? pfEl('p', { class: 'br-why', text: s.x }) : null,
    ]),
  ];
  return pfEl('li', { class: 'br-story' + (n ? ' br-story-first' : '') }, children);
}

function brMoveRow(move) {
  const market = !Number.isFinite(move.mk) ? '' : move.mk === 0 ? 'The S&P 500 was flat that day.'
    : `The S&P 500 was ${move.mk > 0 ? '+' : '−'}${Math.abs(move.mk)}% that day.`;
  const verdict = BR_VERDICT[move.v] ? `Moved ${BR_VERDICT[move.v]}.` : '';
  return pfEl('li', { class: 'br-move' }, [
    pfEl('a', { class: 'br-ticker', href: companyHref(move.t), text: move.t }),
    pfEl('span', { class: 'br-move-pct ' + (move.m >= 0 ? 'pos' : 'neg'), text: `${move.m >= 0 ? '+' : '−'}${Math.abs(move.m)}%` }),
    pfEl('span', { class: 'br-move-words', text: `${pfDay(move.d)}. ${verdict} ${market}`.trim() }),
    pfEl('span', { class: 'br-share', text: brShare(move.weight) }),
  ]);
}

function brEventRow(event) {
  const href = brHttp(event.u);
  const when = event.inDays === 0 ? 'Today' : event.inDays === 1 ? 'Tomorrow' : pfDay(event.d);
  return pfEl('li', { class: 'br-event' + (event.inDays <= PortfolioBrief.SOON_DAYS ? ' br-event-soon' : '') }, [
    pfEl('span', { class: 'br-event-when', text: when }),
    pfEl('span', { class: 'br-event-what' }, [
      pfEl('a', { class: 'br-ticker', href: companyHref(event.t), text: event.t }),
      ' ',
      href ? pfEl('a', { href, target: '_blank', rel: 'noopener noreferrer', text: BR_EVENT[event.k] || 'Event' }) : (BR_EVENT[event.k] || 'Event'),
      event.est ? pfEl('span', { class: 'br-est', text: ' (estimated)' }) : null,
    ]),
    pfEl('span', { class: 'br-share', text: brShare(event.weight) }),
  ]);
}

function brRender() {
  const box = document.getElementById('pfBrief');
  if (!box) return;
  const holdings = PF.holdings.length ? brHoldings() : [];
  box.hidden = holdings.length === 0;
  const tabCount = document.getElementById('pfBriefCount');
  if (!holdings.length) { if (tabCount) tabCount.hidden = true; return; }
  if (BRIEF.status === 'idle') { brLoad(); }

  const lead = document.getElementById('brLead');
  const sub = document.getElementById('brSub');
  const today = brToday();
  document.getElementById('brDate').textContent = new Date().toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' });
  if (BRIEF.status !== 'ok') {
    lead.textContent = BRIEF.status === 'failed' ? 'The briefing couldn’t be loaded just now.' : 'Reading the latest stories…';
    sub.textContent = '';
    ['brFirstWrap', 'brMovesWrap', 'brComingWrap', 'brRestWrap', 'brQuietWrap'].forEach(id => { document.getElementById(id).hidden = true; });
    return;
  }

  const brief = PortfolioBrief.build(BRIEF.data, holdings, brSeen(), today);
  BRIEF.last = brief;
  if (tabCount) {
    tabCount.hidden = brief.newCount === 0;
    tabCount.textContent = brief.newCount > 99 ? '99+' : String(brief.newCount);
  }

  // The lead: two sentences that say whether there's anything to do at all.
  const since = brSinceWords(brief);
  if (!brief.covered) {
    lead.textContent = 'StockPulse doesn’t follow any of the companies you hold yet.';
    sub.textContent = 'The briefing covers the 100 or so companies on the watchlist. Funds and other tickers are priced, but their news isn’t collected.';
  } else if (!brief.newCount && !brief.moves.length) {
    lead.textContent = `${since}, nothing new about what you own.`;
    sub.textContent = brief.soonResults.length ? '' : 'Nothing is due in the next two weeks either.';
  } else {
    const stories = brief.newCount ? plural(brief.newCount, 'story', 'stories') : 'no stories';
    lead.textContent = `${since}: ${stories} about what you own${brief.first.length ? `, ${brief.first.length} worth reading first` : ''}.`;
    const bits = [];
    if (brief.quiet.length) {
      bits.push(`Nothing new for ${brief.quiet.length === 1 ? pfShortName(brief.quiet[0]) : plural(brief.quiet.length, 'company', 'companies')} (${pfPercent(brief.quietShare, 0)} of your money).`);
    }
    if (brief.soonResults.length) {
      bits.push(`Companies holding ${pfPercent(brief.soonShare, 0)} of your money report results in the next two weeks.`);
    }
    sub.textContent = bits.join(' ');
  }

  // Read first
  const firstWrap = document.getElementById('brFirstWrap');
  const firstList = document.getElementById('brFirst');
  firstWrap.hidden = brief.first.length === 0;
  firstList.replaceChildren(...brief.first.map((item, i) => brStoryRow(item, i + 1)));

  // Big days
  const movesWrap = document.getElementById('brMovesWrap');
  movesWrap.hidden = brief.moves.length === 0;
  document.getElementById('brMoves').replaceChildren(...brief.moves.slice(0, 6).map(brMoveRow));

  // Coming up: the next two weeks in full, then just results further out.
  const coming = brief.coming.filter(e => e.inDays <= PortfolioBrief.SOON_DAYS || e.k === 'results').slice(0, 8);
  document.getElementById('brComingWrap').hidden = coming.length === 0;
  document.getElementById('brComing').replaceChildren(...coming.map(brEventRow));

  // The rest of what's new
  const restWrap = document.getElementById('brRestWrap');
  restWrap.hidden = brief.rest.length === 0;
  document.getElementById('brRestHeading').textContent = `Also new (${brief.rest.length})`;
  const rest = BRIEF.showRest ? brief.rest : brief.rest.slice(0, 4);
  document.getElementById('brRest').replaceChildren(...rest.map(item => brStoryRow(item, 0)));
  const restAll = document.getElementById('brRestAll');
  restAll.hidden = brief.rest.length <= 4;
  restAll.textContent = BRIEF.showRest ? 'Show fewer' : `Show all ${brief.rest.length}`;

  // Quiet, and what the briefing can't cover
  const quietWrap = document.getElementById('brQuietWrap');
  const notes = [];
  if (brief.quiet.length) {
    notes.push(`Nothing new, no big days and nothing due soon: ${pfList(brief.quiet.map(pfShortName))}. You can skip ${brief.quiet.length === 1 ? 'it' : 'them'} today.`);
  }
  if (brief.funds.length) notes.push(`${pfList(brief.funds)} ${brief.funds.length === 1 ? 'is a fund' : 'are funds'}, so ${brief.funds.length === 1 ? 'its' : 'their'} news is the whole market’s.`);
  if (brief.uncovered.length) notes.push(`StockPulse doesn’t follow ${pfList(brief.uncovered)}, so ${brief.uncovered.length === 1 ? 'its' : 'their'} news isn’t here.`);
  quietWrap.hidden = notes.length === 0;
  document.getElementById('brQuiet').replaceChildren(...notes.map(text => pfEl('p', { class: 'pf-note', text })));

  document.getElementById('brMarkRead').hidden = brief.newCount === 0;
  document.getElementById('brSeenNote').textContent = brief.since
    ? `“New” means published after ${pfDay(brief.since)}, when you last marked this read.`
    : '“New” means the past seven days. Mark it read and next time it starts from today.';
}

function brMarkRead() {
  try { localStorage.setItem(BRIEF_SEEN_KEY, brToday()); } catch (e) { /* stays as it was */ }
  BRIEF.showRest = false;
  brRender();
  pfSay('Marked as read. New stories will show from here.', 'good');
}

async function brCopy(button) {
  if (!BRIEF.last) return;
  const text = PortfolioBrief.asText(BRIEF.last, COMPANY_NAMES, new Date().toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' }));
  try {
    await navigator.clipboard.writeText(text);
    button.textContent = 'Copied';
  } catch (e) {
    button.textContent = 'Couldn’t copy';
  }
  setTimeout(() => { button.textContent = 'Copy as text'; }, 2000);
}

PF.listeners.push(brRender);
Object.assign(PAGE_ACTIONS.click, {
  brMarkRead: () => brMarkRead(),
  brCopy: el => brCopy(el),
  brRestAll: () => { BRIEF.showRest = !BRIEF.showRest; brRender(); },
});
