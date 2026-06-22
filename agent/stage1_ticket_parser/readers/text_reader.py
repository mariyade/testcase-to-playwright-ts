from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.request import Request, urlopen

from agent.models import InputSource, TestCase, TestSpec
from agent.stage1_ticket_parser.extractor import extract_text_spec
from agent.stage1_ticket_parser.readers.parser_utils import is_url


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


def read_text_spec(source: str | Path, title: str | None = None) -> TestSpec:
    raw_content = _read_text_source(source)
    cleaned = _html_to_text(raw_content) if _looks_like_html(raw_content) else raw_content
    return extract_text_spec(cleaned, source=source, title=title)


def _read_text_source(source: str | Path) -> str:
    if is_url(source):
        request = Request(str(source), headers={"User-Agent": "testcase-to-playwright-ts/1.0"})
        with urlopen(request, timeout=20) as response:
            return response.read().decode("utf-8", errors="replace")
    return Path(source).read_text(encoding="utf-8")


def _looks_like_html(text: str) -> bool:
    return "<html" in text[:500].lower() or "<!doctype html" in text[:500].lower()


def _html_to_text(html: str) -> str:
    parser = _TextExtractor()
    parser.feed(html)
    return parser.text()


def extract_urls(text: str) -> list[str]:
    urls = sorted(set(re.findall(r"https?://[^\s)>\"]+", text)))
    return urls[:10]
