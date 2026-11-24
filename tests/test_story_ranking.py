"""Ranking: news that never names its company, and stock-picking lists, sink; the score reads plainly."""

from pipeline.render import _plain_breakdown
from pipeline.score import STOCK_PICKING, is_named, score_item


def news(ticker, company, headline, summary="", category="Earnings & Financials"):
    return score_item({"ticker": ticker, "company_name": company, "source": "news_media", "category": category,
                       "headline": headline, "summary": summary, "published_date": "2026-11-01"})


def test_an_article_that_never_names_the_company_sinks():
    # Live on 2026-11-07: filed under NVIDIA, scored 10, about memory makers.
    off = news("NVDA", "NVIDIA Corporation", "Micron and Sandisk Lead the Memory Market. 1 Stock Has Far Greater Upside.",
               "SK Hynix is a clear leader in the memory market.")
    on = news("NVDA", "NVIDIA Corporation", "Nvidia reports record data center revenue")
    assert off["score"] <= 5 and "Not about the company: -4" in off["score_breakdown"]
    assert on["score"] - off["score"] >= 5


def test_named_only_in_the_text_is_neither_rewarded_nor_sunk():
    item = news("USB", "U.S. Bancorp", "Regional bank restarts buybacks", "U.S. Bancorp said it would resume buybacks.")
    assert "Not about the company" not in item["score_breakdown"] and "Headline: +1" not in item["score_breakdown"]


def test_filings_and_press_releases_are_never_marked_off_topic():
    item = score_item({"ticker": "NVDA", "company_name": "NVIDIA Corporation", "source": "sec_edgar",
                       "source_type": "regulatory_filing", "form_or_type": "8-K", "category": "Earnings & Financials",
                       "headline": "8-K: Results of Operations", "summary": "", "published_date": "2026-11-01"})
    assert "Not about the company" not in item["score_breakdown"]


def test_companies_are_recognised_the_way_headlines_write_them():
    assert is_named("Goldman Sachs raises its forecast", "GS", "The Goldman Sachs Group, Inc.")
    assert is_named("U.S. Bancorp Plans to Restart Buybacks", "USB", "U.S. Bancorp")
    assert is_named("Google buys a data center site", "GOOGL", "Alphabet Inc.")
    assert is_named("Disney+ adds subscribers", "DIS", "The Walt Disney Company")
    assert is_named("3M Rises 13.9% in the Past Year", "MMM", "3M Company")
    assert not is_named("Shoppers can't find deals", "T", "AT&T Inc.")
    assert not is_named("Prices hit a new low", "LOW", "Lowe's Companies, Inc.")
    assert not is_named("Southern California sees heavy rain", "SO", "The Southern Company")
    assert not is_named("Work from home is fading", "HD", "The Home Depot, Inc.")


def test_stock_picking_lists_and_roundups_are_marked():
    for headline in ("5 Best Stocks to Buy After Democrats’ Midterm Election Victory", "1 AI Stock I'll Buy Hand Over Fist",
                     "Micron vs. Nvidia: Which AI Stock Is a Better Buy for 2027?", "Stock Market Today, Nov. 6: AMD Surges 11%",
                     "If You Invested $100 In GE Aerospace Stock 5 Years Ago", "10 Latest Jim Cramer Stock Picks",
                     "Pfizer And 2 More AI Healthcare Stocks To Watch", "AT&T Stock Falls 11.8% in a Year: Should You Buy the Dip?"):
        assert STOCK_PICKING.search(headline), headline
    for headline in ("Lam Research Unleashes $25 Billion Stock Buyback",
                     "American Express’s CEO Sold $99 Million of Stock the Day Before the Crash",
                     "Nvidia reports record data center revenue", "Boeing to cut 10% of jobs"):
        assert not STOCK_PICKING.search(headline), headline
    picked = news("AMD", "Advanced Micro Devices, Inc.", "1 Reason to Buy AMD Stock Before 2027")
    assert "Stock picks: -3" in picked["score_breakdown"]


def test_the_score_is_explained_in_plain_words():
    text = _plain_breakdown("Base: 8 (Earnings & Financials) | Source: +1 (News Media / Press) | "
                            "Recency: +1 (under 24h old (+1)) | Headline: +1 (Named) => Score: 10.0")
    assert text == ("Earnings & Financials 8 · a news report on results, a deal or leadership +1 · "
                    "under 24 hours old +1 · names the company in the headline +1")
    assert "=>" not in text and "Base:" not in text
    assert _plain_breakdown("Base: 8 (Earnings & Financials) | Not about the company: -4 (Not named)").endswith(
        "doesn't name the company −4")


def test_without_a_company_name_nothing_is_marked_off_topic():
    item = score_item({"ticker": "BA", "source": "news_media", "category": "Regulation & Policy / Litigation",
                       "headline": "Boeing faces FAA grounding", "summary": ""})
    assert "Not about the company" not in item["score_breakdown"]


