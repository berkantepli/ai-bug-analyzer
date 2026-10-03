from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook

from app.main import app
from app.schemas.analysis import BugAnalysis
from app.services import batch_analyzer
from app.services.llm_analyzer import OllamaUnavailableError


client = TestClient(app)

FAKE_ANALYSIS = BugAnalysis(
    severity="HIGH",
    priority="P2",
    category="Authentication",
    impact="Users cannot sign in.",
    possible_root_cause="Login validation fails.",
    suggested_test_scenarios=[],
    missing_information=[],
    confidence=0.8,
)

TURKISH_HEADER = (
    "No",
    "Başlık",
    "Açıklama",
    "Tekrarlama Adımları",
    "Beklenen Sonuç",
    "Gerçekleşen Sonuç",
    "Öncelik",
)
TURKISH_ROW = (
    "1",
    "Giriş butonu pasif kalıyor",
    "Geçerli bilgilerle giriş yapılamıyor",
    "1. Giriş sayfasını aç",
    "Buton aktif olur",
    "Buton pasif kalır",
    "P1",
)
TURKISH_MAPPING = {
    "title": 1,
    "description": 2,
    "steps_to_reproduce": 3,
    "expected_result": 4,
    "actual_result": 5,
    "severity": None,
    "priority": 6,
    "category": None,
}


def excel_bytes(rows) -> bytes:
    workbook = Workbook()
    for row in rows:
        workbook.active.append(row)
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


@pytest.fixture(autouse=True)
def fake_llm(monkeypatch) -> None:
    async def fake_analyze_with_llm(bug, screenshots=None):
        return FAKE_ANALYSIS

    monkeypatch.setattr("app.api.bugs.analyze_with_llm", fake_analyze_with_llm)


def fake_column_matching(monkeypatch, mapping=None, error=None) -> list:
    calls = []

    async def fake_match(headers, samples):
        calls.append((headers, samples))
        if error:
            raise error
        return mapping

    monkeypatch.setattr(batch_analyzer, "match_spreadsheet_columns", fake_match)
    return calls


def post_excel(rows):
    return client.post("/bugs/batch", files={"file": ("bugs.xlsx", excel_bytes(rows))})


def test_unknown_headers_are_matched_by_the_llm(monkeypatch) -> None:
    calls = fake_column_matching(monkeypatch, TURKISH_MAPPING)

    response = post_excel([("Sprint 12 hataları",), TURKISH_HEADER, TURKISH_ROW])

    assert response.status_code == 200
    data = response.json()
    headers, samples = calls[0]
    assert headers == list(TURKISH_HEADER)
    assert samples == [list(TURKISH_ROW)]
    bug = data["bugs"][0]
    assert bug["row"] == 3
    assert bug["status"] == "analyzed"
    assert bug["bug"]["title"] == "Giriş butonu pasif kalıyor"
    assert bug["analysis"]["priority"] == "P1"
    assert data["detected_columns"] == {
        "title": "Başlık",
        "description": "Açıklama",
        "steps_to_reproduce": "Tekrarlama Adımları",
        "expected_result": "Beklenen Sonuç",
        "actual_result": "Gerçekleşen Sonuç",
        "priority": "Öncelik",
    }


def test_known_headers_do_not_call_the_llm(monkeypatch) -> None:
    calls = fake_column_matching(monkeypatch, TURKISH_MAPPING)

    response = post_excel(
        [
            ("Title", "Description", "Steps", "Expected Result", "Actual Result"),
            ("Login fails", "Cannot sign in", "1. Login", "Dashboard", "Error"),
        ]
    )

    assert response.status_code == 200
    assert response.json()["detected_columns"] is None
    assert calls == []


@pytest.mark.parametrize(
    "mapping",
    [
        {**TURKISH_MAPPING, "actual_result": None},
        {**TURKISH_MAPPING, "actual_result": 4},
        {**TURKISH_MAPPING, "actual_result": 99},
    ],
    ids=["missing field", "same column twice", "column out of range"],
)
def test_incomplete_llm_matching_is_rejected(monkeypatch, mapping) -> None:
    fake_column_matching(monkeypatch, mapping)

    response = post_excel([TURKISH_HEADER, TURKISH_ROW])

    assert response.status_code == 422
    assert response.json()["detail"].startswith("Missing required Excel columns:")


def test_optional_field_on_a_used_column_is_dropped(monkeypatch) -> None:
    fake_column_matching(monkeypatch, {**TURKISH_MAPPING, "category": 1})

    response = post_excel([TURKISH_HEADER, TURKISH_ROW])

    assert response.status_code == 200
    assert "category" not in response.json()["detected_columns"]


def test_unknown_headers_without_ollama_explain_why(monkeypatch) -> None:
    fake_column_matching(
        monkeypatch, error=OllamaUnavailableError("Could not connect to Ollama.")
    )

    response = post_excel([TURKISH_HEADER, TURKISH_ROW])

    assert response.status_code == 422
    assert "Ollama is unavailable" in response.json()["detail"]
