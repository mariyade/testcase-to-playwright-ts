from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from agent.models import InputSource, TestCase, TestSpec
from agent.stage1_ticket_parser.readers.parser_utils import extract_section, source_id, split_lines, title_from_source


SYSTEM_PROMPT = """
You are Stage 1 of a test automation agent. Convert an incoming requirement,
ticket, issue, or free-text note into one normalized TestSpec JSON object for
downstream Playwright test generation.

Read the source as evidence. Preserve explicit requirements, acceptance
criteria, user roles, affected areas, and testable outcomes. When the source
contains enough detail, split the work into focused test cases that cover the
main success path, supported error paths, and meaningful boundaries. When the
source is sparse, keep the output conservative instead of filling gaps with
assumptions.

Return only valid JSON. Do not include markdown, commentary, or code fences.

Required JSON shape:
{
  "title": "short feature or flow name",
  "description": "brief summary of the requested behavior",
  "acceptance_criteria": ["criteria explicitly present or directly restated from the source"],
  "affected_pages": ["snake_case page, screen, module, or endpoint names when supported by the source"],
  "user_types": ["snake_case user roles or states when supported by the source"],
  "test_cases": [
    {
      "id": "TC_001",
      "title": "action-oriented test case title",
      "priority": "Critical|High|Medium|Low",
      "type": "Smoke|Regression|Sanity",
      "preconditions": ["required setup or state"],
      "steps": ["ordered user or system actions"],
      "expected_result": "observable outcome to assert",
      "tags": ["short labels from the source or inferred from explicit context"]
    }
  ]
}

Extraction rules:
- Use the source language as the authority. Do not invent product behavior, selectors, routes, accounts, data, APIs, permissions, or UI states.
- Normalize names to snake_case in affected_pages, user_types, and tags.
- Use Critical only for flows whose failure blocks a primary business or user journey.
- Use High for important customer-visible behavior that does not fully block the main journey.
- Use Medium or Low for secondary, informational, or low-risk behavior.
- Use Smoke for minimal happy-path coverage, Regression for deeper behavior coverage, and Sanity for quick post-change checks.
- Include negative, permission, validation, or empty-state cases only when the source implies or states those behaviors.
- Prefer 3 to 15 test cases for rich tickets. For sparse input, fewer test cases are acceptable.
- Every test case must have an observable expected_result. If steps are missing from the source, keep steps minimal and do not invent unavailable implementation details.
""".strip()


def extract_text_spec(content: str, source: str | Path, title: str | None = None) -> TestSpec:
    if os.getenv("OPENAI_API_KEY"):
        try:
            return extract_text_spec_with_llm(content, source=source, title=title)
        except Exception:
            pass

    return extract_text_spec_heuristic(content, source=source, title=title)


def extract_text_spec_with_llm(
    content: str,
    source: str | Path,
    title: str | None = None,
    input_source: InputSource = InputSource.TEXT,
) -> TestSpec:
    from openai import OpenAI

    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    response = client.chat.completions.create(
        model=os.getenv("OPENAI_MODEL", "gpt-4o"),
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": _build_user_prompt(content, source=source, title=title)},
        ],
        response_format={"type": "json_object"},
        temperature=0,
        max_tokens=4000,
    )
    payload = json.loads(response.choices[0].message.content or "{}")
    return _spec_from_payload(payload, content=content, source=source, title=title, input_source=input_source)


def extract_text_spec_heuristic(content: str, source: str | Path, title: str | None = None) -> TestSpec:
    lines = split_lines(content)
    inferred_title = title or _first_heading(lines) or title_from_source(source)
    acceptance_criteria = extract_section(
        content,
        ("acceptance criteria", "acceptance", "criteria", "expected result", "expected"),
    )
    steps = extract_section(content, ("steps", "test steps", "flow"))

    return TestSpec(
        source=InputSource.TEXT,
        source_id=source_id(source),
        title=inferred_title,
        description=_description_from_lines(lines, inferred_title),
        acceptance_criteria=acceptance_criteria,
        affected_pages=_extract_urls(content),
        test_cases=[
            TestCase(
                id="TEXT_001",
                title=inferred_title,
                steps=steps,
                expected_result="\n".join(acceptance_criteria),
            )
        ],
        raw_content=content,
    )


def _build_user_prompt(content: str, source: str | Path, title: str | None = None) -> str:
    title_line = f"Known title: {title}\n\n" if title else ""
    return (
        f"{title_line}"
        f"Source: {source_id(source)}\n\n"
        "Raw ticket or requirement text:\n"
        f"{content}"
    )


def _spec_from_payload(
    payload: dict[str, Any],
    content: str,
    source: str | Path,
    title: str | None = None,
    input_source: InputSource = InputSource.TEXT,
) -> TestSpec:
    data = {
        "source": input_source,
        "source_id": source_id(source),
        "raw_content": content,
        **payload,
    }
    if title:
        data["title"] = title
    if not data.get("title"):
        data["title"] = title_from_source(source)
    return TestSpec.model_validate(data)


def _first_heading(lines: list[str]) -> str:
    for line in lines:
        cleaned = line.lstrip("#").strip()
        if cleaned:
            return cleaned[:120]
    return ""


def _description_from_lines(lines: list[str], title: str) -> str:
    description_lines = [line for line in lines if line != title]
    return "\n".join(description_lines[:8])


def _extract_urls(text: str) -> list[str]:
    import re

    urls = sorted(set(re.findall(r"https?://[^\s)>\"]+", text)))
    return urls[:10]
