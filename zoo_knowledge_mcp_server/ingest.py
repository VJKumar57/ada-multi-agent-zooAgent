import os

from zoo_knowledge_mcp_server.embeddings import VertexEmbeddingProvider
from zoo_knowledge_mcp_server.ingestion import ingest_document
from zoo_knowledge_mcp_server.server import load_documents
from zoo_knowledge_mcp_server.storage import (
    KnowledgeRepository,
    PostgresKnowledgeRepository,
)


def ingest_documents(
    documents: list[dict[str, str]],
    repository: KnowledgeRepository,
    embedding_provider: VertexEmbeddingProvider,
) -> list[dict[str, object]]:
    """Initialize storage once and ingest every validated approved document."""
    repository.initialize()
    return [
        ingest_document(document, embedding_provider, repository)
        for document in documents
    ]


def main() -> None:
    database_url = os.getenv("KNOWLEDGE_DATABASE_URL")
    if not database_url:
        raise RuntimeError(
            "KNOWLEDGE_DATABASE_URL is required for knowledge ingestion."
        )
    results = ingest_documents(
        load_documents(),
        PostgresKnowledgeRepository(database_url),
        VertexEmbeddingProvider(),
    )
    ingested_count = sum(result["status"] == "ingested" for result in results)
    unchanged_count = sum(result["status"] == "unchanged" for result in results)
    print(
        f"Knowledge ingestion complete: {ingested_count} ingested, "
        f"{unchanged_count} unchanged."
    )


if __name__ == "__main__":
    main()