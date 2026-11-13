// Run with: node --test tests/node/history.test.mjs
import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { after, beforeEach, test } from "node:test";
import { fileURLToPath, pathToFileURL } from "node:url";

import { copyFunctions } from "./helpers.mjs";

const SECRET = "not-a-real-key-0123456789";
const ORIGIN = "https://stocks.example";
const here = dirname(fileURLToPath(import.meta.url));
const tempDir = mkdtempSync(join(tmpdir(), "history-test-"));
const realFetch = globalThis.fetch;
let loadCount = 0;
let upstreamCalls = [];
let upstreamHandler = null;

after(() => {
  rmSync(tempDir, { recursive: true, force: true });
  globalThis.fetch = realFetch;
});

/** A fresh copy each time, so the module's in-memory limits and cache start empty. */
async function loadModule() {
  loadCount += 1;
  return import(pathToFileURL(join(copyFunctions(tempDir, `copy-${loadCount}`), "api", "history.js")).href);
}

/** Midnight in New York on that day, as Yahoo stamps a monthly bar (05:00 UTC in winter). */
function stamp(day, hourUtc = 5) {
  return Date.UTC(Number(day.slice(0, 4)), Number(day.slice(5, 7)) - 1, Number(day.slice(8, 10)), hourUtc) / 1000;
}

const BARS = [["2025-12-01", 10], ["2026-01-01", 11], ["2026-02-01", 12], ["2026-03-01", 12.4]];

function chart(bars = BARS, { price = 12.5, day = "2026-03-10", kind = "EQUITY", currency = "USD" } = {}) {
  return {
    meta: { currency, instrumentType: kind, longName: "Test Co", gmtoffset: -18000, dataGranularity: "1mo",
            regularMarketPrice: price, regularMarketTime: stamp(day, 21) },
    timestamp: bars.map(([d]) => stamp(d)),
    indicators: { quote: [{ close: bars.map(([, v]) => v) }], adjclose: [{ adjclose: bars.map(([, v]) => v) }] },
  };
}

function yahoo(body) {
  return { chart: { result: [body], error: null } };
}

function goodUpstream(url) {
  if (url.includes("finance.yahoo.com")) return yahoo(chart());
  if (url.includes("finnhub.io")) return { finnhubIndustry: "Semiconductors", name: "Test Co" };
  return {};
}

beforeEach(() => {
  upstreamCalls = [];
  upstreamHandler = goodUpstream;
  globalThis.fetch = async (url, options) => {
    upstreamCalls.push({ url: String(url), options });
    const body = upstreamHandler(String(url));
    if (body instanceof Response) return body;
    if (body instanceof Error) throw body;
    return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
  };
});

function context(path, { method = "GET", headers = {}, env = { FINNHUB_API_KEY: SECRET } } = {}) {
  return { request: new Request(`${ORIGIN}${path}`, { method, headers }), env };
}

async function assertNoLeak(res) {
  const text = await res.clone().text();
  assert.ok(!text.includes(SECRET), "response contains the API key");
  for (const word of ["yahoo", "finnhub", "FINNHUB_API_KEY", "query2"]) {
    assert.ok(!text.toLowerCase().includes(word.toLowerCase()), `response names ${word}`);
  }
  assert.ok(!/\bat .+:\d+:\d+/.test(text), "response contains a stack trace");
}

test("a ticker returns finished months, the latest price and its sector", async () => {
  const { onRequestGet } = await loadModule();
  const res = await onRequestGet(context("/api/history?ticker=test"));
  assert.equal(res.status, 200);
  assert.equal(res.headers.get("Content-Type"), "application/json; charset=utf-8");
  const body = await res.json();
  assert.deepEqual(
    { ...body, fetched: "x" },
    {
      found: true, symbol: "TEST", name: "Test Co", kind: "stock", currency: "USD", first_month: "2025-12",
      months: [["2025-12", 10], ["2026-01", 11], ["2026-02", 12]],
      price: { value: 12.5, date: "2026-03-10" }, fetched: "x", sector: "Technology", industry: "Semiconductors",
    }
  );
  assert.match(body.fetched, /^\d{4}-\d{2}-\d{2}$/);
});

