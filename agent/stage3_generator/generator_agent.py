from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from openai import OpenAI

from agent.config import AgentConfig
from agent.models import MissingPageObjectMethod, RepoContext, TestSpec

SYSTEM_PROMPT = """You are Stage 3 of a QA automation agent.

Rules:
- Use the provided TestSpec, RepoContext, and Knowledge.
- Output only JSON. Do not wrap it in markdown.
- JSON shape:
  {
    "files": [
      {
        "path": "tests/generated/e2e/guest_books_room.spec.ts",
        "test_type": "e2e",
        "code": "TypeScript Playwright source"
      },
      {
        "path": "tests/generated/visual/guest_browses_rooms.visual.spec.ts",
        "test_type": "visual",
        "code": "TypeScript Playwright visual regression source"
      }
    ],
    "missing_page_object_methods": [
      {
        "page_object": "HomePage",
        "method_signature": "async fillContactForm(data: ContactFormData): Promise<void>",
        "filepath": "playwright/pages/HomePage.ts",
        "reason": "The spec needs to fill the contact form, but no helper exists.",
        "suggested_usage": "await homePage.fillContactForm(contactMessage);"
      }
    ]
  }
- Prefer "files". Backward-compatible single-file output with "code" is accepted.
- Do not invent selectors, fixtures, routes, credentials, page-object methods, or business rules.
- If a needed page-object method is missing, do not call it in code; add it to missing_page_object_methods.
- Generate only tests that can be implemented honestly from the provided context.
- Use Playwright test details syntax with singular "tag", for example { tag: '@e2e' }. Do not use "tags".
- Do not generate placeholder tests with comments standing in for actions or assertions.
- If a test case cannot be implemented because a helper is missing, either omit it or create a real test.skip(true, "Missing page-object helper: ...") guard.
- Every non-skipped test must contain meaningful awaited actions and meaningful await expect(...) assertions.
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
class GeneratedFile:
    path: Path
    code: str
    test_type: str = "e2e"


@dataclass
class GenerationResult:
    success: bool
    code: str = ""
    filepath: Path | None = None
    files: list[GeneratedFile] = field(default_factory=list)
    missing_page_object_methods: list[MissingPageObjectMethod] = field(default_factory=list)
    missing_methods_filepath: Path | None = None
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
                response_format={"type": "json_object"},
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

        payload = _parse_generation_payload(raw)
        slug = re.sub(r"[^a-z0-9]+", "_", spec.title.lower()).strip("_") or "generated_test"
        generated_files = _generated_files_from_payload(payload, context.playwright_root, slug)
        code = "\n\n".join(file.code for file in generated_files).strip()
        missing_methods = [
            MissingPageObjectMethod.model_validate(item)
            for item in payload.get("missing_page_object_methods", [])
            if isinstance(item, dict)
        ]
        if not code:
            return GenerationResult(
                False,
                missing_page_object_methods=missing_methods,
                error="Model returned no code",
                tool_calls=tool_calls,
                tokens_used=tokens,
            )

        primary_file = generated_files[0]
        filepath = primary_file.path
        missing_methods_filepath = (
            context.playwright_root / "tests" / "generated" / f"{slug}.missing-page-methods.json"
        )
        if not dry_run:
            for generated_file in generated_files:
                generated_file.path.parent.mkdir(parents=True, exist_ok=True)
                generated_file.path.write_text(generated_file.code, encoding="utf-8")
            if missing_methods:
                missing_methods_filepath.write_text(
                    json.dumps(
                        [method.model_dump(mode="json") for method in missing_methods],
                        indent=2,
                    )
                    + "\n",
                    encoding="utf-8",
                )

        return GenerationResult(
            True,
            code=code,
            filepath=None if dry_run else filepath,
            files=[] if dry_run else generated_files,
            missing_page_object_methods=missing_methods,
            missing_methods_filepath=None
            if dry_run or not missing_methods
            else missing_methods_filepath,
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
            "Return JSON with files and missing_page_object_methods.",
            "Each files item must include path, test_type, and code.",
            "Follow the routing, tagging, and coding rules from the Knowledge section.",
            "List absent page-object helpers in missing_page_object_methods.",
        ]
    )
    return "\n".join(sections)


def _parse_generation_payload(raw: str) -> dict:
    content = raw.strip()
    if content.startswith("```"):
        content = re.sub(r"^```[a-zA-Z0-9_-]*\n?", "", content)
        content = re.sub(r"\n?```$", "", content)
    try:
        payload = json.loads(content)
    except json.JSONDecodeError:
        return {"code": content, "missing_page_object_methods": []}
    if not isinstance(payload, dict):
        return {"code": "", "missing_page_object_methods": []}
    return payload


def _generated_files_from_payload(
    payload: dict, playwright_root: Path, slug: str
) -> list[GeneratedFile]:
    files = payload.get("files", [])
    if isinstance(files, list):
        generated_files = [
            _generated_file_from_item(item, playwright_root, slug)
            for item in files
            if isinstance(item, dict)
        ]
        generated_files = [file for file in generated_files if file.code.strip()]
        if generated_files:
            return generated_files

    code = str(payload.get("code") or "").strip()
    if not code:
        return []

    return [
        GeneratedFile(
            path=playwright_root / "tests" / "generated" / "e2e" / f"{slug}.spec.ts",
            code=code,
            test_type="e2e",
        )
    ]


def _generated_file_from_item(item: dict, playwright_root: Path, slug: str) -> GeneratedFile:
    test_type = str(item.get("test_type") or "e2e").strip().lower()
    if test_type not in {"e2e", "visual", "api"}:
        test_type = "e2e"

    requested_path = str(item.get("path") or "").strip()
    if not requested_path:
        suffix = ".visual.spec.ts" if test_type == "visual" else ".spec.ts"
        requested_path = f"tests/generated/{test_type}/{slug}{suffix}"

    return GeneratedFile(
        path=_safe_generated_path(playwright_root, requested_path, test_type, slug),
        code=_normalize_generated_code(str(item.get("code") or "").strip()),
        test_type=test_type,
    )


def _normalize_generated_code(code: str) -> str:
    return re.sub(r"\{\s*tags\s*:", "{ tag:", code)


def _safe_generated_path(
    playwright_root: Path, requested_path: str, test_type: str, slug: str
) -> Path:
    relative = Path(requested_path)
    if relative.is_absolute():
        relative = Path(*relative.parts[-3:])

    allowed_prefix = Path("tests") / "generated" / test_type
    suffix = ".visual.spec.ts" if test_type == "visual" else ".spec.ts"
    if not str(relative).startswith(str(allowed_prefix)) or relative.suffix != ".ts":
        relative = allowed_prefix / f"{slug}{suffix}"

    target = (playwright_root / relative).resolve()
    generated_root = (playwright_root / "tests" / "generated").resolve()
    if generated_root not in target.parents:
        target = generated_root / test_type / f"{slug}{suffix}"
    return target


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
