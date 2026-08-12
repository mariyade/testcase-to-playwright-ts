from __future__ import annotations

import argparse
import json
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
        "--quick-eval",
        action="store_true",
        help="Run only the quick Stage 4 LLM metric subset",
    )
    parser.add_argument(
        "--eval-file",
        help="Stage 4 only: evaluate an existing generated Playwright spec file",
    )
    parser.add_argument(
        "--spec",
        help="Path to a saved Stage 1 TestSpec JSON for --eval-file",
    )
    args = parser.parse_args()

    config = AgentConfig()
    vector_store_dir = config.project_root / "agent" / "vector_store"
    knowledge_dir = config.project_root / "agent" / "knowledge"

    if args.build_index:
        _build_stage2_index(config, knowledge_dir, vector_store_dir)
        return

    if args.eval_file:
        if not args.spec:
            parser.error("--spec is required with --eval-file")
        _evaluate_existing_file(
            Path(args.eval_file),
            Path(args.spec),
            knowledge_dir,
            vector_store_dir,
            full_eval=not args.quick_eval,
        )
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
        full_eval=not args.quick_eval,
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
    if chroma_available():
        counts = collection_counts(vector_store_dir)
        print("Backend: ChromaDB + sentence-transformers")
        for name, count in counts.items():
            print(f"- {name}: {count}")
    else:
        print("Backend: JSON lexical fallback")
        print("Install chromadb and sentence-transformers to enable embedding retrieval.")


def _parse_stage1_spec(args: argparse.Namespace, parser: argparse.ArgumentParser) -> TestSpec:
    from agent.stage1_ticket_parser.parser import parse_ticket_source

    sources = {"jira": args.jira, "github": args.github, "text": args.text}

    for source, value in sources.items():
        if value:
            return parse_ticket_source(source, value)

    parser.error("one of --jira, --github, --text, or --build-index is required")


def _save_stage1_spec(spec: TestSpec, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(spec.model_dump_json(indent=2), encoding="utf-8")
    print(f"Saved Stage 1 spec: {output_path}")


def _evaluate_existing_file(
    eval_file: Path,
    spec_path: Path,
    knowledge_dir: Path,
    vector_store_dir: Path,
    full_eval: bool,
) -> None:
    from agent.stage2_context_retrieval.scanner import scan_playwright_repo_with_retrieval
    from agent.stage4_eval.eval_agent import Stage4EvalAgent

    config = AgentConfig.load()
    spec = TestSpec.model_validate_json(spec_path.read_text(encoding="utf-8"))
    context = scan_playwright_repo_with_retrieval(
        config.playwright_path(), knowledge_dir, vector_store_dir, spec
    )
    report = Stage4EvalAgent().evaluate(eval_file, spec, context, full=full_eval)
    report_path = _save_eval_report(report, config.project_root)

    print(f"Evaluated: {eval_file}")
    print(f"Evaluation report: {report_path}")
    print(f"Score: {report.overall_score} Recommendation: {report.recommendation.value}")
    for issue in report.issues:
        print(f"- {issue}")


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

    if dry_run or not generation.files:
        print(generation.code)
        return

    if skip_eval:
        for generated_file in generation.files:
            print(f"Generated: {generated_file.path}")
        print("Skipped Stage 4 evaluation")
        return
    # Stage 4: evaluate every generated file.
    evaluator = Stage4EvalAgent()
    for generated_file in generation.files:
        report = evaluator.evaluate(generated_file.path, spec, context, full=full_eval)
        report_path = _save_eval_report(report, config.project_root)
        print(f"Generated: {generated_file.path}")
        print(f"Evaluation report: {report_path}")
        print(f"Score: {report.overall_score} Recommendation: {report.recommendation.value}")
        for issue in report.issues:
            print(f"- {issue}")


def _save_eval_report(report, project_root: Path) -> Path:
    source_path = Path(report.filepath)
    report_dir = project_root / "evaluation_results" / "stage4"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / f"{source_path.stem}.eval.json"
    report_path.write_text(json.dumps(report.to_json_dict(), indent=2) + "\n", encoding="utf-8")
    return report_path


if __name__ == "__main__":
    main()
