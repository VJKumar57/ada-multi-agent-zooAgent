import pytest

from zoo_knowledge_mcp_server.reranking import GeminiReranker, LexicalReranker


def candidates():
    return [
        {"chunk_id": "one", "content": "Ticket prices and opening times."},
        {"chunk_id": "two", "content": "Elephant habitat and enrichment."},
    ]


def test_lexical_reranker_promotes_matching_content():
    results = LexicalReranker().rerank("elephant habitat", candidates())

    assert [result["chunk_id"] for result in results] == ["two", "one"]


class FakeModels:
    def generate_content(self, **kwargs):
        return type("Response", (), {"text": '["two", "one"]'})()


class FakeClient:
    models = FakeModels()


def test_gemini_reranker_accepts_only_the_supplied_candidate_ids():
    results = GeminiReranker(client=FakeClient()).rerank("elephant", candidates())

    assert [result["chunk_id"] for result in results] == ["two", "one"]


def test_gemini_reranker_rejects_unknown_candidate_ids():
    class InvalidModels:
        def generate_content(self, **kwargs):
            return type("Response", (), {"text": '["unknown"]'})()

    client = type("Client", (), {"models": InvalidModels()})()
    with pytest.raises(ValueError, match="invalid candidate IDs"):
        GeminiReranker(client=client).rerank("elephant", candidates())