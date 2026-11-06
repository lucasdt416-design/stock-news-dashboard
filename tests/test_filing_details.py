"""Filings show what's in them: insider trades, planned sales, 8-K text and report figures."""

import json
from datetime import date, timedelta
from unittest import mock

from collectors import edgar_details as ed
from pipeline.normalize import normalize_edgar_item

FORM4 = """<?xml version="1.0"?><ownershipDocument>
<reportingOwner><reportingOwnerId><rptOwnerName>Newstead Jennifer</rptOwnerName></reportingOwnerId>
<reportingOwnerRelationship><isDirector>false</isDirector><isOfficer>true</isOfficer>
<officerTitle>SVP, GC and Government Affairs</officerTitle></reportingOwnerRelationship></reportingOwner>
<aff10b5One>true</aff10b5One>
<nonDerivativeTable>
<nonDerivativeTransaction><transactionCoding><transactionCode>M</transactionCode></transactionCoding>
<transactionAmounts><transactionShares><value>1714</value></transactionShares>
<transactionPricePerShare><value>0</value></transactionPricePerShare></transactionAmounts>
<postTransactionAmounts><sharesOwnedFollowingTransaction><value>31711</value></sharesOwnedFollowingTransaction></postTransactionAmounts>
</nonDerivativeTransaction>
<nonDerivativeTransaction><transactionCoding><transactionCode>S</transactionCode></transactionCoding>
<transactionAmounts><transactionShares><value>2399</value></transactionShares>
<transactionPricePerShare><value>325.75</value></transactionPricePerShare></transactionAmounts>
<postTransactionAmounts><sharesOwnedFollowingTransaction><value>29997</value></sharesOwnedFollowingTransaction></postTransactionAmounts>
</nonDerivativeTransaction>
</nonDerivativeTable></ownershipDocument>"""

FORM144 = """<?xml version="1.0" encoding="UTF-8"?><edgarSubmission xmlns="http://www.sec.gov/edgar/ownership">
<formData><issuerInfo><nameOfPersonForWhoseAccountTheSecuritiesAreToBeSold>Newstead Jennifer</nameOfPersonForWhoseAccountTheSecuritiesAreToBeSold>
<relationshipsToIssuer><relationshipToIssuer>Officer</relationshipToIssuer></relationshipsToIssuer></issuerInfo>
<securitiesInformation><noOfUnitsSold>1392</noOfUnitsSold><aggregateMarketValue>476064.00</aggregateMarketValue>
<approxSaleDate>10/16/2026</approxSaleDate></securitiesInformation>
<noticeSignature><planAdoptionDates><planAdoptionDate>11/21/2025</planAdoptionDate></planAdoptionDates></noticeSignature>
</formData></edgarSubmission>"""


def test_insider_sale_names_the_person_role_shares_price_and_value():
    headline, text = ed.describe_form4(FORM4)
    assert headline == "insider Jennifer Newstead sells $781,474 of stock"
    assert text.startswith("Jennifer Newstead (SVP, GC and Government Affairs) sold 2,399 shares at $325.75, about $781,474")
    assert "pre-arranged trading plan" in text
    assert "Also exercised options for 1,714 shares." in text
    assert text.endswith("Now holds 29,997 shares.")


def test_options_only_filing_does_not_claim_a_sale():
    xml = FORM4.replace("<transactionCode>S</transactionCode>", "<transactionCode>F</transactionCode>")
    headline, text = ed.describe_form4(xml)
    assert "sell" not in headline and "sold" not in text
    assert headline == "insider Jennifer Newstead exercises options for 1,714 shares"
    assert "trading plan" not in text  # only said for open-market trades


def test_unreadable_xml_gives_nothing_rather_than_filler():
    assert ed.describe_form4("<not xml") == ("", "")
    assert ed.describe_form144("") == ("", "")


def test_planned_sale_reads_namespaced_xml():
    headline, text = ed.describe_form144(FORM144)
    assert "plans to sell 1,392 shares, worth about $476,064, around Oct 16, 2026" in text
    assert "trading plan adopted Nov 21, 2025" in text
    assert "$476,064 share sale" in headline


def test_planned_sale_uses_the_form4_spelling_of_the_same_person():
    filings = [
        {"detail_headline": "insider Newstead Jennifer plans $476,064 share sale", "detail_text": "Newstead Jennifer (Officer) plans to sell"},
        {"detail_headline": "insider Jennifer Newstead sells $781,474 of stock"},
    ]
    ed._match_planned_sale_names(filings)
    assert filings[0]["detail_headline"].startswith("insider Jennifer Newstead plans")
    assert filings[0]["detail_text"].startswith("Jennifer Newstead (Officer)")


