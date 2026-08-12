from __future__ import annotations

import math
import re
from collections import Counter
from pathlib import Path

from agent.models import CodeChunk, RetrievalResult, TestSpec
from agent.stage2_context_retrieval.indexer import (
    COLLECTIONS,
    EMBEDDING_MODEL,
    chroma_available,
    load_index,
)

TOKEN_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9_]+")


# Build a broad query from the full TestSpec and retrieve the most relevant chunks.
# This is the normal Stage 2 retrieval path used before Stage 3 generation.
def retrieve_context(spec: TestSpec, vector_store_dir: Path, top_k: int = 12) -> RetrievalResult:
    query = _query_from_spec(spec)
    return _retrieve_from_index(query, vector_store_dir, top_k, COLLECTIONS)


# Search the Stage 2 index with an explicit query.
# Tools and evals can restrict this to code, test, or knowledge collections.
def search_index(
    query: str,
    vector_store_dir: Path,
    top_k: int = 10,
    collections: tuple[str, ...] | None = None,
) -> RetrievalResult:
    return _retrieve_from_index(query, vector_store_dir, top_k, collections or COLLECTIONS)


# Try semantic Chroma retrieval first.
# If it is unavailable or empty, use the saved JSON index with lexical scoring.
def _retrieve_from_index(
    query: str,
    vector_store_dir: Path,
    top_k: int,
    collections: tuple[str, ...],
) -> RetrievalResult:
    if chroma_available():
        result = _retrieve_chroma(query, vector_store_dir, top_k, collections)
        if result.chunks:
            return result

    all_chunks = load_index(vector_store_dir)
    chunks = [chunk for chunk in all_chunks if chunk.collection in collections]
    if not chunks:
        if all_chunks:
            collection_names = ", ".join(collections)
            return RetrievalResult(
                query=query,
                warnings=[f"No Stage 2 chunks found in selected collections: {collection_names}"],
            )
        return RetrievalResult(
            query=query, warnings=[f"No Stage 2 index found in {vector_store_dir}"]
        )

    scored = sorted(
        ((score_chunk(query, chunk), chunk) for chunk in chunks),
        key=lambda item: item[0],
        reverse=True,
    )
    selected = [chunk for score, chunk in scored if score > 0][:top_k]
    return RetrievalResult(query=query, chunks=selected, warnings=_warnings(selected))


# Embed the query locally and search the selected Chroma collections.
# Returned Chroma metadata is converted back into CodeChunk objects.
def _retrieve_chroma(
    query: str,
    vector_store_dir: Path,
    top_k: int,
    collections: tuple[str, ...],
) -> RetrievalResult:
    try:
        import chromadb
        from sentence_transformers import SentenceTransformer

        client = chromadb.PersistentClient(path=str(vector_store_dir / "chroma"))
        embedder = SentenceTransformer(EMBEDDING_MODEL, local_files_only=True)
        query_embedding = embedder.encode([query], normalize_embeddings=True).tolist()[0]
    except Exception as exc:
        return RetrievalResult(
            query=query,
            warnings=[
                f"ChromaDB embedding retrieval unavailable; using JSON lexical fallback. Reason: {exc}"
            ],
        )

    chunks: list[CodeChunk] = []
    warnings: list[str] = []
    per_collection = max(1, top_k // len(collections) + 1)
    for collection_name in collections:
        collection = client.get_or_create_collection(collection_name)
        if collection.count() == 0:
            continue
        result = collection.query(
            query_embeddings=[query_embedding],
            n_results=min(per_collection, collection.count()),
            include=["documents", "metadatas", "distances"],
        )
        for chunk_id, document, metadata, distance in zip(
            result.get("ids", [[]])[0],
            result.get("documents", [[]])[0],
            result.get("metadatas", [[]])[0],
            result.get("distances", [[]])[0],
            strict=False,
        ):
            chunk_metadata = {str(key): str(value) for key, value in (metadata or {}).items()}
            collection_name = chunk_metadata.pop("collection", "")
            chunk_type = chunk_metadata.pop("chunk_type", "")
            filepath = Path(chunk_metadata.pop("filepath", ""))
            symbol = chunk_metadata.pop("symbol", "")
            chunk_metadata["distance"] = str(round(distance, 6))
            chunks.append(
                CodeChunk(
                    id=chunk_id,
                    collection=collection_name,
                    chunk_type=chunk_type,
                    filepath=filepath,
                    symbol=symbol,
                    text=document,
                    metadata=chunk_metadata,
                )
            )

    chunks = sorted(chunks, key=lambda chunk: float(chunk.metadata.get("distance", "999")))[:top_k]
    if not chunks:
        warnings.append(f"No ChromaDB chunks found in {vector_store_dir / 'chroma'}")
    warnings.extend(_warnings(chunks))
    return RetrievalResult(query=query, chunks=chunks, warnings=warnings)


# Calculate a simple token-overlap score for fallback retrieval.
# Code and knowledge chunks get small boosts because they are usually most useful.
def score_chunk(query: str, chunk: CodeChunk) -> float:
    query_terms = Counter(token.lower() for token in TOKEN_RE.findall(query))
    if not query_terms:
        return 0.0
    chunk_text = " ".join([chunk.symbol, chunk.text, " ".join(chunk.metadata.values())])
    text_terms = Counter(token.lower() for token in TOKEN_RE.findall(chunk_text))
    if not text_terms:
        return 0.0
    overlap = sum(min(count, text_terms[token]) for token, count in query_terms.items())
    norm = math.sqrt(sum(count * count for count in query_terms.values())) * math.sqrt(
        sum(count * count for count in text_terms.values())
    )
    boost = 1.0
    boost += 0.25 if chunk.collection == "code_index" else 0.0
    boost += 0.15 if chunk.collection == "know_index" else 0.0
    return (overlap / norm) * boost if norm else 0.0


# Flatten the TestSpec into one text query for retrieval.
# It includes story-level context and every extracted test-case detail.
def _query_from_spec(spec: TestSpec) -> str:
    parts = [
        spec.title,
        spec.description,
        " ".join(spec.acceptance_criteria),
        " ".join(spec.affected_pages),
        " ".join(spec.user_types),
    ]
    parts.extend(
        part
        for test_case in spec.test_cases
        for part in (
            test_case.title,
            " ".join(test_case.preconditions),
            " ".join(test_case.steps),
            test_case.expected_result,
            " ".join(test_case.tags),
        )
    )
    return "\n".join(filter(None, parts))


# Surface possible ambiguity when two retrieved files define the same symbol.
# This helps explain confusing retrieval context without failing the pipeline.
def _warnings(chunks: list[CodeChunk]) -> list[str]:
    warnings: list[str] = []
    seen_symbols: dict[str, Path] = {}
    for chunk in chunks:
        existing_path = seen_symbols.get(chunk.symbol)
        if chunk.symbol and existing_path and existing_path != chunk.filepath:
            warnings.append(
                f"Potential duplicate symbol {chunk.symbol} in {existing_path} and {chunk.filepath}"
            )
        seen_symbols[chunk.symbol] = chunk.filepath
    return warnings
