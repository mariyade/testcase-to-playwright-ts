from __future__ import annotations

import json
import re
from pathlib import Path

from agent.models import RepoContext
from agent.stage3_generator.generation_types import GeneratedFile
from agent.stage3_generator.prompting import fixture_import_lines


# Parse the model's JSON response, tolerating accidental markdown fences.
def parse_generation_payload(raw: str) -> dict:
    content = raw.strip()
    if content.startswith("```"):
        content = re.sub(r"^```[a-zA-Z0-9_-]*\n?", "", content)
        content = re.sub(r"\n?```$", "", content)
    try:
        payload = json.loads(content)
    except json.JSONDecodeError:
        return {}
    if not isinstance(payload, dict):
        return {}
    return payload


# Convert the model payload into safe GeneratedFile objects.
# Python owns output paths and fixture imports even when the model supplies code.
def generated_files_from_payload(
    payload: dict, context: RepoContext, slug: str, output_scope: str = ""
) -> list[GeneratedFile]:
    files = payload.get("files", [])
    if not isinstance(files, list):
        return []

    generated_files: list[GeneratedFile] = []
    for item in files:
        if not isinstance(item, dict):
            continue

        requested_path = str(item.get("path") or "").strip()
        if not requested_path:
            requested_path = f"tests/generated/{slug}.spec.ts"
        code = _with_pipeline_fixture_import(str(item.get("code") or "").strip(), context)
        if not code.strip():
            continue
        generated_files.append(
            GeneratedFile(
                path=_safe_generated_path(
                    context.playwright_root,
                    requested_path,
                    slug,
                    output_scope,
                ),
                code=code,
            )
        )

    return generated_files


# Force model-requested files under playwright/tests/generated/<scope>.
# The model may suggest a filename, but Python owns the final safe location.
def _safe_generated_path(
    playwright_root: Path, requested_path: str, slug: str, output_scope: str = ""
) -> Path:
    output_dir = playwright_root / "tests" / "generated"
    if output_scope:
        output_dir = output_dir / output_scope

    filename = Path(requested_path).name
    if not filename.endswith(".spec.ts"):
        filename = f"{slug}.spec.ts"
    return output_dir / filename


# Prepend the deterministic fixture import and remove accidental duplicate test imports.
def _with_pipeline_fixture_import(code: str, context: RepoContext) -> str:
    if not code:
        return ""
    cleaned_lines = []
    for line in code.lstrip().splitlines():
        match = re.fullmatch(
            r"\s*import\s*\{\s*([^}]+)\s*\}\s*from\s*['\"]([^'\"]+)['\"]\s*;?\s*",
            line,
        )
        if match:
            names = {name.strip() for name in match.group(1).split(",")}
            module = match.group(2)
            if names <= {"test", "expect"} and (
                module == "@playwright/test"
                or module.endswith("/fixtures/test")
                or module.endswith("/fixtures")
            ):
                continue
        cleaned_lines.append(line)

    code = "\n".join(cleaned_lines).lstrip()
    imports = fixture_import_lines(context, include_expect=bool(re.search(r"\bexpect\s*\(", code)))
    if not imports:
        return code
    return "\n\n".join([imports[0], code]).strip()
