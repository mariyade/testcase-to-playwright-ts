from __future__ import annotations

import json
import os
import re
from pathlib import Path
from urllib.request import Request, urlopen

from agent.config import AgentConfig
from agent.models import InputSource, TestCase, TestSpec
from agent.stage1_ticket_parser.llm import Stage1ParserAgent

GITHUB_ISSUE_RE = re.compile(r"github\.com/([^/]+)/([^/]+)/issues/(\d+)")


def read_github_issue_spec(source: str | Path) -> TestSpec:
    if str(source).lower().startswith(("http://", "https://")):
        match = GITHUB_ISSUE_RE.search(str(source))
        if not match:
            raise ValueError(f"Not a supported GitHub issue URL: {source}")
        owner, repo, number = match.groups()
        api_url = f"https://api.github.com/repos/{owner}/{repo}/issues/{number}"
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "testcase-to-playwright-ts/1.0",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        token = os.getenv("GITHUB_TOKEN")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        request = Request(api_url, headers=headers)
        with urlopen(request, timeout=20) as response:
            issue = json.loads(response.read().decode("utf-8"))
    else:
        issue = json.loads(Path(source).read_text(encoding="utf-8"))

    issue_id = f"GH_{issue.get('number', 'ISSUE')}"
    title = str(issue.get("title") or issue_id)
    body = str(issue.get("body") or "")
    raw_labels = issue.get("labels", [])
    labels = (
        [str(label.get("name", "")).strip() for label in raw_labels if isinstance(label, dict)]
        if isinstance(raw_labels, list)
        else []
    )
    labels = [label for label in labels if label]

    if AgentConfig.has_agent_llm_config():
        try:
            prompt_text = "\n".join(
                [
                    f"GitHub issue: #{issue.get('number', '')}",
                    f"Title: {title}",
                    f"State: {issue.get('state', '')}",
                    f"Labels: {', '.join(labels)}",
                    "",
                    "Body:",
                    body,
                ]
            )
            extracted = Stage1ParserAgent().extract(
                prompt_text,
                source=source,
                title=title,
                input_source=InputSource.GITHUB,
            )
            return extracted.model_copy(
                update={"raw_content": json.dumps(issue, indent=2, default=str)}
            )
        except Exception as exc:
            print(f"Stage 1 LLM extraction failed: {type(exc).__name__}: {exc}")
            raise

    acceptance_criteria = _extract_section(
        body, ("acceptance criteria", "acceptance", "criteria", "expected")
    )
    steps = _extract_section(body, ("steps", "test steps", "reproduction steps", "flow")) or [
        f"Perform the behaviour described by: {title}"
    ]
    expected_result = "\n".join(acceptance_criteria) or body or title
    affected_pages = []
    for label in labels:
        normalized = label.strip().lower().replace(" ", "_").replace("-", "_")
        if normalized.endswith("_page") or normalized.startswith("page_"):
            affected_pages.append(normalized)

    return TestSpec(
        source=InputSource.GITHUB,
        source_id=str(source),
        title=title,
        description=body,
        acceptance_criteria=acceptance_criteria,
        affected_pages=sorted(set(affected_pages)),
        test_cases=[
            TestCase(
                id=issue_id,
                title=title,
                steps=steps,
                expected_result=expected_result,
                tags=labels,
            )
        ],
        raw_content=json.dumps(issue, indent=2, default=str),
    )


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
