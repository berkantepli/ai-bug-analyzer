"""The error scenarios in samples/error-scenarios, run through the endpoints.

The sample files are generated into a temporary folder, so these tests also
keep the messages listed in samples/error-scenarios/README.md up to date.
"""

import importlib.util
import json
from pathlib import Path
from urllib.error import URLError

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import batch_analyzer
from app.services.llm_analyzer import (
    InvalidBugReportError,
    OllamaUnavailableError,
    UnreadableScreenshotError,
)
from helpers import FAKE_ANALYSIS


SAMPLES = Path(__file__).parent.parent / "samples" / "error-scenarios"

spec = importlib.util.spec_from_file_location(
    "generate_samples", SAMPLES / "generate_samples.py"
)
generate_samples = importlib.util.module_from_spec(spec)
spec.loader.exec_module(generate_samples)

SINGLE_SCENARIOS = json.loads(
    (SAMPLES / "single" / "single_scenarios.json").read_text(encoding="utf-8")
)

client = TestClient(app)

# What the LLM answers for reports that are not about software.
NOT_A_BUG_REPORT = {
    "Chocolate cake recipe": "The text describes a cake recipe, not software behavior.",
    "The purple window sings quietly": (
        "The text describes a poetic or fictional scenario, not software behavior."
    ),
}

DAMAGED_SCREENSHOT_ERROR = (
    "A screenshot could not be read; the file may be damaged or incomplete. "
    "Save it again or remove it, then try again."
)


@pytest.fixture(scope="module")
def sample_files(tmp_path_factory) -> tuple[Path, Path]:
    return generate_samples.generate(tmp_path_factory.mktemp("error-scenarios"))


@pytest.fixture(autouse=True)
def fake_llm(monkeypatch) -> None:
    async def fake_analyze_with_llm(bug, screenshots=None):
        if bug.title in NOT_A_BUG_REPORT:
            raise InvalidBugReportError(NOT_A_BUG_REPORT[bug.title])
        if any(shot.filename == "hasarli_yarim.png" for shot in screenshots or []):
            raise UnreadableScreenshotError(DAMAGED_SCREENSHOT_ERROR)
        return FAKE_ANALYSIS

    monkeypatch.setattr("app.api.bugs.analyze_with_llm", fake_analyze_with_llm)


def post_batch(path: Path):
    return client.post("/bugs/batch", files={"file": (path.name, path.read_bytes())})


# --- Batch: the whole file is rejected -------------------------------------


@pytest.mark.parametrize(
    ("file_name", "status_code", "detail"),
    [
        (
            "01_eksik_sutunlar.xlsx",
            422,
            "Missing required Excel columns: expected result, actual result.",
        ),
        ("02_sadece_baslik_satiri.xlsx", 422, "The Excel file contains no bug records."),
        (
            "03_tum_satirlar_gizli.xlsx",
            422,
            "The Excel file contains no bug records. 3 hidden rows were skipped; "
            "unhide them to analyze them.",
        ),
        (
            "04_500den_fazla_kayit.xlsx",
            422,
            "The Excel file contains 501 bug records; the maximum is 500.",
        ),
        (
            "05_2000den_fazla_dolu_satir.xlsx",
            422,
            "The Excel file has more than 2000 rows with data.",
        ),
        (
            "06_50000den_fazla_bicimli_bos_satir.xlsx",
            422,
            "The Excel file has more than 50000 rows, including empty formatted "
            "rows. Delete the unused rows below the data and try again.",
        ),
        (
            "07_sifreli_dosya.xlsx",
            422,
            "The Excel file is password-protected. Remove the password, save the "
            "file and upload it again.",
        ),
        ("08_bozuk_dosya.xlsx", 422, "The uploaded Excel file could not be read."),
        (
            "09_desteklenmeyen_format.txt",
            415,
            "Only .xlsx, .xls and .csv files are supported for batch analysis.",
        ),
        ("10_bos_dosya.xlsx", 422, "The uploaded file is empty."),
        ("11_5mb_ustu_dosya.xlsx", 413, "The Excel file is larger than 5 MB."),
        ("22_csv_eksik_sutun.csv", 422, "Missing required CSV columns: actual result."),
    ],
)
def test_rejected_batch_file(sample_files, file_name, status_code, detail) -> None:
    batch, _ = sample_files

    response = post_batch(batch / file_name)

    assert response.status_code == status_code
    assert response.json() == {"detail": detail}


