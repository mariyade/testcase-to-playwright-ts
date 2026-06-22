from __future__ import annotations

import re
from enum import Enum
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from agent.models import Priority, TestType


URL_RE = re.compile(r"^https?://", re.IGNORECASE)


def is_url(value: str | Path) -> bool:
    return bool(URL_RE.match(str(value)))


def source_id(value: str | Path) -> str:
    return str(value)


def title_from_source(value: str | Path) -> str:
    text = str(value)
    if is_url(text):
        parsed = urlparse(text)
        return parsed.netloc + parsed.path.rstrip("/")
    return Path(text).stem


def normalise_header(value: Any) -> str:
    return str(value or "").strip().lower()


def first(data: dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        value = data.get(key)
        if value not in (None, ""):
            return value
    return default


def split_lines(value: Any) -> list[str]:
    if value in (None, ""):
        return []
    text = str(value).replace("\r\n", "\n")
    return [line.strip(" -\t") for line in text.split("\n") if line.strip(" -\t")]


def split_tags(value: Any) -> list[str]:
    if value in (None, ""):
        return []
    if isinstance(value, list):
        return [str(part).strip() for part in value if str(part).strip()]
    return [part.strip() for part in str(value).split(",") if part.strip()]


def enum_or_default(enum_type: type[Enum], value: Any, default: Enum):
    text = str(value or "").strip().lower()
    for item in enum_type:
        if item.value.lower() == text:
            return item
    return default


def priority_from_text(value: Any) -> Priority:
    return enum_or_default(Priority, value, Priority.HIGH)


def test_type_from_text(value: Any) -> TestType:
    return enum_or_default(TestType, value, TestType.REGRESSION)


def extract_section(text: str, names: tuple[str, ...]) -> list[str]:
    lines = text.replace("\r\n", "\n").split("\n")
    collected: list[str] = []
    collecting = False
    section_pattern = re.compile(r"^\s*([A-Za-z][A-Za-z /_-]{1,50})\s*:\s*$")
    wanted = {name.lower() for name in names}

    for line in lines:
        stripped = line.strip()
        match = section_pattern.match(stripped)
        if match:
            section_name = match.group(1).strip().lower()
            if collecting and section_name not in wanted:
                break
            collecting = section_name in wanted
            continue
        if collecting and stripped:
            collected.append(stripped.strip(" -\t"))

    return collected

