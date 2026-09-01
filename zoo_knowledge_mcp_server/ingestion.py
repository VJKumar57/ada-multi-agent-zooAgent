from hashlib import sha256

from zoo_knowledge_mcp_server.rag import EmbeddingProvider, build_chunk_records
from zoo_knowledge_mcp_server.storage import KnowledgeRepository


def ingest_document(
    document: dict[str, str],
    embedding_provider: EmbeddingProvider,
    repository: KnowledgeRepository,
) -> dict[str, object]:
    """Ingest a changed approved document as embedding-backed chunks."""
    document_hash = sha256(document["content"].encode()).hexdigest()
    if repository.is_current(document["id"], document["version"], document_hash):
        return {"status": "unchanged", "document_id": document["id"]}
    records = build_chunk_records(document, embedding_provider)
    repository.upsert_chunks(records, document_hash)
    return {
        "status": "ingested",
        "document_id": document["id"],
        "chunk_count": len(records),
    }