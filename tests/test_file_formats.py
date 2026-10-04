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


@pytest.mark.parametrize(
    ("content", "encoding"),
    [
        ("Bug Title,Description,Steps to Reproduce,Expected Result,Actual Result\n"
         'Login fails,Cannot sign in,"1. Login\n2. Submit",Dashboard,Error\n', "utf-8"),
        ("Bug Title;Description;Steps to Reproduce;Expected Result;Actual Result\n"
         "Giriş başarısız;Giriş yapılamıyor;1. Giriş;Panel açılır;Hata\n", "cp1254"),
        ("﻿Bug Title\tDescription\tSteps to Reproduce\tExpected Result\tActual Result\n"
         "Login fails\tCannot sign in\t1. Login\tDashboard\tError\n", "utf-8"),
    ],
    ids=["comma", "semicolon in Turkish Windows encoding", "tab with BOM"],
)
def test_csv_files_are_read(content, encoding) -> None:
    response = post("bugs.csv", content.encode(encoding))

    assert response.status_code == 200
    bug = response.json()["bugs"][0]
    assert bug["status"] == "analyzed"
    assert bug["bug"]["title"] in {"Login fails", "Giriş başarısız"}


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
