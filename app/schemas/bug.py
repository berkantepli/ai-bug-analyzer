from pydantic import BaseModel, Field


class BugReportCreate(BaseModel):
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    steps_to_reproduce: list[str] = Field(min_length=1)
    expected_result: str = Field(min_length=1)
    actual_result: str = Field(min_length=1)
