/**
 * Cloudflare Pages Function: /api/lookup
 *
 * Quick lookup for a stock outside the watchlist: price and 2-3 recent headlines from Finnhub.
 *
 * GET /api/lookup?ticker=NFLX  (or symbol=, q=, query=; a company name also works: q=Netflix)
 *
 * Success: { found, symbol, company_name, resolved_from, price, headlines, queried_at }
 * Failure: { found: false, error | message }, with 400, 403, 404, 405, 429, 502 or 503.
 *
 * This endpoint spends a free-tier API quota on behalf of anonymous visitors, so it only answers
 * this site's own pages, checks input against an allow-list, caches per query and rate limits.
 * Errors never contain the API key, an upstream URL or a stack trace.
 */

const TICKER_PATTERN = /^[A-Za-z0-9][A-Za-z0-9.\-]{0,9}$/;
const NAME_PATTERN = /^[A-Za-z0-9][A-Za-z0-9 .,&'\-]{0,59}$/;

const CACHE_SECONDS = 60;
const UPSTREAM_TIMEOUT_MS = 8000;
const MAX_HEADLINE = 300;
const MAX_SUMMARY = 600;
const MAX_SOURCE = 80;
const MAX_URL = 2048;

// Limits are per isolate, so they are best effort: Cloudflare can run several at once and restarts
// them freely. They stop one visitor burning the quota by accident or with a simple loop. A WAF
// rate-limit rule (see docs/security-review.md) is the hard limit.
const WINDOW_MS = 60 * 1000;
const MAX_REQUESTS_PER_VISITOR = 30;
const MAX_UPSTREAM_LOOKUPS = 15; // Each lookup costs 2-3 Finnhub calls; the free tier allows 60 a minute.
const MAX_TRACKED = 5000;

const visitors = new Map();
const memoryCache = new Map();
let upstream = { windowStart: 0, count: 0 };

export async function onRequestGet(context) {
  return handleLookup(context);
}

export async function onRequest(context) {
  const { request } = context;
  const origin = request.headers.get("Origin");
  if (request.method === "OPTIONS") {
    if (origin && !isAllowedOrigin(origin, context)) {
      return json({ found: false, error: "Origin not allowed." }, 403, context);
    }
    return new Response(null, {
      status: 204,
      headers: {
        ...baseHeaders(context),
        "Access-Control-Allow-Methods": "GET",
        "Access-Control-Max-Age": "86400",
      },
    });
  }
  if (request.method === "GET") {
    return handleLookup(context);
  }
  return json({ found: false, error: "Method not allowed." }, 405, context, { Allow: "GET, OPTIONS" });
}

function ownOrigin(context) {
  return new URL(context.request.url).origin;
}

function isAllowedOrigin(origin, context) {
  if (origin === ownOrigin(context)) return true;
  const extra = String(context.env?.ALLOWED_ORIGINS || "").split(",").map((o) => o.trim()).filter(Boolean);
  return extra.includes(origin);
}

function baseHeaders(context) {
  const headers = {
    "Content-Type": "application/json; charset=utf-8",
    "X-Content-Type-Options": "nosniff",
    Vary: "Origin",
  };
  const origin = context.request.headers.get("Origin");
  if (origin && isAllowedOrigin(origin, context)) {
    headers["Access-Control-Allow-Origin"] = origin;
  }
  return headers;
}

function json(body, status, context, extra = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Cache-Control": "no-store", ...baseHeaders(context), ...extra },
  });
}

/** Browsers mark cross-site calls; anything marked that way, or from another origin, is refused. */
function isCrossSite(context) {
  const { headers } = context.request;
  const origin = headers.get("Origin");
  if (origin && !isAllowedOrigin(origin, context)) return true;
  const site = headers.get("Sec-Fetch-Site");
  return site === "cross-site" && !origin;
}

function allowVisitor(ip, now) {
  if (!ip) return true;
  let entry = visitors.get(ip);
  if (!entry || now - entry.windowStart >= WINDOW_MS) {
    if (visitors.size >= MAX_TRACKED) {
      for (const [key, value] of visitors) {
        if (now - value.windowStart >= WINDOW_MS) visitors.delete(key);
      }
      if (visitors.size >= MAX_TRACKED) visitors.clear();
    }
    entry = { windowStart: now, count: 0 };
    visitors.set(ip, entry);
  }
  entry.count += 1;
  return entry.count <= MAX_REQUESTS_PER_VISITOR;
}

function allowUpstream(now) {
  if (now - upstream.windowStart >= WINDOW_MS) upstream = { windowStart: now, count: 0 };
  upstream.count += 1;
  return upstream.count <= MAX_UPSTREAM_LOOKUPS;
}

