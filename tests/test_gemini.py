"""Gemini: a model that exists, the key kept out of URLs, no invented numbers, and no wasted quota."""

import io
import json
import urllib.error
from unittest import mock

from pipeline import summarize as sm
from pipeline.persist import save_news_items
from pipeline.render import _ai_summary

KEY = "test-key-not-real"


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def info(self):
        return {}


def answer(obj):
    return FakeResponse(json.dumps({"candidates": [{"content": {"parts": [{"text": json.dumps(obj)}]}}]}).encode())


def http_error(code, message="nope"):
    return urllib.error.HTTPError("u", code, "err", {}, io.BytesIO(json.dumps({"error": {"message": message}}).encode()))


def story(uid, summary="Nxera to receive US$100 million upfront and up to US$1.37 billion in milestones.", score=8.0, form="news"):
    return {"item_uid": uid, "ticker": "ABBV", "company_name": "AbbVie", "headline": "AbbVie licenses Nxera drug",
            "summary": summary, "score": score, "published_date": "2026-11-05", "form_or_type": form,
            "source": "news_media", "source_label": "News", "source_type": "news", "url": "https://x.test/" + uid}


def test_newest_stable_flash_model_is_chosen():
    models = {"models": [
        {"name": "models/gemini-2.0-flash", "supportedGenerationMethods": ["generateContent"]},
        {"name": "models/gemini-3.0-flash", "supportedGenerationMethods": ["generateContent"]},
        {"name": "models/gemini-3.5-flash-preview-05-20", "supportedGenerationMethods": ["generateContent"]},
        {"name": "models/gemini-3.5-flash-lite", "supportedGenerationMethods": ["generateContent"]},
        {"name": "models/gemini-3.5-flash-image", "supportedGenerationMethods": ["generateContent"]},
        {"name": "models/text-embedding-004", "supportedGenerationMethods": ["embedContent"]},
    ]}
    with mock.patch.dict("os.environ", {"GEMINI_MODEL": ""}), \
         mock.patch("urllib.request.urlopen", return_value=FakeResponse(json.dumps(models).encode())):
        assert sm.choose_gemini_model(KEY) == "gemini-3.0-flash"


def test_configured_model_wins_without_a_request():
    with mock.patch.dict("os.environ", {"GEMINI_MODEL": "gemini-x-flash"}), mock.patch("urllib.request.urlopen") as op:
        assert sm.choose_gemini_model(KEY) == "gemini-x-flash"
        op.assert_not_called()


def test_key_travels_in_a_header_never_the_url():
    seen = []

    def capture(req, timeout=0):
        seen.append(req)
        return answer({"a": "Nxera gets US$100 million upfront."})

    with mock.patch("urllib.request.urlopen", side_effect=capture):
        sm.summarize_batch_with_gemini([story("a")], KEY, model="gemini-test-flash")
    assert KEY not in seen[0].full_url
    assert seen[0].get_header("X-goog-api-key") == KEY


def test_summary_with_a_number_not_in_the_source_is_dropped():
    reply = {"a": "Nxera receives US$100 million upfront, up to US$1.37 billion later.",
             "b": "Nxera receives US$150 million upfront."}
    with mock.patch("urllib.request.urlopen", return_value=answer(reply)):
        kept = sm.summarize_batch_with_gemini([story("a"), story("b")], KEY, model="m")
    assert kept == {"a": reply["a"]}


def test_grounding_ignores_thousands_separators():
    assert sm.grounded("Sold 2,399 shares", "sold 2399 shares at $325.75")
    assert not sm.grounded("Sold 2,400 shares", "sold 2399 shares")


def test_a_retired_model_stops_the_run_after_one_request():
    calls = []

    def fail(req, timeout=0):
        calls.append(req)
        raise http_error(404, "models/gemini-2.5-flash is not found for API version v1beta")

    items = [story(str(i)) for i in range(60)]
    with mock.patch.dict("os.environ", {"GEMINI_MODEL": "gemini-2.5-flash"}), \
         mock.patch("urllib.request.urlopen", side_effect=fail), mock.patch("time.sleep"):
        out = sm.summarize_items(items, api_key=KEY)
    assert len(calls) == 1
    assert all(it["summary_origin"] == "template" and it["llm_summary"] for it in out)


