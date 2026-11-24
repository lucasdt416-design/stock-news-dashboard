// Run with: node --test tests/node/portfolio_input.test.mjs
// Reading what people type, paste and import on the portfolio page, and what is kept in the browser.
import assert from "node:assert/strict";
import { test } from "node:test";

import { loadPageScript } from "./helpers.mjs";

const P = loadPageScript("portfolio_input.js", "PortfolioInput");
const row = (ticker, fields = {}) => ({ ticker, shares: null, usd: null, paid: null, bought: null, ...fields });

test("tickers are tidied, and anything that isn't one is refused", () => {
  assert.equal(P.normalizeTicker(" nvda "), "NVDA");
  assert.equal(P.normalizeTicker("$AAPL"), "AAPL");
  assert.equal(P.normalizeTicker("brk.b"), "BRK-B");
  assert.equal(P.normalizeTicker("BRK/B"), "BRK-B");
  for (const bad of ["", " ", "10", "TOOLONGX", "A B", "<script>", "NV$DA", "../x", "A--B", null, undefined, {}]) {
    assert.equal(P.normalizeTicker(bad), "", String(bad));
  }
});

test("amounts are read the ways people write them", () => {
  assert.equal(P.parseAmount("2,000"), 2000);
  assert.equal(P.parseAmount("$2k"), 2000);
  assert.equal(P.parseAmount("1.5M"), 1500000);
  assert.equal(P.parseAmount(" 10 "), 10);
  assert.equal(P.parseAmount(".5"), 0.5);
  assert.equal(P.parseAmount("(12)"), -12);
  for (const bad of ["", "abc", "1e5", "10 shares", "--3", "1.2.3"]) assert.ok(Number.isNaN(P.parseAmount(bad)), bad);
});

test("the example from the task reads as three holdings", () => {
  assert.deepEqual(P.parsePaste("NVDA 10, AAPL 5 shares, VOO $2000"), {
    rows: [row("NVDA", { shares: 10 }), row("AAPL", { shares: 5 }), row("VOO", { usd: 2000 })],
    unread: [],
  });
});

test("every way of writing a line in the plan's table", () => {
  const shares = ["NVDA 10", "10 NVDA", "NVDA 10 shares", "NVDA x10", "10 shares of nvda", "NVDA: 10", "nvda\t10"];
  for (const text of shares) assert.deepEqual(P.parsePaste(text).rows, [row("NVDA", { shares: 10 })], text);
  const dollars = ["VOO $2000", "VOO 2,000 USD", "$2k VOO", "VOO $2,000.00", "voo 2000 dollars"];
  for (const text of dollars) assert.deepEqual(P.parsePaste(text).rows, [row("VOO", { usd: 2000 })], text);
  assert.deepEqual(P.parsePaste("AAPL 5 @ 150").rows, [row("AAPL", { shares: 5, paid: 750 })]);
  assert.deepEqual(P.parsePaste("AAPL 5 @ $150.50").rows, [row("AAPL", { shares: 5, paid: 752.5 })]);
  assert.deepEqual(P.parsePaste("BRK.B 2.5").rows, [row("BRK-B", { shares: 2.5 })]);
});

test("lines, semicolons and commas separate holdings, but a comma inside a number doesn't", () => {
  const { rows, unread } = P.parsePaste("NVDA 1,200\nAAPL 5; MSFT 3,VOO $12,500\n\n");
  assert.deepEqual(rows, [row("NVDA", { shares: 1200 }), row("AAPL", { shares: 5 }), row("MSFT", { shares: 3 }), row("VOO", { usd: 12500 })]);
  assert.deepEqual(unread, []);
});

