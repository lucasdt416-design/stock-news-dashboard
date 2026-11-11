/**
 * Protection shared by the site's Pages Functions (/api/lookup and /api/history).
 *
 * Each endpoint spends a free upstream quota on behalf of anonymous visitors, so each one only
 * answers this site's own pages, caches per query and rate limits. Every endpoint gets its own
 * counters and cache from createGuard(), so one can't use up another's allowance.
 *
 * Limits are per isolate, so they are best effort: Cloudflare can run several at once and restarts
 * them freely. They stop one visitor burning the quota by accident or with a simple loop. A WAF
 * rate-limit rule (see docs/security-review.md) is the hard limit.
 */

const WINDOW_MS = 60 * 1000;
const MAX_TRACKED = 5000;
const MAX_CACHED = 500;

export function ownOrigin(context) {
  return new URL(context.request.url).origin;
}

export function isAllowedOrigin(origin, context) {
  if (origin === ownOrigin(context)) return true;
  const extra = String(context.env?.ALLOWED_ORIGINS || "").split(",").map((o) => o.trim()).filter(Boolean);
  return extra.includes(origin);
}

export function baseHeaders(context) {
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

export function json(body, status, context, extra = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Cache-Control": "no-store", ...baseHeaders(context), ...extra },
  });
}

/** Browsers mark cross-site calls; anything marked that way, or from another origin, is refused. */
export function isCrossSite(context) {
  const { headers } = context.request;
  const origin = headers.get("Origin");
  if (origin && !isAllowedOrigin(origin, context)) return true;
  const site = headers.get("Sec-Fetch-Site");
  return site === "cross-site" && !origin;
}

/** Answers OPTIONS and refuses every method but GET. Returns null when the request is a GET. */
export function refuseOtherMethods(context) {
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
  if (request.method === "GET") return null;
  return json({ found: false, error: "Method not allowed." }, 405, context, { Allow: "GET, OPTIONS" });
}

export function cleanText(value, limit) {
  // eslint-disable-next-line no-control-regex
  return String(value ?? "").replace(/[\u0000-\u001f\u007f]+/g, " ").trim().slice(0, limit);
}

function edgeCache() {
  // caches.default only exists on Cloudflare, and can be missing on some hostnames.
  return typeof caches !== "undefined" && caches.default ? caches.default : null;
}

/**
 * One endpoint's counters and cache.
 *   header: prefix for the cache headers, e.g. "X-Lookup" gives X-Lookup-Cache and X-Lookup-Status
 *   cacheSeconds: how long an answer is reused unless writeCache is told otherwise
 *   maxPerVisitor / maxUpstream: requests allowed in any one minute
 */
export function createGuard({ header, cacheSeconds, maxPerVisitor, maxUpstream }) {
  const visitors = new Map();
  const memoryCache = new Map();
  let upstream = { windowStart: 0, count: 0 };
  const statusHeader = `${header}-Status`;
  const ttlHeader = `${header}-Seconds`;

  function secondsUntilReset(windowStart, now) {
    return String(Math.max(1, Math.ceil((windowStart + WINDOW_MS - now) / 1000)));
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
    return entry.count <= maxPerVisitor;
  }

  /** Seconds until this visitor may ask again. */
  function visitorRetryAfter(ip, now) {
    const entry = visitors.get(ip);
    return secondsUntilReset(entry ? entry.windowStart : now, now);
  }

  function allowUpstream(now) {
    if (now - upstream.windowStart >= WINDOW_MS) upstream = { windowStart: now, count: 0 };
    upstream.count += 1;
    return upstream.count <= maxUpstream;
  }

  function upstreamRetryAfter(now) {
    return secondsUntilReset(upstream.windowStart, now);
  }

  async function readCache(key, now) {
    const hit = memoryCache.get(key);
    if (hit && hit.expires > now) return { status: hit.status, body: hit.body, seconds: hit.seconds };
    memoryCache.delete(key);
    const cache = edgeCache();
    if (!cache) return null;
    try {
      const res = await cache.match(new Request(key));
      if (!res) return null;
      return {
        status: Number(res.headers.get(statusHeader)) || 200,
        body: await res.text(),
        seconds: Number(res.headers.get(ttlHeader)) || cacheSeconds,
      };
    } catch {
      return null;
    }
  }

  async function writeCache(key, status, body, now, context, seconds = cacheSeconds) {
    if (memoryCache.size >= MAX_CACHED) memoryCache.clear();
    memoryCache.set(key, { status, body, seconds, expires: now + seconds * 1000 });
    const cache = edgeCache();
    if (!cache) return;
    const store = new Response(body, {
      // The Cache API refuses to store some statuses, so everything goes in as a 200 and the real
      // status travels in a header.
      status: 200,
      headers: {
        "Content-Type": "application/json; charset=utf-8",
        "Cache-Control": `public, max-age=${seconds}`,
        [statusHeader]: String(status),
        [ttlHeader]: String(seconds),
      },
    });
    const put = cache.put(new Request(key), store).catch(() => {});
    if (context.waitUntil) context.waitUntil(put);
    else await put;
  }

  function cachedResponse(status, body, context, state, seconds = cacheSeconds) {
    return new Response(body, {
      status,
      headers: {
        ...baseHeaders(context),
        "Cache-Control": `public, max-age=${seconds}`,
        [`${header}-Cache`]: state,
      },
    });
  }

  return { allowVisitor, visitorRetryAfter, allowUpstream, upstreamRetryAfter, readCache, writeCache, cachedResponse };
}
