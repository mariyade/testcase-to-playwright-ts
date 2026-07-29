from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from openai import OpenAI

from agent.config import AgentConfig
from agent.models import RepoContext, TestSpec

SYSTEM_PROMPT = """You generate TypeScript Playwright tests.

Rules:
- Output only TypeScript source. Do not wrap it in markdown.
- Generated specs live in playwright/tests/generated/.
- Import test and expect with ../../fixtures/test because that path is relative to playwright/tests/generated/*.spec.ts.
- Use @playwright/test style only when no custom fixture is needed.
- Prefer custom fixtures from fixtures/test.ts when available.
- Use page object methods and properties that are present in the provided context.
- Do not invent page methods, fixture names, routes, selectors, or business rules.
- Every generated test must include meaningful await expect(...) assertions.
- Use async tests and await every Playwright/page-object action.
- If relevant page-object helpers exist, generate complete tests with no TODO placeholders.
- If a flow needs an external browser extension, injected provider, or credentials
  and no fixture for that dependency exists, include a clear runtime test.skip(...)
  guard instead of generating a test that will hang in plain Chromium.
- If required context is missing, generate only the test cases that can be implemented honestly.
"""

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "list_page_objects",
            "description": "List available TypeScript page objects and their methods.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_fixtures",
            "description": "List available Playwright fixtures.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a file under the Playwright project root.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    },
]


@dataclass
class GenerationResult:
    success: bool
    code: str = ""
    filepath: Path | None = None
    tool_calls: list[str] = field(default_factory=list)
    error: str = ""
    tokens_used: int = 0


class Stage3GeneratorAgent:
    def __init__(self, config: AgentConfig | None = None):
        self.config = config or AgentConfig.load()
        self.client = OpenAI(api_key=self.config.openai_api_key)

    def generate(
        self,
        spec: TestSpec,
        context: RepoContext,
        feedback: str = "",
        dry_run: bool = False,
    ) -> GenerationResult:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": _build_generation_prompt(spec, context, feedback)},
        ]
        tool_calls: list[str] = []
        tokens = 0
        raw = ""

        for _ in range(self.config.max_tool_rounds):
            response = self.client.chat.completions.create(
                model=self.config.openai_model,
                messages=messages,
                tools=TOOL_SCHEMAS,
                tool_choice="auto",
                max_tokens=6000,
            )
            choice = response.choices[0]
            if response.usage:
                tokens += response.usage.prompt_tokens + response.usage.completion_tokens

            if choice.finish_reason == "tool_calls":
                messages.append(choice.message)
                for call in choice.message.tool_calls or []:
                    name = call.function.name
                    args = json.loads(call.function.arguments or "{}")
                    tool_calls.append(f"{name}({args})")
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call.id,
                            "content": _run_tool(context, name, args),
                        }
                    )
                continue

            raw = choice.message.content or ""
            break

        code = raw.strip()
        if code.startswith("```"):
            code = re.sub(r"^```[a-zA-Z0-9_-]*\n?", "", code)
            code = re.sub(r"\n?```$", "", code)
        code = code.strip()
        if not code:
            return GenerationResult(
                False, error="Model returned no code", tool_calls=tool_calls, tokens_used=tokens
            )

        slug = re.sub(r"[^a-z0-9]+", "_", spec.title.lower()).strip("_") or "generated_test"
        filepath = context.playwright_root / "tests" / "generated" / f"{slug}.spec.ts"
        if not dry_run:
            filepath.parent.mkdir(parents=True, exist_ok=True)
            filepath.write_text(code, encoding="utf-8")

        return GenerationResult(
            True,
            code=code,
            filepath=None if dry_run else filepath,
            tool_calls=tool_calls,
            tokens_used=tokens,
        )


def _build_generation_prompt(spec: TestSpec, context: RepoContext, feedback: str = "") -> str:
    sections = [
        "# Test Specification",
        spec.model_dump_json(indent=2),
        "",
        "# Available Page Objects",
        context.page_api_summary() or "(none found)",
        "",
        "# Available Fixtures",
        "\n".join(f"- {fixture.name} from {fixture.source_file}" for fixture in context.fixtures)
        or "(none found)",
        "",
        "# Existing Example Specs",
        "\n".join(str(path) for path in context.example_specs[:5]) or "(none found)",
        "",
        "# Knowledge",
        "\n\n".join(f"## {name}\n{content}" for name, content in context.knowledge.items())
        or "(none provided)",
    ]

    if context.retrieved_chunks:
        sections.extend(
            [
                "",
                "# Retrieved Stage 2 Context",
                "\n\n".join(
                    f"## {chunk.collection} / {chunk.symbol}\nFile: {chunk.filepath}\n{chunk.text[:1800]}"
                    for chunk in context.retrieved_chunks[:12]
                ),
            ]
        )

    if feedback:
        sections.extend(["", "# Evaluation Feedback To Fix", feedback])

    sections.extend(
        [
            "",
            "# Required Output",
            "Generate one complete TypeScript Playwright spec file for tests/generated/.",
        ]
    )
    return "\n".join(sections)


def _run_tool(context: RepoContext, name: str, args: dict) -> str:
    if name == "list_page_objects":
        return context.page_api_summary()
    if name == "get_fixtures":
        return "\n".join(f"{fixture.name}: {fixture.source_file}" for fixture in context.fixtures)
    if name == "read_file":
        root = context.playwright_root.resolve()
        target = (root / args["path"]).resolve()
        if root not in target.parents and target != root:
            return "Refused: path is outside Playwright root"
        if not target.exists() or not target.is_file():
            return f"File not found: {args['path']}"
        return target.read_text(encoding="utf-8")[:12000]
    return f"Unknown tool: {name}"