test("what can't be read is kept and explained, never guessed or dropped", () => {
  const { rows, unread } = P.parsePaste("NVDA\n10\nNVDA 10 20\nNVDA AAPL 5\nNVDA 0\nNVDA -5\nhello world\nNVDA 10 $500\nMSFT 4");
  assert.deepEqual(rows, [row("MSFT", { shares: 4 })]);
  assert.deepEqual(unread.map((u) => [u.text, u.reason]), [
    ["NVDA", "no amount"],
    ["10", "no ticker"],
    ["NVDA 10 20", "more than one number"],
    ["NVDA AAPL 5", "more than one ticker"],
    ["NVDA 0", "the number of shares has to be more than zero"],
    ["NVDA -5", '"-5" isn\'t a ticker or a number'],
    ["hello world", "more than one ticker"],
    ["NVDA 10 $500", "both a number of shares and a dollar amount"],
  ]);
});

test("hostile pasted text comes back as plain text in the unread list", () => {
  const { rows, unread } = P.parsePaste('<img src=x onerror=alert(1)> 5\n"><script>x</script>');
  assert.deepEqual(rows, []);
  assert.equal(unread.length, 2);
  for (const u of unread) assert.equal(typeof u.text, "string");
  assert.ok(P.parsePaste("A".repeat(50000) + " 5").unread[0].text.length <= 200);
});

test("CSV cells: quotes, doubled quotes, commas and new lines inside quotes, a byte-order mark, CRLF", () => {
  assert.deepEqual(P.parseCsv('﻿a,"b,c","d ""e"""\r\n1,"two\nlines",3\n', ","), [
    ["a", "b,c", 'd "e"'],
    ["1", "two\nlines", "3"],
  ]);
});

test("a broker export with a preamble, odd column names, cash and a totals row", () => {
  const csv = [
    '"Positions for account XXXX-1234 as of 11/10/2026"',
    "",
    '"Symbol","Description","Quantity","Price","Market Value","Cost Basis"',
    '"NVDA","NVIDIA CORP","10","$173.94","$1,739.40","$1,200.00"',
    '"BRK/B","BERKSHIRE HATHAWAY","2.5","$578.97","$1,447.43","--"',
    '"Cash & Cash Investments","--","--","--","$512.11","--"',
    '"Account Total","--","--","--","$3,698.94","$1,200.00"',
    "",
  ].join("\r\n");
  const { rows, unread, skipped, error } = P.readCsv(csv);
  assert.equal(error, undefined);
  assert.deepEqual(rows, [row("NVDA", { shares: 10, paid: 1200 }), row("BRK-B", { shares: 2.5 })]);
  // Cash and the total aren't holdings: left out and counted, not listed as lines that couldn't be read.
  assert.deepEqual(unread, []);
  assert.equal(skipped, 2);
});

test("other brokers' column names, a per-share cost, semicolons and tabs", () => {
  assert.deepEqual(P.readCsv("Ticker;Shares;Avg Price\nAAPL;4;150.25\n").rows, [row("AAPL", { shares: 4, paid: 601 })]);
  assert.deepEqual(P.readCsv("Instrument\tQty\tAverage Cost\nMSFT\t2\t300\n").rows, [row("MSFT", { shares: 2, paid: 600 })]);
  assert.deepEqual(P.readCsv("Security,Units,Total Cost\nKO,100,5000\n").rows, [row("KO", { shares: 100, paid: 5000 })]);
});

test("a file with values but no share counts gives dollar entries", () => {
  assert.deepEqual(P.readCsv("Symbol,Current Value\nVOO,\"$2,000.00\"\n").rows, [row("VOO", { usd: 2000 })]);
});

test("rows with zero or negative shares are flagged", () => {
  const { rows, unread } = P.readCsv("Symbol,Quantity\nNVDA,0\nAAPL,(5)\nMSFT,3\n");
  assert.deepEqual(rows, [row("MSFT", { shares: 3 })]);
  assert.equal(unread.length, 2);
});

