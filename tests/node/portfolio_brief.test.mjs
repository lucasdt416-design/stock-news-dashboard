// Run with: node --test tests/node/portfolio_brief.test.mjs
// The Briefing: matching stories, big days and dates to what someone holds, and ranking by their money.
import assert from "node:assert/strict";
import { test } from "node:test";

import { loadPageScript } from "./helpers.mjs";

const B = loadPageScript("portfolio_brief_logic.js", "PortfolioBrief");
const TODAY = "2026-11-23";
const story = (t, d, s, extra = {}) => ({ t, d, s, k: "news", h: `${t} story ${d}`, u: "https://example.com", rel: [], why: {}, ...extra });

const DATA = {
  stories: [
    story("NVDA", "2026-11-20", 8, { k: "results" }),
    story("NVDA", "2026-11-21", 4),
    story("KO", "2026-11-22", 9),
    story("TSM", "2026-11-22", 9, { rel: ["NVDA"], why: { NVDA: "NVIDIA is its largest customer." } }),
    story("NVDA", "2026-11-01", 9),            // before the last visit
    story("XOM", "2026-11-22", 9),             // not held
    story("NVDA", "2026-11-30", 9),            // dated after today: ignored
  ],
  events: [
    { t: "NVDA", d: "2026-11-26", k: "results", h: "NVIDIA results" },
    { t: "KO", d: "2027-01-02", k: "dividend", h: "Coca-Cola dividend" },
    { t: "XOM", d: "2026-11-25", k: "results", h: "Exxon results" },
  ],
  days: [{ t: "NVDA", d: "2026-11-19", m: -6.2, mk: 0.3, v: "own" }, { t: "JPM", d: "2026-11-02", m: 3, mk: 0, v: "own" }],
};
const HOLDINGS = [
  { t: "NVDA", company: "NVDA", weight: 0.6, fund: false },
  { t: "KO", company: "KO", weight: 0.1, fund: false },
  { t: "JPM", company: "JPM", weight: 0.2, fund: false },
  { t: "VOO", company: "", weight: 0.05, fund: true },
  { t: "RDDT", company: "", weight: 0.05, fund: false },
];

test("only stories about what's held, or naming it, and only new ones count as new", () => {
  const b = B.build(DATA, HOLDINGS, "2026-11-15", TODAY);
  const all = [...b.first, ...b.rest];
  assert.equal(b.newCount, 4);
  assert.ok(all.every(i => ["NVDA", "KO"].includes(i.company)));
  assert.ok(!all.some(i => i.story.t === "XOM"));
  assert.ok(!all.some(i => i.story.d > TODAY));
  const related = all.find(i => i.story.t === "TSM");
  assert.equal(related.how, "related");
  assert.equal(related.why, "NVIDIA is its largest customer.");
});

test("read-first is one per company, the bigger holding's results first", () => {
  const b = B.build(DATA, HOLDINGS, "2026-11-15", TODAY);
  assert.deepEqual(b.first.map(i => i.company), ["NVDA", "KO"]);
  assert.equal(b.first[0].story.k, "results");
});

test("big days, what's due and what's quiet", () => {
  const b = B.build(DATA, HOLDINGS, "2026-11-15", TODAY);
  assert.deepEqual(b.moves.map(m => m.t), ["NVDA"], "JPM's day was before the last visit");
  assert.deepEqual(b.soonResults.map(e => e.t), ["NVDA"]);
  assert.equal(b.soonShare, 0.6);
  assert.deepEqual(b.quiet, ["JPM"]);
  assert.deepEqual(b.funds, ["VOO"]);
  assert.deepEqual(b.uncovered, ["RDDT"]);
});

test("with no visit on record, new means the past week", () => {
  const b = B.build(DATA, HOLDINGS, "", TODAY);
  assert.equal(b.since, "");
  assert.equal(b.from, "2026-11-16");
  const late = B.build(DATA, HOLDINGS, "2026-11-22", TODAY);
  assert.equal(late.newCount, 0, "nothing after the 22nd");
});

test("the text version names companies and links, never amounts", () => {
  const b = B.build(DATA, HOLDINGS, "2026-11-15", TODAY);
  const text = B.asText(b, { NVDA: "NVIDIA", KO: "Coca-Cola", JPM: "JPMorgan" }, "November 23, 2026");
  assert.match(text, /Read first\n- NVIDIA: NVDA story 2026-11-20/);
  assert.match(text, /Nothing new: JPMorgan/);
  assert.doesNotMatch(text, /%\s*of your money|\$/);
});

test("bad data gives an empty briefing, not an error", () => {
  for (const bad of [null, {}, { stories: "x", events: 3, days: null }]) {
    const b = B.build(bad, HOLDINGS, "nonsense", TODAY);
    assert.equal(b.newCount, 0);
    assert.equal(b.first.length, 0);
  }
});