def test_eight_k_items_in_plain_english():
    assert ed.item_labels("2.02,9.01") == ["Quarterly results"]
    assert ed.item_labels("5.02,7.01") == ["Director or executive change", "Investor disclosure"]
    assert ed.item_labels("") == []


def test_press_release_excerpt_skips_headings_quotes_footnotes_and_boilerplate():
    page = """<html><head><title>x</title></head><body>
    <p>Apple Reports Fourth Quarter Results September Quarter Records For Total Company Revenue And EPS</p>
    <p>CUPERTINO, CALIFORNIA — Apple today announced financial results for its fiscal 2026 fourth quarter. The Company posted quarterly revenue of $114.5 billion, up 12 percent year over year.</p>
    <p>“Today, Apple is proud to report a September quarter revenue record, capping off our best fiscal year ever,” said the CEO of the company.</p>
    <p>5 Non-GAAP financial measure; defined as cash flow from operating activities, less additions to property, plant and equipment.</p>
    <p>This press release contains forward-looking statements, within the meaning of the Private Securities Litigation Reform Act of 1995.</p>
    <p>Diluted earnings per share was $2.10, up 14 percent year over year, and the board declared a cash dividend of $0.27 per share.</p>
    </body></html>"""
    text = ed.excerpt(ed.html_paragraphs(page))
    assert text.startswith("CUPERTINO")
    assert "$114.5 billion" in text and "$2.10" in text
    assert "proud" not in text and "forward-looking" not in text and "Non-GAAP" not in text
    assert "Fourth Quarter Results September" not in text


def _concept(accn, rows):
    return {"units": {"USD": [{"accn": accn, "start": s, "end": e, "val": v} for s, e, v in rows]}}


def test_report_figures_come_from_that_filing_with_year_on_year_change():
    acc = "0000320193-26-000026"
    concepts = {
        "RevenueFromContractWithCustomerExcludingAssessedTax": _concept(acc, [
            ("2025-09-28", "2026-09-26", 478834000000), ("2024-09-29", "2025-09-27", 416161000000),
        ]),
        "NetIncomeLoss": _concept(acc, [("2025-09-28", "2026-09-26", 132175000000), ("2024-09-29", "2025-09-27", 112010000000)]),
        "EarningsPerShareDiluted": {"units": {"USD/shares": [
            {"accn": acc, "start": "2025-09-28", "end": "2026-09-26", "val": 8.98},
            {"accn": acc, "start": "2024-09-29", "end": "2025-09-27", "val": 7.46},
            {"accn": "someone-else", "start": "2025-09-28", "end": "2026-09-26", "val": 99.0},
        ]}},
    }
    headline, text = ed.describe_financials(concepts, acc, "10-K")
    assert headline == "annual report: revenue $478.8 billion, up 15%"
    assert text.startswith("Year ended Sep 26, 2026: revenue $478.8 billion, up 15%; net income $132.2 billion, up 18%; diluted earnings per share $8.98, up 20%.")
    assert "99" not in text


def test_quarterly_report_uses_the_three_month_figure_not_year_to_date():
    acc = "a-1"
    concepts = {"Revenues": _concept(acc, [
        ("2026-07-01", "2026-09-30", 24.2e9), ("2026-01-01", "2026-09-30", 70e9), ("2025-07-01", "2025-09-30", 23.3e9),
    ]), "NetIncomeLoss": _concept(acc, [("2026-07-01", "2026-09-30", -116e6), ("2025-07-01", "2025-09-30", 50e6)])}
    headline, text = ed.describe_financials(concepts, acc, "10-Q")
    assert "revenue $24.2 billion, up 4%" in text
    assert "net loss $116.0 million" in text
    assert "70" not in text


def test_normalized_filing_shows_the_detail_instead_of_the_accession_number():
    raw = {"ticker": "AAPL", "company_name": "Apple Inc.", "form": "4", "accession_number": "0001-26-1",
           "url": "https://www.sec.gov/x", "filing_date": "2026-11-05",
           "detail_headline": "insider Jennifer Newstead sells $781,474 of stock", "detail_text": "Jennifer Newstead sold 2,399 shares."}
    item = normalize_edgar_item(raw)
    assert item["headline"] == "Apple Inc. insider Jennifer Newstead sells $781,474 of stock"
    assert item["summary"] == "Jennifer Newstead sold 2,399 shares."
    plain = normalize_edgar_item({k: v for k, v in raw.items() if not k.startswith("detail")})
    assert plain["summary"].startswith("Official SEC submission")
    assert plain["item_uid"] == item["item_uid"]  # same story, so the old row is updated, not duplicated


