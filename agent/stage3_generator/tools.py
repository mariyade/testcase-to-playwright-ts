from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from agent.models import RepoContext
from agent.stage2_context_retrieval.retriever import search_index

GROUNDING_COLLECTIONS = ("know_index", "test_index")


class BaseToolArgs(BaseModel):
    pass


class ReadFileArgs(BaseToolArgs):
    path: str


class RetrieveGroundingArgs(BaseToolArgs):
    query: str
    top_k: int = 5


@dataclass(frozen=True)
class ToolCall:
    name: str
    arguments: str
    id: str | None = None

    @classmethod
    def from_openai(cls, tool_call) -> ToolCall:
        return cls(
            name=tool_call.function.name,
            arguments=tool_call.function.arguments or "{}",
            id=tool_call.id,
        )


@dataclass(frozen=True)
class ToolDefinition:
    description: str
    args_model: type[BaseToolArgs]
    handler: Callable[[RepoContext, BaseToolArgs], str]

    def schema(self, name: str) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": name,
                "description": self.description,
                "parameters": self.args_model.model_json_schema(),
            },
        }

    def run(self, context: RepoContext, arguments: str) -> str:
        args = self.args_model.model_validate_json(arguments)
        return self.handler(context, args)


class ToolRegistry(dict[str, ToolDefinition]):
    @property
    def schema(self) -> list[dict[str, Any]]:
        return [tool.schema(name) for name, tool in self.items()]

    def run_tool_call(self, context: RepoContext, tool_call: ToolCall) -> str:
        tool = self.get(tool_call.name)
        if tool is None:
            return f"Unknown tool: {tool_call.name}"
        return tool.run(context, tool_call.arguments)


def execute_tool_call(
    context: RepoContext,
    tool_call: ToolCall,
    registry: ToolRegistry | None = None,
) -> str:
    return (registry or TOOLS).run_tool_call(context, tool_call)


# Read a planned page-object file or fixtures/test.ts, with path safety checks.
def read_file(context: RepoContext, args: BaseToolArgs) -> str:
    if not isinstance(args, ReadFileArgs):
        return "Invalid read_file arguments"

    root = context.playwright_root.resolve()
    target = (root / Path(args.path)).resolve()
    if root not in target.parents and target != root:
        return "Refused: path is outside Playwright root"
    if target not in _allowed_read_paths(context):
        return "Refused: path is not part of the Stage 3 implementation plan"
    if not target.exists() or not target.is_file():
        return f"File not found: {args.path}"
    return target.read_text(encoding="utf-8")[:12000]


def retrieve_grounding(vector_store_dir: Path) -> Callable[[RepoContext, BaseToolArgs], str]:
    def _handler(_: RepoContext, args: BaseToolArgs) -> str:
        if not isinstance(args, RetrieveGroundingArgs):
            return "Invalid retrieve_grounding arguments"

        result = search_index(
            args.query,
            vector_store_dir,
            top_k=args.top_k,
            collections=GROUNDING_COLLECTIONS,
        )
        if not result.chunks:
            return "No grounded context found."

        chunks = [
            f"[{chunk.collection}] {chunk.symbol} ({chunk.filepath})\n{chunk.text[:2000]}"
            for chunk in result.chunks
        ]
        return "\n\n---\n\n".join([*result.warnings, *chunks])

    return _handler


def _allowed_read_paths(context: RepoContext) -> set[Path]:
    planned_pages = {
        test_case_plan.primary_page_object
        for test_case_plan in context.implementation.test_cases
        if test_case_plan.primary_page_object
    }
    paths = {
        page.filepath.resolve()
        for page in context.page_objects
        if not planned_pages or page.name in planned_pages
    }
    fixture_path = (context.playwright_root / "fixtures" / "test.ts").resolve()
    if fixture_path.exists():
        paths.add(fixture_path)
    return paths


def tool_registry(vector_store_dir: Path) -> ToolRegistry:
    return ToolRegistry(
        {
            "read_file": ToolDefinition(
                description=(
                    "Read a planned page-object file or fixtures/test.ts when exact "
                    "implementation details or grounded argument values are needed."
                ),
                args_model=ReadFileArgs,
                handler=read_file,
            ),
            "retrieve_grounding": ToolDefinition(
                description=(
                    "Retrieve grounded repository knowledge or existing test examples for exact "
                    "argument values such as environment data, credentials, IDs, routes, or expected UI text."
                ),
                args_model=RetrieveGroundingArgs,
                handler=retrieve_grounding(vector_store_dir),
            ),
        }
    )


TOOLS = tool_registry(Path("agent/vector_store"))
