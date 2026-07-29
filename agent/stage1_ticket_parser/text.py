from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path
from urllib.request import Request, urlopen

from agent.models import TestSpec
from agent.stage1_ticket_parser.llm import Stage1ParserAgent


def read_text_spec(source: str | Path, title: str | None = None) -> TestSpec:
    if str(source).lower().startswith(("http://", "https://")):
        request = Request(str(source), headers={"User-Agent": "testcase-to-playwright-ts/1.0"})
        with urlopen(request, timeout=20) as response:
            raw_content = response.read().decode("utf-8", errors="replace")
    else:
        raw_content = Path(source).read_text(encoding="utf-8")

    if "<html" in raw_content[:500].lower() or "<!doctype html" in raw_content[:500].lower():
        parser = _TextExtractor()
        parser.feed(raw_content)
        content = parser.text()
    else:
        content = raw_content

    return Stage1ParserAgent().extract(content, source=source, title=title)


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        text = data.strip()
        if text:
            self.parts.append(text)

    def text(self) -> str:
        return "\n".join(self.parts)
