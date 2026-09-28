import pytest
from pydantic import ValidationError

from app.schemas.bug import BugReportCreate


def test_valid_bug_report_is_accepted() -> None:
    bug = BugReportCreate(
        title="App crashes when uploading a large image",
        description="The application crashes when the user selects an image larger than 50MB.",
        steps_to_reproduce=[
            "Open the application",
            "Go to Profile",
            "Select Change Photo",
            "Select a 50MB+ image",
            "Tap Upload",
        ],
        expected_result="Image should be uploaded successfully.",
        actual_result="Application crashes.",
    )

    assert bug.title == "App crashes when uploading a large image"


def test_empty_title_is_rejected() -> None:
    with pytest.raises(ValidationError):
        BugReportCreate(
            title="",
            description="The application crashes.",
            steps_to_reproduce=["Open the application"],
            expected_result="Application should work.",
            actual_result="Application crashes.",
        )


def test_empty_description_is_rejected() -> None:
    with pytest.raises(ValidationError):
        BugReportCreate(
            title="App crashes",
            description="",
            steps_to_reproduce=["Open the application"],
            expected_result="Application should work.",
            actual_result="Application crashes.",
        )


def test_empty_steps_to_reproduce_is_rejected() -> None:
    with pytest.raises(ValidationError):
        BugReportCreate(
            title="App crashes",
            description="The application crashes.",
            steps_to_reproduce=[],
            expected_result="Application should work.",
            actual_result="Application crashes.",
        )


def test_empty_expected_result_is_rejected() -> None:
    with pytest.raises(ValidationError):
        BugReportCreate(
            title="App crashes",
            description="The application crashes.",
            steps_to_reproduce=["Open the application"],
            expected_result="",
            actual_result="Application crashes.",
        )


def test_empty_actual_result_is_rejected() -> None:
    with pytest.raises(ValidationError):
        BugReportCreate(
            title="App crashes",
            description="The application crashes.",
            steps_to_reproduce=["Open the application"],
            expected_result="Application should work.",
            actual_result="",
        )
