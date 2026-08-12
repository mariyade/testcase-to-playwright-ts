from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from agent.config import AgentConfig
from agent.models import InputSource, TestCase, TestSpec
from agent.stage1_ticket_parser.llm import Stage1ParserAgent


def read_jira_spec(source: str | Path) -> TestSpec:
    issue = _read_issue(source)
    fields = issue.get("fields", issue)
    key = str(issue.get("key") or fields.get("key") or source)
    summary = str(fields.get("summary") or issue.get("summary") or key)
    description = _jira_text(fields.get("description") or issue.get("description") or "")
    raw_content = json.dumps(issue, indent=2, default=str)

    llm_spec = _try_llm_extract(
        source=source,
        key=key,
        summary=summary,
        description=description,
        raw_content=raw_content,
    )
    if llm_spec:
        return llm_spec

    return _build_basic_jira_spec(
        source=source,
        issue=issue,
        fields=fields,
        key=key,
        summary=summary,
        description=description,
        raw_content=raw_content,
    )


def _read_issue(source: str | Path) -> dict[str, Any]:
    source_text = str(source)
    if not source_text.lower().startswith(("http://", "https://")):
        return json.loads(Path(source).read_text(encoding="utf-8"))

    headers = {
        "Accept": "application/json",
        "User-Agent": "testcase-to-playwright-ts/1.0",
    }
    email = os.getenv("JIRA_EMAIL")
    token = os.getenv("JIRA_API_TOKEN")
    if email and token:
        encoded = base64.b64encode(f"{email}:{token}".encode()).decode("ascii")
        headers["Authorization"] = f"Basic {encoded}"

    request = Request(source_text, headers=headers)
    try:
        with urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace").strip()
        message = f"Failed to read Jira issue {source}: HTTP {exc.code} {exc.reason}."
        if detail:
            message = f"{message}\nResponse: {detail}"
        raise RuntimeError(
            f"{message}\nCheck the Jira URL, credentials, and project permissions."
        ) from exc
    except URLError as exc:
        raise RuntimeError(f"Failed to connect to Jira issue {source}: {exc.reason}") from exc


def _try_llm_extract(
    *,
    source: str | Path,
    key: str,
    summary: str,
    description: str,
    raw_content: str,
) -> TestSpec | None:
    if not AgentConfig.has_agent_llm_config():
        return None

    try:
        prompt_text = "\n".join(
            [
                f"Jira key: {key}",
                f"Summary: {summary}",
                "",
                "Description:",
                description,
            ]
        )
        extracted = Stage1ParserAgent().extract(
            prompt_text,
            source=source,
            title=summary,
            input_source=InputSource.JIRA,
        )
        return extracted.model_copy(update={"raw_content": raw_content})
    except Exception as exc:
        print(f"Stage 1 LLM extraction failed: {type(exc).__name__}: {exc}")
        raise


def _build_basic_jira_spec(
    *,
    source: str | Path,
    issue: dict[str, Any],
    fields: dict[str, Any],
    key: str,
    summary: str,
    description: str,
    raw_content: str,
) -> TestSpec:
    acceptance_criteria = _acceptance_criteria(fields, description)
    steps = _extract_section(description, ("steps", "test steps", "flow")) or [
        f"Perform the behaviour described by: {summary}"
    ]
    expected_result = "\n".join(acceptance_criteria) or description or summary
    return TestSpec(
        source=InputSource.JIRA,
        source_id=str(source),
        title=summary,
        description=description,
        acceptance_criteria=acceptance_criteria,
        affected_pages=_affected_pages(fields),
        test_cases=[
            TestCase(
                id=key,
                title=summary,
                steps=steps,
                expected_result=expected_result,
                tags=_labels(fields.get("labels") or issue.get("labels") or []),
            )
        ],
        raw_content=raw_content,
    )


def _acceptance_criteria(fields: dict[str, Any], description: str) -> list[str]:
    for field_key, value in fields.items():
        if "acceptance" in field_key.lower() and value:
            return _clean_lines(_jira_text(value))

    return _extract_section(
        description,
        ("acceptance criteria", "acceptance", "criteria", "expected"),
    )


def _labels(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(label).strip() for label in value if str(label).strip()]
    if value:
        return [label.strip() for label in str(value).split(",") if label.strip()]
    return []


def _affected_pages(fields: dict[str, Any]) -> list[str]:
    affected_pages: list[str] = []
    for field_key in ("components", "fixVersions"):
        for item in fields.get(field_key) or []:
            page = _field_name(item)
            if page:
                affected_pages.append(page)
    return sorted(set(affected_pages))


def _field_name(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("name") or value.get("value") or "")
    return str(value or "")


def _jira_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, (dict, list)):
        return "\n".join(_walk_adf(value))
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


def _extract_section(text: str, names: tuple[str, ...]) -> list[str]:
    lines = text.replace("\r\n", "\n").split("\n")
    collected: list[str] = []
    collecting = False
    wanted = {name.lower() for name in names}

    for line in lines:
        stripped = line.strip()
        if stripped.endswith(":"):
            section_name = stripped[:-1].strip().lower()
            if collecting and section_name not in wanted:
                break
            collecting = section_name in wanted
            continue
        if collecting and stripped:
            collected.append(stripped.strip(" -\t"))

    return collected


def _clean_lines(text: str) -> list[str]:
    return [
        line.strip(" -\t") for line in text.replace("\r\n", "\n").split("\n") if line.strip(" -\t")
    ]
