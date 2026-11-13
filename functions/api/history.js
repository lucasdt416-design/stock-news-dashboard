/**
 * Cloudflare Pages Function: /api/history
 *
 * Long monthly price history for one US ticker that isn't on the watchlist, for the portfolio page.
 * Watchlist companies never come here: their history is a static file under /data/prices/.
 *
 * GET /api/history?ticker=VOO  (or symbol=)
 *
 * Success: { found: true, symbol, name, kind, currency, first_month, months, price, fetched,
 *            sector, industry }, the same shape as the static files plus sector and industry.
 *   months   [["2010-10", 81.8031], ...]: finished months only, the adjusted close at month end
 *   price    { value, date }: the latest price Yahoo has, with its date
 *   kind     "stock" or "fund"
 *   sector   one of the site's sector names, or null when it isn't known
 * Failure: { found: false, error }, with 400, 403, 404, 405, 429 or 502.
 *
 * Only the ticker arrives here, never how much of it anyone holds. Nothing is logged or stored
 * about who asked. Prices come from Yahoo Finance, which needs no key. The sector comes from
 * Finnhub when FINNHUB_API_KEY is set, and is simply left out when it isn't.
 * Errors never contain the API key, an upstream URL or a stack trace.
 */

import { cleanText, createGuard, isCrossSite, json, ownOrigin, refuseOtherMethods } from "../_shared/guard.js";

const TICKER_PATTERN = /^[A-Za-z0-9][A-Za-z0-9.\-]{0,9}$/;

const FOUND_SECONDS = 6 * 60 * 60;
const NOT_FOUND_SECONDS = 60 * 60;
const UPSTREAM_TIMEOUT_MS = 8000;
const MAX_REQUESTS_PER_VISITOR = 60; // A portfolio is priced one ticker at a time.
const MAX_UPSTREAM_LOOKUPS = 60;
const MAX_SECTOR_LOOKUPS = 10; // Finnhub's 60 calls a minute are shared with /api/lookup.
const WINDOW_MS = 60 * 1000;
const FUND_TYPES = new Set(["ETF", "MUTUALFUND"]);
const BROWSER_AGENT =
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36";

const guard = createGuard({
  header: "X-History",
  cacheSeconds: FOUND_SECONDS,
  maxPerVisitor: MAX_REQUESTS_PER_VISITOR,
  maxUpstream: MAX_UPSTREAM_LOOKUPS,
});
let sectorWindow = { windowStart: 0, count: 0 };

/**
 * Finnhub's industry words, mapped to the sector names the site already uses
 * (SECTOR_METADATA in pipeline/render.py; tests/test_history_sectors.py keeps the two in step).
 * An industry that isn't here is "not known", never a best guess. "Media" is left out on purpose:
 * Finnhub uses it for Meta and Alphabet (Technology here) as well as Disney and Netflix (Consumer
 * Staples here), so one word can't say which.
 */
export const INDUSTRY_SECTORS = {
  "Semiconductors": "Technology",
  "Technology": "Technology",
  "Banking": "Finance",
  "Financial Services": "Finance",
  "Insurance": "Finance",
  "Pharmaceuticals": "Healthcare",
  "Biotechnology": "Healthcare",
  "Health Care": "Healthcare",
  "Life Sciences Tools & Services": "Healthcare",
  "Energy": "Energy",
  "Machinery": "Industrials",
  "Industrial Conglomerates": "Industrials",
  "Electrical Equipment": "Industrials",
  "Building": "Industrials",
  "Construction": "Industrials",
  "Road & Rail": "Industrials",
  "Airlines": "Industrials",
  "Marine": "Industrials",
  "Logistics & Transportation": "Industrials",
  "Transportation Infrastructure": "Industrials",
  "Commercial Services & Supplies": "Industrials",
  "Professional Services": "Industrials",
  "Trading Companies & Distributors": "Industrials",
  "Aerospace & Defense": "Aerospace",
  "Retail": "Retail",
  "Distributors": "Retail",
  "Beverages": "Consumer Staples",
  "Food Products": "Consumer Staples",
  "Tobacco": "Consumer Staples",
  "Consumer products": "Consumer Staples",
  "Telecommunication": "Telecom",
  "Communications": "Telecom",
  "Utilities": "Utilities",
  "Chemicals": "Materials",
  "Metals & Mining": "Materials",
  "Packaging": "Materials",
  "Paper & Forest": "Materials",
  "Real Estate": "Real Estate",
  "Automobiles": "Consumer Goods",
  "Auto Components": "Consumer Goods",
  "Textiles, Apparel & Luxury Goods": "Consumer Goods",
  "Leisure Products": "Consumer Goods",
  "Hotels, Restaurants & Leisure": "Consumer Goods",
  "Diversified Consumer Services": "Consumer Goods",
};