def fake_column_matching(monkeypatch, mapping=None, error=None) -> None:
    async def fake_match(headers, samples):
        if error:
            raise error
        return mapping

    monkeypatch.setattr(batch_analyzer, "match_spreadsheet_columns", fake_match)


def test_turkish_headers_are_matched_by_the_llm(sample_files, monkeypatch) -> None:
    batch, _ = sample_files
    fake_column_matching(
        monkeypatch,
        {
            "title": 0,
            "description": 1,
            "steps_to_reproduce": 2,
            "expected_result": 3,
            "actual_result": 4,
        },
    )

    response = post_batch(batch / "12_turkce_basliklar_ollama_gerekir.xlsx")

    assert response.status_code == 200
    data = response.json()
    assert data["detected_columns"] == {
        "title": "Başlık",
        "description": "Açıklama",
        "steps_to_reproduce": "Tekrar Adımları",
        "expected_result": "Beklenen Sonuç",
        "actual_result": "Gerçekleşen Sonuç",
    }
    assert [bug["status"] for bug in data["bugs"]] == ["analyzed"]


def test_turkish_headers_need_ollama(sample_files, monkeypatch) -> None:
    batch, _ = sample_files
    fake_column_matching(monkeypatch, error=OllamaUnavailableError("down"))

    response = post_batch(batch / "12_turkce_basliklar_ollama_gerekir.xlsx")

    assert response.status_code == 422
    assert response.json() == {
        "detail": (
            "Missing required Excel columns: title, description, steps to "
            "reproduce, expected result, actual result. Headers that are not in "
            "English are matched by the LLM, but Ollama is unavailable."
        )
    }


def test_headers_the_llm_cannot_match(sample_files, monkeypatch) -> None:
    batch, _ = sample_files
    fake_column_matching(monkeypatch, {})

    response = post_batch(batch / "13_anlamsiz_basliklar.xlsx")

    assert response.status_code == 422
    assert response.json() == {
        "detail": (
            "Missing required Excel columns: title, description, steps to "
            "reproduce, expected result, actual result."
        )
    }


# --- Batch: rows fail, the rest of the file is analyzed --------------------


def test_row_level_errors(sample_files) -> None:
    batch, _ = sample_files

    response = post_batch(batch / "20_satir_bazli_hatalar.xlsx")

    assert response.status_code == 200
    data = response.json()
    assert data["skipped_hidden_rows"] == 1
    assert [
        (bug["row"], bug["status"], bug["error"], bug["duplicate_of"])
        for bug in data["bugs"]
    ] == [
        (4, "analyzed", None, None),
        (5, "failed", "Missing required values: expected result.", None),
        (6, "failed", "Missing required values: description.", None),
        (7, "failed", "The bug report text is unreadable.", None),
        (8, "failed", "The bug report contains only placeholder text.", None),
        (9, "failed", "The bug report contains only placeholder text.", None),
        (10, "failed", "Expected result and actual result contain the same text.", None),
        (11, "failed", "Description is longer than 5000 characters.", None),
        (12, "duplicate", None, 1),
        (13, "duplicate", None, 1),
        (
            14,
            "failed",
            "Not a valid bug report: The text describes a cake recipe, not "
            "software behavior.",
            None,
        ),
        (15, "analyzed", None, None),
        (16, "analyzed", None, None),
        (17, "analyzed", None, None),
        (
            18,
            "failed",
            "Formula without a saved result in: description. Open the file in "
            "Excel and save it again so the formula results are stored.",
            None,
        ),
    ]

    analyses = {bug["row"]: bug["analysis"] for bug in data["bugs"]}
    # Blocker / Highest / UI from the file replace the LLM's values.
    assert (analyses[4]["severity"], analyses[4]["priority"]) == ("CRITICAL", "P1")
    assert analyses[4]["category"] == "UI"
    # Unknown values (Very Bad / ASAP) keep the LLM's values.
    assert (analyses[16]["severity"], analyses[16]["priority"]) == (
        FAKE_ANALYSIS.severity,
        FAKE_ANALYSIS.priority,
    )
    # Jira values: Major -> HIGH, Low -> P4.
    assert (analyses[17]["severity"], analyses[17]["priority"]) == ("HIGH", "P4")


