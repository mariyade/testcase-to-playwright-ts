from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

from agent.models import InputSource, TestCase, TestSpec, TestType
from agent.stage1_ticket_parser.extractor import extract_text_spec_with_llm
from agent.stage1_ticket_parser.readers.parser_utils import (
    extract_section,
    is_url,
    source_id,
    split_tags,
)


GITHUB_ISSUE_RE = re.compile(r"github\.com/([^/]+)/([^/]+)/issues/(\d+)")


def read_github_issue_spec(source: str | Path) -> TestSpec:
    issue = _read_github_issue(source)
    issue_id = f"GH_{issue.get('number', 'ISSUE')}"
    title = str(issue.get("title") or issue_id)
    body = str(issue.get("body") or "")

    if os.getenv("OPENAI_API_KEY"):
        try:
            extracted = extract_text_spec_with_llm(
                _github_prompt_text(issue, title, body),
                source=source,
                title=title,
                input_source=InputSource.GITHUB,
            )
            return extracted.model_copy(update={"raw_content": json.dumps(issue, indent=2, default=str)})
        except Exception:
            pass

    labels = _label_names(issue)
    acceptance_criteria = extract_section(body, ("acceptance criteria", "acceptance", "criteria", "expected"))
    steps = extract_section(body, ("steps", "test steps", "reproduction steps", "flow"))

    return TestSpec(
        source=InputSource.GITHUB,
        source_id=source_id(source),
        title=title,
        description=body,
        acceptance_criteria=acceptance_criteria,
        affected_pages=_affected_pages(labels),
        test_cases=[
            TestCase(
                id=issue_id,
                title=title,
                type=TestType.REGRESSION,
                steps=steps,
                expected_result="\n".join(acceptance_criteria),
                tags=labels,
            )
        ],
        raw_content=json.dumps(issue, indent=2, default=str),
    )


def _read_github_issue(source: str | Path) -> dict[str, Any]:
    if is_url(source):
        request = Request(_github_api_url(str(source)), headers=_github_headers())
        with urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))
    return json.loads(Path(source).read_text(encoding="utf-8"))


def _github_api_url(url: str) -> str:
    match = GITHUB_ISSUE_RE.search(url)
    if not match:
        raise ValueError(f"Not a supported GitHub issue URL: {url}")
    owner, repo, number = match.groups()
    return f"https://api.github.com/repos/{owner}/{repo}/issues/{number}"


def _github_headers() -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "testcase-to-playwright-ts/1.0",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = os.getenv("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _github_prompt_text(issue: dict[str, Any], title: str, body: str) -> str:
    labels = _label_names(issue)
    return "\n".join([
        f"GitHub issue: #{issue.get('number', '')}",
        f"Title: {title}",
        f"State: {issue.get('state', '')}",
        f"Labels: {', '.join(labels)}",
        "",
        "Body:",
        body,
    ])


def _label_names(issue: dict[str, Any]) -> list[str]:
    labels = issue.get("labels", [])
    if not isinstance(labels, list):
        return []
    return split_tags([label.get("name", "") for label in labels if isinstance(label, dict)])


def _affected_pages(labels: list[str]) -> list[str]:
    page_labels: list[str] = []
    for label in labels:
        normalized = label.strip().lower().replace(" ", "_").replace("-", "_")
        if normalized.endswith("_page") or normalized.startswith("page_"):
            page_labels.append(normalized)
    return sorted(set(page_labels))
