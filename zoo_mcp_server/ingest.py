import os

from zoo_mcp_server.catalog import ANIMALS, validate_animal_catalog
from zoo_mcp_server.storage import (
    AnimalCatalogRepository,
    PostgresAnimalCatalogRepository,
)


def ingest_animal_catalog(
    animals: list[dict[str, str | int]], repository: AnimalCatalogRepository
) -> dict[str, int | str]:
    """Validate the source catalog and upsert it as one controlled operation."""
    validate_animal_catalog(animals)
    repository.initialize()
    repository.upsert_animals(animals)
    return {"status": "ingested", "animal_count": len(animals)}


def main() -> None:
    database_url = os.getenv("CATALOG_DATABASE_URL")
    if not database_url:
        raise RuntimeError("CATALOG_DATABASE_URL is required for catalog ingestion.")
    result = ingest_animal_catalog(
        ANIMALS,
        PostgresAnimalCatalogRepository(database_url),
    )
    print(f"Animal catalog ingestion complete: {result['animal_count']} records.")


if __name__ == "__main__":
    main()