def test_each_filing_is_fetched_once_then_read_from_the_cache(tmp_path):
    db = str(tmp_path / "t.db")
    today = date.today().isoformat()
    filing = {"form": "4", "cik": "0000320193", "accession_number": "0001140361-26-042149",
              "primary_doc_name": "xslF345X06/form4.xml", "filing_date": today}
    calls = []

    def fake_get(self, url, timeout=20):
        calls.append(url)
        self.left -= 1
        return FORM4

    with mock.patch.object(ed._Fetcher, "get", fake_get):
        first = [dict(filing)]
        ed.enrich_filings(first, db_path=db)
        second = [dict(filing)]
        ed.enrich_filings(second, db_path=db)
    assert calls == ["https://www.sec.gov/Archives/edgar/data/320193/000114036126042149/form4.xml"]
    assert first[0]["detail_text"] == second[0]["detail_text"]
    assert "2,399 shares" in second[0]["detail_text"]


def test_network_failure_is_retried_next_run_and_old_filings_are_left_alone(tmp_path):
    db = str(tmp_path / "t.db")
    old = (date.today() - timedelta(days=400)).isoformat()
    filings = [
        {"form": "4", "cik": "1", "accession_number": "a", "primary_doc_name": "f.xml", "filing_date": date.today().isoformat()},
        {"form": "4", "cik": "1", "accession_number": "b", "primary_doc_name": "f.xml", "filing_date": old},
    ]
    calls = []

    def failing(self, url, timeout=20):
        calls.append(url)
        return None

    with mock.patch.object(ed._Fetcher, "get", failing):
        ed.enrich_filings(filings, db_path=db)
    assert len(calls) == 1  # the 400-day-old filing wasn't fetched
    assert "detail_text" not in filings[0]
    assert ed._load_cache(db) == {}  # nothing cached, so it's tried again


def test_request_budget_is_respected():
    f = ed._Fetcher("ua", 0, max_requests=0)
    assert f.get("https://www.sec.gov/anything") is None


def test_grant_only_form4_describes_the_units():
    xml = """<ownershipDocument><reportingOwner><reportingOwnerId><rptOwnerName>Khan Sabih</rptOwnerName></reportingOwnerId>
    <reportingOwnerRelationship><isOfficer>1</isOfficer><officerTitle>COO</officerTitle></reportingOwnerRelationship></reportingOwner>
    <derivativeTable><derivativeTransaction><securityTitle><value>Restricted Stock Unit</value></securityTitle>
    <transactionCoding><transactionCode>A</transactionCode></transactionCoding>
    <transactionAmounts><transactionShares><value>47645</value></transactionShares></transactionAmounts>
    </derivativeTransaction></derivativeTable></ownershipDocument>"""
    headline, text = ed.describe_form4(xml)
    assert headline == "insider Sabih Khan is granted 47,645 restricted stock units"
    assert text == "Sabih Khan (COO) was granted 47,645 restricted stock units."


def test_huge_change_from_a_tiny_base_shows_the_earlier_figure_instead():
    acc = "x"
    concepts = {"NetIncomeLoss": _concept(acc, [("2026-07-01", "2026-09-30", 4.2e9), ("2025-07-01", "2025-09-30", 185e6)])}
    _, text = ed.describe_financials(concepts, acc, "10-Q")
    assert "net income $4.2 billion, up from $185.0 million" in text
    assert "%" not in text


def test_lettered_paragraph_in_an_8k_body_is_kept():
    paras = ["Item 5.02. Departure of Directors or Certain Officers",
             "(b) On November 4, 2026, a member of the Board of Directors informed the Company that she will not stand for re-election at the annual meeting."]
    text = ed.excerpt(paras, skip_until=__import__("re").compile(r"(?i)^item\s+[1-8]\.\d\d"))
    assert text.startswith("On November 4, 2026")


def test_line_broken_filing_text_is_rejoined_into_sentences():
    page = ("<div>Item 8.01 Other Events.</div><div>On November 3, 2026, The Procter &amp; Gamble Company closed an underwritten public</div>"
            "<div>offering of &#8364;750,000,000 aggregate principal amount of 3.750% Notes due November 3, 2030, under its</div>"
            "<div>registration statement, and the opinions are incorporated herein by reference.</div>")
    text = ed.excerpt(ed.html_paragraphs(page), skip_until=__import__("re").compile(r"(?i)^item\s+[1-8]\.\d\d"))
    assert "closed an underwritten public offering of €750,000,000 aggregate principal amount of 3.750% Notes" in text


def test_viewer_links_point_at_the_document():
    row = '<tr><td>1</td><td>x</td><td><a href="/ix?doc=/Archives/edgar/data/1/2/ex99.htm">ex99.htm</a></td><td>EX-99.1</td></tr>'
    assert ed.exhibit_documents(row) == [("EX-99.1", "/Archives/edgar/data/1/2/ex99.htm")]
