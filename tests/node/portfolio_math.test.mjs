// Run with: node --test tests/node/portfolio_math.test.mjs
// The portfolio page's arithmetic, against numbers worked out by hand (the working is in the comments).
import assert from "node:assert/strict";
import { test } from "node:test";

import { loadPageScript } from "./helpers.mjs";

const M = loadPageScript("portfolio_math.js", "PortfolioMath");
const near = (actual, expected, label) => assert.ok(Math.abs(actual - expected) < 1e-9, `${label || ""} ${actual} vs ${expected}`);
const stock = (t, value, sector, extra = {}) => ({ t, company: t, value, fund: false, sector, paid: null, bought: null, ...extra });
const fund = (t, value) => ({ t, company: "", value, fund: true, sector: "Funds", paid: null, bought: null });

test("sector shares add up to the whole, with funds and unknowns as their own groups", () => {
  // 500 + 300 tech, 200 finance, 600 fund, 400 unknown = 2000
  const rows = [stock("A", 500, "Technology"), stock("B", 300, "Technology"), stock("C", 200, "Finance"),
                fund("VOO", 600), stock("D", 400, "")];
  const out = M.sectors(rows);
  assert.deepEqual(out.map((s) => [s.name, s.tickers]), [
    ["Technology", ["A", "B"]], ["Finance", ["C"]], ["Funds", ["VOO"]], ["Sector unknown", ["D"]],
  ]);
  near(out[0].weight, 0.4);   // 800 / 2000
  near(out[1].weight, 0.1);   // 200 / 2000
  near(out[2].weight, 0.3);   // 600 / 2000
  near(out[3].weight, 0.2);   // 400 / 2000
  near(out.reduce((a, s) => a + s.weight, 0), 1);
  assert.deepEqual(M.sectors([]), []);
});

test("effective number of holdings: 50/30/20 behaves like 2.63 equal ones", () => {
  // 1 / (0.5^2 + 0.3^2 + 0.2^2) = 1 / (0.25 + 0.09 + 0.04) = 1 / 0.38 = 2.6315789...
  const c = M.concentration([stock("A", 500, "Technology"), stock("B", 300, "Technology"), stock("C", 200, "Finance")]);
  near(c.effective, 1 / 0.38);
  assert.equal(c.stocks, 3);
  assert.deepEqual(c.largest, { name: "A", weight: 0.5 });
  assert.deepEqual(c.topThree.names, ["A", "B", "C"]);
  near(c.topThree.weight, 1);
  assert.equal(c.largestSector.name, "Technology");
  near(c.largestSector.weight, 0.8);
  assert.equal(c.fundWeight, 0);
});

test("equal holdings count as exactly that many, and one holding as one", () => {
  near(M.concentration([1, 2, 3, 4].map((i) => stock("S" + i, 250, "Energy"))).effective, 4);
  const one = M.concentration([stock("A", 10, "Energy")]);
  near(one.effective, 1);
  near(one.topThree.weight, 1);
  // 12 holdings: one of 45%, eleven of 5% -> 1 / (0.2025 + 11 * 0.0025) = 1 / 0.23 = 4.3478...
  const lumpy = [stock("BIG", 45, "Technology")].concat([...Array(11)].map((_, i) => stock("S" + i, 5, "Finance")));
  near(M.concentration(lumpy).effective, 1 / 0.23);
});

test("funds are left out of concentration and their share is reported beside it", () => {
  // Stocks 600 + 400; fund 1000. Among stocks: 60% and 40% -> 1 / (0.36 + 0.16) = 1.923...
  const c = M.concentration([stock("A", 600, "Technology"), stock("B", 400, "Finance"), fund("VOO", 1000)]);
  near(c.largest.weight, 0.6);
  near(c.effective, 1 / 0.52);
  near(c.fundWeight, 0.5);
  assert.deepEqual(c.fundTickers, ["VOO"]);
});