function secondsUntilReset(windowStart, now) {
  return String(Math.max(1, Math.ceil((windowStart + WINDOW_MS - now) / 1000)));
}

/** The first non-empty query parameter, or "" if none was given. */
function readQuery(url) {
  for (const name of ["ticker", "symbol", "q", "query"]) {
    const value = url.searchParams.get(name);
    if (value && value.trim()) return value.trim();
  }
  return "";
}

function edgeCache() {
  // caches.default only exists on Cloudflare, and can be missing on some hostnames.
  return typeof caches !== "undefined" && caches.default ? caches.default : null;
}

function cacheKeyFor(context, query) {
  return `${ownOrigin(context)}/api/lookup?cache=${encodeURIComponent(query.toUpperCase())}`;
}

async function readCache(key, now) {
  const hit = memoryCache.get(key);
  if (hit && hit.expires > now) return { status: hit.status, body: hit.body };
  memoryCache.delete(key);
  const cache = edgeCache();
  if (!cache) return null;
  try {
    const res = await cache.match(new Request(key));
    return res ? { status: Number(res.headers.get("X-Lookup-Status")) || 200, body: await res.text() } : null;
  } catch {
    return null;
  }
}

async function writeCache(key, status, body, now, context) {
  if (memoryCache.size >= 500) memoryCache.clear();
  memoryCache.set(key, { status, body, expires: now + CACHE_SECONDS * 1000 });
  const cache = edgeCache();
  if (!cache) return;
  const store = new Response(body, {
    // The Cache API refuses to store some statuses, so everything goes in as a 200 and the real
    // status travels in a header.
    status: 200,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": `public, max-age=${CACHE_SECONDS}`,
      "X-Lookup-Status": String(status),
    },
  });
  const put = cache.put(new Request(key), store).catch(() => {});
  if (context.waitUntil) context.waitUntil(put);
  else await put;
}

function cachedResponse(status, body, context, state) {
  return new Response(body, {
    status,
    headers: {
      ...baseHeaders(context),
      "Cache-Control": `public, max-age=${CACHE_SECONDS}`,
      "X-Lookup-Cache": state,
    },
  });
}

function safeHttpUrl(value) {
  if (typeof value !== "string" || value.length > MAX_URL) return null;
  try {
    const { protocol } = new URL(value);
    return protocol === "https:" || protocol === "http:" ? value : null;
  } catch {
    return null;
  }
}

function cleanText(value, limit) {
  // eslint-disable-next-line no-control-regex
  return String(value ?? "").replace(/[\u0000-\u001f\u007f]+/g, " ").trim().slice(0, limit);
}

async function fetchJson(path, params, apiKey, signal) {
  // The key travels in a header, so it can never appear in a URL, a log line or an error message.
  const target = `https://finnhub.io/api/v1/${path}?${new URLSearchParams(params)}`;
  const res = await fetch(target, {
    signal,
    headers: {
      "User-Agent": "StockNewsDashboard-Lookup/1.0",
      Accept: "application/json",
      "X-Finnhub-Token": apiKey,
    },
  });
  if (res.status === 401 || res.status === 403) throw new Error("UPSTREAM_AUTH");
  if (res.status === 429) throw new Error("UPSTREAM_RATE_LIMIT");
  if (!res.ok) return null;
  return res.json();
}

async function fetchQuoteAndNews(symbol, apiKey, signal) {
  const now = new Date();
  const to = now.toISOString().split("T")[0];
  const from = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000).toISOString().split("T")[0];
  const [quote, news] = await Promise.all([
    // https://finnhub.io/api/v1/quote
    fetchJson("quote", { symbol }, apiKey, signal),
    // https://finnhub.io/api/v1/company-news
    fetchJson("company-news", { symbol, from, to }, apiKey, signal),
  ]);
  return { quote, news: Array.isArray(news) ? news : [] };
}

function hasPrice(quote) {
  return Boolean(quote && (quote.c || quote.pc || quote.h));
}

function bestSearchResult(results, query) {
  const usable = results.filter((r) => r && typeof r.symbol === "string" && TICKER_PATTERN.test(r.symbol));
  return (
    usable.find((r) => r.symbol.toUpperCase() === query.toUpperCase()) ||
    usable.find((r) => r.type === "Common Stock" && !r.symbol.includes(".")) ||
    usable.find((r) => r.type === "Common Stock" || r.type === "EQS") ||
    usable[0] ||
    null
  );
}

