from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


VALID_BUG = {
    "title": "App crashes when uploading a large image",
    "description": "The application crashes when the user selects an image larger than 50MB.",
    "steps_to_reproduce": [
        "Open the application",
        "Go to Profile",
        "Select Change Photo",
        "Select a 50MB+ image",
        "Tap Upload",
    ],
    "expected_result": "Image should be uploaded successfully.",
    "actual_result": "Application crashes.",
}


def test_bug_analysis_endpoint_returns_analysis() -> None:
    response = client.post("/bugs/analyze", json=VALID_BUG)

    assert response.status_code == 200

    data = response.json()

    assert "severity" in data
    assert "priority" in data
    assert "category" in data
    assert "possible_root_cause" in data
    assert "suggested_test_scenarios" in data
    assert "missing_information" in data


def test_bug_analysis_rejects_invalid_bug_report() -> None:
    invalid_bug = VALID_BUG.copy()
    invalid_bug["title"] = ""

    response = client.post("/bugs/analyze", json=invalid_bug)

    assert response.status_code == 422
