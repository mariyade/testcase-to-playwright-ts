from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

from agent.models import InputSource, TestCase, TestSpec, TestType
from agent.stage1_ticket_parser.extractor import extract_text_spec_with_llm
from agent.stage1_ticket_parser.readers.parser_utils import (
    extract_section,
    is_url,
    priority_from_text,
    source_id,
    split_lines,
    split_tags,
)


def read_jira_spec(source: str | Path) -> TestSpec:
    issue = _read_jira_source(source)
    fields = issue.get("fields", issue)

    key = str(issue.get("key") or fields.get("key") or source)
    summary = str(fields.get("summary") or issue.get("summary") or key)
    description = _jira_text(fields.get("description") or issue.get("description") or "")

    if os.getenv("OPENAI_API_KEY"):
        try:
            extracted = extract_text_spec_with_llm(
                _jira_prompt_text(key, summary, description),
                source=source,
                title=summary,
                input_source=InputSource.JIRA,
            )
            return extracted.model_copy(update={"raw_content": json.dumps(issue, indent=2, default=str)})
        except Exception:
            pass

    acceptance_criteria = _acceptance_criteria(fields, description)
    steps = extract_section(description, ("steps", "test steps", "flow"))
    labels = split_tags(fields.get("labels") or issue.get("labels") or [])

    return TestSpec(
        source=InputSource.JIRA,
        source_id=source_id(source),
        title=summary,
        description=description,
        acceptance_criteria=acceptance_criteria,
        affected_pages=_affected_pages(fields),
        test_cases=[
            TestCase(
                id=key,
                title=summary,
                priority=priority_from_text(_field_name(fields.get("priority"))),
                type=TestType.REGRESSION,
                steps=steps,
                expected_result="\n".join(acceptance_criteria),
                tags=labels,
            )
        ],
        raw_content=json.dumps(issue, indent=2, default=str),
    )


def _read_jira_source(source: str | Path) -> dict[str, Any]:
    if is_url(source):
        request = Request(str(source), headers=_jira_headers())
        with urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))
    return json.loads(Path(source).read_text(encoding="utf-8"))


def _jira_headers() -> dict[str, str]:
    headers = {
        "Accept": "application/json",
        "User-Agent": "testcase-to-playwright-ts/1.0",
    }
    email = os.getenv("JIRA_EMAIL")
    token = os.getenv("JIRA_API_TOKEN")
    if email and token:
        encoded = base64.b64encode(f"{email}:{token}".encode("utf-8")).decode("ascii")
        headers["Authorization"] = f"Basic {encoded}"
    return headers


def _jira_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return "\n".join(_walk_adf(value))
    if isinstance(value, list):
        return "\n".join(_jira_text(item) for item in value)
    return str(value or "")


def _walk_adf(node: Any) -> list[str]:
    if isinstance(node, dict):
        if node.get("type") == "text":
            return [str(node.get("text", ""))]
        lines: list[str] = []
        for child in node.get("content", []):
            lines.extend(_walk_adf(child))
        return lines
    if isinstance(node, list):
        lines: list[str] = []
        for child in node:
            lines.extend(_walk_adf(child))
        return lines
    return []


def _acceptance_criteria(fields: dict[str, Any], description: str) -> list[str]:
    for key, value in fields.items():
        if "acceptance" in key.lower() and value:
            return split_lines(_jira_text(value))
    return extract_section(description, ("acceptance criteria", "acceptance", "criteria", "expected"))


def _affected_pages(fields: dict[str, Any]) -> list[str]:
    pages: list[str] = []
    for key in ("components", "fixVersions"):
        for item in fields.get(key) or []:
            name = _field_name(item)
            if name:
                pages.append(name)
    return sorted(set(pages))


def _field_name(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("name") or value.get("value") or "")
    return str(value or "")


def _jira_prompt_text(key: str, summary: str, description: str) -> str:
    return "\n".join([
        f"Jira key: {key}",
        f"Summary: {summary}",
        "",
        "Description:",
        description,
    ])