test("a portfolio of only funds has no concentration numbers", () => {
  const c = M.concentration([fund("VOO", 700), fund("SPY", 300)]);
  assert.equal(c.stocks, 0);
  assert.equal(c.largest, undefined);
  near(c.fundWeight, 1);
});

test("two share classes of one company are one position", () => {
  const rows = [stock("GOOGL", 300, "Technology"), { ...stock("GOOG", 200, "Technology"), company: "GOOGL" }, stock("KO", 500, "Consumer Staples")];
  const c = M.concentration(rows);
  assert.equal(c.stocks, 2);
  // 500 and 500 -> two equal positions
  near(c.effective, 2);
  assert.ok(["GOOGL + GOOG", "KO"].includes(c.largest.name));
});

test("the month used is the one asked for, or the nearest earlier one that has a price", () => {
  const months = [["2020-01", 10], ["2020-02", 11], ["2020-04", 13]];
  assert.deepEqual(M.monthAtOrBefore(months, "2020-02"), ["2020-02", 11]);
  assert.deepEqual(M.monthAtOrBefore(months, "2020-03"), ["2020-02", 11]);   // March has no price: not made up
  assert.deepEqual(M.monthAtOrBefore(months, "2025-01"), ["2020-04", 13]);
  assert.equal(M.monthAtOrBefore(months, "2019-12"), null);
  assert.equal(M.monthAtOrBefore([], "2020-01"), null);
});

const SPY = { months: [["2020-01", 300], ["2021-06", 400], ["2023-05", 420]], price: 600 };

test("gain is value against cost, over the holdings that have a cost", () => {
  const rows = [stock("A", 1500, "Technology", { paid: 1000 }), stock("B", 800, "Finance", { paid: 1000 }), stock("C", 999, "Energy")];
  const g = M.gains(rows, null);
  assert.equal(g.count, 2);
  assert.equal(g.without, 1);
  assert.equal(g.paid, 2000);
  assert.equal(g.value, 2300);
  assert.equal(g.gain, 300);
  near(g.pct, 0.15);
  assert.equal(g.spy, null);
  assert.equal(M.gains([stock("C", 999, "Energy")], SPY), null);
});

test("the S&P 500 comparison needs a buy month, and uses that month's real close", () => {
  // A: paid 1000 in 2020-01 (fund at 300, now 600) -> same money = 1000 * 600 / 300 = 2000
  // B: paid 1000 in 2021-06 (fund at 400)          -> same money = 1000 * 600 / 400 = 1500
  // C: paid 500, no buy month -> gain counted, not compared
  const rows = [
    stock("A", 3000, "Technology", { paid: 1000, bought: "2020-01" }),
    stock("B", 900, "Finance", { paid: 1000, bought: "2021-06" }),
    stock("C", 600, "Energy", { paid: 500 }),
  ];
  const g = M.gains(rows, SPY);
  assert.equal(g.paid, 2500);
  assert.equal(g.value, 4500);
  assert.equal(g.spy.rows.length, 2);
  assert.equal(g.spy.skipped, 1);
  assert.equal(g.spy.paid, 2000);
  assert.equal(g.spy.value, 3900);
  assert.equal(g.spy.same, 3500);
  near(g.spy.pct, 0.95);      // (3900 - 2000) / 2000
  near(g.spy.spyPct, 0.75);   // (3500 - 2000) / 2000
});

test("no comparison for a buy month before the fund existed or one it has no price for", () => {
  const rows = [stock("A", 3000, "Technology", { paid: 1000, bought: "1985-03" }), stock("B", 900, "Finance", { paid: 1000, bought: "2020-02" })];
  const g = M.gains(rows, SPY);
  assert.equal(g.count, 2);
  assert.equal(g.spy, null);
});

