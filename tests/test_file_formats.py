import pytest
from fastapi.testclient import TestClient

from app.main import app
from helpers import FAKE_ANALYSIS


client = TestClient(app)


@pytest.fixture(autouse=True)
def fake_llm(monkeypatch) -> list:
    titles = []

    async def fake_analyze_with_llm(bug, screenshots=None):
        titles.append(bug.title)
        return FAKE_ANALYSIS

    monkeypatch.setattr("app.api.bugs.analyze_with_llm", fake_analyze_with_llm)
    return titles


def post(name: str, content: bytes):
    return client.post("/bugs/batch", files={"file": (name, content)})


def test_empty_file_is_reported() -> None:
    response = post("bugs.xlsx", b"")

    assert response.status_code == 422
    assert response.json()["detail"] == "The uploaded file is empty."


def test_password_protected_xlsx_is_reported() -> None:
    # Encrypted .xlsx files are OLE containers instead of zip files.
    content = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 512

    response = post("bugs.xlsx", content)

    assert response.status_code == 422
    assert "password-protected" in response.json()["detail"]
