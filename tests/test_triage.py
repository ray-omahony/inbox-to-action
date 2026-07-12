"""Tests for the triage pipeline's failure paths and digest rendering.

Every test here runs offline: the Anthropic client is replaced with a
mock, so the suite is free, fast, and deterministic. The cases come
straight from code-review findings — each one reproduces a bug that
existed (or nearly existed) at some point, which is what regression
tests are for.

Run: .venv/bin/python -m pytest
"""

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

import triage

SAMPLES = Path(__file__).resolve().parent.parent / "samples"


def make_client(payload: str, stop_reason: str = "end_turn") -> MagicMock:
    """A fake Anthropic client whose every call returns `payload` as text."""
    block = MagicMock()
    block.type = "text"
    block.text = payload
    response = MagicMock()
    response.content = [block]
    response.stop_reason = stop_reason
    response.usage.input_tokens = 100
    response.usage.output_tokens = 50
    client = MagicMock()
    client.messages.create.return_value = response
    return client


def valid_payload(**overrides) -> str:
    """A minimal model response containing every required key."""
    record = {
        "summary": "An invoice for 100 euro.",
        "category": "invoice",
        "urgency": "medium",
        "urgency_reason": "Due in two weeks.",
        "suggested_action": "Schedule payment.",
        "key_dates": ["2026-07-25"],
        "confidence": "high",
    }
    record.update(overrides)
    return json.dumps(record)


# --- triage_document: bad model responses must flag, never crash ---------


def test_non_dict_json_becomes_review_record():
    client = make_client('["not", "a", "dict"]')
    result = triage.triage_document(client, "t", "doc.txt", "body")
    assert result["needs_review"] is True
    assert client.messages.create.call_count == 2  # one retry, then flag


def test_non_string_urgency_becomes_review_record():
    client = make_client(valid_payload(urgency=["high"]))
    result = triage.triage_document(client, "t", "doc.txt", "body")
    assert result["needs_review"] is True
    assert "urgency must be a string" in result["summary"]


def test_truncated_response_names_the_real_cause():
    client = make_client('{"summary": "cut off', stop_reason="max_tokens")
    result = triage.triage_document(client, "t", "doc.txt", "body")
    assert result["needs_review"] is True
    # The human should be told about the token limit, not "invalid JSON".
    assert "max_tokens" in result["summary"]


def test_model_cannot_spoof_needs_review():
    client = make_client(valid_payload(needs_review=True))
    result = triage.triage_document(client, "t", "doc.txt", "body")
    assert result["needs_review"] is False  # bookkeeping fields are ours


# --- fill_template: prompt assembly --------------------------------------


def test_fill_template_substitutes_today_and_keeps_json_braces():
    from datetime import date

    template = 'Today is {today}. {"example": "braces survive"} File: {filename}\n{document_text}'
    filled = triage.fill_template(template, "a.txt", "hello")
    assert date.today().isoformat() in filled
    assert '{"example": "braces survive"}' in filled  # str.format would choke here
    assert "{today}" not in filled and "{filename}" not in filled


def test_prompt_file_contains_all_placeholders():
    # The template lives outside the code — this catches someone editing
    # the .md file and breaking the contract fill_template relies on.
    template = triage.load_prompt_template()
    for placeholder in ("{today}", "{filename}", "{document_text}"):
        assert placeholder in template


# --- extract_text: the translation boundary ------------------------------


def test_corrupt_pdf_raises_value_error_only():
    with pytest.raises(ValueError, match="unreadable PDF"):
        triage.extract_text(SAMPLES / "corrupt.pdf")


# --- triage_folder: the shared CLI/MCP pipeline ---------------------------


def test_triage_folder_mixes_success_and_review(tmp_path):
    (tmp_path / "good.txt").write_text("An invoice for 100 euro due soon.")
    (tmp_path / "bad.xyz").write_text("unsupported extension")
    (tmp_path / ".DS_Store").write_text("macos noise")
    client = make_client(valid_payload())
    results = triage.triage_folder(client, tmp_path)
    by_name = {r["filename"]: r for r in results}
    assert set(by_name) == {"good.txt", "bad.xyz"}  # dotfile skipped
    assert by_name["good.txt"]["needs_review"] is False
    assert by_name["bad.xyz"]["needs_review"] is True  # flagged, not dropped


# --- build_digest: rendering must survive whatever reaches it ------------


def test_digest_sorts_urgent_first_and_marks_review_items():
    results = [
        json.loads(valid_payload(urgency="low")) | {"filename": "b_low.txt"},
        triage.review_record("a_failed.pdf", "unreadable"),
        json.loads(valid_payload(urgency="high")) | {"filename": "c_high.txt"},
    ]
    digest = triage.build_digest(results)
    order = [
        digest.index("a_failed.pdf"),  # high + alphabetically first
        digest.index("c_high.txt"),
        digest.index("b_low.txt"),
    ]
    assert order == sorted(order)
    assert "NEEDS HUMAN REVIEW" in digest
    assert "1 needs review" in digest


def test_digest_empty_results_is_still_a_valid_document():
    digest = triage.build_digest([])
    assert "No documents were processed." in digest
    assert "0 documents processed" in digest


def test_digest_renders_string_key_dates_instead_of_dropping():
    record = json.loads(valid_payload(key_dates="2026-08-01"))
    record["filename"] = "doc.txt"
    digest = triage.build_digest([record])
    assert "2026-08-01" in digest
