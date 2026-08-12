from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field


class InputSource(StrEnum):
    JIRA = "jira"
    GITHUB = "github"
    TEXT = "text"


class TestCase(BaseModel):
    id: str
    title: str = Field(min_length=1)
    preconditions: list[str] = Field(default_factory=list)
    steps: list[str] = Field(min_length=1)
    expected_result: str = Field(min_length=1)
    tags: list[str] = Field(default_factory=list)


class ParameterContract(BaseModel):
    name: str
    type: str = ""
    required: bool = True
    properties: dict[str, str] = Field(default_factory=dict)


class MethodContract(BaseModel):
    name: str
    intent: str = ""
    signature: str = ""
    returns: str = ""
    parameters: list[ParameterContract] = Field(default_factory=list)
    navigates_to: str = ""
    stays_on: str = ""


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


class PageObjectContract(BaseModel):
    name: str
    filepath: Path
    page: str = ""
    fixture: str = ""
    methods: list[MethodContract] = Field(default_factory=list)
    properties: list[str] = Field(default_factory=list)


class FixtureContract(BaseModel):
    name: str
    source_file: Path


class AssertionContract(BaseModel):
    name: str
    page_object: str = ""
    fixture: str = ""
    source_file: Path | None = None


class RepositoryContracts(BaseModel):
    page_objects: list[PageObjectContract] = Field(default_factory=list)
    fixtures: list[FixtureContract] = Field(default_factory=list)
    assertions: list[AssertionContract] = Field(default_factory=list)

    def page_api_summary(self) -> str:
        lines: list[str] = []
        for page in self.page_objects:
            page_bits = [page.name]
            if page.page:
                page_bits.append(f"page={page.page}")
            if page.fixture:
                page_bits.append(f"fixture={page.fixture}")
            lines.append(f"{' '.join(page_bits)} ({page.filepath})")
            for method in page.methods:
                contract = []
                if method.intent:
                    contract.append(f"intent={method.intent}")
                if method.signature:
                    contract.append(f"signature={method.signature}")
                for parameter in method.parameters:
                    if parameter.properties:
                        properties = ", ".join(
                            f"{name}: {type_name}"
                            for name, type_name in parameter.properties.items()
                        )
                        contract.append(
                            f"parameter {parameter.name}: {parameter.type} {{{properties}}}"
                        )
                    elif parameter.type:
                        contract.append(f"parameter {parameter.name}: {parameter.type}")
                if method.returns:
                    contract.append(f"returns={method.returns}")
                if method.navigates_to:
                    contract.append(f"navigates_to={method.navigates_to}")
                if method.stays_on:
                    contract.append(f"stays_on={method.stays_on}")
                details = f" [{', '.join(contract)}]" if contract else ""
                lines.append(f"  - {method.name}(){details}")
            for prop in page.properties:
                lines.append(f"  - property {prop}")
        return "\n".join(lines)


class TestCaseImplementation(BaseModel):
    test_case_id: str
    primary_page_object: str = ""
    required_methods: list[str] = Field(default_factory=list)
    missing_capabilities: list[str] = Field(default_factory=list)


class ImplementationPlan(BaseModel):
    output_scope: str = ""
    test_cases: list[TestCaseImplementation] = Field(default_factory=list)


# Backward-compatible aliases while Stage 2/3 migrate to RepositoryContracts.
PageObjectMethodInfo = MethodContract
PageObjectInfo = PageObjectContract
FixtureInfo = FixtureContract


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
    repository_contracts: RepositoryContracts = Field(default_factory=RepositoryContracts)
    implementation: ImplementationPlan = Field(default_factory=ImplementationPlan)
    example_specs: list[Path] = Field(default_factory=list)
    knowledge: dict[str, str] = Field(default_factory=dict)
    retrieved_chunks: list[CodeChunk] = Field(default_factory=list)

    @property
    def page_objects(self) -> list[PageObjectContract]:
        return self.repository_contracts.page_objects

    @property
    def fixtures(self) -> list[FixtureContract]:
        return self.repository_contracts.fixtures

    def page_api_summary(self) -> str:
        return self.repository_contracts.page_api_summary()
