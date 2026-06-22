from __future__ import annotations

from pathlib import Path

from agent.models import TestSpec


def parse_ticket_source(
    source_type: str,
    source: str | Path,
    sheet_name: str | None = None,
    status_filter: str | None = None,
    limit: int | None = None,
) -> TestSpec:
    normalised = source_type.strip().lower()
    if normalised == "excel":
        from agent.stage1_ticket_parser.readers.excel_reader import read_excel_spec

        return read_excel_spec(source, sheet_name, status_filter=status_filter, limit=limit)
    if normalised == "jira":
        from agent.stage1_ticket_parser.readers.jira_reader import read_jira_spec

        return read_jira_spec(source)
    if normalised == "github":
        from agent.stage1_ticket_parser.readers.github_reader import read_github_issue_spec

        return read_github_issue_spec(source)
    if normalised == "text":
        from agent.stage1_ticket_parser.readers.text_reader import read_text_spec

        return read_text_spec(source)
    raise ValueError(f"Unsupported source type: {source_type}")


read_spec = parse_ticket_source
