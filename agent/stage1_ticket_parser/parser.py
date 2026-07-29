from __future__ import annotations

from pathlib import Path

from agent.models import TestSpec


def parse_ticket_source(source_type: str, source: str | Path) -> TestSpec:
    source_type = source_type.strip().lower()

    if source_type == "jira":
        from agent.stage1_ticket_parser.jira import read_jira_spec

        return read_jira_spec(source)

    if source_type == "github":
        from agent.stage1_ticket_parser.github import read_github_issue_spec

        return read_github_issue_spec(source)

    if source_type == "text":
        from agent.stage1_ticket_parser.text import read_text_spec

        return read_text_spec(source)

    raise ValueError(f"Unsupported source type: {source_type}")
