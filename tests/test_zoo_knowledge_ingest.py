from zoo_knowledge_mcp_server.ingest import ingest_documents


class FakeEmbeddingProvider:
    def embed(self, texts):
        return [[1.0] for _ in texts]


class FakeRepository:
    def __init__(self):
        self.initialized = False
        self.persisted = []

    def initialize(self):
        self.initialized = True

    def is_current(self, document_id, version, document_hash):
        return False

    def upsert_chunks(self, records, document_hash):
        self.persisted.append(records)


def test_ingest_documents_initializes_storage_once_and_ingests_all_documents():
    repository = FakeRepository()
    documents = [
        {
            "id": "elephant-care",
            "title": "Elephant Care",
            "source": "Animal Care",
            "updated_at": "2026-09-01",
            "version": "v1",
            "approval_status": "approved",
            "zoo_id": "global",
            "content": "Elephants need enrichment.",
        }
    ]

    results = ingest_documents(documents, repository, FakeEmbeddingProvider())

    assert repository.initialized is True
    assert results == [
        {"status": "ingested", "document_id": "elephant-care", "chunk_count": 1}
    ]
    assert len(repository.persisted) == 1