import pytest
from pydantic import ValidationError

from app.schemas.analysis import BugAnalysis


def valid_analysis_data() -> dict:
    return {
        "severity": "HIGH",
        "priority": "P1",
        "category": "Functional",
        "possible_root_cause": "The application does not validate the uploaded file size.",
        "suggested_test_scenarios": [
            "Upload a file larger than the allowed limit.",
            "Upload a file exactly at the allowed limit.",
        ],
        "missing_information": [
            "Maximum allowed file size",
            "Supported image formats",
        ],
    }


def test_valid_analysis_is_accepted() -> None:
    analysis = BugAnalysis(**valid_analysis_data())

    assert analysis.severity == "HIGH"
    assert analysis.priority == "P1"
    assert analysis.category == "Functional"


def test_invalid_severity_is_rejected() -> None:
    data = valid_analysis_data()
    data["severity"] = "URGENT"

    with pytest.raises(ValidationError):
        BugAnalysis(**data)


def test_missing_required_field_is_rejected() -> None:
    data = valid_analysis_data()
    del data["possible_root_cause"]

    with pytest.raises(ValidationError):
        BugAnalysis(**data)


def test_invalid_suggested_test_scenarios_type_is_rejected() -> None:
    data = valid_analysis_data()
    data["suggested_test_scenarios"] = "Run regression tests"

    with pytest.raises(ValidationError):
        BugAnalysis(**data)


def test_invalid_missing_information_type_is_rejected() -> None:
    data = valid_analysis_data()
    data["missing_information"] = "No information"

    with pytest.raises(ValidationError):
        BugAnalysis(**data)


def test_empty_root_cause_is_rejected() -> None:
    data = valid_analysis_data()
    data["possible_root_cause"] = ""

    with pytest.raises(ValidationError):
        BugAnalysis(**data)


def test_unexpected_extra_field_is_rejected() -> None:
    data = valid_analysis_data()
    data["unexpected_field"] = "should not be accepted"

    with pytest.raises(ValidationError):
        BugAnalysis(**data)
