from __future__ import annotations

from pathlib import Path

from agent.models import RepoContext
from agent.stage2_context_retrieval.implementation_planner import enrich_implementation_plan
from agent.stage2_context_retrieval.typescript_scanner import (
    assertion_contracts,
    read_fixtures,
    read_page_objects,
    read_type_shapes,
)

try:
    import yaml
except ModuleNotFoundError:
    yaml = None


# Build the complete Stage 2 context used by Stage 3.
# It scans the repo, retrieves relevant chunks, then plans how each test maps to code.
def scan_playwright_repo_with_retrieval(
    playwright_root: str | Path,
    knowledge_dir: str | Path,
    vector_store_dir: str | Path,
    spec,
) -> RepoContext:
    from agent.stage2_context_retrieval.retriever import retrieve_context

    context = scan_playwright_repo(playwright_root, knowledge_dir)
    context.retrieved_chunks = retrieve_context(spec, Path(vector_store_dir)).chunks
    context.implementation = enrich_implementation_plan(context, spec)
    return context


# Read static repository facts into RepoContext without using the vector index.
# This captures page-object contracts, fixtures, existing specs, and knowledge docs.
def scan_playwright_repo(
    playwright_root: str | Path, knowledge_dir: str | Path | None = None
) -> RepoContext:
    root = Path(playwright_root)
    pages_dir = root / "pages"
    fixtures_dir = root / "fixtures"
    tests_dir = root / "tests"

    context = RepoContext(playwright_root=root)
    type_shapes = read_type_shapes(pages_dir)

    if pages_dir.exists():
        for path in sorted(pages_dir.rglob("*.ts")):
            context.page_objects.extend(read_page_objects(path, type_shapes))
        context.repository_contracts.assertions = assertion_contracts(context.page_objects)

    if fixtures_dir.exists():
        for path in sorted(fixtures_dir.rglob("*.ts")):
            context.fixtures.extend(read_fixtures(path))

    if tests_dir.exists():
        context.example_specs = sorted(
            path for path in tests_dir.rglob("*.spec.ts") if "generated" not in path.parts
        )

    if knowledge_dir:
        context.knowledge = _read_knowledge(Path(knowledge_dir))

    return context


KNOWLEDGE_EXTENSIONS = {".md", ".yaml", ".yml"}


# Load markdown/YAML knowledge files into plain text.
# YAML is normalized when PyYAML is installed so prompt output is stable.
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