test("the month in progress and Yahoo's extra live point are never months", async () => {
  const { parseMonthlyHistory } = await loadModule();
  const body = chart();
  body.timestamp.push(body.meta.regularMarketTime);
  body.indicators.adjclose[0].adjclose.push(12.5);
  assert.deepEqual(parseMonthlyHistory("T", body).months.map(([m]) => m), ["2025-12", "2026-01", "2026-02"]);
});

test("summer months, stamped an hour earlier, stay in their own month", async () => {
  const { parseMonthlyHistory } = await loadModule();
  const body = chart([["2025-07-01", 9], ["2025-08-01", 9.5], ["2026-03-01", 12.4]]);
  body.timestamp[0] -= 3600;
  body.timestamp[1] -= 3600;
  assert.deepEqual(parseMonthlyHistory("T", body).months, [["2025-07", 9], ["2025-08", 9.5]]);
});

test("a month with no value is left out, and values keep six significant figures", async () => {
  const { parseMonthlyHistory } = await loadModule();
  const body = chart([["2025-12-01", 0.041804272681474686], ["2026-01-01", null], ["2026-02-01", 12], ["2026-03-01", 12.4]]);
  assert.deepEqual(parseMonthlyHistory("T", body).months, [["2025-12", 0.0418043], ["2026-02", 12]]);
});

test("anything odd is refused rather than guessed", async () => {
  const { parseMonthlyHistory } = await loadModule();
  const odd = [
    chart(BARS, { currency: "GBp" }),
    chart(BARS, { kind: "CRYPTOCURRENCY" }),
    chart(BARS, { price: 0 }),
    chart(BARS, { price: null }),
    chart([["2026-01-01", 11], ["2025-12-01", 10], ["2026-03-01", 12.4]]),
    chart([["2025-12-01", -1], ["2026-03-01", 12.4]]),
    { meta: {} },
    {},
    null,
  ];
  for (const body of odd) assert.equal(parseMonthlyHistory("T", body), null);
});

test("weekly prices passed off as monthly are refused", async () => {
  const { parseMonthlyHistory } = await loadModule();
  const body = chart();
  body.meta.dataGranularity = "1wk";
  assert.equal(parseMonthlyHistory("T", body), null);
});

test("a fund is marked as one and its sector is not asked for", async () => {
  const { onRequestGet } = await loadModule();
  upstreamHandler = (url) => (url.includes("yahoo") ? yahoo(chart(BARS, { kind: "ETF" })) : goodUpstream(url));
  const body = await (await onRequestGet(context("/api/history?ticker=VOO"))).json();
  assert.equal(body.kind, "fund");
  assert.equal(body.sector, null);
  assert.equal(upstreamCalls.filter((c) => c.url.includes("finnhub")).length, 0);
});

test("it works with no key: prices come back and the sector is simply not known", async () => {
  const { onRequestGet } = await loadModule();
  const res = await onRequestGet(context("/api/history?ticker=TEST", { env: {} }));
  assert.equal(res.status, 200);
  await assertNoLeak(res);
  const body = await res.json();
  assert.equal(body.months.length, 3);
  assert.equal(body.sector, null);
  assert.equal(body.industry, null);
  assert.equal(upstreamCalls.length, 1);
});

test("an industry that isn't in the table is not guessed", async () => {
  const { onRequestGet, sectorForIndustry } = await loadModule();
  upstreamHandler = (url) => (url.includes("finnhub") ? { finnhubIndustry: "Something New" } : goodUpstream(url));
  const body = await (await onRequestGet(context("/api/history?ticker=TEST"))).json();
  assert.equal(body.sector, null);
  assert.equal(body.industry, "Something New");
  assert.equal(sectorForIndustry("constructor"), null);
  assert.equal(sectorForIndustry("N/A"), null);
  // Finnhub files Meta and Disney alike under "Media"; the site puts them in different sectors.
  assert.equal(sectorForIndustry("Media"), null);
  assert.equal(sectorForIndustry("Aerospace & Defense"), "Aerospace");
});

test("a failed sector lookup still returns prices, cached for less time", async () => {
  const { onRequestGet } = await loadModule();
  upstreamHandler = (url) => (url.includes("finnhub") ? new Response("no", { status: 500 }) : goodUpstream(url));
  const res = await onRequestGet(context("/api/history?ticker=TEST"));
  assert.equal(res.status, 200);
  assert.equal((await res.json()).sector, null);
  assert.equal(res.headers.get("Cache-Control"), "public, max-age=3600");
});

