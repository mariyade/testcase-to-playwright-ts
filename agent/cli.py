from __future__ import annotations

import argparse
from pathlib import Path

from agent.config import AgentConfig
from agent.models import TestSpec


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate and evaluate TypeScript Playwright tests."
    )
    utilities = parser.add_mutually_exclusive_group()
    utilities.add_argument(
        "--build-index",
        action="store_true",
        help="Stage 2 utility: rebuild the retrieval index",
    )
    utilities.add_argument(
        "--search-index",
        help="Stage 2 utility: search the retrieval index without generating tests",
    )

    source = parser.add_mutually_exclusive_group()
    source.add_argument("--jira", help="Path or URL to Jira issue JSON")
    source.add_argument("--github", help="Path to GitHub issue JSON or URL to a GitHub issue")
    source.add_argument("--text", help="Path or URL to plain text, markdown, or HTML spec")

    parser.add_argument(
        "--save-spec",
        default=None,
        help="Optional path to save the normalized Stage 1 TestSpec JSON",
    )
    parser.add_argument(
        "--stage1-only",
        action="store_true",
        help="Stage 1 only: parse and optionally save the TestSpec, then exit",
    )
    parser.add_argument("--dry-run", action="store_true", help="Generate without writing tests")
    parser.add_argument(
        "--skip-eval",
        action="store_true",
        help="Skip Stage 4 LLM evaluation after writing generated tests",
    )
    parser.add_argument(
        "--full-eval",
        action="store_true",
        help="Run the full Stage 4 LLM metric suite instead of the quick default",
    )
    args = parser.parse_args()

    config = AgentConfig()
    vector_store_dir = config.project_root / "agent" / "vector_store"
    knowledge_dir = config.project_root / "agent" / "knowledge"

    if args.build_index:
        _build_stage2_index(config, knowledge_dir, vector_store_dir)
        return

    if args.search_index:
        _search_stage2_index(args.search_index, vector_store_dir)
        return

    spec = _parse_stage1_spec(args, parser)

    if args.save_spec:
        _save_stage1_spec(spec, Path(args.save_spec))

    if args.stage1_only:
        if not args.save_spec:
            print(spec.model_dump_json(indent=2))
        return

    _generate_and_evaluate(
        spec,
        knowledge_dir,
        vector_store_dir,
        dry_run=args.dry_run,
        skip_eval=args.skip_eval,
        full_eval=args.full_eval,
    )


def _build_stage2_index(config: AgentConfig, knowledge_dir: Path, vector_store_dir: Path) -> None:
    from agent.stage2_context_retrieval.indexer import (
        build_index,
        chroma_available,
        collection_counts,
    )

    chunks = build_index(config.playwright_path(), knowledge_dir, vector_store_dir)
    print(f"Built Stage 2 index: {vector_store_dir}")
    print(f"Chunks: {len(chunks)}")
    print(f"Collections: {', '.join(sorted({chunk.collection for chunk in chunks}))}")
    if chroma_available():
        counts = collection_counts(vector_store_dir)
        print("Backend: ChromaDB + sentence-transformers")
        for name, count in counts.items():
            print(f"- {name}: {count}")
    else:
        print("Backend: JSON lexical fallback")
        print("Install chromadb and sentence-transformers to enable embedding retrieval.")


def _search_stage2_index(query: str, vector_store_dir: Path) -> None:
    from agent.stage2_context_retrieval.retriever import search_index

    result = search_index(query, vector_store_dir)
    print(f"Query: {result.query[:300]}")
    if result.warnings:
        print("Warnings:")
        for warning in result.warnings:
            print(f"- {warning}")
    if not result.chunks:
        print("No matching chunks found.")
        return

    print("Retrieved chunks:")
    for index, chunk in enumerate(result.chunks, start=1):
        print(f"{index}. [{chunk.collection}] {chunk.symbol} ({chunk.filepath})")
        preview = " ".join(chunk.text.split())[:220]
        print(f"   {preview}")


def _parse_stage1_spec(args: argparse.Namespace, parser: argparse.ArgumentParser) -> TestSpec:
    from agent.stage1_ticket_parser.parser import parse_ticket_source

    if args.jira:
        return parse_ticket_source("jira", args.jira)
    if args.github:
        return parse_ticket_source("github", args.github)
    if args.text:
        return parse_ticket_source("text", args.text)

    parser.error("one of --jira, --github, --text, --build-index, or --search-index is required")


def _save_stage1_spec(spec: TestSpec, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(spec.model_dump_json(indent=2), encoding="utf-8")
    print(f"Saved Stage 1 spec: {output_path}")


def _generate_and_evaluate(
    spec: TestSpec,
    knowledge_dir: Path,
    vector_store_dir: Path,
    dry_run: bool,
    skip_eval: bool,
    full_eval: bool,
) -> None:
    from agent.stage2_context_retrieval.scanner import scan_playwright_repo_with_retrieval
    from agent.stage3_generator.generator_agent import Stage3GeneratorAgent
    from agent.stage4_eval.eval_agent import Stage4EvalAgent

    config = AgentConfig.load()

    # Stage 2: collect generation context from page objects, fixtures, knowledge, and retrieval.
    context = scan_playwright_repo_with_retrieval(
        config.playwright_path(), knowledge_dir, vector_store_dir, spec
    )

    # Stage 3: generate Playwright tests from the TestSpec and Stage 2 context.
    generation = Stage3GeneratorAgent(config).generate(spec, context, dry_run=dry_run)
    if not generation.success:
        raise SystemExit(generation.error)

    if generation.missing_methods_filepath:
        print(f"Missing page-object methods: {generation.missing_methods_filepath}")

    if dry_run or not generation.files:
        print(generation.code)
        return

    if skip_eval:
        for generated_file in generation.files:
            print(f"Generated: {generated_file.path}")
            print(f"Type: {generated_file.test_type}")
        print("Skipped Stage 4 evaluation")
        return

    # Stage 4: evaluate every generated file.
    evaluator = Stage4EvalAgent()
    for generated_file in generation.files:
        report = evaluator.evaluate(generated_file.path, spec, context, full=full_eval)
        print(f"Generated: {generated_file.path}")
        print(f"Type: {generated_file.test_type}")
        print(f"Score: {report.overall_score} Recommendation: {report.recommendation.value}")
        for issue in report.issues:
            print(f"- {issue}")


if __name__ == "__main__":
    main()
