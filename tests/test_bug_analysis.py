from fastapi.testclient import TestClient

from app.main import app
from app.schemas.analysis import BugAnalysis


client = TestClient(app)


VALID_BUG = {
    "title": "App crashes when uploading a large image",
    "description": "The application crashes when the user selects an image larger than 50MB.",
    "steps_to_reproduce": "Open the application\nGo to Profile\nSelect a 50MB+ image",
    "expected_result": "Image should be uploaded successfully.",
    "actual_result": "Application crashes.",
}


FAKE_ANALYSIS = BugAnalysis(
    severity="CRITICAL",
    priority="P1",
    category="Functional",
    impact="Users cannot change their profile photo.",
    possible_root_cause="Missing file size validation.",
    suggested_test_scenarios=[],
    missing_information=[],
    confidence=0.8,
)


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
