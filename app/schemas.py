from typing import Literal

from pydantic import BaseModel, Field


class Requirement(BaseModel):
    description: str
    category: Literal["functional", "non-functional", "compliance", "commercial", "other"]
    mandatory: bool = Field(description="True if the RFP says must/shall/required")
    source: str = Field(description="Section or short quote from the RFP backing this requirement")


class ApproachStep(BaseModel):
    phase: str
    description: str


class Risk(BaseModel):
    description: str
    severity: Literal["low", "medium", "high"]
    mitigation: str


class SolutionSummary(BaseModel):
    project_title: str
    client: str
    overview: str = Field(description="2-3 sentence summary of what the client is asking for")
    requirements: list[Requirement]
    approach: list[ApproachStep]
    risks: list[Risk]
