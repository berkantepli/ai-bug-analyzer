from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class TestScenario(BaseModel):
    test_case_id: str = Field(min_length=1)
    category: str = Field(min_length=1)
    type: Literal["Positive", "Negative", "Boundary", "Regression"]
    scenario: str = Field(min_length=1)
    expected_result: str = Field(min_length=1)
    purpose: str = Field(min_length=1)
    priority: Literal["Low", "Medium", "High", "Critical"]


class BugAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    severity: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    priority: Literal["P1", "P2", "P3", "P4"]
    category: str = Field(min_length=1)
    impact: str = Field(min_length=1)
    possible_root_cause: str = Field(min_length=1)
    suggested_test_scenarios: list[TestScenario]
    missing_information: list[str]
    confidence: float = Field(ge=0.0, le=1.0)
    visual_evidence: Optional[str] = None
