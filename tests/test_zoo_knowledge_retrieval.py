from zoo_knowledge_mcp_server.retrieval import HybridKnowledgeRetriever


class FakeEmbeddingProvider:
    def __init__(self):
        self.queries = []

    def embed_query(self, query):
        self.queries.append(query)
        return [0.1, 0.2]


class FakeRepository:
    def __init__(self):
        self.calls = []

    def search_semantic(self, query_embedding, zoo_id, limit):
        self.calls.append(("semantic", query_embedding, zoo_id, limit))
        return [
            {"chunk_id": "semantic-only", "content": "semantic"},
            {"chunk_id": "shared", "content": "shared"},
        ]

    def search_keyword(self, query, zoo_id, limit):
        self.calls.append(("keyword", query, zoo_id, limit))
        return [
            {"chunk_id": "keyword-only", "content": "keyword"},
            {"chunk_id": "shared", "content": "shared"},
        ]


def test_hybrid_retriever_fuses_semantic_and_keyword_candidates():
    provider = FakeEmbeddingProvider()
    repository = FakeRepository()

    results = HybridKnowledgeRetriever(repository, provider).search(
        "elephant habitat", "chicago", max_results=2
    )

    assert [result["chunk_id"] for result in results] == ["shared", "keyword-only"]
    assert repository.calls == [
        ("semantic", [0.1, 0.2], "chicago", 6),
        ("keyword", "elephant habitat", "chicago", 6),
    ]