const DETAILS = {
  NVDA: { th: ["datacenter_capex", "export_controls_china"], ec: ["interest_rates"], cu: ["MSFT", "META", "Super Micro"], su: ["TSMC"], co: ["AMD", "INTC"] },
  AMD: { th: ["datacenter_capex", "pc_market_demand"], ec: ["interest_rates"], cu: ["MSFT", "Super Micro"], su: ["TSMC"], co: ["NVDA", "INTC"] },
  INTC: { th: ["pc_market_demand"], ec: [], cu: [], su: [], co: ["AMD"] },
  MSFT: { th: [], ec: ["interest_rates"], cu: [], su: ["NVDA"], co: ["GOOGL"] },
  KO: {},
};

test("shared bets: each line names its holdings and sums their shares once", () => {
  // NVDA 400, AMD 200, MSFT 300, KO 100 = 1000
  const rows = [stock("NVDA", 400, "Technology"), stock("AMD", 200, "Technology"), stock("MSFT", 300, "Technology"), stock("KO", 100, "Consumer Staples")];
  const { lines, covered, outside } = M.overlap(rows, DETAILS);
  assert.equal(covered, 4);
  assert.deepEqual(outside, []);
  const find = (kind, subject) => lines.find((l) => l.kind === kind && l.subject === subject);

  const theme = find("theme", "datacenter_capex");
  assert.deepEqual(theme.tickers, ["NVDA", "AMD"]);
  near(theme.weight, 0.6);                               // (400 + 200) / 1000
  assert.equal(find("theme", "export_controls_china"), undefined, "a theme only one holding has isn't a shared bet");
  assert.equal(find("theme", "pc_market_demand"), undefined, "INTC isn't held");

  const rates = find("economy", "interest_rates");
  assert.deepEqual(rates.tickers, ["NVDA", "MSFT", "AMD"]);
  near(rates.weight, 0.9);                               // (400 + 300 + 200) / 1000

  // NVDA lists MSFT as a customer and MSFT lists NVDA as a supplier: one relationship, counted once.
  const nvda = find("customers", "NVDA");
  assert.deepEqual(nvda.others, ["MSFT"]);
  near(nvda.weight, 0.7);                                // NVDA + MSFT
  const amd = find("customers", "AMD");
  assert.deepEqual(amd.others, ["MSFT"]);
  near(amd.weight, 0.5);                                 // AMD + MSFT

  // Named by two holdings, whether held (MSFT) or not (Super Micro, TSMC).
  near(find("sameCustomer", "MSFT").weight, 0.6);
  assert.deepEqual(find("sameCustomer", "Super Micro").tickers, ["NVDA", "AMD"]);
  assert.deepEqual(find("sameSupplier", "TSMC").tickers, ["NVDA", "AMD"]);
  assert.equal(find("sameCustomer", "META"), undefined, "only NVDA names META");

  const rivals = lines.filter((l) => l.kind === "competitors");
  assert.equal(rivals.length, 1, "NVDA with AMD, and AMD with NVDA, is one line");
  assert.deepEqual(rivals[0].tickers, ["NVDA", "AMD"]);
  near(rivals[0].weight, 0.6);

  for (const l of lines) assert.ok(l.weight > 0 && l.weight <= 1 + 1e-12 && l.tickers.length >= 2, l.kind);
  assert.deepEqual(lines.map((l) => l.weight), [...lines.map((l) => l.weight)].sort((a, b) => b - a), "largest first");
});

test("shared bets say what they couldn't see: funds and companies StockPulse doesn't follow", () => {
  // NVDA 500, RDDT 300 (not followed), VOO 200 (fund)
  const rows = [stock("NVDA", 500, "Technology"), { ...stock("RDDT", 300, ""), company: "" }, fund("VOO", 200)];
  const out = M.overlap(rows, DETAILS);
  assert.deepEqual(out.lines, []);
  assert.equal(out.covered, 1);
  assert.deepEqual(out.outside, ["RDDT"]);
  near(out.outsideWeight, 0.3);
  assert.deepEqual(M.overlap([], DETAILS), { lines: [], covered: 0, outside: [], outsideWeight: 0 });
});

