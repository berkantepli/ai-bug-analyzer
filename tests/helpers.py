"""Shared test data: a fixed LLM analysis and Excel files built in memory."""

from io import BytesIO

from openpyxl import Workbook

from app.schemas.analysis import BugAnalysis


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

HEADER = (
    "Bug Title",
    "Description",
    "Steps to Reproduce",
    "Expected Result",
    "Actual Result",
)


def excel_bytes(rows: list[tuple[object, ...]]) -> bytes:
    workbook = Workbook()
    for row in rows:
        workbook.active.append(row)
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()
