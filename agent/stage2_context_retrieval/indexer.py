from __future__ import annotations

import json
from pathlib import Path

from agent.models import CodeChunk
from agent.stage2_context_retrieval.chunker import chunk_playwright_repo

INDEX_FILE = "stage2_index.json"
COLLECTIONS = ("code_index", "test_index", "know_index")
EMBEDDING_MODEL = "all-MiniLM-L6-v2"


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


def load_index(vector_store_dir: Path) -> list[CodeChunk]:
    path = vector_store_dir / INDEX_FILE
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [CodeChunk.model_validate(item) for item in payload]


def chroma_available() -> bool:
    try:
        import chromadb  # noqa: F401
        from sentence_transformers import SentenceTransformer  # noqa: F401
    except Exception:
        return False
    return True


def collection_counts(vector_store_dir: Path) -> dict[str, int]:
    if not chroma_available():
        return {}
    client = _chroma_client(vector_store_dir)
    counts: dict[str, int] = {}
    for collection_name in COLLECTIONS:
        collection = client.get_or_create_collection(collection_name)
        counts[collection_name] = collection.count()
    return counts


def _write_chroma_index(chunks: list[CodeChunk], vector_store_dir: Path) -> None:
    if not chroma_available():
        return

    try:
        client = _chroma_client(vector_store_dir)
        from sentence_transformers import SentenceTransformer

        embedder = SentenceTransformer(EMBEDDING_MODEL, local_files_only=True)
    except Exception:
        return

    for collection_name in COLLECTIONS:
        existing = client.get_or_create_collection(collection_name)
        client.delete_collection(existing.name)
        collection = client.get_or_create_collection(collection_name)
        collection_chunks = [chunk for chunk in chunks if chunk.collection == collection_name]
        if not collection_chunks:
            continue

        documents = [
            "\n".join(
                [
                    f"symbol: {chunk.symbol}",
                    f"type: {chunk.chunk_type}",
                    f"path: {chunk.filepath}",
                    chunk.text,
                ]
            )
            for chunk in collection_chunks
        ]
        metadatas = []
        for chunk in collection_chunks:
            metadata = {
                "collection": chunk.collection,
                "chunk_type": chunk.chunk_type,
                "filepath": str(chunk.filepath),
                "symbol": chunk.symbol,
            }
            metadata.update({f"meta_{key}": value for key, value in chunk.metadata.items()})
            metadatas.append(metadata)

        embeddings = embedder.encode(documents, normalize_embeddings=True).tolist()
        collection.add(
            ids=[chunk.id for chunk in collection_chunks],
            documents=documents,
            embeddings=embeddings,
            metadatas=metadatas,
        )


def _chroma_client(vector_store_dir: Path):
    import chromadb

    return chromadb.PersistentClient(path=str(vector_store_dir / "chroma"))