test("a file that isn't holdings, or is too big, is refused with a reason", () => {
  assert.match(P.readCsv("name,email\nx,y\n").error, /Couldn't find a column/);
  assert.match(P.readCsv("Symbol,Quantity\n" + "NVDA,1\n".repeat(2001)).error, /too many lines/);
  assert.match(P.readCsv("x".repeat(1024 * 1024 + 1)).error, /too big/);
});

const SECTORS = new Set(["Technology", "Finance"]);

test("stored holdings are checked field by field", () => {
  const good = { t: "NVDA", sh: 10, paid: 1200, bought: "2023-05", sector: "Technology", usd: null };
  const { holdings, dropped } = P.readStored(JSON.stringify({ v: 1, holdings: [good] }), SECTORS);
  assert.deepEqual(holdings, [good]);
  assert.equal(dropped, 0);
  assert.deepEqual(P.readStored(P.toStored(holdings), SECTORS).holdings, [good]);
});

test("bad stored rows are dropped and counted; bad optional fields are blanked", () => {
  const stored = JSON.stringify({ v: 1, holdings: [
    { t: "NVDA", sh: 10 },
    { t: "nvda", sh: 1 },
    { t: "NVDA", sh: 5 },
    { t: "<img>", sh: 1 },
    { t: "AAPL", sh: -1 },
    { t: "MSFT", sh: "10" },
    { t: "KO", sh: 1e13 },
    { t: "VOO", usd: 2000 },
    { t: "JPM", sh: 2, paid: "x", bought: "2023-13", sector: "<b>", extra: "ignored" },
    null, "text", 7,
  ] });
  const { holdings, dropped } = P.readStored(stored, SECTORS);
  assert.deepEqual(holdings, [
    { t: "NVDA", sh: 10, paid: null, bought: null, sector: null, usd: null },
    { t: "VOO", sh: null, paid: null, bought: null, sector: null, usd: 2000 },
    { t: "JPM", sh: 2, paid: null, bought: null, sector: null, usd: null },
  ]);
  assert.equal(dropped, 9);
});

test("broken or hostile storage reads as empty, and the list is capped", () => {
  for (const text of [null, "", "{", "[]", '"x"', "null", '{"holdings":"x"}', '{"__proto__":{"holdings":[]}}']) {
    assert.deepEqual(P.readStored(text, SECTORS), { holdings: [], dropped: 0 }, String(text));
  }
  const many = [];
  for (let i = 0; i < 300; i += 1) many.push({ t: "A" + String.fromCharCode(65 + (i % 26)) + String.fromCharCode(65 + Math.floor(i / 26)), sh: 1 });
  const { holdings, dropped } = P.readStored(JSON.stringify({ holdings: many }), SECTORS);
  assert.equal(holdings.length, 200);
  assert.equal(dropped, 100);
});

test("adding the same ticker again makes one holding", () => {
  let list = P.addRow([], row("NVDA", { shares: 10, paid: 1000, bought: "2022-01" })).holdings;
  const second = P.addRow(list, row("NVDA", { shares: 5, paid: 800, bought: "2024-06" }));
  assert.equal(second.merged, true);
  assert.deepEqual(second.holdings, [{ t: "NVDA", sh: 15, paid: 1800, bought: "2022-01", sector: null, usd: null }]);
  const refused = P.addRow(second.holdings, row("NVDA", { usd: 500 }));
  assert.equal(refused.added, false);
  assert.deepEqual(refused.holdings, second.holdings);
  list = P.addRow([], row("VOO", { usd: 2000 })).holdings;
  assert.equal(P.addRow(list, row("VOO", { usd: 500 })).holdings[0].usd, 2500);
  assert.deepEqual(P.addRow(list, row("VOO", { shares: 3 })).holdings[0], { t: "VOO", sh: 3, paid: null, bought: null, sector: null, usd: null });
});

test("dollars become shares at a real price, and only then", () => {
  assert.equal(P.sharesFromDollars(2000, 695.26), 2.876622);
  assert.equal(P.sharesFromDollars(2000, 0), null);
  assert.equal(P.sharesFromDollars(2000, undefined), null);
  assert.equal(P.sharesFromDollars(-1, 10), null);
});

// Shaped like the real exports. Each broker adds rows that aren't holdings, which must not become holdings.
test("a Schwab positions file is read, brackets in its headers and all", () => {
  const csv = `"Positions for account Individual ...123 as of 09:15 AM ET, 2026/11/23","",""
"Symbol","Description","Qty (Quantity)","Price","Mkt Val (Market Value)","Cost Basis","Security Type"
"MSFT","MICROSOFT CORP","12","$420.00","$5,040.00","$3,600.00","Equity"
"Cash & Cash Investments","--","--","--","$1,200.00","--","Cash and Money Market"
"Account Total","--","--","--","$6,240.00","$3,600.00","--"`;
  const out = P.readCsv(csv);
  assert.deepEqual(out.rows, [row("MSFT", { shares: 12, paid: 3600 })]);
  assert.equal(out.unread.length, 0);
  assert.equal(out.skipped, 2);
});

test("cash, pending money, totals and footnotes are left out quietly", () => {
  const fidelity = `Account Number,Account Name,Symbol,Description,Quantity,Last Price,Current Value,Cost Basis Total,Average Cost Basis
Z1,Individual,SPAXX**,HELD IN MONEY MARKET,,,$1520.33,,
Z1,Individual,AAPL,APPLE INC,10,$230.10,$2301.00,$1500.00,$150.00
Z1,Individual,Pending Activity,,,,$-200.00,,

"The data and information in this spreadsheet is provided to you solely for your use"
"Date downloaded 11/23/2026 9:15 AM ET"`;
  const f = P.readCsv(fidelity);
  assert.deepEqual(f.rows, [row("AAPL", { shares: 10, paid: 1500 })]);
  assert.equal(f.unread.length, 0);
  const etrade = `Symbol,Last Price $,Qty #,Price Paid $,Value $
AMZN,210.5,20,150,4210
CASH,,,,1000.00
TOTAL,,,,5210`;
  assert.deepEqual(P.readCsv(etrade).rows, [row("AMZN", { shares: 20, paid: 3000 })]);
});

test("a second table under the holdings ends them", () => {
  const vanguard = `Account Number,Investment Name,Symbol,Shares,Share Price,Total Value,
1,VANGUARD S&P 500 ETF,VOO,8.25,540.1,4455.83,

Account Number,Trade Date,Settlement Date,Transaction Type,Transaction Description,Investment Name,Symbol,Shares,Share Price,Principal Amount,
1,2026-11-01,2026-11-03,Buy,Buy,NVIDIA CORP,NVDA,5,170,-850,`;
  const out = P.readCsv(vanguard);
  assert.deepEqual(out.rows.map(r => r.ticker), ["VOO"]);
  assert.equal(out.unread.length, 0);
});

test("a file of trades is added up: buys minus sells, with the cost that's left", () => {
  const robinhood = `"Activity Date","Process Date","Settle Date","Instrument","Description","Trans Code","Quantity","Price","Amount"
"11/01/2026","11/01/2026","11/03/2026","AAPL","Apple","Buy","10","$200.00","($2,000.00)"
"11/10/2026","11/10/2026","11/12/2026","AAPL","Apple","Sell","4","$220.00","$880.00"
"11/12/2026","11/12/2026","11/12/2026","AAPL","Apple","CDIV","","","$1.20"
"11/13/2026","11/13/2026","11/15/2026","TSLA","Tesla","Buy","2","$300.00","($600.00)"
"11/14/2026","11/14/2026","11/16/2026","TSLA","Tesla","Sell","2","$310.00","$620.00"
"11/15/2026","11/15/2026","11/15/2026","","ACH Deposit","ACH","","","$500.00"`;
  const out = P.readCsv(robinhood);
  assert.equal(out.trades, true);
  assert.deepEqual(out.rows, [row("AAPL", { shares: 6, paid: 1200 })]);
  assert.equal(out.closed, 1, "TSLA was sold off completely");
  assert.equal(out.skipped, 2, "the dividend and the deposit");
});
