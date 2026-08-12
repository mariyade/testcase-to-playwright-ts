from __future__ import annotations

import re
from pathlib import Path

from agent.models import CodeChunk

TS_CLASS_RE = re.compile(r"export\s+class\s+([A-Z][A-Za-z0-9_]*)")
TS_METHOD_RE = re.compile(
    r"(?P<prefix>(?:(?P<access>public|private|protected)\s+)?(?:async\s+)?(?P<name>[a-zA-Z_][A-Za-z0-9_]*)\s*\([^)]*\)\s*(?::\s*[^{]+)?\s*)\{"
)
TS_TEST_RE = re.compile(r"\b(?:test|it)(?:\.only|\.skip)?\s*\(\s*['\"]([^'\"]+)['\"]")
FIXTURE_RE = re.compile(r"\b([a-zA-Z_][A-Za-z0-9_]*)\s*:\s*async\s*\(")
CONTRACT_ANNOTATION_RE = re.compile(r"/\*\*[\s\S]*?@contract[\s\S]*?\*/\s*$")


# Collect page objects, fixtures, authored tests, and knowledge into CodeChunk records.
# These chunks are later saved to JSON and, when available, embedded into Chroma.
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


# Walk one TypeScript directory and route each file to the right chunking strategy.
# Generated tests are skipped so the index stays focused on human-authored examples.
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


# Extract public page-object methods so retrieval can find available actions/assertions.
# If @contract annotations exist, only annotated methods are indexed.
def _chunk_typescript_methods(
    path: Path, source: str, collection: str, chunk_type: str
) -> list[CodeChunk]:
    class_match = TS_CLASS_RE.search(source)
    class_name = class_match.group(1) if class_match else ""
    chunks: list[CodeChunk] = []
    matches = [
        match
        for match in TS_METHOD_RE.finditer(source)
        if match.group("access") != "private"
        and match.group("name") not in {"if", "for", "while", "switch", "catch", "constructor"}
    ]
    has_contract_annotations = any(
        _has_contract_annotation(source, match.start()) for match in matches
    )
    for match in matches:
        name = match.group("name")
        if has_contract_annotations and not _has_contract_annotation(source, match.start()):
            continue
        text = match.group("prefix").strip()
        if not has_contract_annotations:
            text = _balanced_block(source, match.start(), match.end() - 1)
        symbol = f"{class_name}.{name}" if class_name else name
        chunks.append(_chunk(path, collection, chunk_type, symbol, text, {"class": class_name}))
    if not chunks and source.strip():
        chunks.append(_chunk(path, collection, "file", path.stem, source, {}))
    return chunks


# Look just before a method declaration for an @contract docblock.
# This lets page objects intentionally expose only supported generator methods.
def _has_contract_annotation(source: str, method_start: int) -> bool:
    prefix = source[max(0, method_start - 500) : method_start]
    return bool(CONTRACT_ANNOTATION_RE.search(prefix))


# Index each fixture name exposed by a fixture file.
# If fixture names cannot be detected, keep the whole file as one fallback chunk.
def _chunk_fixtures(path: Path, source: str, collection: str) -> list[CodeChunk]:
    names = sorted(set(FIXTURE_RE.findall(source)))
    if "test.extend" in source and "page" not in names:
        names.append("page")
    if not names:
        return [_chunk(path, collection, "fixture_file", path.stem, source, {})]
    return [_chunk(path, collection, "fixture", name, source, {"fixture": name}) for name in names]


# Split authored specs into individual test examples.
# These examples help retrieval find existing project style and patterns.
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


# Add human-authored markdown/YAML guidance to the knowledge collection.
# This is where QA strategy, test data notes, and product rules become retrievable.
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


# Build the shared CodeChunk model used by JSON fallback and vector retrieval.
# The chunk ID includes collection, path, and symbol so rebuilds stay stable.
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


# Return a complete TypeScript method block by balancing braces.
# This keeps method chunks useful when no @contract annotation narrows the text.
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
