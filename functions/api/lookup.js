/**
 * Cloudflare Pages Function: /api/lookup
 * 
 * Lightweight serverless quick-lookup endpoint for any stock ticker or company name
 * outside the curated watchlist.
 * Calls Finnhub's /quote, /company-news, and /search (for company name to ticker resolution) live
 * and returns price + 2-3 recent headlines.
 * 
 * Query Parameters:
 *   - ticker, symbol, q, or query: Stock symbol or company name (e.g. NFLX, Netflix, TSM, Spotify, PLTR)
 * 
 * Response Format:
 *   {
 *     "found": true,
 *     "symbol": "NFLX",
 *     "company_name": "NETFLIX INC",
 *     "resolved_from": "Netflix",
 *     "price": {
 *       "current": 690.50,
 *       "change": 8.20,
 *       "change_pct": 1.20,
 *       "high": 695.10,
 *       "low": 685.80,
 *       "open": 688.00,
 *       "prev_close": 682.30,
 *       "timestamp": 1726430400
 *     },
 *     "headlines": [
 *       {
 *         "headline": "...",
 *         "url": "https://...",
 *         "source": "Reuters",
 *         "datetime": 1726425600,
 *         "time_ago": "2h ago",
 *         "summary": "..."
 *       }
 *     ],
 *     "queried_at": "2026-09-17T15:30:00.000Z"
 *   }
 */

export async function onRequestGet(context) {
  return handleLookup(context);
}

export async function onRequest(context) {
  if (context.request.method === "OPTIONS") {
    return new Response(null, {
      status: 204,
      headers: {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
      },
    });
  }
  return handleLookup(context);
}

