import asyncio
import json

import pytest

from app.schemas.bug import BugReportCreate
from app.services import llm_analyzer


BUG = BugReportCreate(
    title="Login fails",
    description="Cannot sign in",
    steps_to_reproduce=["Open login", "Submit"],
    expected_result="Dashboard opens",
    actual_result="Error appears",
)


@pytest.mark.parametrize(
    "response",
    [
        {},
        {"message": {"content": ""}},
        {"message": {"content": "not json"}},
        {"message": {"content": '{"severity": "HIGH"}'}},
    ],
)
def test_empty_or_invalid_llm_response_raises(monkeypatch, response) -> None:
    monkeypatch.setattr(llm_analyzer, "_call_ollama", lambda payload: response)

    with pytest.raises(RuntimeError):
        asyncio.run(llm_analyzer.analyze_with_llm(BUG))


ANALYSIS_FIELDS = {
    "severity": "LOW",
    "priority": "P4",
    "category": "General",
    "impact": "None",
    "possible_root_cause": "None",
    "suggested_test_scenarios": [],
    "missing_information": [],
    "confidence": 0.1,
}


def llm_message(content: dict) -> dict:
    return {"message": {"content": json.dumps(content)}}


def validity(language="English", valid=True, reason="") -> dict:
    return llm_message(
        {
            "report_language": language,
            "is_valid_bug_report": valid,
            "invalid_reason": reason,
        }
    )


def fake_ollama(monkeypatch, *responses) -> list[dict]:
    """Answer successive Ollama calls in order and record their payloads."""
    payloads = []

    def fake_call_ollama(payload):
        payloads.append(payload)
        return responses[len(payloads) - 1]

    monkeypatch.setattr(llm_analyzer, "_call_ollama", fake_call_ollama)
    return payloads


class FakeUpload:
    def __init__(self, content: bytes) -> None:
        self.content = content

    async def read(self) -> bytes:
        return self.content


def test_invalid_bug_report_is_rejected_before_analysis(monkeypatch) -> None:
    payloads = fake_ollama(
        monkeypatch,
        validity(valid=False, reason="The text is a cake recipe, not a bug report."),
    )

    with pytest.raises(llm_analyzer.InvalidBugReportError) as error:
        asyncio.run(llm_analyzer.analyze_with_llm(BUG))

    assert str(error.value) == "The text is a cake recipe, not a bug report."
    assert len(payloads) == 1


def test_analysis_is_written_in_the_detected_language(monkeypatch) -> None:
    payloads = fake_ollama(
        monkeypatch, validity(language="German"), llm_message(ANALYSIS_FIELDS)
    )

    analysis = asyncio.run(llm_analyzer.analyze_with_llm(BUG))

    validity_call, analysis_call = payloads
    assert "report_language" in validity_call["format"]["properties"]
    assert "Write all free-text values in German" in (
        analysis_call["messages"][0]["content"]
    )
    assert analysis.severity == "LOW"


def test_screenshot_is_only_sent_with_the_analysis(monkeypatch) -> None:
    payloads = fake_ollama(
        monkeypatch,
        validity(language="Turkish"),
        llm_message(
            {
                **ANALYSIS_FIELDS,
                "screenshot_matches_report": True,
                "confidence": 0.9,
                "visual_evidence": "The screenshot shows the disabled button.",
            }
        ),
    )

    analysis = asyncio.run(
        llm_analyzer.analyze_with_llm(BUG, [FakeUpload(b"image-bytes")])
    )

    validity_call, analysis_call = payloads
    assert validity_call["messages"][0]["images"] == []
    assert analysis_call["messages"][0]["images"] != []
    assert "Write all free-text values in Turkish" in (
        analysis_call["messages"][0]["content"]
    )
    assert analysis.visual_evidence == "The screenshot shows the disabled button."
    assert analysis.confidence == 0.9


def test_mismatched_screenshot_caps_confidence(monkeypatch) -> None:
    fake_ollama(
        monkeypatch,
        validity(),
        llm_message(
            {
                **ANALYSIS_FIELDS,
                "screenshot_matches_report": False,
                "confidence": 0.95,
                "visual_evidence": "The screenshot shows a login page.",
            }
        ),
    )

    analysis = asyncio.run(
        llm_analyzer.analyze_with_llm(BUG, [FakeUpload(b"image-bytes")])
    )

    assert analysis.confidence == 0.6
