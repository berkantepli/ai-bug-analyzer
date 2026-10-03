from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook

from app.api import bugs
from app.main import app
from app.schemas.analysis import BugAnalysis
from app.services import batch_analyzer


client = TestClient(app)

VALID_BUG = {
    "title": "App crashes when uploading a large image",
    "description": "The application crashes when the user selects a large image.",
    "steps_to_reproduce": "Open the application\nSelect a large image",
    "expected_result": "Image should be uploaded successfully.",
    "actual_result": "Application crashes.",
}

FAKE_ANALYSIS = BugAnalysis(
    severity="HIGH",
    priority="P2",
    category="Functional",
    impact="Users cannot upload images.",
    possible_root_cause="Missing size validation.",
    suggested_test_scenarios=[],
    missing_information=[],
    confidence=0.8,
)

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
TIFF = b"II*\x00" + b"\x00" * 32

HEADER = (
    "Bug Title",
    "Description",
    "Steps to Reproduce",
    "Expected Result",
    "Actual Result",
)


@pytest.fixture
def fake_llm(monkeypatch) -> None:
    async def fake_analyze_with_llm(bug, screenshots=None):
        return FAKE_ANALYSIS

    monkeypatch.setattr("app.api.bugs.analyze_with_llm", fake_analyze_with_llm)


def excel_bytes(rows) -> bytes:
    workbook = Workbook()
    for row in rows:
        workbook.active.append(row)
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


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
