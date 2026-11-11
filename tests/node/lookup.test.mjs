// Run with: node --test tests/node/lookup.test.mjs
// The functions are ES modules without a package.json saying so, so tests load a temporary copy
// of functions/ that has one (see helpers.mjs).
import assert from "node:assert/strict";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { after, beforeEach, test } from "node:test";
import { pathToFileURL } from "node:url";

import { copyFunctions } from "./helpers.mjs";

const SECRET = "not-a-real-key-0123456789";
const ORIGIN = "https://stocks.example";
const tempDir = mkdtempSync(join(tmpdir(), "lookup-test-"));
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
  return import(pathToFileURL(join(copyFunctions(tempDir, `copy-${loadCount}`), "api", "lookup.js")).href);
}

function goodUpstream(url) {
  if (url.includes("/quote")) return { c: 100, d: 1, dp: 1, h: 101, l: 99, o: 100, pc: 99, t: 1700000000 };
  if (url.includes("/company-news")) {
    return [{ headline: "Real headline", url: "https://example.com/a", source: "Wire", datetime: 1700000000, summary: "S" }];
  }
  if (url.includes("/search")) return { result: [{ symbol: "NFLX", description: "NETFLIX INC", type: "Common Stock" }] };
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
  return {
    request: new Request(`${ORIGIN}${path}`, { method, headers }),
    env,
  };
}

async function assertNoLeak(res) {
  const text = await res.clone().text();
  assert.ok(!text.includes(SECRET), "response contains the API key");
  assert.ok(!text.includes("finnhub.io"), "response contains the upstream URL");
  assert.ok(!/\bat .+:\d+:\d+/.test(text), "response contains a stack trace");
  return text;
}

test("a ticker returns price and headlines as JSON", async () => {
  const { onRequestGet } = await loadModule();
  const res = await onRequestGet(context("/api/lookup?ticker=nflx"));
  assert.equal(res.status, 200);
  assert.match(res.headers.get("Content-Type"), /application\/json/);
  assert.equal(res.headers.get("X-Content-Type-Options"), "nosniff");
  const data = JSON.parse(await assertNoLeak(res));
  assert.equal(data.symbol, "NFLX");
  assert.equal(data.price.current, 100);
  assert.equal(data.headlines[0].headline, "Real headline");
});

test("a company name still resolves through search", async () => {
  const { onRequestGet } = await loadModule();
  upstreamHandler = (url) => (url.includes("/search") ? goodUpstream(url) : url.includes("symbol=NFLX") ? goodUpstream(url) : {});
  const res = await onRequestGet(context("/api/lookup?ticker=Netflix%20Inc"));
  assert.equal(res.status, 200);
  const data = await res.json();
  assert.equal(data.symbol, "NFLX");
  assert.equal(data.resolved_from, "Netflix Inc");
});

test("only GET and OPTIONS are accepted", async () => {
  const { onRequest } = await loadModule();
  for (const method of ["POST", "PUT", "DELETE", "PATCH"]) {
    const res = await onRequest(context("/api/lookup?ticker=NFLX", { method }));
    assert.equal(res.status, 405, method);
    assert.match(res.headers.get("Allow"), /GET/);
  }
  assert.equal(upstreamCalls.length, 0);
});

test("hostile or oversized input is rejected before any upstream call", async () => {
  const { onRequestGet } = await loadModule();
  const bad = [
    "",
    "<script>alert(1)</script>",
    "'><img src=x onerror=alert(1)>",
    "A".repeat(61),
    "../../etc/passwd",
    "AAPL&token=stolen",
    "a\u0000b",
    "line\r\nbreak",
    "javascript:alert(1)",
  ];
  for (const value of bad) {
    const res = await onRequestGet(context(`/api/lookup?ticker=${encodeURIComponent(value)}`));
    assert.equal(res.status, 400, JSON.stringify(value));
    await assertNoLeak(res);
  }
  assert.equal(upstreamCalls.length, 0);
});

test("parameters are encoded and the key is only ever in a header", async () => {
  const { onRequestGet } = await loadModule();
  upstreamHandler = () => ({});
  await onRequestGet(context("/api/lookup?q=" + encodeURIComponent("AT&T Inc")));
  const search = upstreamCalls.find((c) => c.url.includes("/search"));
  assert.ok(search.url.includes("q=AT%26T+Inc"), search.url);
  for (const call of upstreamCalls) {
    assert.ok(!call.url.includes(SECRET), "key leaked into a URL");
    assert.equal(call.options.headers["X-Finnhub-Token"], SECRET);
  }
});

test("upstream failures never reveal the key, URL or error details", async () => {
  const { onRequestGet } = await loadModule();
  upstreamHandler = () => new Error(`connect failed https://finnhub.io/api/v1/quote?token=${SECRET}\n    at x (y.js:1:2)`);
  let res = await onRequestGet(context("/api/lookup?ticker=AAA"));
  assert.equal(res.status, 502);
  await assertNoLeak(res);

  upstreamHandler = () => new Response("nope", { status: 401 });
  res = await onRequestGet(context("/api/lookup?ticker=BBB"));
  assert.equal(res.status, 502);
  const text = await assertNoLeak(res);
  assert.ok(!text.includes("FINNHUB_API_KEY"));

  upstreamHandler = () => new Response("slow down", { status: 429 });
  res = await onRequestGet(context("/api/lookup?ticker=CCC"));
  assert.equal(res.status, 429);
  assert.ok(res.headers.get("Retry-After"));
});

test("a missing key is a plain 503 that does not name the setting", async () => {
  const { onRequestGet } = await loadModule();
  const res = await onRequestGet(context("/api/lookup?ticker=AAA", { env: {} }));
  assert.equal(res.status, 503);
  assert.ok(!(await res.text()).includes("FINNHUB"));
});

