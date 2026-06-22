from __future__ import annotations

from agent.models import RepoContext, TestSpec


SYSTEM_PROMPT = """You generate TypeScript Playwright tests.

Rules:
- Output only TypeScript source. Do not wrap it in markdown.
- Generated specs live in playwright/tests/generated/.
- Import test and expect from ../../fixtures/test when custom fixtures are available.
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


def build_generation_prompt(spec: TestSpec, context: RepoContext, feedback: str = "") -> str:
    sections = [
        "# Test Specification",
        spec.model_dump_json(indent=2),
        "",
        "# Available Page Objects",
        context.page_api_summary() or "(none found)",
        "",
        "# Available Fixtures",
        "\n".join(f"- {fixture.name} from {fixture.source_file}" for fixture in context.fixtures) or "(none found)",
        "",
        "# Existing Example Specs",
        "\n".join(str(path) for path in context.example_specs[:5]) or "(none found)",
        "",
        "# Knowledge",
        "\n\n".join(f"## {name}\n{content}" for name, content in context.knowledge.items()) or "(none provided)",
    ]

    if context.retrieved_chunks:
        sections.extend([
            "",
            "# Retrieved Stage 2 Context",
            "\n\n".join(
                f"## {chunk.collection} / {chunk.symbol}\nFile: {chunk.filepath}\n{chunk.text[:1800]}"
                for chunk in context.retrieved_chunks[:12]
            ),
        ])

    if feedback:
        sections.extend(["", "# Evaluation Feedback To Fix", feedback])

    sections.extend([
        "",
        "# Required Output",
        "Generate one complete TypeScript Playwright spec file for tests/generated/.",
    ])
    return "\n".join(sections)