export function sectorForIndustry(industry) {
  const key = String(industry || "").trim();
  return Object.prototype.hasOwnProperty.call(INDUSTRY_SECTORS, key) ? INDUSTRY_SECTORS[key] : null;
}

export async function onRequestGet(context) {
  return handleHistory(context);
}

export async function onRequest(context) {
  return refuseOtherMethods(context) || handleHistory(context);
}

function readTicker(url) {
  for (const name of ["ticker", "symbol"]) {
    const value = url.searchParams.get(name);
    if (value && value.trim()) return value.trim();
  }
  return "";
}

function sixFigures(value) {
  return Number(value.toPrecision(6));
}

function isoDay(date) {
  return date.toISOString().slice(0, 10);
}

/**
 * Month-end adjusted closes and the latest price from one Yahoo monthly chart answer.
 * Only finished months are kept: the month in progress is a part-month. A month with no value is
 * left out, not filled in. Anything that doesn't look right returns null. This mirrors
 * parse_monthly_history in collectors/stock_prices.py.
 */
export function parseMonthlyHistory(symbol, chart) {
  const meta = chart?.meta || {};
  const kind = FUND_TYPES.has(meta.instrumentType) ? "fund" : meta.instrumentType === "EQUITY" ? "stock" : null;
  const price = meta.regularMarketPrice;
  const priceTime = meta.regularMarketTime;
  if (!kind || meta.currency !== "USD") return null;
  // Asked for months, Yahoo sometimes answers in weeks. A week isn't a month-end, so refuse it.
  if (meta.dataGranularity !== "1mo") return null;
  if (!Number.isFinite(price) || price <= 0 || !Number.isFinite(priceTime)) return null;
  const offsetSeconds = Number.isFinite(meta.gmtoffset) ? meta.gmtoffset : 0;
  const priceDate = isoDay(new Date((priceTime + offsetSeconds) * 1000));
  const currentMonth = priceDate.slice(0, 7);

  const timestamps = Array.isArray(chart.timestamp) ? chart.timestamp : [];
  const adjusted = chart.indicators?.adjclose?.[0]?.adjclose;
  const values = Array.isArray(adjusted) ? adjusted : [];
  const months = [];
  for (let i = 0; i < Math.min(timestamps.length, values.length); i += 1) {
    const value = values[i];
    if (value === null || value === undefined) continue;
    if (!Number.isFinite(timestamps[i])) return null;
    // A bar is stamped at midnight in New York on the 1st, which is 04:00 or 05:00 UTC depending
    // on daylight saving, so the UTC date names the month either way.
    const month = isoDay(new Date(timestamps[i] * 1000)).slice(0, 7);
    if (month >= currentMonth) continue;
    if (!Number.isFinite(value) || value <= 0) return null;
    if (months.length && month <= months[months.length - 1][0]) return null;
    months.push([month, sixFigures(value)]);
  }

  return {
    symbol,
    name: cleanText(meta.longName || meta.shortName || symbol, 120),
    kind,
    currency: "USD",
    first_month: months.length ? months[0][0] : null,
    months,
    price: { value: Math.round(price * 10000) / 10000, date: priceDate },
  };
}

async function fetchChart(symbol, signal) {
  // https://query2.finance.yahoo.com/v8/finance/chart/<symbol>
  const target =
    `https://query2.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(symbol)}` +
    // Not range=max: for a company listed in the last few years Yahoo answers that with weekly prices.
    `?period1=0&period2=${Math.floor(Date.now() / 1000)}&interval=1mo&includePrePost=false`;
  const res = await fetch(target, {
    signal,
    headers: {
      "User-Agent": BROWSER_AGENT,
      Accept: "*/*",
      "Accept-Language": "en-US,en;q=0.9",
      Referer: "https://finance.yahoo.com/",
    },
  });
  if (res.status === 404) return { missing: true };
  if (res.status === 429) throw new Error("UPSTREAM_RATE_LIMIT");
  if (!res.ok) throw new Error("UPSTREAM_FAILED");
  const data = await res.json();
  const chart = data?.chart?.result?.[0];
  return chart ? { chart } : { missing: true };
}

