from typing import Literal

from pydantic import BaseModel, Field


class Requirement(BaseModel):
    description: str
    category: Literal["functional", "non-functional", "compliance", "commercial", "other"]
    mandatory: bool = Field(description="True if the RFP says must/shall/required")
    source: str = Field(description="Section or short quote from the RFP backing this requirement")


class ExtractedRequirement(BaseModel):
    """What the LLM returns for one requirement found in a section."""

    description: str = Field(description="One self-contained sentence stating what the supplier must do or provide")
    category: Literal["functional", "non-functional", "compliance", "commercial", "other"]
    mandatory: bool = Field(description="True only if the RFP says must/shall/required/mandatory")
    quote: str = Field(description="Verbatim span copied from the section that states this requirement")


class SectionExtraction(BaseModel):
    requirements: list[ExtractedRequirement]


class SectionRequirement(ExtractedRequirement):
    """An extracted requirement plus fields set by code, never by the LLM."""

    section_id: str
    quote_found: bool = Field(description="True if the quote was found in the section text")


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

class DocumentSection(BaseModel):
    id: str
    title: str
    level: int
    text: str
    path: list[str] = []          # parent headings, outermost first

    @property
    def breadcrumb(self) -> str:
        return " > ".join([*self.path, self.title])

    @property
    def char_count(self) -> int:
        return len(self.text)


