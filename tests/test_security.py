import asyncio
from io import BytesIO
from urllib.error import HTTPError

import pytest
from fastapi.testclient import TestClient

from app.api import bugs
from app.main import app
from app.schemas.bug import BugReportCreate
from app.services import batch_analyzer, llm_analyzer
from helpers import excel_bytes, FAKE_ANALYSIS, HEADER


client = TestClient(app)

VALID_BUG = {
    "title": "App crashes when uploading a large image",
    "description": "The application crashes when the user selects a large image.",
    "steps_to_reproduce": "Open the application\nSelect a large image",
    "expected_result": "Image should be uploaded successfully.",
    "actual_result": "Application crashes.",
}

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
TIFF = b"II*\x00" + b"\x00" * 32

@pytest.fixture
def fake_llm(monkeypatch) -> None:
    async def fake_analyze_with_llm(bug, screenshots=None):
        return FAKE_ANALYSIS

    monkeypatch.setattr("app.api.bugs.analyze_with_llm", fake_analyze_with_llm)


# ---------------- requests from other websites ----------------


@pytest.mark.parametrize(
    "headers",
    [
        {"Sec-Fetch-Site": "cross-site"},
        {"Sec-Fetch-Site": "same-site"},
        {"Origin": "https://evil.example"},
        {"Origin": "null"},
    ],
)
def test_analysis_requests_from_other_websites_are_rejected(fake_llm, headers) -> None:
    response = client.post("/bugs/analyze", data=VALID_BUG, headers=headers)

    assert response.status_code == 403


def test_inference_health_check_from_other_websites_is_rejected() -> None:
    response = client.get(
        "/health/analysis", headers={"Sec-Fetch-Site": "cross-site"}
    )

    assert response.status_code == 403


def test_same_origin_requests_are_allowed(fake_llm) -> None:
    response = client.post(
        "/bugs/analyze",
        data=VALID_BUG,
        headers={"Sec-Fetch-Site": "same-origin", "Origin": "http://testserver"},
    )

    assert response.status_code == 200


def test_page_and_basic_health_check_stay_reachable_from_links() -> None:
    headers = {"Sec-Fetch-Site": "cross-site"}

    assert client.get("/", headers=headers).status_code == 200
    assert client.get("/health", headers=headers).status_code == 200


# ---------------- screenshots ----------------


def test_supported_screenshot_is_accepted(fake_llm) -> None:
    response = client.post(
        "/bugs/analyze",
        data=VALID_BUG,
        files=[("screenshots", ("shot.png", PNG, "image/png"))],
    )

    assert response.status_code == 200


def test_non_image_screenshot_is_rejected(fake_llm) -> None:
    response = client.post(
        "/bugs/analyze",
        data=VALID_BUG,
        files=[("screenshots", ("shot.tiff", TIFF, "image/tiff"))],
    )

    assert response.status_code == 415
    assert "shot.tiff" in response.json()["detail"]


def test_file_renamed_to_png_is_still_rejected(fake_llm) -> None:
    response = client.post(
        "/bugs/analyze",
        data=VALID_BUG,
        files=[("screenshots", ("notes.png", b"plain text", "image/png"))],
    )

    assert response.status_code == 415


def test_too_large_screenshot_is_rejected(fake_llm, monkeypatch) -> None:
    monkeypatch.setattr(bugs, "MAX_SCREENSHOT_BYTES", len(PNG) - 1)

    response = client.post(
        "/bugs/analyze",
        data=VALID_BUG,
        files=[("screenshots", ("shot.png", PNG, "image/png"))],
    )

    assert response.status_code == 413


def test_too_many_screenshots_are_rejected(fake_llm) -> None:
    files = [
        ("screenshots", (f"shot{i}.png", PNG, "image/png"))
        for i in range(bugs.MAX_SCREENSHOTS + 1)
    ]

    response = client.post("/bugs/analyze", data=VALID_BUG, files=files)

    assert response.status_code == 422


# ---------------- Excel limits ----------------


def test_too_large_excel_file_is_rejected(monkeypatch) -> None:
    content = excel_bytes([HEADER])
    monkeypatch.setattr(batch_analyzer, "MAX_EXCEL_BYTES", len(content) - 1)

    response = client.post("/bugs/batch", files={"file": ("bugs.xlsx", content)})

    assert response.status_code == 413


def test_sheet_with_too_many_rows_is_rejected(monkeypatch) -> None:
    monkeypatch.setattr(batch_analyzer, "MAX_SHEET_ROWS", 2)
    row = ("Login fails", "Cannot sign in", "1. Login", "Dashboard", "Error")

    response = client.post(
        "/bugs/batch", files={"file": ("bugs.xlsx", excel_bytes([HEADER, row, row]))}
    )

    assert response.status_code == 422
    assert "more than 2 rows" in response.json()["detail"]


def test_too_many_bug_records_are_rejected(monkeypatch) -> None:
    monkeypatch.setattr(batch_analyzer, "MAX_BUG_RECORDS", 1)
    rows = [
        HEADER,
        ("Login fails", "Cannot sign in", "1. Login", "Dashboard", "Error"),
        ("Logout fails", "Cannot sign out", "1. Logout", "Login page", "Error"),
    ]

    response = client.post(
        "/bugs/batch", files={"file": ("bugs.xlsx", excel_bytes(rows))}
    )

    assert response.status_code == 422
    assert "the maximum is 1" in response.json()["detail"]


# ---------------- error details stay on the server ----------------


def test_ollama_error_body_is_not_returned_to_the_user(monkeypatch) -> None:
    def failing_urlopen(request, timeout):
        raise HTTPError(
            request.full_url, 500, "error", {}, BytesIO(b"internal stack trace")
        )

    monkeypatch.setattr(llm_analyzer, "urlopen", failing_urlopen)

    with pytest.raises(RuntimeError) as error:
        llm_analyzer._call_ollama({})

    assert str(error.value) == "Ollama returned HTTP 500."


def test_validation_details_are_not_returned_to_the_user(monkeypatch) -> None:
    monkeypatch.setattr(
        llm_analyzer,
        "_call_ollama",
        lambda payload: {"message": {"content": '{"severity": "HIGH"}'}},
    )
    bug = BugReportCreate(**{**VALID_BUG, "steps_to_reproduce": ["Open"]})

    with pytest.raises(RuntimeError) as error:
        asyncio.run(llm_analyzer.analyze_with_llm(bug))

    assert str(error.value) == "The LLM returned an incomplete analysis."


# ---------------- batch ids and retry requests ----------------


@pytest.mark.parametrize("batch_id", ["x" * 101, "has space", "../etc"])
def test_invalid_batch_ids_are_rejected(batch_id) -> None:
    response = client.post(
        "/bugs/batch/retry",
        json={"batch_id": batch_id, "bugs": [{"row": 2, "bug": {"title": "x"}}]},
    )

    assert response.status_code == 422


@pytest.mark.parametrize(
    "bug",
    [
        {"title": "Login fails", "script": "<b>not a field</b>"},
        {"title": "Login fails", "description": "x" * 5001},
    ],
    ids=["unknown field", "value too long"],
)
def test_retry_accepts_only_known_fields_of_limited_length(bug) -> None:
    response = client.post("/bugs/batch/retry", json={"bugs": [{"row": 2, "bug": bug}]})

    assert response.status_code == 422
