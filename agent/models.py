from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field


class Priority(StrEnum):
    CRITICAL = "Critical"
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"


class TestType(StrEnum):
    SMOKE = "Smoke"
    REGRESSION = "Regression"
    SANITY = "Sanity"


class InputSource(StrEnum):
    JIRA = "jira"
    GITHUB = "github"
    TEXT = "text"


class TestCase(BaseModel):
    id: str
    title: str
    priority: Priority = Priority.HIGH
    type: TestType = TestType.REGRESSION
    preconditions: list[str] = Field(default_factory=list)
    steps: list[str] = Field(default_factory=list)
    expected_result: str = ""
    tags: list[str] = Field(default_factory=list)


class TestSpec(BaseModel):
    source: InputSource
    source_id: str
    title: str
    description: str = ""
    acceptance_criteria: list[str] = Field(default_factory=list)
    affected_pages: list[str] = Field(default_factory=list)
    user_types: list[str] = Field(default_factory=list)
    test_cases: list[TestCase] = Field(default_factory=list)
    raw_content: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)


class PageObjectInfo(BaseModel):
    name: str
    filepath: Path
    methods: list[str] = Field(default_factory=list)
    properties: list[str] = Field(default_factory=list)


class FixtureInfo(BaseModel):
    name: str
    source_file: Path


class CodeChunk(BaseModel):
    id: str
    collection: str
    chunk_type: str
    filepath: Path
    symbol: str = ""
    text: str
    metadata: dict[str, str] = Field(default_factory=dict)


class RetrievalResult(BaseModel):
    query: str
    chunks: list[CodeChunk] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class MissingPageObjectMethod(BaseModel):
    page_object: str
    method_signature: str
    filepath: Path | None = None
    reason: str = ""
    suggested_usage: str = ""


class RepoContext(BaseModel):
    playwright_root: Path
    page_objects: list[PageObjectInfo] = Field(default_factory=list)
    fixtures: list[FixtureInfo] = Field(default_factory=list)
    example_specs: list[Path] = Field(default_factory=list)
    knowledge: dict[str, str] = Field(default_factory=dict)
    retrieved_chunks: list[CodeChunk] = Field(default_factory=list)

    def page_api_summary(self) -> str:
        lines: list[str] = []
        for page in self.page_objects:
            lines.append(f"{page.name} ({page.filepath})")
            for method in page.methods:
                lines.append(f"  - {method}()")
            for prop in page.properties:
                lines.append(f"  - property {prop}")
        return "\n".join(lines)
