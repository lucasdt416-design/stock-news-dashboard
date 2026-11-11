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