def test_semicolon_csv_in_turkish_encoding(sample_files) -> None:
    batch, _ = sample_files

    response = post_batch(batch / "21_noktali_virgul_cp1254.csv")

    assert response.status_code == 200
    bugs = response.json()["bugs"]
    assert bugs[0]["title"] == "Ödeme sayfası açılmıyor"
    assert [(bug["row"], bug["status"], bug["error"]) for bug in bugs] == [
        (2, "analyzed", None),
        (3, "failed", "Missing required values: description."),
        (4, "failed", "The bug report contains only placeholder text."),
    ]


# --- Single bug ------------------------------------------------------------

# Status code and detail for each scenario in single_scenarios.json; None
# means the report reaches the LLM and is analyzed.
SINGLE_EXPECTED = {
    "S01": (200, None),
    "S02": (422, "Missing required values: description."),
    "S03": (422, "The bug report text is unreadable."),
    "S04": (422, "The bug report contains only placeholder text."),
    "S05": (422, "The bug report contains only placeholder text."),
    "S06": (422, "Expected result and actual result contain the same text."),
    "S07": (422, "Title, description and actual result contain the same text."),
    "S08": (422, "Description is longer than 5000 characters."),
    "S09": (
        422,
        "Not a valid bug report: The text describes a cake recipe, not software "
        "behavior.",
    ),
    "S10": (
        422,
        "Not a valid bug report: The text describes a poetic or fictional "
        "scenario, not software behavior.",
    ),
    # Vague, prompt injection and a mismatching screenshot are still analyzed.
    "S11": (200, None),
    "S12": (200, None),
    "S13": (200, None),
    "S14": (422, "At most 5 screenshots can be uploaded."),
    "S15": (
        415,
        "Screenshot 'aslinda_metin.png' is not a supported image "
        "(PNG, JPEG, WEBP, GIF or BMP).",
    ),
    "S16": (413, "Screenshot '10mb_ustu.png' is larger than 10 MB."),
    "S17": (422, DAMAGED_SCREENSHOT_ERROR),
    "S18": (
        503,
        "The LLM could not analyze this bug: Could not connect to Ollama. Make "
        "sure Ollama is running on http://127.0.0.1:11434.",
    ),
}

FORM_FIELDS = (
    "title",
    "description",
    "steps_to_reproduce",
    "expected_result",
    "actual_result",
)


def test_every_single_scenario_has_an_expected_result() -> None:
    assert [scenario["id"] for scenario in SINGLE_SCENARIOS] == list(SINGLE_EXPECTED)


def post_single_scenario(scenario: dict, screenshots: Path):
    by_id = {item["id"]: item for item in SINGLE_SCENARIOS}
    text = by_id[scenario["base"]] if "base" in scenario else scenario
    data = {field: text[field] for field in FORM_FIELDS}
    if data["description"] == "__LONG_LOG__":
        data["description"] = generate_samples.LONG_LOG

    files = [
        ("screenshots", (name, (screenshots / name).read_bytes(), "image/png"))
        for name in scenario.get("screenshots", [])
    ]
    return client.post("/bugs/analyze", data=data, files=files or None)


@pytest.mark.parametrize(
    "scenario", SINGLE_SCENARIOS, ids=[item["id"] for item in SINGLE_SCENARIOS]
)
def test_single_bug_scenario(sample_files, monkeypatch, scenario) -> None:
    _, screenshots = sample_files
    if scenario["id"] == "S18":
        # Ollama is not running: the real analyzer cannot connect.
        def refuse_connection(*args, **kwargs):
            raise URLError("Connection refused")

        monkeypatch.undo()
        monkeypatch.setattr("app.services.llm_analyzer.urlopen", refuse_connection)

    response = post_single_scenario(scenario, screenshots)

    status_code, detail = SINGLE_EXPECTED[scenario["id"]]
    assert response.status_code == status_code
    if detail is None:
        assert response.json() == FAKE_ANALYSIS.model_dump()
    else:
        assert response.json() == {"detail": detail}
