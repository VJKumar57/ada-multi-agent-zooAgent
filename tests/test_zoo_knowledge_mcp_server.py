from zoo_knowledge_mcp_server import server


def test_search_curated_knowledge_returns_approved_source_attribution():
    result = server.search_curated_knowledge("Asian elephant habitat")

    assert result == {
        "status": "success",
        "retrieval_mode": "bm25",
        "results": [
        {
            "source_id": "elephant-care-v1",
            "title": "Elephant Care And Habitat Guide",
            "source": "Zoo Animal Care Team approved reference",
            "updated_at": "2026-08-31",
            "version": "v1",
            "zoo_id": "global",
            "content": server.DOCUMENTS[0]["content"],
        }
        ],
    }


def test_search_curated_knowledge_rejects_invalid_requests():
    assert server.search_curated_knowledge(" ") == {
        "status": "error",
        "error_message": "A search query is required.",
    }
    assert server.search_curated_knowledge("elephant", max_results=6) == {
        "status": "error",
        "error_message": "max_results must be between 1 and 5.",
    }
    assert server.search_curated_knowledge("elephant", zoo_id=" ") == {
        "status": "error",
        "error_message": "A Zoo ID is required.",
    }


def test_search_curated_knowledge_returns_no_match_for_unapproved_content():
    result = server.search_curated_knowledge("giraffe")

    assert result == {"status": "success", "retrieval_mode": "bm25", "results": []}


def test_search_curated_knowledge_uses_hybrid_retrieval_when_configured(
    monkeypatch,
):
    class FakeRetriever:
        def search(self, query, zoo_id, max_results):
            assert (query, zoo_id, max_results) == ("elephant", "chicago", 3)
            return [{"chunk_id": "elephant-care:v1:1", "content": "Care guidance."}]

    monkeypatch.setattr(server, "hybrid_retriever", lambda: FakeRetriever())

    assert server.search_curated_knowledge("elephant", "chicago") == {
        "status": "success",
        "retrieval_mode": "hybrid",
        "results": [{"chunk_id": "elephant-care:v1:1", "content": "Care guidance."}],
    }