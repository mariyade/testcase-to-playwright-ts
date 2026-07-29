from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

from agent.models import InputSource, Priority, TestCase, TestSpec, TestType
from agent.stage1_ticket_parser.llm import Stage1ParserAgent


def read_jira_spec(source: str | Path) -> TestSpec:
    def field_name(value: Any) -> str:
        if isinstance(value, dict):
            return str(value.get("name") or value.get("value") or "")
        return str(value or "")

    if str(source).lower().startswith(("http://", "https://")):
        headers = {
            "Accept": "application/json",
            "User-Agent": "testcase-to-playwright-ts/1.0",
        }
        email = os.getenv("JIRA_EMAIL")
        token = os.getenv("JIRA_API_TOKEN")
        if email and token:
            encoded = base64.b64encode(f"{email}:{token}".encode()).decode("ascii")
            headers["Authorization"] = f"Basic {encoded}"
        request = Request(str(source), headers=headers)
        with urlopen(request, timeout=20) as response:
            issue = json.loads(response.read().decode("utf-8"))
    else:
        issue = json.loads(Path(source).read_text(encoding="utf-8"))

    fields = issue.get("fields", issue)

    key = str(issue.get("key") or fields.get("key") or source)
    summary = str(fields.get("summary") or issue.get("summary") or key)
    description = _jira_text(fields.get("description") or issue.get("description") or "")

    if os.getenv("OPENAI_API_KEY"):
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
            return extracted.model_copy(
                update={"raw_content": json.dumps(issue, indent=2, default=str)}
            )
        except Exception:
            pass

    acceptance_criteria: list[str] = []
    for field_name, value in fields.items():
        if "acceptance" in field_name.lower() and value:
            criteria_text = _jira_text(value).replace("\r\n", "\n")
            acceptance_criteria = [
                line.strip(" -\t") for line in criteria_text.split("\n") if line.strip(" -\t")
            ]
            break
    if not acceptance_criteria:
        acceptance_criteria = _extract_section(
            description, ("acceptance criteria", "acceptance", "criteria", "expected")
        )

    steps = _extract_section(description, ("steps", "test steps", "flow"))
    raw_labels = fields.get("labels") or issue.get("labels") or []
    if isinstance(raw_labels, list):
        labels = [str(label).strip() for label in raw_labels if str(label).strip()]
    elif raw_labels:
        labels = [label.strip() for label in str(raw_labels).split(",") if label.strip()]
    else:
        labels = []

    affected_pages: list[str] = []
    for field_key in ("components", "fixVersions"):
        for item in fields.get(field_key) or []:
            page = field_name(item)
            if page:
                affected_pages.append(page)

    return TestSpec(
        source=InputSource.JIRA,
        source_id=str(source),
        title=summary,
        description=description,
        acceptance_criteria=acceptance_criteria,
        affected_pages=sorted(set(affected_pages)),
        test_cases=[
            TestCase(
                id=key,
                title=summary,
                priority=next(
                    (
                        priority
                        for priority in Priority
                        if priority.value.lower()
                        == field_name(fields.get("priority")).strip().lower()
                    ),
                    Priority.HIGH,
                ),
                type=TestType.REGRESSION,
                steps=steps,
                expected_result="\n".join(acceptance_criteria),
                tags=labels,
            )
        ],
        raw_content=json.dumps(issue, indent=2, default=str),
    )


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