test("share classes are written the way each provider expects, and the key is only in a header", async () => {
  const { onRequestGet } = await loadModule();
  const body = await (await onRequestGet(context("/api/history?ticker=brk.b"))).json();
  assert.equal(body.symbol, "BRK-B");
  const [prices, profile] = upstreamCalls;
  // An explicit start and end, never range=max, which Yahoo answers in weeks for newer companies.
  assert.match(prices.url, /\/chart\/BRK-B\?period1=0&period2=\d{10}&interval=1mo&/);
  assert.ok(profile.url.endsWith("symbol=BRK.B"));
  assert.equal(profile.options.headers["X-Finnhub-Token"], SECRET);
  for (const call of upstreamCalls) assert.ok(!call.url.includes(SECRET));
  assert.equal(prices.options.headers["X-Finnhub-Token"], undefined);
});

test("only GET and OPTIONS are accepted", async () => {
  const { onRequest } = await loadModule();
  for (const method of ["POST", "PUT", "DELETE", "PATCH"]) {
    const res = await onRequest(context("/api/history?ticker=TEST", { method }));
    assert.equal(res.status, 405);
    assert.equal(res.headers.get("Allow"), "GET, OPTIONS");
  }
  assert.equal((await onRequest(context("/api/history", { method: "OPTIONS" }))).status, 204);
  assert.equal(upstreamCalls.length, 0);
});

test("hostile, missing or name-like input is rejected before any upstream call", async () => {
  const { onRequestGet } = await loadModule();
  const bad = ["", "?ticker=", "?ticker=" + "A".repeat(11), "?ticker=<script>", "?ticker=../etc", "?ticker=AB%20CD",
               "?ticker=Netflix%20Inc", "?ticker=A%0AB", "?q=NVDA", "?ticker=%27%20OR%201=1"];
  for (const query of bad) {
    const res = await onRequestGet(context(`/api/history${query}`));
    assert.equal(res.status, 400, query);
    await assertNoLeak(res);
  }
  assert.equal(upstreamCalls.length, 0);
});

test("other origins are refused and never given CORS access", async () => {
  const { onRequestGet, onRequest } = await loadModule();
  const evil = { Origin: "https://evil.example" };
  const res = await onRequestGet(context("/api/history?ticker=TEST", { headers: evil }));
  assert.equal(res.status, 403);
  assert.equal(res.headers.get("Access-Control-Allow-Origin"), null);
  assert.equal((await onRequest(context("/api/history", { method: "OPTIONS", headers: evil }))).status, 403);
  const marked = await onRequestGet(context("/api/history?ticker=TEST", { headers: { "Sec-Fetch-Site": "cross-site" } }));
  assert.equal(marked.status, 403);
  assert.equal(upstreamCalls.length, 0);
  const own = await onRequestGet(context("/api/history?ticker=TEST", { headers: { Origin: ORIGIN } }));
  assert.equal(own.status, 200);
  assert.equal(own.headers.get("Access-Control-Allow-Origin"), ORIGIN);
});

test("a ticker that doesn't exist is a cached 404", async () => {
  const { onRequestGet } = await loadModule();
  upstreamHandler = () => new Response('{"chart":{"result":null,"error":{"code":"Not Found"}}}', { status: 404 });
  const first = await onRequestGet(context("/api/history?ticker=ZZZZQ"));
  assert.equal(first.status, 404);
  assert.deepEqual(await first.json(), { found: false, symbol: "ZZZZQ", error: "No price history found for ZZZZQ." });
  const second = await onRequestGet(context("/api/history?ticker=zzzzq"));
  assert.equal(second.status, 404);
  assert.equal(second.headers.get("X-History-Cache"), "hit");
  assert.equal(second.headers.get("Cache-Control"), "public, max-age=3600");
  assert.equal(upstreamCalls.length, 1);
});