test("a line's percentage is of the whole portfolio, funds included", () => {
  // NVDA 300, AMD 200, VOO 500 -> the datacenter line is 50%, not 100%
  const out = M.overlap([stock("NVDA", 300, "Technology"), stock("AMD", 200, "Technology"), fund("VOO", 500)], DETAILS);
  near(out.lines.find((l) => l.kind === "theme").weight, 0.5);
});

// ---- "What if I'd invested" ----------------------------------------------------------------

test("months are counted the way a calendar counts them", () => {
  assert.equal(M.addMonths("2021-11", -1), "2021-10");
  assert.equal(M.addMonths("2021-01", -1), "2020-12");
  assert.equal(M.addMonths("2020-12", 1), "2021-01");
  assert.equal(M.addMonths("2026-11", -61), "2021-10");
  assert.equal(M.monthsApart("2021-10", "2026-10"), 60);
  // "5 years ago" from 11 Nov 2026 is 11 Nov 2021; the last finished month on or before it is October 2021.
  assert.equal(M.monthYearsAgo("2026-11-11", 5), "2021-10");
  assert.equal(M.monthYearsAgo("2026-01-05", 1), "2024-12");
  // 31 Oct 2021 to 31 Oct 2026 is 1826 days = 4.99932 years of 365.25 days.
  near(M.yearsSince("2021-10", "2026-10-31"), 1826 / 365.25);
  near(M.yearsSince("2024-02", "2024-03-01"), 1 / 365.25);   // a leap-year February ends on the 29th
});

const H = { months: [["2020-12", 50], ["2021-01", 100], ["2021-02", 110], ["2021-03", 121]], price: 121, date: "2021-03-31" };

test("a lump sum: value is the amount times the price now over the price then", () => {
  // $1,000 at 100 buys 10 shares; at 121 they're worth $1,210: +21%.
  const r = M.whatIf(H, 1000, "2021-01", 0);
  assert.equal(r.from, "2021-01");
  near(r.value, 1210);
  assert.equal(r.putIn, 1000);
  near(r.pct, 0.21);
  assert.equal(r.contributions, 0);
  assert.equal(r.perYear, null, "under a year, no yearly rate is quoted");
  assert.deepEqual(r.series.map(([m, v]) => [m, Math.round(v)]), [["2021-01", 1000], ["2021-02", 1100], ["2021-03", 1210], ["2021-03-31", 1210]]);
});

test("the plan's worked example with a monthly amount", () => {
  // $1,000 at 100, then $100 at 110 and $100 at 121; latest price 121.
  // shares = 10 + 100/110 + 100/121 = 10 + 0.909091 + 0.826446 = 11.735537
  // value  = 11.735537 x 121 = 1,420.00;  put in 1,200;  gain 220 = 18.33%
  const r = M.whatIf(H, 1000, "2021-01", 100);
  near(r.value, 1420);
  assert.equal(r.putIn, 1200);
  assert.equal(r.contributions, 2);
  near(r.gain, 220);
  near(r.pct, 220 / 1200);
  // After February: (10 + 0.909091) x 110 = 1,200.00
  near(r.series[1][1], 1200);
});

test("the yearly rate of a lump sum is the compound rate, checked by compounding it back", () => {
  // 100 -> 200 over exactly 4 years (31 Dec 2016 to 31 Dec 2020 = 1461 days): 2^(1/4) - 1 = 18.92%
  const h = { months: [["2016-12", 100], ["2020-11", 190]], price: 200, date: "2020-12-31" };
  const r = M.whatIf(h, 5000, "2016-12", 0);
  near(r.years, 4);
  near(r.perYear, Math.pow(2, 0.25) - 1);
  near(5000 * Math.pow(1 + r.perYear, 4), r.value);
});

