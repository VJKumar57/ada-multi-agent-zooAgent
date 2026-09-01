import pytest

from zoo_mcp_server.catalog import CANONICAL_ZOO_IDS, EXCLUSIVE_SPECIES
from zoo_mcp_server.server import find_animals, get_animal_count, list_animals


@pytest.mark.parametrize("zoo_id", CANONICAL_ZOO_IDS)
def test_each_zoo_has_exactly_one_hundred_animals(zoo_id):
    result = get_animal_count(zoo_id)

    assert result == {"status": "success", "zoo_id": zoo_id, "count": 100}


def test_chicago_elephant_search_is_scoped_and_preserves_demo_animals():
    result = find_animals("elephants", "CHICAGO")

    assert result["status"] == "success"
    assert result["zoo_id"] == "chicago"
    assert result["count"] == 20
    assert {animal["name"] for animal in result["animals"]} >= {"Asha", "Milo"}
    assert {animal["zoo_id"] for animal in result["animals"]} == {"chicago"}


def test_exclusive_species_search_has_results_only_at_its_home_zoo():
    species = EXCLUSIVE_SPECIES["chicago"][0]

    assert find_animals(species, "chicago")["count"] == 10
    assert find_animals(species, "san_diego")["count"] == 0


@pytest.mark.parametrize(
    "tool_call",
    [
        lambda: find_animals("elephant", "unknown"),
        lambda: list_animals("unknown"),
        lambda: get_animal_count("unknown"),
    ],
)
def test_invalid_zoo_returns_a_structured_error(tool_call):
    result = tool_call()

    assert result["status"] == "error"
    assert "Unknown zoo_id" in result["error_message"]


def test_list_animals_returns_only_the_requested_location():
    result = list_animals("bronx")

    assert result["count"] == 100
    assert {animal["zoo_id"] for animal in result["animals"]} == {"bronx"}


def test_database_repository_is_used_when_server_configuration_enables_it(monkeypatch):
    class FakeRepository:
        def get_animal_count(self, zoo_id):
            assert zoo_id == "chicago"
            return 99

    monkeypatch.setattr("zoo_mcp_server.server.catalog_repository", FakeRepository)

    assert get_animal_count("chicago") == {
        "status": "success",
        "zoo_id": "chicago",
        "count": 99,
    }
