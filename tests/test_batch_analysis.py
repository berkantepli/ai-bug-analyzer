from io import BytesIO

from openpyxl import Workbook
from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def excel_bytes(rows: list[tuple[object, ...]]) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    for row in rows:
        sheet.append(row)
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


def test_batch_endpoint_reads_bug_reports_from_xlsx() -> None:
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
    assert response.json() == {
        "count": 1,
        "bugs": [
            {
                "title": "Login fails",
                "analysis": {
                    "severity": "HIGH",
                    "priority": "P2",
                    "category": "Functional",
                    "possible_root_cause": (
                        "The authentication flow may contain an incorrect validation "
                        "or authentication handling issue."
                    ),
                    "suggested_test_scenarios": [
                        "Reproduce the issue using the provided steps.",
                        "Verify the expected result with valid input.",
                        "Verify the behavior with invalid or boundary input.",
                        "Retest the affected functionality after the fix.",
                        "Perform regression testing on related functionality.",
                    ],
                    "missing_information": [],
                    "confidence": 0.9,
                },
            }
        ],
    }


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
