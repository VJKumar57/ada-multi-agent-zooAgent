import pytest

from zoo_knowledge_mcp_server.rag import (
    build_chunk_records,
    chunk_document,
    reciprocal_rank_fusion,
)


class FakeEmbeddingProvider:
    def embed(self, texts):
        return [[float(index)] for index, _ in enumerate(texts, start=1)]


def test_chunk_document_preserves_order_and_overlap():
    content = "Alpha is first. Bravo is second. Charlie is third. Delta is fourth."

    chunks = chunk_document(content, chunk_size=35, overlap=12)

    assert chunks == [
        "Alpha is first. Bravo is second.",
        "is second. Charlie is third.",
        "is third. Delta is fourth.",
    ]


@pytest.mark.parametrize("chunk_size, overlap", [(0, 0), (10, -1), (10, 10)])
def test_chunk_document_rejects_invalid_boundaries(chunk_size, overlap):
    with pytest.raises(ValueError, match="chunk_size"):
        chunk_document("content", chunk_size=chunk_size, overlap=overlap)


def test_reciprocal_rank_fusion_rewards_candidates_from_both_searches():
    fused = reciprocal_rank_fusion(
        [
            ["semantic-only", "shared", "other"],
            ["keyword-only", "shared"],
        ]
    )

    assert fused[0] == "shared"
    assert set(fused) == {"semantic-only", "keyword-only", "shared", "other"}


def test_reciprocal_rank_fusion_rejects_invalid_rank_constant():
    with pytest.raises(ValueError, match="rank_constant"):
        reciprocal_rank_fusion([["chunk-1"]], rank_constant=0)


def test_build_chunk_records_retains_metadata_and_stable_ids():
    records = build_chunk_records(
        {
            "id": "elephant-guide",
            "title": "Elephant Guide",
            "source": "Animal Care",
            "updated_at": "2026-09-01",
            "version": "v1",
            "approval_status": "approved",
            "zoo_id": "chicago",
            "content": "Elephants need care. Their habitat needs enrichment.",
        },
        FakeEmbeddingProvider(),
    )

    assert records[0]["chunk_id"] == "elephant-guide:v1:1"
    assert records[0]["zoo_id"] == "chicago"
    assert records[0]["approval_status"] == "approved"
    assert records[0]["embedding"] == [1.0]
    assert len(records[0]["content_hash"]) == 64


def test_build_chunk_records_rejects_unapproved_documents():
    document = {
        "id": "draft",
        "title": "Draft",
        "source": "Animal Care",
        "updated_at": "2026-09-01",
        "version": "v1",
        "approval_status": "draft",
        "zoo_id": "",
        "content": "Draft content.",
    }

    with pytest.raises(ValueError, match="approved"):
        build_chunk_records(document, FakeEmbeddingProvider())