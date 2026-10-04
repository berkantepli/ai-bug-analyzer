import asyncio
import json
import socket
import time
from io import BytesIO
from urllib.error import HTTPError, URLError

import pytest

from app.config import OLLAMA_CONTEXT_LENGTH
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


def test_every_request_uses_the_configured_context_length(monkeypatch) -> None:
    payloads = fake_ollama(monkeypatch, validity(), llm_message(ANALYSIS_FIELDS))

    asyncio.run(llm_analyzer.analyze_with_llm(BUG))

    assert [payload["options"]["num_ctx"] for payload in payloads] == [
        OLLAMA_CONTEXT_LENGTH,
        OLLAMA_CONTEXT_LENGTH,
    ]


def test_context_overflow_becomes_a_clear_error(monkeypatch) -> None:
    body = (
        b'{"error": "request (20000 tokens) exceeds the available context size", '
        b'"type": "exceed_context_size_error"}'
    )

    def failing_urlopen(request, timeout):
        raise HTTPError(request.full_url, 400, "Bad Request", {}, BytesIO(body))

    monkeypatch.setattr(llm_analyzer, "urlopen", failing_urlopen)

    with pytest.raises(llm_analyzer.ContextTooLargeError) as error:
        llm_analyzer._call_ollama({})

    assert "Use fewer screenshots or a shorter text" in str(error.value)


def test_ollama_timeout_becomes_a_clear_error(monkeypatch) -> None:
    def slow_urlopen(request, timeout):
        raise socket.timeout("timed out")

    monkeypatch.setattr(llm_analyzer, "urlopen", slow_urlopen)

    with pytest.raises(llm_analyzer.OllamaUnavailableError) as error:
        llm_analyzer._call_ollama({})

    assert str(error.value).startswith("Ollama did not respond within 120 seconds.")


def test_unreachable_ollama_is_reported_as_unavailable(monkeypatch) -> None:
    def unreachable(request, timeout):
        raise URLError("connection refused")

    monkeypatch.setattr(llm_analyzer, "urlopen", unreachable)

    with pytest.raises(llm_analyzer.OllamaUnavailableError) as error:
        llm_analyzer._call_ollama({})

    assert str(error.value).startswith("Could not connect to Ollama.")


def test_ollama_server_error_is_reported_as_unavailable(monkeypatch) -> None:
    def crashed(request, timeout):
        raise HTTPError(request.full_url, 500, "error", {}, BytesIO(b"runner crashed"))

    monkeypatch.setattr(llm_analyzer, "urlopen", crashed)

    with pytest.raises(llm_analyzer.OllamaUnavailableError) as error:
        llm_analyzer._call_ollama({})

    assert str(error.value) == "Ollama returned HTTP 500."


def test_missing_model_is_reported_as_unavailable(monkeypatch) -> None:
    def missing(request, timeout):
        body = b'{"error":"model \'qwen3-vl:8b-instruct\' not found"}'
        raise HTTPError(request.full_url, 404, "Not Found", {}, BytesIO(body))

    monkeypatch.setattr(llm_analyzer, "urlopen", missing)

    with pytest.raises(llm_analyzer.OllamaUnavailableError) as error:
        llm_analyzer._call_ollama({})

    assert "is not installed in Ollama. Run: ollama pull" in str(error.value)


# Any small response schema; the answers are not validated here.
SCHEMA = llm_analyzer.ScreenshotMatch


def test_ollama_requests_are_sent_one_at_a_time(monkeypatch) -> None:
    # Ollama queues parallel requests, and the queue time would count
    # against the timeout.
    running = []
    most_at_once = []

    def fake_call_ollama(payload):
        running.append(1)
        most_at_once.append(len(running))
        time.sleep(0.05)
        running.pop()
        return {"message": {"content": "{}"}}

    monkeypatch.setattr(llm_analyzer, "_call_ollama", fake_call_ollama)

    async def send_three():
        await asyncio.gather(
            *(llm_analyzer._request_json("prompt", [], SCHEMA) for _ in range(3))
        )

    asyncio.run(send_three())

    assert max(most_at_once) == 1


def test_cancelled_request_waiting_for_its_turn_never_reaches_ollama(monkeypatch) -> None:
    prompts = []

    def fake_call_ollama(payload):
        prompts.append(payload["messages"][0]["content"])
        time.sleep(0.1)
        return {"message": {"content": "{}"}}

    monkeypatch.setattr(llm_analyzer, "_call_ollama", fake_call_ollama)

    async def cancel_the_second():
        first = asyncio.ensure_future(llm_analyzer._request_json("first", [], SCHEMA))
        second = asyncio.ensure_future(llm_analyzer._request_json("second", [], SCHEMA))
        await asyncio.sleep(0.02)
        second.cancel()
        await first

    asyncio.run(cancel_the_second())

    assert prompts == ["first"]
