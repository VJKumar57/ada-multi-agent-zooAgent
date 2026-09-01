from zoo_knowledge_mcp_server.ingestion import ingest_document


class FakeEmbeddingProvider:
    def __init__(self):
        self.calls = 0

    def embed(self, texts):
        self.calls += 1
        return [[1.0] for _ in texts]


class FakeRepository:
    def __init__(self, is_current):
        self.current = is_current
        self.records = None

    def initialize(self):
        pass

    def is_current(self, document_id, version, document_hash):
        return self.current

    def upsert_chunks(self, records, document_hash):
        self.records = records


def approved_document():
    return {
        "id": "elephant-care",
        "title": "Elephant Care",
        "source": "Animal Care",
        "updated_at": "2026-09-01",
        "version": "v1",
        "approval_status": "approved",
        "zoo_id": "global",
        "content": "Elephants need enrichment.",
    }


def test_ingest_document_embeds_and_persists_changed_approved_content():
    provider = FakeEmbeddingProvider()
    repository = FakeRepository(is_current=False)

    result = ingest_document(approved_document(), provider, repository)

    assert result == {
        "status": "ingested",
        "document_id": "elephant-care",
        "chunk_count": 1,
    }
    assert provider.calls == 1
    assert repository.records[0]["document_id"] == "elephant-care"


def test_ingest_document_skips_embedding_for_an_unchanged_version():
    provider = FakeEmbeddingProvider()
    repository = FakeRepository(is_current=True)

    result = ingest_document(approved_document(), provider, repository)

    assert result == {"status": "unchanged", "document_id": "elephant-care"}
    assert provider.calls == 0
    assert repository.records is None