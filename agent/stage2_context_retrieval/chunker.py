from __future__ import annotations

import re
from pathlib import Path

from agent.models import CodeChunk

TS_CLASS_RE = re.compile(r"export\s+class\s+([A-Z][A-Za-z0-9_]*)")
TS_METHOD_RE = re.compile(
    r"(?P<prefix>(?:async\s+)?(?P<name>[a-zA-Z_][A-Za-z0-9_]*)\s*\([^)]*\)\s*(?::\s*[^{]+)?\s*)\{"
)
TS_TEST_RE = re.compile(r"\b(?:test|it)(?:\.only|\.skip)?\s*\(\s*['\"]([^'\"]+)['\"]")
FIXTURE_RE = re.compile(r"\b([a-zA-Z_][A-Za-z0-9_]*)\s*:\s*async\s*\(")


def chunk_playwright_repo(
    playwright_root: Path, knowledge_dir: Path | None = None
) -> list[CodeChunk]:
    chunks: list[CodeChunk] = []
    chunks.extend(_chunk_source_dir(playwright_root / "pages", "code_index", "page_method"))
    chunks.extend(_chunk_source_dir(playwright_root / "fixtures", "code_index", "fixture"))
    chunks.extend(_chunk_source_dir(playwright_root / "tests", "test_index", "test_example"))
    if knowledge_dir:
        chunks.extend(_chunk_knowledge(knowledge_dir))
    return chunks


def _chunk_source_dir(root: Path, collection: str, chunk_type: str) -> list[CodeChunk]:
    if not root.exists():
        return []
    chunks: list[CodeChunk] = []
    for path in sorted(root.rglob("*.ts")):
        if chunk_type == "test_example" and "generated" in path.parts:
            continue
        source = path.read_text(encoding="utf-8")
        if chunk_type == "test_example":
            chunks.extend(_chunk_tests(path, source, collection))
        elif chunk_type == "fixture":
            chunks.extend(_chunk_fixtures(path, source, collection))
        else:
            chunks.extend(_chunk_typescript_methods(path, source, collection, chunk_type))
    return chunks


def _chunk_typescript_methods(
    path: Path, source: str, collection: str, chunk_type: str
) -> list[CodeChunk]:
    class_match = TS_CLASS_RE.search(source)
    class_name = class_match.group(1) if class_match else ""
    chunks: list[CodeChunk] = []
    for match in TS_METHOD_RE.finditer(source):
        name = match.group("name")
        if name in {"if", "for", "while", "switch", "catch", "constructor"}:
            continue
        body = _balanced_block(source, match.start(), match.end() - 1)
        symbol = f"{class_name}.{name}" if class_name else name
        chunks.append(_chunk(path, collection, chunk_type, symbol, body, {"class": class_name}))
    if not chunks and source.strip():
        chunks.append(_chunk(path, collection, "file", path.stem, source, {}))
    return chunks


def _chunk_fixtures(path: Path, source: str, collection: str) -> list[CodeChunk]:
    names = sorted(set(FIXTURE_RE.findall(source)))
    if "test.extend" in source and "page" not in names:
        names.append("page")
    if not names:
        return [_chunk(path, collection, "fixture_file", path.stem, source, {})]
    return [_chunk(path, collection, "fixture", name, source, {"fixture": name}) for name in names]


def _chunk_tests(path: Path, source: str, collection: str) -> list[CodeChunk]:
    matches = list(TS_TEST_RE.finditer(source))
    if not matches:
        return [_chunk(path, collection, "test_file", path.stem, source, {})]

    chunks: list[CodeChunk] = []
    for index, match in enumerate(matches):
        title = match.group(1)
        end = matches[index + 1].start() if index + 1 < len(matches) else len(source)
        text = source[match.start() : end].strip()
        chunks.append(_chunk(path, collection, "test_case", title, text, {"title": title}))
    return chunks


def _chunk_knowledge(root: Path) -> list[CodeChunk]:
    if not root.exists():
        return []
    chunks: list[CodeChunk] = []
    for path in sorted(root.iterdir()):
        if path.suffix.lower() not in {".yaml", ".yml", ".md"}:
            continue
        text = path.read_text(encoding="utf-8")
        chunks.append(
            _chunk(path, "know_index", "knowledge", path.stem, text, {"knowledge": path.stem})
        )
    return chunks


def _chunk(
    path: Path, collection: str, chunk_type: str, symbol: str, text: str, metadata: dict[str, str]
) -> CodeChunk:
    chunk_id = f"{collection}:{path}:{symbol}".replace(" ", "_")
    return CodeChunk(
        id=chunk_id,
        collection=collection,
        chunk_type=chunk_type,
        filepath=path,
        symbol=symbol,
        text=text.strip(),
        metadata=metadata,
    )


def _balanced_block(source: str, start: int, open_brace: int) -> str:
    depth = 0
    for index in range(open_brace, len(source)):
        char = source[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return source[start : index + 1]
    return source[start:].strip()
