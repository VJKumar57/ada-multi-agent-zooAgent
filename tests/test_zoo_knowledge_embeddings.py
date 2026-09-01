import pytest

from zoo_knowledge_mcp_server.embeddings import VertexEmbeddingProvider


class FakeEmbedding:
    def __init__(self, values):
        self.values = values


class FakeResponse:
    def __init__(self, embeddings):
        self.embeddings = embeddings


class FakeModels:
    def __init__(self, response):
        self.response = response
        self.call = None

    def embed_content(self, **kwargs):
        self.call = kwargs
        return self.response


class FakeClient:
    def __init__(self, response):
        self.models = FakeModels(response)


def test_vertex_embedding_provider_requests_retrieval_document_embeddings():
    client = FakeClient(FakeResponse([FakeEmbedding([0.1, 0.2])]))
    provider = VertexEmbeddingProvider(client=client, model="test-model", dimensions=2)

    result = provider.embed(["elephant habitat"])

    assert result == [[0.1, 0.2]]
    assert client.models.call == {
        "model": "test-model",
        "contents": ["elephant habitat"],
        "config": {"task_type": "RETRIEVAL_DOCUMENT", "output_dimensionality": 2},
    }


def test_vertex_embedding_provider_rejects_wrong_response_dimensions():
    client = FakeClient(FakeResponse([FakeEmbedding([0.1])]))
    provider = VertexEmbeddingProvider(client=client, dimensions=2)

    with pytest.raises(ValueError, match="unexpected dimensions"):
        provider.embed(["elephant habitat"])


def test_vertex_embedding_provider_uses_query_task_for_searches():
    client = FakeClient(FakeResponse([FakeEmbedding([0.1, 0.2])]))
    provider = VertexEmbeddingProvider(client=client, dimensions=2)

    assert provider.embed_query("elephant habitat") == [0.1, 0.2]
    assert client.models.call["config"]["task_type"] == "RETRIEVAL_QUERY"


def test_vertex_embedding_provider_skips_empty_requests():
    provider = VertexEmbeddingProvider(dimensions=2)

    assert provider.embed([]) == []