function allowSectorLookup(now) {
  if (now - sectorWindow.windowStart >= WINDOW_MS) sectorWindow = { windowStart: now, count: 0 };
  sectorWindow.count += 1;
  return sectorWindow.count <= MAX_SECTOR_LOOKUPS;
}

/** { industry, sector, asked }: asked is false when Finnhub wasn't reachable, so the answer is cached for less time. */
async function fetchSector(symbol, apiKey, now, signal) {
  if (!apiKey) return { industry: null, sector: null, asked: true };
  if (!allowSectorLookup(now)) return { industry: null, sector: null, asked: false };
  try {
    // https://finnhub.io/api/v1/stock/profile2 ; Finnhub writes share classes with a dot (BRK.B).
    const target = `https://finnhub.io/api/v1/stock/profile2?${new URLSearchParams({ symbol: symbol.replace("-", ".") })}`;
    const res = await fetch(target, {
      signal,
      // The key travels in a header, so it can never appear in a URL, a log line or an error message.
      headers: { "User-Agent": "StockNewsDashboard-History/1.0", Accept: "application/json", "X-Finnhub-Token": apiKey },
    });
    if (!res.ok) return { industry: null, sector: null, asked: false };
    const profile = await res.json();
    const industry = cleanText(profile?.finnhubIndustry, 80) || null;
    return { industry, sector: sectorForIndustry(industry), asked: true };
  } catch {
    return { industry: null, sector: null, asked: false };
  }
}

async function handleHistory(context) {
  const now = Date.now();

  if (isCrossSite(context)) {
    return json({ found: false, error: "Origin not allowed." }, 403, context);
  }

  const ip = context.request.headers.get("CF-Connecting-IP");
  if (!guard.allowVisitor(ip, now)) {
    return json({ found: false, error: "Too many requests. Try again in a minute." }, 429, context, {
      "Retry-After": guard.visitorRetryAfter(ip, now),
    });
  }

  const query = readTicker(new URL(context.request.url));
  if (!TICKER_PATTERN.test(query)) {
    return json({ found: false, error: "Provide a stock symbol, for example ?ticker=VOO." }, 400, context);
  }
  // Yahoo writes share classes with a hyphen (BRK-B).
  const symbol = query.toUpperCase().replace(/\./g, "-");

  const cacheKey = `${ownOrigin(context)}/api/history?cache=${encodeURIComponent(symbol)}`;
  const cached = await guard.readCache(cacheKey, now);
  if (cached) return guard.cachedResponse(cached.status, cached.body, context, "hit", cached.seconds);

  if (!guard.allowUpstream(now)) {
    return json({ found: false, error: "Price history is busy. Try again in a minute." }, 429, context, {
      "Retry-After": guard.upstreamRetryAfter(now),
    });
  }

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), UPSTREAM_TIMEOUT_MS);

  try {
    const answer = await fetchChart(symbol, controller.signal);
    const record = answer.chart ? parseMonthlyHistory(symbol, answer.chart) : null;

    if (!record) {
      const body = JSON.stringify({
        found: false,
        symbol,
        error: answer.missing
          ? `No price history found for ${symbol}.`
          : "StockPulse only prices US-listed stocks and funds in dollars.",
      });
      await guard.writeCache(cacheKey, 404, body, now, context, NOT_FOUND_SECONDS);
      return guard.cachedResponse(404, body, context, "miss", NOT_FOUND_SECONDS);
    }

    const sector =
      record.kind === "stock"
        ? await fetchSector(symbol, context.env?.FINNHUB_API_KEY || "", now, controller.signal)
        : { industry: null, sector: null, asked: true };
    const seconds = sector.asked ? FOUND_SECONDS : NOT_FOUND_SECONDS;
    const body = JSON.stringify({
      found: true,
      ...record,
      fetched: isoDay(new Date(now)),
      sector: sector.sector,
      industry: sector.industry,
    });
    await guard.writeCache(cacheKey, 200, body, now, context, seconds);
    return guard.cachedResponse(200, body, context, "miss", seconds);
  } catch (err) {
    // A rate limit, a block and a network failure all look the same from outside on purpose.
    const busy = err && err.message === "UPSTREAM_RATE_LIMIT";
    return json(
      { found: false, error: busy ? "Price history is busy. Try again in a minute." : "Could not reach the data provider." },
      busy ? 429 : 502,
      context,
      busy ? { "Retry-After": "60" } : {}
    );
  } finally {
    clearTimeout(timer);
  }
}