test("the yearly rate with contributions is the rate that grows each payment to today's value", () => {
  // $1,200 a year ago and $1,200 six months ago, worth $2,640 now.
  // At 1% a month: 1200 x 1.01^12 + 1200 x 1.01^6 = 1352.19 + 1273.82 = 2626.01 (a little low)
  // The answer must grow both payments to exactly 2,640.
  const rate = M.yearlyRate([{ months: 12, amount: 1200 }, { months: 6, amount: 1200 }], 2640);
  const monthly = Math.pow(1 + rate, 1 / 12) - 1;
  near(1200 * Math.pow(1 + monthly, 12) + 1200 * Math.pow(1 + monthly, 6), 2640);
  assert.ok(monthly > 0.01 && monthly < 0.011);
  // One payment a year ago that doubled is +100% a year; one that halved is -50%.
  near(M.yearlyRate([{ months: 12, amount: 100 }], 200), 1);
  near(M.yearlyRate([{ months: 12, amount: 100 }], 50), -0.5);
  assert.equal(M.yearlyRate([{ months: 12, amount: 100 }], 0), null);
});

test("a start before the first month isn't guessed: it says so and offers the first month", () => {
  assert.deepEqual(M.whatIf(H, 1000, "2019-06", 0), { error: "before", first: "2020-12" });
  assert.deepEqual(M.whatIf({ months: [], price: 5, date: "2021-03-31" }, 1000, "2019-06", 0), { error: "noHistory" });
});

test("a month with no price uses the nearest earlier real month and says which", () => {
  const gap = { months: [["2021-01", 100], ["2021-03", 121]], price: 121, date: "2021-03-31" };
  const r = M.whatIf(gap, 1000, "2021-02", 0);
  assert.equal(r.asked, "2021-02");
  assert.equal(r.from, "2021-01");
  near(r.value, 1210);
  assert.deepEqual(r.series.map(([m]) => m), ["2021-01", "2021-03", "2021-03-31"], "February isn't drawn");
});

test("a whole portfolio is split by today's weights, each part bought the same month", () => {
  // 60% in A (100 -> 150, +50%), 40% in B (10 -> 30, +200%)
  const a = { t: "A", weight: 0.6, months: [["2021-01", 100], ["2021-02", 120]], price: 150, date: "2021-03-10" };
  const b = { t: "B", weight: 0.4, months: [["2021-01", 10], ["2021-02", 20]], price: 30, date: "2021-03-10" };
  const r = M.whatIfPortfolio([a, b], 1000, "2021-01");
  // A: 600 x 150/100 = 900.  B: 400 x 30/10 = 1,200.  Together 2,100: +110%.
  near(r.value, 2100);
  near(r.pct, 1.1);
  assert.deepEqual(r.leftOut, []);
  assert.deepEqual(r.included.map((p) => [p.t, p.share, Math.round(p.value)]), [["A", 0.6, 900], ["B", 0.4, 1200]]);
  // February: 600 x 1.2 + 400 x 2 = 720 + 800 = 1,520
  assert.deepEqual(r.series.map(([m, v]) => [m, Math.round(v)]), [["2021-01", 1000], ["2021-02", 1520], ["2021-03-10", 2100]]);
});

test("a holding that wasn't trading yet is left out, named, and the rest rescaled to 100%", () => {
  const a = { t: "A", weight: 0.3, months: [["2021-01", 100], ["2021-02", 120]], price: 150, date: "2021-03-10" };
  const young = { t: "NEW", weight: 0.7, months: [["2021-02", 10]], price: 30, date: "2021-03-10" };
  const r = M.whatIfPortfolio([a, young], 1000, "2021-01");
  assert.deepEqual(r.leftOut, ["NEW"]);
  assert.deepEqual(r.included.map((p) => [p.t, p.share]), [["A", 1]]);
  near(r.value, 1500);   // all 1,000 in A: 1000 x 150/100
  assert.deepEqual(M.whatIfPortfolio([young], 1000, "2021-01"), { error: "none", leftOut: ["NEW"] });
});
