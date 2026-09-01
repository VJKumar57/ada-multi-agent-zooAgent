from zoo_mcp_server.catalog import ANIMALS
from zoo_mcp_server.ingest import ingest_animal_catalog


class FakeRepository:
    def __init__(self):
        self.initialized = False
        self.animals = []

    def initialize(self):
        self.initialized = True

    def upsert_animals(self, animals):
        self.animals = animals


def test_catalog_ingestion_validates_and_upserts_all_approved_animals():
    repository = FakeRepository()

    result = ingest_animal_catalog(ANIMALS, repository)

    assert result == {"status": "ingested", "animal_count": 400}
    assert repository.initialized is True
    assert repository.animals == ANIMALS