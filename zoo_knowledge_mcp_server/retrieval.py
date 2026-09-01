import json
from typing import Protocol

try:
    from zoo_knowledge_mcp_server.rag import reciprocal_rank_fusion
    from zoo_knowledge_mcp_server.reranking import Reranker
    from zoo_knowledge_mcp_server.storage import KnowledgeRepository
except ModuleNotFoundError:
    from rag import reciprocal_rank_fusion
    from reranking import Reranker
    from storage import KnowledgeRepository


class QueryEmbeddingProvider(Protocol):
    def embed_query(self, query: str) -> list[float]: ...


class HybridKnowledgeRetriever:
    """Retrieve approved, Zoo-scoped chunks with vector and lexical search."""

    def __init__(
        self,
        repository: KnowledgeRepository,
        embedding_provider: QueryEmbeddingProvider,
        reranker: Reranker | None = None,
    ) -> None:
        self.repository = repository
        self.embedding_provider = embedding_provider
        self.reranker = reranker

    def search(
        self, query: str, zoo_id: str, max_results: int = 3
    ) -> list[dict[str, object]]:
        query_embedding = self.embedding_provider.embed_query(query)
        candidate_limit = max_results * 3
        semantic = self.repository.search_semantic(
            query_embedding, zoo_id, candidate_limit
        )
        keyword = self.repository.search_keyword(query, zoo_id, candidate_limit)
        candidates = {
            candidate["chunk_id"]: candidate for candidate in semantic + keyword
        }
        fused_ids = reciprocal_rank_fusion(
            [[candidate["chunk_id"] for candidate in semantic],
            [candidate["chunk_id"] for candidate in keyword]]
        )
        results = [candidates[chunk_id] for chunk_id in fused_ids]
        if self.reranker:
            try:
                results = self.reranker.rerank(query, results)
            except (RuntimeError, ValueError, json.JSONDecodeError):
                pass
        return results[:max_results]