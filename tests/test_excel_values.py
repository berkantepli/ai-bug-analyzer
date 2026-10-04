import pytest

from app.services.excel_values import map_priority, map_severity


SEVERITY_TABLE = {
    "CRITICAL": [
        "Critical", "Blocker", "Showstopper", "Show-stopper", "Urgent",
        "Emergency", "Immediate", "Fatal", "Kritik", "Engelleyici", "Acil",
    ],
    "HIGH": ["High", "Highest", "Major", "Severe", "Important", "Yüksek", "Önemli"],
    "MEDIUM": ["Medium", "Normal", "Moderate", "Average", "Orta"],
    "LOW": [
        "Low", "Lowest", "Minor", "Trivial", "Cosmetic",
        "Düşük", "Çok düşük", "En düşük",
    ],
}

PRIORITY_TABLE = {
    "P1": [
        "Highest", "Critical", "Blocker", "Urgent", "Immediate", "P0",
        "Acil", "Kritik", "En yüksek",
    ],
    "P2": ["High", "Major", "Important", "Yüksek", "Önemli"],
    "P3": ["Medium", "Normal", "Moderate", "Orta"],
    "P4": ["Low", "Lowest", "Minor", "Trivial", "P5", "Planning", "Düşük", "En düşük"],
}


@pytest.mark.parametrize(
    ("value", "expected"),
    [(value, level) for level, values in SEVERITY_TABLE.items() for value in values],
)
def test_severity_words(value, expected) -> None:
    assert map_severity(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [(value, level) for level, values in PRIORITY_TABLE.items() for value in values],
)
def test_priority_words(value, expected) -> None:
    assert map_priority(value) == expected


@pytest.mark.parametrize(
    "value", ["CRITICAL", "critical.", "  Blocker ", "KRİTİK", "YÜKSEK", "yuksek"]
)
def test_case_accents_and_punctuation_do_not_matter(value) -> None:
    assert map_severity(value) in {"CRITICAL", "HIGH"}


@pytest.mark.parametrize(
    ("value", "severity", "priority"),
    [
        ("1", "CRITICAL", "P1"),
        ("S1", "CRITICAL", "P1"),
        ("Sev 2", "HIGH", "P2"),
        ("Severity 3", "MEDIUM", "P3"),
        ("4", "LOW", "P4"),
        ("5 - Planning", "LOW", "P4"),
        ("1 - Critical", "CRITICAL", "P1"),
        ("3 - Moderate", "MEDIUM", "P3"),
        ("P2", "HIGH", "P2"),
    ],
)
def test_numbered_values(value, severity, priority) -> None:
    assert map_severity(value) == severity
    assert map_priority(value) == priority


@pytest.mark.parametrize("value", ["", "  ", "Zq#9", "Enhancement", "Feature", "9"])
def test_unknown_values_are_not_mapped(value) -> None:
    assert map_severity(value) is None
    assert map_priority(value) is None
