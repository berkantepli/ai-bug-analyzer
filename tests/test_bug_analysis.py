from fastapi.testclient import TestClient

from app.main import app
from app.services.llm_analyzer import ContextTooLargeError, InvalidBugReportError
from helpers import FAKE_ANALYSIS


client = TestClient(app)


VALID_BUG = {
    "title": "App crashes when uploading a large image",
    "description": "The application crashes when the user selects an image larger than 50MB.",
    "steps_to_reproduce": "Open the application\nGo to Profile\nSelect a 50MB+ image",
    "expected_result": "Image should be uploaded successfully.",
    "actual_result": "Application crashes.",
}


def test_bug_analysis_endpoint_returns_analysis(monkeypatch) -> None:
    received = {}

    async def fake_analyze_with_llm(bug, screenshots=None):
        received["bug"] = bug
        return FAKE_ANALYSIS

    monkeypatch.setattr("app.api.bugs.analyze_with_llm", fake_analyze_with_llm)

    response = client.post("/bugs/analyze", data=VALID_BUG)

    assert response.status_code == 200
    assert response.json() == FAKE_ANALYSIS.model_dump()
    assert received["bug"].steps_to_reproduce == [
        "Open the application",
        "Go to Profile",
        "Select a 50MB+ image",
    ]


def test_bug_analysis_rejects_invalid_bug_report() -> None:
    invalid_bug = VALID_BUG.copy()
    del invalid_bug["title"]

    response = client.post("/bugs/analyze", data=invalid_bug)

    assert response.status_code == 422


def test_bug_analysis_rejects_unreadable_text(monkeypatch) -> None:
    async def fake_analyze_with_llm(bug, screenshots=None):
        raise AssertionError("LLM should not be called")

    monkeypatch.setattr("app.api.bugs.analyze_with_llm", fake_analyze_with_llm)

    gibberish = {
        **VALID_BUG,
        "title": "asdfasdf qwerqwer",
        "description": "lkjsdf poiuqwe mnbzx",
        "expected_result": "zxcvqw poiuy",
        "actual_result": "mnbvc lkjhg",
    }

    response = client.post("/bugs/analyze", data=gibberish)

    assert response.status_code == 422
    assert response.json() == {"detail": "The bug report text is unreadable."}


def test_bug_analysis_rejects_report_the_llm_marks_invalid(monkeypatch) -> None:
    async def fake_analyze_with_llm(bug, screenshots=None):
        raise InvalidBugReportError("The text is a cake recipe, not a bug report.")

    monkeypatch.setattr("app.api.bugs.analyze_with_llm", fake_analyze_with_llm)

    response = client.post("/bugs/analyze", data=VALID_BUG)

    assert response.status_code == 422
    assert response.json() == {
        "detail": "Not a valid bug report: The text is a cake recipe, not a bug report."
    }


def test_bug_analysis_rejects_identical_expected_and_actual_results(
    monkeypatch,
) -> None:
    async def fake_analyze_with_llm(bug, screenshots=None):
        raise AssertionError("LLM should not be called")

    monkeypatch.setattr("app.api.bugs.analyze_with_llm", fake_analyze_with_llm)

    same_results = {
        **VALID_BUG,
        "expected_result": "Application crashes.",
        "actual_result": "Application crashes.",
    }

    response = client.post("/bugs/analyze", data=same_results)

    assert response.status_code == 422
    assert response.json() == {
        "detail": "Expected result and actual result contain the same text."
    }


def test_bug_analysis_rejects_too_long_field(monkeypatch) -> None:
    async def fake_analyze_with_llm(bug, screenshots=None):
        raise AssertionError("LLM should not be called")

    monkeypatch.setattr("app.api.bugs.analyze_with_llm", fake_analyze_with_llm)

    long_bug = {**VALID_BUG, "description": "Long text. " * 1000}

    response = client.post("/bugs/analyze", data=long_bug)

    assert response.status_code == 422
    assert response.json() == {
        "detail": "Description is longer than 5000 characters."
    }


def test_bug_analysis_explains_context_overflow(monkeypatch) -> None:
    async def fake_analyze_with_llm(bug, screenshots=None):
        raise ContextTooLargeError("The report and screenshots are too long.")

    monkeypatch.setattr("app.api.bugs.analyze_with_llm", fake_analyze_with_llm)

    response = client.post("/bugs/analyze", data=VALID_BUG)

    assert response.status_code == 413
    assert response.json() == {"detail": "The report and screenshots are too long."}


def test_bug_analysis_explains_llm_errors(monkeypatch) -> None:
    async def fake_analyze_with_llm(bug, screenshots=None):
        raise RuntimeError("Could not connect to Ollama.")

    monkeypatch.setattr("app.api.bugs.analyze_with_llm", fake_analyze_with_llm)

    response = client.post("/bugs/analyze", data=VALID_BUG)

    assert response.status_code == 503
    assert response.json() == {
        "detail": "The LLM could not analyze this bug: Could not connect to Ollama."
    }
