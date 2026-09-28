from app.schemas.analysis import BugAnalysis
from app.schemas.bug import BugReportCreate


def analyze_bug_report(bug: BugReportCreate) -> BugAnalysis:
    description = bug.description.lower()
    title = bug.title.lower()

    text = f"{title} {description}"

    # Severity
    if any(
        keyword in text
        for keyword in [
            "crash",
            "data loss",
            "security",
            "payment",
            "cannot login",
        ]
    ):
        severity = "CRITICAL"
    elif any(
        keyword in text
        for keyword in [
            "not working",
            "error",
            "fail",
            "failure",
            "broken",
        ]
    ):
        severity = "HIGH"
    elif any(
        keyword in text
        for keyword in [
            "slow",
            "delay",
            "performance",
        ]
    ):
        severity = "MEDIUM"
    else:
        severity = "LOW"

    # Priority
    if severity == "CRITICAL":
        priority = "P1"
    elif severity == "HIGH":
        priority = "P2"
    elif severity == "MEDIUM":
        priority = "P3"
    else:
        priority = "P4"

    # Category
    if any(
        keyword in text
        for keyword in ["crash", "error", "fail", "failure", "not working"]
    ):
        category = "Functional"
    elif any(keyword in text for keyword in ["slow", "delay", "performance"]):
        category = "Performance"
    elif any(keyword in text for keyword in ["login", "password", "authentication"]):
        category = "Authentication"
    elif any(keyword in text for keyword in ["payment", "transaction"]):
        category = "Payment"
    else:
        category = "General"

    # Possible root cause
    possible_root_cause = (
        "The application may not be handling the reported scenario correctly."
    )

    if "crash" in text:
        possible_root_cause = (
            "An unhandled exception or missing validation may be causing "
            "the application to crash."
        )
    elif "slow" in text or "performance" in text:
        possible_root_cause = (
            "The affected operation may have a performance or resource handling issue."
        )
    elif "login" in text or "password" in text:
        possible_root_cause = (
            "The authentication flow may contain an incorrect validation "
            "or authentication handling issue."
        )

    suggested_test_scenarios = [
        "Reproduce the issue using the provided steps.",
        "Verify the expected result with valid input.",
        "Verify the behavior with invalid or boundary input.",
        "Retest the affected functionality after the fix.",
        "Perform regression testing on related functionality.",
    ]

    missing_information = []

    if not bug.steps_to_reproduce:
        missing_information.append("Steps to reproduce")

    if not bug.expected_result:
        missing_information.append("Expected result")

    if not bug.actual_result:
        missing_information.append("Actual result")

    return BugAnalysis(
        severity=severity,
        priority=priority,
        category=category,
        possible_root_cause=possible_root_cause,
        suggested_test_scenarios=suggested_test_scenarios,
        missing_information=missing_information,
        confidence=0.9,
    )
