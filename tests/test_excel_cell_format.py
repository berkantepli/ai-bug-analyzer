from datetime import date, datetime
from io import BytesIO
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook

from app.main import app
from app.services.batch_analyzer import _format_cell


client = TestClient(app)

FIXTURES = Path(__file__).parent / "fixtures"

HEADER = (
    "Bug Title",
    "Description",
    "Steps to Reproduce",
    "Expected Result",
    "Actual Result",
)

EXPECTED_VALUES = [
    ("200", "404"),
    ("15%", "10%"),
    ("2026-10-02", "2026-09-02 14:30"),
]


@pytest.mark.parametrize(
    ("value", "number_format", "expected"),
    [
        (404, "General", "404"),
        (404.0, "General", "404"),
        (19.99, "General", "19.99"),
        (0.15, "0%", "15%"),
        (0.125, "0.0%", "12.5%"),
        (date(2026, 10, 2), "General", "2026-10-02"),
        (datetime(2026, 10, 2), "General", "2026-10-02"),
        (datetime(2026, 10, 2, 14, 30), "General", "2026-10-02 14:30"),
        (datetime(2026, 10, 2, 14, 30, 5), "General", "2026-10-02 14:30:05"),
        ("Already text", "General", "Already text"),
        (None, "General", None),
    ],
)
def test_format_cell(value, number_format, expected) -> None:
    assert _format_cell(value, number_format) == expected


def batch_values(response) -> list[tuple[str, str]]:
    return [
        (bug["bug"]["expected_result"], bug["bug"]["actual_result"])
        for bug in response.json()["bugs"]
    ]


@pytest.fixture
def fake_llm(monkeypatch) -> None:
    async def fake_analyze_with_llm(bug, screenshots=None):
        raise RuntimeError("LLM is not needed for this test")

    monkeypatch.setattr("app.api.bugs.analyze_with_llm", fake_analyze_with_llm)


def test_xlsx_cells_are_read_as_displayed(fake_llm) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(HEADER)
    sheet.append(("Error 404 on profile page", "Error code", "1. Open", 200, 404))
    sheet.append(("Wrong discount", "Discount is wrong", "1. Add item", 0.15, 0.1))
    sheet.append(
        (
            "Wrong due date",
            "Due date is wrong",
            "1. Open invoice",
            date(2026, 10, 2),
            datetime(2026, 9, 2, 14, 30),
        )
    )
    sheet["D3"].number_format = "0%"
    sheet["E3"].number_format = "0%"
    output = BytesIO()
    workbook.save(output)

    response = client.post(
        "/bugs/batch", files={"file": ("bugs.xlsx", output.getvalue())}
    )

    assert response.status_code == 200
    assert batch_values(response) == EXPECTED_VALUES


def test_xls_cells_are_read_as_displayed(fake_llm) -> None:
    content = (FIXTURES / "formatted_cells.xls").read_bytes()

    response = client.post("/bugs/batch", files={"file": ("bugs.xls", content)})

    assert response.status_code == 200
    assert batch_values(response) == EXPECTED_VALUES
