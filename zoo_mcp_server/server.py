import os

from mcp.server.fastmcp import FastMCP


zoo_mcp = FastMCP(
    "Zoo Animal Directory",
    host="0.0.0.0",
    port=int(os.getenv("PORT", "8080")),
)

ANIMALS = [
    {
        "name": "Asha",
        "species": "Asian elephant",
        "age": 24,
        "location": "Elephant Habitat",
    },
    {
        "name": "Milo",
        "species": "African elephant",
        "age": 31,
        "location": "Safari Plains",
    },
    {
        "name": "Nala",
        "species": "African lion",
        "age": 8,
        "location": "Big Cat Ridge",
    },
    {
        "name": "Kiko",
        "species": "Red panda",
        "age": 5,
        "location": "Bamboo Forest",
    },
]


@zoo_mcp.tool()
def find_animals(query: str) -> list[dict[str, str | int]]:
    """Find zoo animals by name or species, including age and exhibit location."""
    normalized_query = query.lower()
    search_terms = {normalized_query}
    if normalized_query.endswith("s"):
        search_terms.add(normalized_query[:-1])

    return [
        animal
        for animal in ANIMALS
        if any(
            term in animal["name"].lower() or term in animal["species"].lower()
            for term in search_terms
        )
    ]


@zoo_mcp.tool()
def list_animals() -> list[dict[str, str | int]]:
    """List every animal at the zoo with its name, species, age, and location."""
    return ANIMALS


if __name__ == "__main__":
    zoo_mcp.run(transport="streamable-http")