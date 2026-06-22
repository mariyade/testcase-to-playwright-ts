from __future__ import annotations

import argparse
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate and evaluate TypeScript Playwright tests.")
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument("--index", action="store_true", help="Build or refresh the Stage 2 retrieval index")
    actions.add_argument("--search", help="Search the Stage 2 retrieval index")

    source = parser.add_mutually_exclusive_group()
    source.add_argument("--excel", help="Path to Excel test case file")
    source.add_argument("--jira", help="Path or URL to Jira issue JSON")
    source.add_argument("--github", help="Path to GitHub issue JSON or URL to a GitHub issue")
    source.add_argument("--text", help="Path or URL to plain text, markdown, or HTML spec")
    parser.add_argument("--sheet", default=None, help="Optional sheet name")
    parser.add_argument("--status", default=None, help="Optional Excel automation status filter")
    parser.add_argument("--limit", type=int, default=None, help="Optional maximum number of parsed test cases")
    parser.add_argument("--save-spec", default=None, help="Optional path to save the normalized Stage 1 TestSpec JSON")
    parser.add_argument("--stage1-only", action="store_true", help="Parse and optionally save the Stage 1 TestSpec, then exit")
    parser.add_argument("--retrieve", action="store_true", help="Parse Stage 1 and retrieve Stage 2 context, then exit")
    parser.add_argument("--dry-run", action="store_true", help="Generate without writing the spec")
    args = parser.parse_args()

    from agent.config import AgentConfig

    config = AgentConfig()
    vector_store_dir = config.project_root / "agent" / "vector_store"
    knowledge_dir = config.project_root / "agent" / "knowledge"

    # Stage 2 utility: build or refresh the retrieval index.
    if args.index:
        from agent.stage2_context_retrieval.indexer import build_index, chroma_available, collection_counts

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
        return

    # Stage 2 utility: search the retrieval index directly with a free-text query.
    if args.search:
        from agent.stage2_context_retrieval.retriever import search_index

        result = search_index(args.search, vector_store_dir)
        _print_retrieval_result(result)
        return

    if not (args.excel or args.jira or args.github or args.text):
        parser.error("one of --excel, --jira, --github, --text, --index, or --search is required")

    from agent.stage1_ticket_parser.parser_agent import parse_ticket_source

    # Stage 1: parse Excel/Jira/GitHub/Text into a normalized TestSpec.
    source_type = "excel" if args.excel else "jira" if args.jira else "github" if args.github else "text"
    source_value = args.excel or args.jira or args.github or args.text
    spec = parse_ticket_source(source_type, source_value, args.sheet, status_filter=args.status, limit=args.limit)

    if args.save_spec:
        output_path = Path(args.save_spec)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(spec.model_dump_json(indent=2), encoding="utf-8")
        print(f"Saved Stage 1 spec: {output_path}")

    if args.stage1_only:
        if not args.save_spec:
            print(spec.model_dump_json(indent=2))
        return

    # Stage 2: retrieve relevant repo context for the parsed TestSpec, then stop.
    if args.retrieve:
        from agent.stage2_context_retrieval.retriever import retrieve_context

        result = retrieve_context(spec, vector_store_dir)
        _print_retrieval_result(result)
        return

    from agent.stage2_context_retrieval.scanner import scan_playwright_repo_with_retrieval
    from agent.stage3_generator.generator_agent import GeneratorAgent
    from agent.stage4_eval.eval_agent import EvalAgent

    config = AgentConfig.load()

    # Stage 2: scan repo context and attach retrieved chunks for generation.
    context = scan_playwright_repo_with_retrieval(config.playwright_path(), knowledge_dir, vector_store_dir, spec)

    # Stage 3: generate the TypeScript Playwright spec from TestSpec + RepoContext.
    generation = GeneratorAgent(config).generate(spec, context, dry_run=args.dry_run)
    if not generation.success:
        raise SystemExit(generation.error)

    if generation.filepath:
        # Stage 4: evaluate the generated spec and print the recommendation.
        report = EvalAgent().evaluate(generation.filepath, spec, context)
        print(f"Generated: {generation.filepath}")
        print(f"Score: {report.overall_score} Recommendation: {report.recommendation.value}")
        for issue in report.issues:
            print(f"- {issue}")
    else:
        print(generation.code)

def _print_retrieval_result(result) -> None:
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


if __name__ == "__main__":
    main()
