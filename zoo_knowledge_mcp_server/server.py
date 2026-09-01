import os
import re
from datetime import date
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP
from rank_bm25 import BM25Okapi


knowledge_mcp = FastMCP(
    "Zoo Curated Knowledge",
    host="0.0.0.0",
    port=int(os.getenv("PORT", "8080")),
)

DOCUMENTS_DIRECTORY = Path(__file__).parent / "documents"


def tokenize(value: str) -> list[str]:
    """Normalize text for lexical retrieval without sending it to third parties."""
    return re.findall(r"[a-z0-9]+", value.lower())


def load_documents() -> list[dict[str, str]]:
    """Load approved local Markdown documents and their required source metadata."""
    documents = []
    for path in sorted(DOCUMENTS_DIRECTORY.glob("*.md")):
        content = path.read_text(encoding="utf-8").strip()
        if not content.startswith("---\n"):
            raise ValueError(f"{path.name} must begin with YAML-style metadata.")
        metadata, separator, body = content.removeprefix("---\n").partition("\n---\n")
        if not separator:
            raise ValueError(f"{path.name} must close its YAML-style metadata.")
        fields = dict(
            line.split(":", 1) for line in metadata.splitlines()
        )
        required = {
            "id",
            "title",
            "source",
            "updated_at",
            "version",
            "approval_status",
            "zoo_id",
        }
        if not required <= fields.keys():
            raise ValueError(f"{path.name} is missing required source metadata.")
        date.fromisoformat(fields["updated_at"].strip())
        if fields["approval_status"].strip() != "approved":
            raise ValueError(f"{path.name} must be approved before it is loaded.")
        if not fields["zoo_id"].strip():
            raise ValueError(f"{path.name} must identify its Zoo scope.")
        documents.append(
            {
                "id": fields["id"].strip(),
                "title": fields["title"].strip(),
                "source": fields["source"].strip(),
                "updated_at": fields["updated_at"].strip(),
                "version": fields["version"].strip(),
                "approval_status": fields["approval_status"].strip(),
                "zoo_id": fields["zoo_id"].strip(),
                "content": body.strip(),
            }
        )
    if not documents:
        raise ValueError("At least one curated knowledge document is required.")
    return documents


DOCUMENTS = load_documents()
RETRIEVER = BM25Okapi([tokenize(document["content"]) for document in DOCUMENTS])


def hybrid_retriever() -> Any | None:
    """Create the production retriever only when Cloud SQL is configured."""
    try:
        from zoo_knowledge_mcp_server.embeddings import VertexEmbeddingProvider
        from zoo_knowledge_mcp_server.reranking import configured_reranker
        from zoo_knowledge_mcp_server.retrieval import HybridKnowledgeRetriever
        from zoo_knowledge_mcp_server.storage import PostgresKnowledgeRepository
    except ModuleNotFoundError:
        from embeddings import VertexEmbeddingProvider
        from reranking import configured_reranker
        from retrieval import HybridKnowledgeRetriever
        from storage import PostgresKnowledgeRepository

    database_url = os.getenv("KNOWLEDGE_DATABASE_URL")
    if not database_url:
        return None
    repository = PostgresKnowledgeRepository(database_url)
    return HybridKnowledgeRetriever(
        repository,
        VertexEmbeddingProvider(),
        configured_reranker(),
    )


@knowledge_mcp.tool()
def search_curated_knowledge(
    query: str, zoo_id: str = "global", max_results: int = 3
) -> dict[str, Any]:
    """Retrieve approved Zoo knowledge with source attribution for animal facts."""
    query_tokens = tokenize(query)
    if not query_tokens:
        return {"status": "error", "error_message": "A search query is required."}
    if not 1 <= max_results <= 5:
        return {
            "status": "error",
            "error_message": "max_results must be between 1 and 5.",
        }
    normalized_zoo_id = zoo_id.strip().lower()
    if not normalized_zoo_id:
        return {"status": "error", "error_message": "A Zoo ID is required."}
    retriever = hybrid_retriever()
    if retriever:
        results = retriever.search(query, normalized_zoo_id, max_results)
        return {"status": "success", "retrieval_mode": "hybrid", "results": results}
    scores = RETRIEVER.get_scores(query_tokens)
    ranked = sorted(enumerate(scores), key=lambda item: item[1], reverse=True)
    query_terms = set(query_tokens)
    results = [
        {
            "source_id": DOCUMENTS[index]["id"],
            "title": DOCUMENTS[index]["title"],
            "source": DOCUMENTS[index]["source"],
            "updated_at": DOCUMENTS[index]["updated_at"],
            "version": DOCUMENTS[index]["version"],
            "zoo_id": DOCUMENTS[index]["zoo_id"],
            "content": DOCUMENTS[index]["content"],
        }
        for index, score in ranked[:max_results]
        if (
            DOCUMENTS[index]["zoo_id"] in {"global", normalized_zoo_id}
            and query_terms.intersection(tokenize(DOCUMENTS[index]["content"]))
        )
    ]
    return {"status": "success", "retrieval_mode": "bm25", "results": results}


if __name__ == "__main__":
    knowledge_mcp.run(transport="streamable-http")