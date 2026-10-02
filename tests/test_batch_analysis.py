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
    assert data["total"] == 1
    assert data["completed"] == 1
    assert data["failed"] == 0
    assert data["bugs"] == [
        {
            "row": 2,
            "status": "analyzed",
            "title": "Login fails",
            "bug": {
                "title": "Login fails",
                "description": "Cannot sign in",
                "steps_to_reproduce": "1. Open login\n2. Submit",
                "expected_result": "Dashboard opens",
                "actual_result": "Error appears",
            },
            "analysis": FAKE_ANALYSIS.model_dump(),
            "error": None,
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


HEADER = (
    "Bug Title",
    "Description",
    "Steps to Reproduce",
    "Expected Result",
    "Actual Result",
)


def test_batch_endpoint_marks_rows_with_missing_values_as_failed(monkeypatch) -> None:
    analyzed_titles = []

    async def fake_analyze_with_llm(bug, screenshots=None):
        analyzed_titles.append(bug.title)
        return FAKE_ANALYSIS

    monkeypatch.setattr("app.api.bugs.analyze_with_llm", fake_analyze_with_llm)

    content = excel_bytes(
        [
            HEADER,
            ("Login fails", "", "1. Open login", "Dashboard opens", "Error appears"),
            ("Logout fails", "Cannot sign out", "1. Logout", "Login page", "Error"),
        ]
    )

    response = client.post("/bugs/batch", files={"file": ("bugs.xlsx", content)})

    assert response.status_code == 200
    data = response.json()
    assert data["completed"] == 1
    assert data["failed"] == 1
    assert analyzed_titles == ["Logout fails"]

    failed_bug, analyzed_bug = data["bugs"]
    assert failed_bug["row"] == 2
    assert failed_bug["status"] == "failed"
    assert failed_bug["analysis"] is None
    assert failed_bug["bug"]["title"] == "Login fails"
    assert failed_bug["error"] == "Missing required values: description."
    assert analyzed_bug["status"] == "analyzed"


def test_batch_endpoint_marks_llm_errors_as_failed(monkeypatch) -> None:
    async def fake_analyze_with_llm(bug, screenshots=None):
        if bug.title == "Login fails":
            raise RuntimeError("The LLM returned invalid JSON.")
        return FAKE_ANALYSIS

    monkeypatch.setattr("app.api.bugs.analyze_with_llm", fake_analyze_with_llm)

    content = excel_bytes(
        [
            HEADER,
            ("Login fails", "Cannot sign in", "1. Login", "Dashboard", "Error"),
            ("Logout fails", "Cannot sign out", "1. Logout", "Login page", "Error"),
        ]
    )

    response = client.post("/bugs/batch", files={"file": ("bugs.xlsx", content)})

    assert response.status_code == 200
    data = response.json()
    assert data["completed"] == 1
    assert data["failed"] == 1

    failed_bug, analyzed_bug = data["bugs"]
    assert failed_bug["status"] == "failed"
    assert failed_bug["analysis"] is None
    assert failed_bug["error"] == (
        "The LLM could not analyze this bug: The LLM returned invalid JSON."
    )
    assert analyzed_bug["status"] == "analyzed"
    assert analyzed_bug["analysis"] == FAKE_ANALYSIS.model_dump()


def test_batch_endpoint_marks_unreadable_rows_as_failed(monkeypatch) -> None:
    analyzed_titles = []

    async def fake_analyze_with_llm(bug, screenshots=None):
        analyzed_titles.append(bug.title)
        return FAKE_ANALYSIS

    monkeypatch.setattr("app.api.bugs.analyze_with_llm", fake_analyze_with_llm)

    content = excel_bytes(
        [
            HEADER,
            (
                "Xq7#vL@ zR9$ kT~pW 4&mN",
                "Fj%8 qwZ!x 9Lp#r Tz@4k Vb^7n",
                "1. Wq#8z Kp@3 lX!",
                "Lx~6p Qr#4 zM@ Vn$1",
                "Dz*2q Pj+9 xK? Ym=5",
            ),
            (
                "TypeError on profile page",
                "TypeError: Cannot read property 'x' of undefined at app.js:42",
                "1. Open /profile",
                "Profile page loads",
                "API returns 500 on GET /api/v1/users?id=12",
            ),
        ]
    )

    response = client.post("/bugs/batch", files={"file": ("bugs.xlsx", content)})

    assert response.status_code == 200
    data = response.json()
    assert data["completed"] == 1
    assert data["failed"] == 1
    assert analyzed_titles == ["TypeError on profile page"]

    unreadable_bug = data["bugs"][0]
    assert unreadable_bug["status"] == "failed"
    assert unreadable_bug["error"] == "The bug report text is unreadable."


def test_batch_endpoint_finds_header_below_report_title(monkeypatch) -> None:
    async def fake_analyze_with_llm(bug, screenshots=None):
        return FAKE_ANALYSIS

    monkeypatch.setattr("app.api.bugs.analyze_with_llm", fake_analyze_with_llm)

    content = excel_bytes(
        [
            ("Sprint 12 Bug Report",),
            ("Exported on 2026-10-02",),
            (),
            HEADER,
            ("Login fails", "Cannot sign in", "1. Login", "Dashboard", "Error"),
            ("Logout fails", "", "1. Logout", "Login page", "Error"),
        ]
    )

    response = client.post("/bugs/batch", files={"file": ("bugs.xlsx", content)})

    assert response.status_code == 200
    data = response.json()
    assert [bug["row"] for bug in data["bugs"]] == [5, 6]
    assert [bug["status"] for bug in data["bugs"]] == ["analyzed", "failed"]


def test_batch_endpoint_keeps_excel_row_numbers_when_sheet_starts_lower(
    monkeypatch,
) -> None:
    async def fake_analyze_with_llm(bug, screenshots=None):
        return FAKE_ANALYSIS

    monkeypatch.setattr("app.api.bugs.analyze_with_llm", fake_analyze_with_llm)

    workbook = Workbook()
    sheet = workbook.active
    for column, value in enumerate(HEADER, start=1):
        sheet.cell(row=3, column=column, value=value)
    for column, value in enumerate(
        ("Login fails", "Cannot sign in", "1. Login", "Dashboard", "Error"),
        start=1,
    ):
        sheet.cell(row=4, column=column, value=value)
    output = BytesIO()
    workbook.save(output)

    response = client.post(
        "/bugs/batch", files={"file": ("bugs.xlsx", output.getvalue())}
    )

    assert response.status_code == 200
    assert response.json()["bugs"][0]["row"] == 4
