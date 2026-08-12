from __future__ import annotations

import json
from pathlib import Path

from agent.models import CodeChunk
from agent.stage2_context_retrieval.chunker import chunk_playwright_repo

INDEX_FILE = "stage2_index.json"
COLLECTIONS = ("code_index", "test_index", "know_index")
EMBEDDING_MODEL = "all-MiniLM-L6-v2"


# Rebuild Stage 2 retrieval data from the current Playwright repo and knowledge files.
# It always writes stage2_index.json, then also writes Chroma collections if available.
def build_index(
    playwright_root: Path, knowledge_dir: Path, vector_store_dir: Path
) -> list[CodeChunk]:
    chunks = chunk_playwright_repo(playwright_root, knowledge_dir)
    vector_store_dir.mkdir(parents=True, exist_ok=True)
    (vector_store_dir / INDEX_FILE).write_text(
        json.dumps([chunk.model_dump(mode="json") for chunk in chunks], indent=2),
        encoding="utf-8",
    )
    _write_chroma_index(chunks, vector_store_dir)
    return chunks


# Read stage2_index.json back into CodeChunk models.
# Retrieval uses this as a lexical fallback when Chroma or embeddings cannot run.
def load_index(vector_store_dir: Path) -> list[CodeChunk]:
    path = vector_store_dir / INDEX_FILE
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [CodeChunk.model_validate(item) for item in payload]


# Check whether the optional vector-search dependencies can be imported.
# Failures are treated as "use JSON fallback" rather than hard errors.
def chroma_available() -> bool:
    try:
        import chromadb  # noqa: F401
        from sentence_transformers import SentenceTransformer  # noqa: F401
    except Exception:
        return False
    return True


# Count documents in each Chroma collection.
# The CLI prints this after --build-index so we can see what was indexed.
def collection_counts(vector_store_dir: Path) -> dict[str, int]:
    if not chroma_available():
        return {}
    import chromadb

    client = chromadb.PersistentClient(path=str(vector_store_dir / "chroma"))
    return {
        collection_name: client.get_or_create_collection(collection_name).count()
        for collection_name in COLLECTIONS
    }


# Rewrite Chroma from scratch using the latest chunks.
# Each collection receives only chunks assigned to that collection.
def _write_chroma_index(chunks: list[CodeChunk], vector_store_dir: Path) -> None:
    if not chroma_available():
        return

    try:
        import chromadb
        from sentence_transformers import SentenceTransformer

        client = chromadb.PersistentClient(path=str(vector_store_dir / "chroma"))
        embedder = SentenceTransformer(EMBEDDING_MODEL, local_files_only=True)
    except Exception:
        return

    for collection_name in COLLECTIONS:
        collection = _reset_collection(client, collection_name)
        collection_chunks = [chunk for chunk in chunks if chunk.collection == collection_name]
        if not collection_chunks:
            continue

        documents = [_document_text(chunk) for chunk in collection_chunks]
        embeddings = embedder.encode(documents, normalize_embeddings=True).tolist()
        collection.add(
            ids=[chunk.id for chunk in collection_chunks],
            documents=documents,
            embeddings=embeddings,
            metadatas=[_metadata(chunk) for chunk in collection_chunks],
        )


# Build the text that gets embedded for semantic search.
# Including symbol/type/path gives retrieval more context than raw code alone.
def _document_text(chunk: CodeChunk) -> str:
    return "\n".join(
        [
            f"symbol: {chunk.symbol}",
            f"type: {chunk.chunk_type}",
            f"path: {chunk.filepath}",
            chunk.text,
        ]
    )


# Convert CodeChunk metadata to Chroma's simple scalar metadata format.
# Custom metadata keys are prefixed so they do not collide with core fields.
def _metadata(chunk: CodeChunk) -> dict[str, str]:
    return {
        "collection": chunk.collection,
        "chunk_type": chunk.chunk_type,
        "filepath": str(chunk.filepath),
        "symbol": chunk.symbol,
        **{f"meta_{key}": value for key, value in chunk.metadata.items()},
    }


# Clear one Chroma collection before adding fresh documents.
# This prevents stale chunks from older repo states staying searchable.
def _reset_collection(client, collection_name: str):
    existing = client.get_or_create_collection(collection_name)
    client.delete_collection(existing.name)
    return client.get_or_create_collection(collection_name)