test("a foreign or non-dollar listing is refused in plain words", async () => {
  const { onRequestGet } = await loadModule();
  upstreamHandler = (url) => (url.includes("yahoo") ? yahoo(chart(BARS, { currency: "GBp" })) : goodUpstream(url));
  const res = await onRequestGet(context("/api/history?ticker=VOD.L"));
  assert.equal(res.status, 404);
  assert.equal((await res.json()).error, "StockPulse only prices US-listed stocks and funds in dollars.");
});

test("repeat requests are served from cache for six hours, whatever the case", async () => {
  const { onRequestGet } = await loadModule();
  const first = await onRequestGet(context("/api/history?ticker=TEST"));
  assert.equal(first.headers.get("X-History-Cache"), "miss");
  assert.equal(first.headers.get("Cache-Control"), "public, max-age=21600");
  const calls = upstreamCalls.length;
  const second = await onRequestGet(context("/api/history?symbol=test"));
  assert.equal(second.headers.get("X-History-Cache"), "hit");
  assert.equal(second.headers.get("Cache-Control"), "public, max-age=21600");
  assert.equal(upstreamCalls.length, calls);
  assert.deepEqual(await second.json(), await first.json());
});

test("upstream failures never reveal the provider, URL or error details", async () => {
  const { onRequestGet } = await loadModule();
  const failures = [
    new Error(`getaddrinfo ENOTFOUND query2.finance.yahoo.com token=${SECRET}`),
    new Response("blocked", { status: 403 }),
    new Response("<html>not json</html>", { status: 200 }),
    new Response("slow down", { status: 429 }),
  ];
  for (const [i, failure] of failures.entries()) {
    upstreamHandler = () => (failure instanceof Response ? failure.clone() : failure);
    const res = await onRequestGet(context(`/api/history?ticker=F${i}`));
    assert.ok([429, 502].includes(res.status), String(res.status));
    assert.equal(res.headers.get("Cache-Control"), "no-store");
    await assertNoLeak(res);
    const body = await res.json();
    assert.equal(body.found, false);
    assert.ok(["Could not reach the data provider.", "Price history is busy. Try again in a minute."].includes(body.error));
  }
});

test("one visitor is rate limited without affecting another", async () => {
  const { onRequestGet } = await loadModule();
  const from = (ip, n) => onRequestGet(context(`/api/history?ticker=T${n}`, { headers: { "CF-Connecting-IP": ip } }));
  for (let i = 0; i < 60; i += 1) assert.notEqual((await from("203.0.113.1", i % 5)).status, 429);
  const limited = await from("203.0.113.1", 0);
  assert.equal(limited.status, 429);
  assert.ok(Number(limited.headers.get("Retry-After")) >= 1);
  assert.equal((await from("203.0.113.2", 0)).status, 200);
});

test("many different tickers cannot burn the upstream or sector quota", async () => {
  const { onRequestGet } = await loadModule();
  let busy = 0;
  for (let i = 0; i < 70; i += 1) {
    const res = await onRequestGet(context(`/api/history?ticker=U${i}`, { headers: { "CF-Connecting-IP": `198.51.100.${i}` } }));
    if (res.status === 429) busy += 1;
  }
  assert.equal(busy, 10);
  assert.equal(upstreamCalls.filter((c) => c.url.includes("yahoo")).length, 60);
  assert.equal(upstreamCalls.filter((c) => c.url.includes("finnhub")).length, 10);
});

test("hostile upstream text is cleaned before it is passed on", async () => {
  const { onRequestGet } = await loadModule();
  upstreamHandler = (url) => {
    if (url.includes("finnhub")) return { finnhubIndustry: "Bad\u0000\nIndustry" + "x".repeat(500) };
    const body = chart();
    body.meta.longName = "Evil\u0000\u001f Co" + "y".repeat(500);
    return yahoo(body);
  };
  const body = await (await onRequestGet(context("/api/history?ticker=TEST"))).json();
  assert.equal(body.name.length, 120);
  assert.ok(!/[\u0000-\u001f]/.test(body.name));
  assert.ok(body.industry.length <= 80 && !/[\u0000-\u001f]/.test(body.industry));
  assert.equal(body.sector, null);
});

test("nothing about a request is logged", () => {
  for (const file of ["api/history.js", "_shared/guard.js"]) {
    const source = readFileSync(join(here, "..", "..", "functions", file), "utf8");
    assert.ok(!/console\.|\bdebugger\b/.test(source), file);
  }
});
