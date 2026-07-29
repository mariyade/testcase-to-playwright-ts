from __future__ import annotations

import re
from pathlib import Path

from agent.models import FixtureInfo, PageObjectInfo, RepoContext

try:
    import yaml
except ModuleNotFoundError:
    yaml = None


CLASS_RE = re.compile(r"export\s+class\s+([A-Z][A-Za-z0-9_]*)")
METHOD_RE = re.compile(r"(?:async\s+)?([a-zA-Z_][A-Za-z0-9_]*)\s*\([^)]*\)\s*(?::\s*[^{]+)?\s*\{")
PROPERTY_RE = re.compile(
    r"(?:readonly|public|private|protected)?\s+([a-zA-Z_][A-Za-z0-9_]*)\s*[:=]"
)
FIXTURE_RE = re.compile(r"\b([a-zA-Z_][A-Za-z0-9_]*)\s*:\s*async\s*\(")


def scan_playwright_repo(
    playwright_root: str | Path, knowledge_dir: str | Path | None = None
) -> RepoContext:
    root = Path(playwright_root)
    pages_dir = root / "pages"
    fixtures_dir = root / "fixtures"
    tests_dir = root / "tests"

    context = RepoContext(playwright_root=root)

    if pages_dir.exists():
        for path in sorted(pages_dir.rglob("*.ts")):
            context.page_objects.extend(_read_page_objects(path))

    if fixtures_dir.exists():
        for path in sorted(fixtures_dir.rglob("*.ts")):
            context.fixtures.extend(_read_fixtures(path))

    if tests_dir.exists():
        context.example_specs = sorted(
            path for path in tests_dir.rglob("*.spec.ts") if "generated" not in path.parts
        )

    if knowledge_dir:
        context.knowledge = _read_knowledge(Path(knowledge_dir))

    return context


def scan_playwright_repo_with_retrieval(
    playwright_root: str | Path,
    knowledge_dir: str | Path,
    vector_store_dir: str | Path,
    spec,
) -> RepoContext:
    from agent.stage2_context_retrieval.retriever import retrieve_context

    context = scan_playwright_repo(playwright_root, knowledge_dir)
    context.retrieved_chunks = retrieve_context(spec, Path(vector_store_dir)).chunks
    return context


def _read_page_objects(path: Path) -> list[PageObjectInfo]:
    source = path.read_text(encoding="utf-8")
    classes = CLASS_RE.findall(source)
    if not classes:
        return []

    methods = [
        name
        for name in METHOD_RE.findall(source)
        if name not in {"if", "for", "while", "switch", "catch", "constructor"}
    ]
    properties = [
        name
        for name in PROPERTY_RE.findall(source)
        if name not in {"return", "const", "let", "var", "await"}
    ]

    return [
        PageObjectInfo(
            name=class_name,
            filepath=path,
            methods=sorted(set(methods)),
            properties=sorted(set(properties)),
        )
        for class_name in classes
    ]


def _read_fixtures(path: Path) -> list[FixtureInfo]:
    source = path.read_text(encoding="utf-8")
    names = set(FIXTURE_RE.findall(source))
    if "test.extend" in source:
        names.add("page")
    return [FixtureInfo(name=name, source_file=path) for name in sorted(names)]


KNOWLEDGE_EXTENSIONS = {".md", ".yaml", ".yml"}


def _read_knowledge(path: Path) -> dict[str, str]:
    knowledge: dict[str, str] = {}
    if not path.exists():
        return knowledge

    files = sorted(file for file in path.iterdir() if file.suffix.lower() in KNOWLEDGE_EXTENSIONS)
    for file in files:
        if file.suffix.lower() == ".md":
            knowledge[file.stem] = file.read_text(encoding="utf-8")
            continue

        source = file.read_text(encoding="utf-8")
        if yaml is None:
            knowledge[file.stem] = source
            continue

        try:
            parsed = yaml.safe_load(source)
            knowledge[file.stem] = yaml.safe_dump(parsed, sort_keys=False)
        except Exception:
            knowledge[file.stem] = source
    return knowledge