def test_where_a_story_is_from_reads_plainly():
    from pipeline.render import _source_line
    assert _source_line({"source": "sec_edgar", "source_label": "SEC EDGAR", "form_or_type": "4"}) == "SEC filing · Form 4"
    assert _source_line({"source": "sec_edgar", "form_or_type": "10-Q"}) == "SEC filing · 10-Q"
    assert _source_line({"source": "sec_edgar", "form_or_type": "SCHEDULE 13G/A"}) == "SEC filing · Schedule 13G/A"
    assert _source_line({"source": "company_ir", "source_label": "Company Release", "form_or_type": "PRESS_RELEASE"}) == "Press release"
    assert _source_line({"source": "news_media", "source_label": "News Media", "form_or_type": "Yahoo"}) == "Yahoo"
    assert _source_line({"source": "news_media", "source_label": "News Media", "form_or_type": "SeekingAlpha"}) == "Seeking Alpha"
    assert _source_line({"source": "news_media", "source_label": "News Media", "form_or_type": ""}) == "News Media"


def test_opinion_and_adverts_rank_below_reports():
    # Live on 2026-11-24, each scored 10 as news.
    for headline in ("Should You Swap Tech For Johnson & Johnson Stock?", "Is Lockheed Martin (LMT) Undervalued After Its New Cybersecurity Partnership?",
                     "Coca-Cola Stock Returned 40%. How Much Is Left?", "How Much RTX Do You Really Get Through 3 ETFs?"):
        item = news("JNJ", "Johnson & Johnson", headline, category="Regulation & Policy / Litigation")
        assert "Opinion: -2" in item["score_breakdown"], headline
    advert = news("ACN", "Accenture plc", "Global Regulatory Data Market Report 2026 | Capitalize on 18.3% CAGR")
    assert "Advert: -4" in advert["score_breakdown"]
    report = news("LLY", "Eli Lilly and Company", "Eli Lilly Acquires Huntington's Disease Drug Developer", category="M&A & Strategic Deals")
    assert "Opinion" not in report["score_breakdown"] and "Advert" not in report["score_breakdown"]
    assert "opinion: a question or a view on the price" in _plain_breakdown("Base: 7 (X) | Opinion: -2 (Question or price take)")


def test_a_teaser_pasted_under_many_stories_is_taken_out():
    from pipeline.normalize import shared_sentences, strip_sentences
    teaser = "Today's big story: Reported SEC Probe: Could Nvidia Stock Fall To $92."
    rows = [{"source": "news_media", "ticker": t, "headline": f"Story {i}", "summary": f"Real point number {i}. {teaser}"}
            for i, t in enumerate(["NVDA", "KO", "JNJ", "TSLA", "AMD"])]
    rows.append({"source": "news_media", "ticker": "NVDA", "headline": "Nvidia reinstates Huang", "summary": "The board voted to reinstate him."})
    keys = shared_sentences(rows)
    assert len(keys) == 1
    assert strip_sentences(rows[1]["summary"], keys) == "Real point number 1."
    assert strip_sentences(rows[-1]["summary"], keys) == rows[-1]["summary"]
    # Under fewer companies it may be a story they share, so it stays.
    assert not shared_sentences([dict(r, ticker="NVDA") for r in rows])


def test_rescoring_cleans_teasers_and_sorts_those_stories_again(tmp_path):
    from pipeline.persist import rescore_database_items, save_news_items, get_all_news_items
    db = str(tmp_path / "t.db")
    teaser = "Today's big story: Reported SEC Probe: Could Nvidia Stock Fall To $92."
    items = [{"item_uid": f"u{i}", "ticker": t, "company_name": n, "source": "news_media", "source_label": "News Media",
              "source_type": "press", "headline": h, "summary": teaser, "url": f"https://example.com/{i}",
              "published_date": "2026-11-23", "form_or_type": "Yahoo", "category": "Regulation & Policy / Litigation", "score": 10}
             for i, (t, n, h) in enumerate([("NVDA", "NVIDIA Corporation", "Why Motorola's Premium Over Cisco Is Harder To Justify"),
                                            ("KO", "The Coca-Cola Company", "Coca-Cola Stock Returned 40%"),
                                            ("JNJ", "Johnson & Johnson", "Johnson & Johnson wins a patent case"),
                                            ("TSLA", "Tesla, Inc.", "Tesla delivers trucks"),
                                            ("AMD", "Advanced Micro Devices, Inc.", "AMD ships a chip")])]
    save_news_items(items, db_path=db)
    rescore_database_items(db_path=db)
    rows = {r["ticker"]: r for r in get_all_news_items(db_path=db)}
    assert all(not r["summary"] for r in rows.values())
    assert rows["NVDA"]["score"] <= 2, rows["NVDA"]["score_breakdown"]  # never named Nvidia once the teaser is gone
    assert rows["NVDA"]["category"] != "Regulation & Policy / Litigation"


def test_feed_rows_say_what_kind_of_story_they_are():
    from pipeline.render import _mark_story
    news_item = _mark_story({"source": "news_media", "category": "Company Announcement", "score_breakdown": "Opinion: -2 (Question or price take)"})
    assert news_item["kind_label"] == "News" and news_item["is_opinion"]
    filing = _mark_story({"source": "company_ir", "category": "Company Announcement", "score_breakdown": ""})
    assert filing["kind_label"] == "Company Announcement" and not filing["is_opinion"]
