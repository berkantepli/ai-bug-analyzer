import asyncio
import json
from io import BytesIO
from urllib.error import URLError

import pytest
from fastapi.testclient import TestClient

from app.api import health
from app.config import OLLAMA_MODEL, OLLAMA_URL
from app.main import app
from app.schemas.bug import BugReportCreate
from app.services import llm_analyzer


client = TestClient(app)


def test_health_check_returns_ok_status() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


AVAILABLE = {"status": "available"}


class FakeResponse(BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def fake_generate(monkeypatch, response_text: str) -> list[dict]:
    payloads = []

    def fake_urlopen(request, timeout):
        payloads.append(json.loads(request.data))
        body = {"model": OLLAMA_MODEL, "response": response_text}
        return FakeResponse(json.dumps(body).encode())

    monkeypatch.setattr(health, "urlopen", fake_urlopen)
    return payloads


@pytest.mark.parametrize(
    "answer", ["INFERENCE_TEST", "INFERENCE_TEST.", " inference_test\n"]
)
def test_inference_test_tolerates_case_and_punctuation(monkeypatch, answer) -> None:
    fake_generate(monkeypatch, answer)

    assert health.check_inference(AVAILABLE, AVAILABLE)["status"] == "available"


def test_wrong_inference_answer_is_reported(monkeypatch) -> None:
    fake_generate(monkeypatch, "Hello there")

    result = health.check_inference(AVAILABLE, AVAILABLE)

    assert result["status"] == "unavailable"
    assert "Hello there" in result["reason"]


def test_inference_test_is_short_and_deterministic(monkeypatch) -> None:
    payloads = fake_generate(monkeypatch, "INFERENCE_TEST")

    health.check_inference(AVAILABLE, AVAILABLE)

    options = payloads[0]["options"]
    assert options["temperature"] == 0
    assert options["num_predict"] == 10


def test_inference_test_is_skipped_while_an_analysis_runs(monkeypatch) -> None:
    payloads = fake_generate(monkeypatch, "INFERENCE_TEST")
    monkeypatch.setattr(health, "is_analyzing", lambda: True)

    result = health.check_inference(AVAILABLE, AVAILABLE)

    assert result["status"] == "available"
    assert "busy analyzing" in result["reason"]
    assert payloads == []


def test_ollama_suggestion_uses_the_configured_url(monkeypatch) -> None:
    def unreachable(request, timeout):
        raise URLError("connection refused")

    monkeypatch.setattr(health, "urlopen", unreachable)

    result = health.check_ollama()

    assert result["status"] == "unavailable"
    assert OLLAMA_URL in result["suggested_action"]


def test_running_analysis_counter_is_reset_after_errors(monkeypatch) -> None:
    states = []

    async def failing_analysis(bug, screenshots):
        states.append(llm_analyzer.is_analyzing())
        raise RuntimeError("Ollama is down.")

    monkeypatch.setattr(llm_analyzer, "_analyze_with_llm", failing_analysis)
    bug = BugReportCreate(
        title="Login fails",
        description="Cannot sign in",
        steps_to_reproduce=["Open login"],
        expected_result="Dashboard opens",
        actual_result="Error appears",
    )

    with pytest.raises(RuntimeError):
        asyncio.run(llm_analyzer.analyze_with_llm(bug))

    assert states == [True]
    assert llm_analyzer.is_analyzing() is False


def test_light_ollama_check_sends_no_inference_request(monkeypatch) -> None:
    requests = []

    def fake_urlopen(request, timeout):
        requests.append(request.full_url)
        body = {"models": [{"name": OLLAMA_MODEL}]}
        return FakeResponse(json.dumps(body).encode())

    monkeypatch.setattr(health, "urlopen", fake_urlopen)

    response = client.get("/health/ollama")

    assert response.json() == {"available": True}
    assert requests == [health.OLLAMA_TAGS_URL]


def test_light_ollama_check_reports_unreachable_ollama(monkeypatch) -> None:
    def unreachable(request, timeout):
        raise URLError("connection refused")

    monkeypatch.setattr(health, "urlopen", unreachable)

    assert client.get("/health/ollama").json() == {"available": False}
