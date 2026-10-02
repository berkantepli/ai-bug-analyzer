import asyncio

import pytest

from app.schemas.bug import BugReportCreate
from app.services import llm_analyzer


BUG = BugReportCreate(
    title="Login fails",
    description="Cannot sign in",
    steps_to_reproduce=["Open login", "Submit"],
    expected_result="Dashboard opens",
    actual_result="Error appears",
)


@pytest.mark.parametrize(
    "response",
    [
        {},
        {"message": {"content": ""}},
        {"message": {"content": "not json"}},
        {"message": {"content": '{"severity": "HIGH"}'}},
    ],
)
def test_empty_or_invalid_llm_response_raises(monkeypatch, response) -> None:
    monkeypatch.setattr(llm_analyzer, "_call_ollama", lambda payload: response)

    with pytest.raises(RuntimeError):
        asyncio.run(llm_analyzer.analyze_with_llm(BUG))
