from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from agent.config import AgentConfig
from agent.stage1_ticket_parser.parser import parse_ticket_source
from agent.stage2_context_retrieval.indexer import INDEX_FILE, build_index
from agent.stage2_context_retrieval.retriever import search_index
from agent.stage2_context_retrieval.scanner import scan_playwright_repo_with_retrieval
from agent.stage3_generator.generator_agent import Stage3GeneratorAgent

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def load_json_rows(relative_path: str) -> list[dict[str, Any]]:
    path = Path(__file__).parent / relative_path
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def retrieved_context(query: str, top_k: int = 8) -> list[str]:
    config = AgentConfig()
    vector_store_dir = config.project_root / "agent" / "vector_store"
    knowledge_dir = config.project_root / "agent" / "knowledge"
    if not (vector_store_dir / INDEX_FILE).exists():
        build_index(config.playwright_path(), knowledge_dir, vector_store_dir)

    result = search_index(query, vector_store_dir, top_k=top_k)
    return [
        "\n".join(
            [
                f"collection: {chunk.collection}",
                f"symbol: {chunk.symbol}",
                f"path: {chunk.filepath}",
                chunk.text,
            ]
        )
        for chunk in result.chunks
    ]


def generated_output(metadata: dict[str, Any]) -> str:
    generated_file = metadata.get("generated_file")
    if generated_file:
        generated_path = PROJECT_ROOT / generated_file
        if generated_path.exists():
            code = generated_path.read_text(encoding="utf-8")
            missing_methods_file = metadata.get("missing_methods_file")
            if missing_methods_file:
                missing_methods_path = PROJECT_ROOT / missing_methods_file
                if missing_methods_path.exists():
                    return "\n\n".join(
                        [
                            code,
                            "# Missing page-object methods",
                            missing_methods_path.read_text(encoding="utf-8"),
                        ]
                    )
            return code

    if not os.getenv("OPENAI_API_KEY"):
        msg = "OPENAI_API_KEY is required when no generated_file is provided"
        raise RuntimeError(msg)

    config = AgentConfig.load()
    source_file = metadata["source_file"]
    spec = parse_ticket_source("text", str(PROJECT_ROOT / source_file))
    context = scan_playwright_repo_with_retrieval(
        config.playwright_path(),
        config.project_root / "agent" / "knowledge",
        config.project_root / "agent" / "vector_store",
        spec,
    )
    result = Stage3GeneratorAgent(config).generate(spec, context, dry_run=True)
    return "\n\n".join(
        [
            result.code,
            "# Missing page-object methods",
            json.dumps(
                [method.model_dump(mode="json") for method in result.missing_page_object_methods],
                indent=2,
            ),
        ]
    )
