/**
 * Cloudflare Pages Function: /api/lookup
 * 
 * Lightweight serverless quick-lookup endpoint for any stock ticker outside the curated watchlist.
 * Calls Finnhub's /quote and /company-news endpoints live and returns price + 2-3 recent headlines.
 * 
 * Query Parameters:
 *   - ticker (or symbol): Stock symbol string (e.g. TSM, PLTR, NFLX, ARM, COIN)
 * 
 * Response Format:
 *   {
 *     "found": true,
 *     "symbol": "TSM",
 *     "price": {
 *       "current": 172.50,
 *       "change": 3.20,
 *       "change_pct": 1.89,
 *       "high": 174.10,
 *       "low": 170.80,
 *       "open": 171.00,
 *       "prev_close": 169.30,
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
 *     "queried_at": "2026-09-15T15:30:00.000Z"
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
  const rawTicker = url.searchParams.get("ticker") || url.searchParams.get("symbol") || "";
  const ticker = rawTicker.trim().toUpperCase();

  // Validate ticker format (1 to 10 alphanumeric characters, dots, or hyphens)
  if (!ticker || !/^[A-Z0-9.\-]{1,10}$/.test(ticker)) {
    return new Response(
      JSON.stringify({
        error: "Invalid or missing ticker parameter. Provide a valid stock symbol (e.g. ?ticker=TSM).",
        symbol: ticker || null,
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
        symbol: ticker,
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

  // Calculate past 7-day date window for Finnhub company news
  const now = new Date();
  const toDate = now.toISOString().split("T")[0];
  const fromDateObj = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
  const fromDate = fromDateObj.toISOString().split("T")[0];

  const quoteUrl = `https://finnhub.io/api/v1/quote?symbol=${encodeURIComponent(ticker)}&token=${encodeURIComponent(apiKey)}`;
  const newsUrl = `https://finnhub.io/api/v1/company-news?symbol=${encodeURIComponent(ticker)}&from=${fromDate}&to=${toDate}&token=${encodeURIComponent(apiKey)}`;

  try {
    const fetchOptions = {
      headers: {
        "User-Agent": "StockNewsDashboard-Lookup/1.0",
        "Accept": "application/json",
      },
    };

    // Execute quote and news calls in parallel
    const [quoteRes, newsRes] = await Promise.all([
      fetch(quoteUrl, fetchOptions),
      fetch(newsUrl, fetchOptions),
    ]);

    // Handle authentication failures
    if (quoteRes.status === 401 || newsRes.status === 401) {
      return new Response(
        JSON.stringify({
          error: "Unauthorized: Invalid FINNHUB_API_KEY configured.",
          symbol: ticker,
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

    let quote = null;
    if (quoteRes.ok) {
      quote = await quoteRes.json();
    }

    let news = [];
    if (newsRes.ok) {
      const rawNews = await newsRes.json();
      if (Array.isArray(rawNews)) {
        news = rawNews;
      }
    }

    // Finnhub returns all zeros for nonexistent/invalid stock symbols
    const hasValidPrice = quote && (quote.c !== 0 || quote.pc !== 0 || quote.h !== 0);
    const hasNews = news && news.length > 0;

    if (!hasValidPrice && !hasNews) {
      return new Response(
        JSON.stringify({
          found: false,
          symbol: ticker,
          message: `No quote or news found on Finnhub for symbol "${ticker}".`,
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
      symbol: ticker,
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
    return new Response(
      JSON.stringify({
        error: "Failed to fetch live data from Finnhub",
        details: err.message,
        symbol: ticker,
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