function timeAgo(datetime) {
  if (!datetime) return "";
  const diff = Math.floor(Date.now() / 1000 - datetime);
  if (diff < 60) return "Just now";
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

function buildHeadlines(news) {
  const headlines = [];
  for (const item of news) {
    if (headlines.length === 3) break;
    const url = safeHttpUrl(item?.url);
    const headline = cleanText(item?.headline, MAX_HEADLINE);
    if (!url || !headline) continue;
    const datetime = Number.isFinite(item.datetime) ? item.datetime : null;
    headlines.push({
      headline,
      url,
      source: cleanText(item.source, MAX_SOURCE) || "Financial Press",
      datetime,
      time_ago: timeAgo(datetime),
      summary: cleanText(item.summary, MAX_SUMMARY),
    });
  }
  return headlines;
}

async function handleLookup(context) {
  const now = Date.now();

  if (isCrossSite(context)) {
    return json({ found: false, error: "Origin not allowed." }, 403, context);
  }

  const ip = context.request.headers.get("CF-Connecting-IP");
  if (!allowVisitor(ip, now)) {
    const entry = visitors.get(ip);
    return json({ found: false, error: "Too many lookups. Try again in a minute." }, 429, context, {
      "Retry-After": secondsUntilReset(entry.windowStart, now),
    });
  }

  const query = readQuery(new URL(context.request.url));
  const isTicker = TICKER_PATTERN.test(query);
  if (!isTicker && !NAME_PATTERN.test(query)) {
    return json(
      { found: false, error: "Provide a stock symbol or company name, for example ?ticker=NFLX or ?q=Netflix." },
      400,
      context
    );
  }

  const cacheKey = cacheKeyFor(context, query);
  const cached = await readCache(cacheKey, now);
  if (cached) return cachedResponse(cached.status, cached.body, context, "hit");

  const apiKey = context.env?.FINNHUB_API_KEY || "";
  if (!apiKey) {
    return json({ found: false, error: "Lookup is not available right now." }, 503, context);
  }

  if (!allowUpstream(now)) {
    return json({ found: false, error: "Lookups are busy. Try again in a minute." }, 429, context, {
      "Retry-After": secondsUntilReset(upstream.windowStart, now),
    });
  }

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), UPSTREAM_TIMEOUT_MS);

  try {
    let symbol = query.toUpperCase();
    let companyName = null;
    let resolvedFrom = null;
    let quote = null;
    let news = [];

    if (isTicker) {
      ({ quote, news } = await fetchQuoteAndNews(symbol, apiKey, controller.signal));
    }

    if (!hasPrice(quote) && news.length === 0) {
      // https://finnhub.io/api/v1/search
      const search = await fetchJson("search", { q: query }, apiKey, controller.signal);
      const best = bestSearchResult(Array.isArray(search?.result) ? search.result : [], query);
      if (best) {
        symbol = best.symbol.toUpperCase();
        companyName = cleanText(best.description, 120) || null;
        resolvedFrom = query;
        ({ quote, news } = await fetchQuoteAndNews(symbol, apiKey, controller.signal));
      }
    }

    if (!hasPrice(quote) && news.length === 0) {
      const body = JSON.stringify({
        found: false,
        symbol,
        resolved_from: resolvedFrom,
        message: `No quote or news found for "${query}".`,
      });
      await writeCache(cacheKey, 404, body, now, context);
      return cachedResponse(404, body, context, "miss");
    }

    const body = JSON.stringify({
      found: true,
      symbol,
      company_name: companyName,
      resolved_from: resolvedFrom,
      price: hasPrice(quote)
        ? {
            current: Number(quote.c) || 0,
            change: Number(quote.d) || 0,
            change_pct: Number(quote.dp) || 0,
            high: Number(quote.h) || 0,
            low: Number(quote.l) || 0,
            open: Number(quote.o) || 0,
            prev_close: Number(quote.pc) || 0,
            timestamp: Number(quote.t) || Math.floor(now / 1000),
          }
        : null,
      headlines: buildHeadlines(news),
      queried_at: new Date(now).toISOString(),
    });
    await writeCache(cacheKey, 200, body, now, context);
    return cachedResponse(200, body, context, "miss");
  } catch (err) {
    // A bad key, a rate limit and a network failure all look the same from outside on purpose.
    const busy = err && err.message === "UPSTREAM_RATE_LIMIT";
    return json(
      { found: false, error: busy ? "Lookups are busy. Try again in a minute." : "Could not reach the data provider." },
      busy ? 429 : 502,
      context,
      busy ? { "Retry-After": "60" } : {}
    );
  } finally {
    clearTimeout(timer);
  }
}
