from io import BytesIO

from openpyxl import Workbook
from fastapi.testclient import TestClient

from app.main import app
from app.schemas.analysis import BugAnalysis


client = TestClient(app)


FAKE_ANALYSIS = BugAnalysis(
    severity="HIGH",
    priority="P2",
    category="Authentication",
    impact="Users cannot sign in.",
    possible_root_cause="The login request is rejected.",
    suggested_test_scenarios=[],
    missing_information=[],
    confidence=0.8,
)


def excel_bytes(rows: list[tuple[object, ...]]) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    for row in rows:
        sheet.append(row)
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


def test_batch_endpoint_reads_bug_reports_from_xlsx(monkeypatch) -> None:
    async def fake_analyze_with_llm(bug, screenshots=None):
        return FAKE_ANALYSIS

    monkeypatch.setattr("app.api.bugs.analyze_with_llm", fake_analyze_with_llm)

    content = excel_bytes(
        [
            (
                "Bug Title",
                "Description",
                "Steps to Reproduce",
                "Expected Result",
                "Actual Result",
            ),
            (
                "Login fails",
                "Cannot sign in",
                "1. Open login\n2. Submit",
                "Dashboard opens",
                "Error appears",
            ),
        ]
    )

    response = client.post("/bugs/batch", files={"file": ("bugs.xlsx", content)})

    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 1
    assert data["failed"] == 0
    assert data["bugs"] == [
        {
            "title": "Login fails",
            "analysis": FAKE_ANALYSIS.model_dump(),
        }
    ]


def test_batch_endpoint_reports_missing_columns() -> None:
    content = excel_bytes([("Title", "Description"), ("Broken", "Details")])

    response = client.post("/bugs/batch", files={"file": ("bugs.xlsx", content)})

    assert response.status_code == 422
    assert "Missing required Excel columns" in response.json()["detail"]


def test_batch_endpoint_rejects_unsupported_file_types() -> None:
    response = client.post(
        "/bugs/batch", files={"file": ("bugs.csv", b"title,description")}
    )

    assert response.status_code == 415
    assert ".xlsx and .xls" in response.json()["detail"]


def test_batch_endpoint_rejects_rows_with_missing_values() -> None:
    content = excel_bytes(
        [
            (
                "Bug Title",
                "Description",
                "Steps to Reproduce",
                "Expected Result",
                "Actual Result",
            ),
            ("Login fails", "", "1. Open login", "Dashboard opens", "Error appears"),
        ]
    )

    response = client.post("/bugs/batch", files={"file": ("bugs.xlsx", content)})

    assert response.status_code == 422
    assert "Row 2 is missing required values: description" in response.json()["detail"]