async function handleLookup(context) {
  const url = new URL(context.request.url);
  const rawQuery = url.searchParams.get("ticker") || 
                   url.searchParams.get("symbol") || 
                   url.searchParams.get("q") || 
                   url.searchParams.get("query") || "";
  const query = rawQuery.trim();

  // Validate query parameter
  if (!query) {
    return new Response(
      JSON.stringify({
        error: "Invalid or missing query parameter. Provide a stock symbol or company name (e.g. ?ticker=NFLX or ?q=Netflix).",
        symbol: null,
        found: false,
      }),
      {
        status: 400,
        headers: {
          "Content-Type": "application/json",
          "Access-Control-Allow-Origin": "*",
        },
      }
    );
  }

  // Retrieve Finnhub API Key from Cloudflare Environment Bindings
  const apiKey = context.env?.FINNHUB_API_KEY || "";
  if (!apiKey) {
    return new Response(
      JSON.stringify({
        error: "FINNHUB_API_KEY environment variable is not configured on Cloudflare Pages.",
        symbol: query.toUpperCase(),
        found: false,
      }),
      {
        status: 500,
        headers: {
          "Content-Type": "application/json",
          "Access-Control-Allow-Origin": "*",
        },
      }
    );
  }

  const fetchOptions = {
    headers: {
      "User-Agent": "StockNewsDashboard-Lookup/1.0",
      "Accept": "application/json",
    },
  };

  const isDirectTickerCandidate = /^[A-Z0-9.\-]{1,6}$/i.test(query);
  let resolvedTicker = query.toUpperCase();
  let resolvedCompanyName = null;
  let resolvedFrom = null;

  try {
    let quote = null;
    let news = [];
    let needSymbolSearch = !isDirectTickerCandidate;

    // Helper to fetch quote and news for a specific ticker symbol
    async function fetchQuoteAndNews(sym) {
      const now = new Date();
      const toDate = now.toISOString().split("T")[0];
      const fromDateObj = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
      const fromDate = fromDateObj.toISOString().split("T")[0];

      const quoteUrl = `https://finnhub.io/api/v1/quote?symbol=${encodeURIComponent(sym)}&token=${encodeURIComponent(apiKey)}`;
      const newsUrl = `https://finnhub.io/api/v1/company-news?symbol=${encodeURIComponent(sym)}&from=${fromDate}&to=${toDate}&token=${encodeURIComponent(apiKey)}`;

      const [qRes, nRes] = await Promise.all([
        fetch(quoteUrl, fetchOptions),
        fetch(newsUrl, fetchOptions),
      ]);

      if (qRes.status === 401 || nRes.status === 401) {
        throw new Error("UNAUTHORIZED");
      }

      let qData = null;
      if (qRes.ok) {
        qData = await qRes.json();
      }

      let nData = [];
      if (nRes.ok) {
        const rawNews = await nRes.json();
        if (Array.isArray(rawNews)) {
          nData = rawNews;
        }
      }

      return { quote: qData, news: nData };
    }

    // 1. If candidate ticker format, attempt direct quote check
    if (isDirectTickerCandidate) {
      const res = await fetchQuoteAndNews(resolvedTicker);
      quote = res.quote;
      news = res.news;

      const hasValidPrice = quote && (quote.c !== 0 || quote.pc !== 0 || quote.h !== 0);
      const hasNews = news && news.length > 0;

      if (!hasValidPrice && !hasNews) {
        // Direct symbol returned no data, fallback to symbol search
        needSymbolSearch = true;
      }
    }

    // 2. Resolve company name to ticker via Finnhub symbol search endpoint (/search?q=...)
    if (needSymbolSearch) {
      const searchUrl = `https://finnhub.io/api/v1/search?q=${encodeURIComponent(query)}&token=${encodeURIComponent(apiKey)}`;
      const searchRes = await fetch(searchUrl, fetchOptions);

      if (searchRes.status === 401) {
        throw new Error("UNAUTHORIZED");
      }

      if (searchRes.ok) {
        const searchData = await searchRes.json();
        const results = Array.isArray(searchData?.result) ? searchData.result : [];

        if (results.length > 0) {
          // Priority matching:
          // 1) Exact symbol match
          // 2) US Common Stock / primary listing (no exchange dots like .TO, .L)
          // 3) Any Common Stock or EQS type
          // 4) First result
          const best = results.find(r => r.symbol && r.symbol.toUpperCase() === query.toUpperCase()) ||
                       results.find(r => r.type === "Common Stock" && !r.symbol.includes(".")) ||
                       results.find(r => (r.type === "Common Stock" || r.type === "EQS") && r.symbol) ||
                       results[0];

          if (best && best.symbol) {
            resolvedTicker = best.symbol.toUpperCase();
            resolvedCompanyName = best.description || null;
            resolvedFrom = query;

            const res = await fetchQuoteAndNews(resolvedTicker);
            quote = res.quote;
            news = res.news;
          }
        }
      }
    }

    // Finnhub returns all zeros for nonexistent/invalid stock symbols
    const hasValidPrice = quote && (quote.c !== 0 || quote.pc !== 0 || quote.h !== 0);
    const hasNews = news && news.length > 0;

    if (!hasValidPrice && !hasNews) {
      return new Response(
        JSON.stringify({
          found: false,
          symbol: resolvedTicker || query.toUpperCase(),
          resolved_from: resolvedFrom,
          message: `No quote or news found on Finnhub for "${query}".`,
        }),
        {
          status: 404,
          headers: {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Cache-Control": "public, max-age=60",
          },
        }
      );
    }

    // Extract top 2-3 most recent headlines
    const topHeadlines = (news || [])
      .filter((item) => item && item.headline && item.url)
      .slice(0, 3)
      .map((item) => {
        let timeAgo = "";
        if (item.datetime) {
          const diffSec = Math.floor(Date.now() / 1000 - item.datetime);
          if (diffSec < 60) timeAgo = "Just now";
          else if (diffSec < 3600) timeAgo = `${Math.floor(diffSec / 60)}m ago`;
          else if (diffSec < 86400) timeAgo = `${Math.floor(diffSec / 3600)}h ago`;
          else timeAgo = `${Math.floor(diffSec / 86400)}d ago`;
        }
        return {
          headline: item.headline.trim(),
          url: item.url,
          source: item.source || "Financial Press",
          datetime: item.datetime || null,
          time_ago: timeAgo,
          summary: item.summary ? item.summary.trim() : "",
        };
      });

    const responsePayload = {
      found: true,
      symbol: resolvedTicker,
      company_name: resolvedCompanyName,
      resolved_from: resolvedFrom,
      price: hasValidPrice
        ? {
            current: Number(quote.c) || 0,
            change: Number(quote.d) || 0,
            change_pct: Number(quote.dp) || 0,
            high: Number(quote.h) || 0,
            low: Number(quote.l) || 0,
            open: Number(quote.o) || 0,
            prev_close: Number(quote.pc) || 0,
            timestamp: quote.t || Math.floor(Date.now() / 1000),
          }
        : null,
      headlines: topHeadlines,
      queried_at: new Date().toISOString(),
    };

    return new Response(JSON.stringify(responsePayload), {
      status: 200,
      headers: {
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": "*",
        "Cache-Control": "public, max-age=60, s-maxage=120",
      },
    });
  } catch (err) {
    if (err.message === "UNAUTHORIZED") {
      return new Response(
        JSON.stringify({
          error: "Unauthorized: Invalid FINNHUB_API_KEY configured.",
          symbol: resolvedTicker,
          found: false,
        }),
        {
          status: 401,
          headers: {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
          },
        }
      );
    }

    return new Response(
      JSON.stringify({
        error: "Failed to fetch live data from Finnhub",
        details: err.message,
        symbol: resolvedTicker,
        found: false,
      }),
      {
        status: 502,
        headers: {
          "Content-Type": "application/json",
          "Access-Control-Allow-Origin": "*",
        },
      }
    );
  }
}
