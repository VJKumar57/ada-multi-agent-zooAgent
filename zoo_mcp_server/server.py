import os
from typing import Any

from mcp.server.fastmcp import FastMCP

try:
    from zoo_mcp_server.catalog import ANIMALS, CANONICAL_ZOO_IDS
except ModuleNotFoundError:
    from catalog import ANIMALS, CANONICAL_ZOO_IDS


zoo_mcp = FastMCP(
    "Zoo Animal Directory",
    host="0.0.0.0",
    port=int(os.getenv("PORT", "8080")),
)


def normalize_zoo_id(zoo_id: str) -> str:
    return zoo_id.strip().lower()


def zoo_error_response(zoo_id: str) -> dict[str, str]:
    options = ", ".join(CANONICAL_ZOO_IDS)
    return {
        "status": "error",
        "error_message": f"Unknown zoo_id '{zoo_id}'. Choose one of: {options}.",
    }


def animals_for_zoo(zoo_id: str) -> list[dict[str, str | int]] | None:
    normalized_zoo_id = normalize_zoo_id(zoo_id)
    if normalized_zoo_id not in CANONICAL_ZOO_IDS:
        return None
    return [animal for animal in ANIMALS if animal["zoo_id"] == normalized_zoo_id]


def catalog_repository() -> Any | None:
    """Create the production catalog repository only when Cloud SQL is configured."""
    database_url = os.getenv("CATALOG_DATABASE_URL")
    if not database_url:
        return None
    try:
        from zoo_mcp_server.storage import PostgresAnimalCatalogRepository
    except ModuleNotFoundError:
        from storage import PostgresAnimalCatalogRepository

    return PostgresAnimalCatalogRepository(database_url)


@zoo_mcp.tool()
def find_animals(query: str, zoo_id: str) -> dict[str, Any]:
    """Find approved animals by name or species at one Zoo location."""
    zoo_animals = animals_for_zoo(zoo_id)
    if zoo_animals is None:
        return zoo_error_response(zoo_id)
    repository = catalog_repository()
    normalized_query = query.strip().lower()
    if not normalized_query:
        return {"status": "error", "error_message": "An animal query is required."}
    if repository:
        matches = repository.find_animals(normalized_query, normalize_zoo_id(zoo_id))
    else:
        search_terms = {normalized_query}
        if normalized_query.endswith("s"):
            search_terms.add(normalized_query[:-1])
        matches = [
            animal
            for animal in zoo_animals
            if any(
                term in str(animal["name"]).lower()
                or term in str(animal["species"]).lower()
                for term in search_terms
            )
        ]
    return {
        "status": "success",
        "zoo_id": normalize_zoo_id(zoo_id),
        "count": len(matches),
        "animals": matches,
    }


@zoo_mcp.tool()
def list_animals(zoo_id: str) -> dict[str, Any]:
    """List every approved demonstration animal at one Zoo location."""
    zoo_animals = animals_for_zoo(zoo_id)
    if zoo_animals is None:
        return zoo_error_response(zoo_id)
    repository = catalog_repository()
    if repository:
        zoo_animals = repository.list_animals(normalize_zoo_id(zoo_id))
    return {
        "status": "success",
        "zoo_id": normalize_zoo_id(zoo_id),
        "count": len(zoo_animals),
        "animals": zoo_animals,
    }


@zoo_mcp.tool()
def get_animal_count(zoo_id: str) -> dict[str, Any]:
    """Return the approved animal count for one Zoo location."""
    zoo_animals = animals_for_zoo(zoo_id)
    if zoo_animals is None:
        return zoo_error_response(zoo_id)
    repository = catalog_repository()
    count = (
        repository.get_animal_count(normalize_zoo_id(zoo_id))
        if repository
        else len(zoo_animals)
    )
    return {
        "status": "success",
        "zoo_id": normalize_zoo_id(zoo_id),
        "count": count,
    }


if __name__ == "__main__":
    zoo_mcp.run(transport="streamable-http")