def test_insider_forms_and_bare_filings_are_not_sent():
    items = [story("f4", form="4"), story("sec", summary="Official SEC submission (8-K). Accession: 1"), story("n")]
    sent = []

    def capture(req, timeout=0):
        sent.append(json.loads(req.data)["contents"][0]["parts"][0]["text"])
        return answer({"n": "Nxera gets US$100 million upfront."})

    with mock.patch.dict("os.environ", {"GEMINI_MODEL": "m"}), mock.patch("urllib.request.urlopen", side_effect=capture):
        out = sm.summarize_items(items, api_key=KEY)
    assert len(sent) == 1 and '"f4"' not in sent[0] and '"sec"' not in sent[0]
    assert {it["item_uid"]: it["summary_origin"] for it in out} == {"f4": "template", "sec": "template", "n": "ai:m"}


def test_stories_summarized_on_an_earlier_run_are_not_sent_again(tmp_path):
    db = str(tmp_path / "t.db")
    first = [story("a")]
    with mock.patch.dict("os.environ", {"GEMINI_MODEL": "m"}), \
         mock.patch("urllib.request.urlopen", return_value=answer({"a": "Nxera gets US$100 million upfront."})):
        sm.summarize_items(first, api_key=KEY, db_path=db)
    save_news_items(first, db_path=db)

    again = [story("a")]
    with mock.patch.dict("os.environ", {"GEMINI_MODEL": "m"}), mock.patch("urllib.request.urlopen") as op:
        sm.summarize_items(again, api_key=KEY, db_path=db)
        op.assert_not_called()
    assert again[0]["llm_summary"] == "Nxera gets US$100 million upfront."
    assert again[0]["summary_origin"] == "ai:m"


def test_per_run_cap_spends_quota_on_the_highest_scores_first():
    items = [story(f"s{i}", score=i) for i in range(10)]
    sent = []

    def capture(req, timeout=0):
        sent.append(req.data.decode())
        return answer({})

    with mock.patch.dict("os.environ", {"GEMINI_MODEL": "m", "GEMINI_MAX_BATCHES": "1"}), \
         mock.patch("urllib.request.urlopen", side_effect=capture):
        sm.summarize_items(items, api_key=KEY, batch_size=3)
    assert len(sent) == 1
    assert '\\"s9\\"' in sent[0] or '"s9"' in sent[0]
    assert '"s0"' not in sent[0] and '\\"s0\\"' not in sent[0]


def test_site_only_shows_checked_ai_summaries():
    assert _ai_summary({"llm_summary": "Nxera gets US$100 million.", "summary_origin": "ai:m"}) == "Nxera gets US$100 million."
    assert _ai_summary({"llm_summary": "Antitrust regulatory scrutiny.", "summary_origin": "template"}) == ""
    assert _ai_summary({"llm_summary": "Antitrust regulatory scrutiny."}) == ""


def test_bold_figures_leave_sentence_punctuation_outside():
    from pipeline.render import _figures_html
    html = str(_figures_html("EPS $5.06, up from $1.82. Sales rose 12 percent."))
    assert '<strong class="fig">$5.06</strong>,' in html
    assert '<strong class="fig">$1.82</strong>.' in html
    assert '<strong class="fig">12 percent</strong>' in html


def test_economy_line_uses_the_header_key_and_drops_invented_numbers():
    from pipeline.economic import generate_economic_synthesis
    seen = []

    def reply(req, timeout=0):
        seen.append(req)
        return answer_text("Rates at 4.25% could lift borrowing costs 30% for NVDA.")

    def answer_text(t):
        return FakeResponse(json.dumps({"candidates": [{"content": {"parts": [{"text": t}]}}]}).encode())

    with mock.patch.dict("os.environ", {"GEMINI_MODEL": "m-econ"}), mock.patch("urllib.request.urlopen", side_effect=reply):
        line = generate_economic_synthesis("interest_rates", "Fed funds rate", "4.25%", "up", 0.25, ["NVDA"], api_key=KEY)
    assert KEY not in seen[0].full_url
    assert "30%" not in line  # 30 was not in the prompt, so the plain fallback is used
