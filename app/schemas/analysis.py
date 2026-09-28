from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class BugAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    severity: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    priority: Literal["P1", "P2", "P3", "P4"]
    category: str = Field(min_length=1)
    possible_root_cause: str = Field(min_length=1)
    suggested_test_scenarios: list[str]
    missing_information: list[str]