test("other origins are refused and never given CORS access", async () => {
  const { onRequestGet, onRequest } = await loadModule();
  let res = await onRequestGet(context("/api/lookup?ticker=AAA", { headers: { Origin: "https://evil.example" } }));
  assert.equal(res.status, 403);
  assert.equal(res.headers.get("Access-Control-Allow-Origin"), null);
  assert.equal(upstreamCalls.length, 0);

  res = await onRequest(context("/api/lookup", { method: "OPTIONS", headers: { Origin: "https://evil.example" } }));
  assert.equal(res.status, 403);

  res = await onRequestGet(context("/api/lookup?ticker=AAA", { headers: { "Sec-Fetch-Site": "cross-site" } }));
  assert.equal(res.status, 403);

  res = await onRequestGet(context("/api/lookup?ticker=AAA", { headers: { Origin: ORIGIN } }));
  assert.equal(res.status, 200);
  assert.equal(res.headers.get("Access-Control-Allow-Origin"), ORIGIN);
  assert.notEqual(res.headers.get("Access-Control-Allow-Origin"), "*");
});

test("repeat lookups within a minute are served from cache, whatever the case", async () => {
  const { onRequestGet } = await loadModule();
  const first = await onRequestGet(context("/api/lookup?ticker=NFLX"));
  assert.equal(first.headers.get("X-Lookup-Cache"), "miss");
  assert.match(first.headers.get("Cache-Control"), /max-age=60/);
  const calls = upstreamCalls.length;
  const second = await onRequestGet(context("/api/lookup?ticker=nflx"));
  assert.equal(second.status, 200);
  assert.equal(second.headers.get("X-Lookup-Cache"), "hit");
  assert.equal(upstreamCalls.length, calls);
});

test("the edge cache is used when Cloudflare provides it", async () => {
  const { onRequestGet } = await loadModule();
  const store = new Map();
  globalThis.caches = {
    default: {
      match: async (req) => store.get(req.url)?.clone(),
      put: async (req, res) => { store.set(req.url, res); },
    },
  };
  try {
    await onRequestGet(context("/api/lookup?ticker=NFLX"));
    assert.equal(store.size, 1);
    assert.ok(![...store.keys()][0].includes(SECRET));
    assert.match((await [...store.values()][0].clone()).headers.get("Cache-Control"), /max-age=60/);
  } finally {
    delete globalThis.caches;
  }
});

test("a cached not-found keeps its 404 status", async () => {
  const first = await loadModule();
  const store = new Map();
  globalThis.caches = {
    default: {
      match: async (req) => store.get(req.url)?.clone(),
      put: async (req, res) => { store.set(req.url, res); },
    },
  };
  try {
    upstreamHandler = () => ({});
    assert.equal((await first.onRequestGet(context("/api/lookup?ticker=ZZZ"))).status, 404);
    const second = await loadModule(); // A new isolate has an empty memory cache.
    const calls = upstreamCalls.length;
    const res = await second.onRequestGet(context("/api/lookup?ticker=ZZZ"));
    assert.equal(res.status, 404);
    assert.equal(upstreamCalls.length, calls);
  } finally {
    delete globalThis.caches;
  }
});

test("one visitor is rate limited without affecting another", async () => {
  const { onRequestGet } = await loadModule();
  const from = (ip, ticker) => context(`/api/lookup?ticker=${ticker}`, { headers: { "CF-Connecting-IP": ip } });
  let last;
  for (let i = 0; i < 31; i += 1) last = await onRequestGet(from("198.51.100.1", "NFLX"));
  assert.equal(last.status, 429);
  assert.ok(last.headers.get("Retry-After"));
  assert.equal((await onRequestGet(from("198.51.100.2", "NFLX"))).status, 200);
});

test("many different tickers cannot burn the upstream quota", async () => {
  const { onRequestGet } = await loadModule();
  const statuses = [];
  for (let i = 0; i < 40; i += 1) {
    const res = await onRequestGet(
      context(`/api/lookup?ticker=T${i}`, { headers: { "CF-Connecting-IP": `203.0.113.${i}` } })
    );
    statuses.push(res.status);
  }
  assert.ok(statuses.includes(429));
  assert.ok(upstreamCalls.length <= 60, `made ${upstreamCalls.length} upstream calls`);
});

test("hostile upstream content is cleaned before it is passed on", async () => {
  const { onRequestGet } = await loadModule();
  upstreamHandler = (url) => {
    if (url.includes("/quote")) return { c: 1, pc: 1, h: 1 };
    return [
      { headline: "Bad link", url: "javascript:alert(1)" },
      { headline: "Data link", url: "data:text/html,x" },
      { headline: "Good\u0000 one\r\n" + "x".repeat(1000), url: "https://example.com/ok", summary: "y".repeat(5000) },
    ];
  };
  const data = await (await onRequestGet(context("/api/lookup?ticker=AAA"))).json();
  assert.equal(data.headlines.length, 1);
  assert.equal(data.headlines[0].url, "https://example.com/ok");
  assert.ok(data.headlines[0].headline.length <= 300);
  assert.ok(data.headlines[0].summary.length <= 600);
  assert.ok(!/[\u0000-\u001f]/.test(data.headlines[0].headline));
});

test("a search result with an odd symbol is ignored", async () => {
  const { onRequestGet } = await loadModule();
  upstreamHandler = (url) => (url.includes("/search") ? { result: [{ symbol: "../../admin", type: "Common Stock" }] } : {});
  const res = await onRequestGet(context("/api/lookup?q=Something"));
  assert.equal(res.status, 404);
  assert.ok(!upstreamCalls.some((c) => c.url.includes("admin")));
});
