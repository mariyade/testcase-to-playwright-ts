from __future__ import annotations

import math
import re
from collections import Counter
from pathlib import Path

from agent.models import CodeChunk, RetrievalResult, TestSpec
from agent.stage2_context_retrieval.indexer import COLLECTIONS, EMBEDDING_MODEL, chroma_available, load_index


TOKEN_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9_]+")


def retrieve_context(spec: TestSpec, vector_store_dir: Path, top_k: int = 12) -> RetrievalResult:
    query = _query_from_spec(spec)
    if chroma_available():
        result = _retrieve_chroma(query, vector_store_dir, top_k)
        if result.chunks:
            return result

    chunks = load_index(vector_store_dir)
    if not chunks:
        return RetrievalResult(query=query, warnings=[f"No Stage 2 index found in {vector_store_dir}"])

    scored = sorted(
        ((score_chunk(query, chunk), chunk) for chunk in chunks),
        key=lambda item: item[0],
        reverse=True,
    )
    selected = [chunk for score, chunk in scored if score > 0][:top_k]
    warnings = _warnings(selected)
    return RetrievalResult(query=query, chunks=selected, warnings=warnings)


def search_index(query: str, vector_store_dir: Path, top_k: int = 10) -> RetrievalResult:
    if chroma_available():
        result = _retrieve_chroma(query, vector_store_dir, top_k)
        if result.chunks:
            return result

    chunks = load_index(vector_store_dir)
    scored = sorted(
        ((score_chunk(query, chunk), chunk) for chunk in chunks),
        key=lambda item: item[0],
        reverse=True,
    )
    selected = [chunk for score, chunk in scored if score > 0][:top_k]
    return RetrievalResult(query=query, chunks=selected, warnings=_warnings(selected))


def _retrieve_chroma(query: str, vector_store_dir: Path, top_k: int) -> RetrievalResult:
    try:
        import chromadb
        from sentence_transformers import SentenceTransformer

        client = chromadb.PersistentClient(path=str(vector_store_dir / "chroma"))
        embedder = SentenceTransformer(EMBEDDING_MODEL, local_files_only=True)
        query_embedding = embedder.encode([query], normalize_embeddings=True).tolist()[0]
    except Exception as exc:
        return RetrievalResult(
            query=query,
            warnings=[f"ChromaDB embedding retrieval unavailable; using JSON lexical fallback. Reason: {exc}"],
        )

    chunks: list[CodeChunk] = []
    warnings: list[str] = []
    per_collection = max(1, top_k // len(COLLECTIONS) + 1)
    for collection_name in COLLECTIONS:
        collection = client.get_or_create_collection(collection_name)
        if collection.count() == 0:
            continue
        result = collection.query(
            query_embeddings=[query_embedding],
            n_results=min(per_collection, collection.count()),
            include=["documents", "metadatas", "distances"],
        )
        documents = result.get("documents", [[]])[0]
        metadatas = result.get("metadatas", [[]])[0]
        ids = result.get("ids", [[]])[0]
        distances = result.get("distances", [[]])[0]
        for chunk_id, document, metadata, distance in zip(ids, documents, metadatas, distances):
            chunks.append(_chunk_from_chroma(chunk_id, document, metadata, distance))

    chunks = sorted(chunks, key=lambda chunk: float(chunk.metadata.get("distance", "999")))[:top_k]
    if not chunks:
        warnings.append(f"No ChromaDB chunks found in {vector_store_dir / 'chroma'}")
    warnings.extend(_warnings(chunks))
    return RetrievalResult(query=query, chunks=chunks, warnings=warnings)


def _chunk_from_chroma(chunk_id: str, document: str, metadata: dict, distance: float) -> CodeChunk:
    metadata = {str(key): str(value) for key, value in (metadata or {}).items()}
    collection = metadata.pop("collection", "")
    chunk_type = metadata.pop("chunk_type", "")
    filepath = Path(metadata.pop("filepath", ""))
    symbol = metadata.pop("symbol", "")
    metadata["distance"] = str(round(distance, 6))
    return CodeChunk(
        id=chunk_id,
        collection=collection,
        chunk_type=chunk_type,
        filepath=filepath,
        symbol=symbol,
        text=document,
        metadata=metadata,
    )


def score_chunk(query: str, chunk: CodeChunk) -> float:
    query_terms = Counter(_tokens(query))
    if not query_terms:
        return 0.0
    text_terms = Counter(_tokens(" ".join([chunk.symbol, chunk.text, " ".join(chunk.metadata.values())])))
    if not text_terms:
        return 0.0
    overlap = sum(min(count, text_terms[token]) for token, count in query_terms.items())
    norm = math.sqrt(sum(count * count for count in query_terms.values())) * math.sqrt(
        sum(count * count for count in text_terms.values())
    )
    boost = 1.0
    if chunk.collection == "code_index":
        boost += 0.25
    if chunk.collection == "know_index":
        boost += 0.15
    return (overlap / norm) * boost if norm else 0.0


def _query_from_spec(spec: TestSpec) -> str:
    parts = [
        spec.title,
        spec.description,
        " ".join(spec.acceptance_criteria),
        " ".join(spec.affected_pages),
        " ".join(spec.user_types),
    ]
    for test_case in spec.test_cases:
        parts.extend([
            test_case.title,
            " ".join(test_case.preconditions),
            " ".join(test_case.steps),
            test_case.expected_result,
            " ".join(test_case.tags),
        ])
    return "\n".join(part for part in parts if part)


def _tokens(text: str) -> list[str]:
    return [token.lower() for token in TOKEN_RE.findall(text)]


def _warnings(chunks: list[CodeChunk]) -> list[str]:
    warnings: list[str] = []
    seen_symbols: dict[str, Path] = {}
    for chunk in chunks:
        if chunk.symbol and chunk.symbol in seen_symbols and seen_symbols[chunk.symbol] != chunk.filepath:
            warnings.append(f"Potential duplicate symbol {chunk.symbol} in {seen_symbols[chunk.symbol]} and {chunk.filepath}")
        seen_symbols[chunk.symbol] = chunk.filepath
    return warnings
