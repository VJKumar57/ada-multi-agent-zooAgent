import pytest

from zoo_mcp_server.catalog import (
    ANIMALS,
    CANONICAL_ZOO_IDS,
    EXCLUSIVE_SPECIES,
    build_animal_catalog,
    validate_animal_catalog,
)


def test_catalog_contains_one_hundred_approved_animals_per_zoo():
    for zoo_id in CANONICAL_ZOO_IDS:
        zoo_animals = [animal for animal in ANIMALS if animal["zoo_id"] == zoo_id]

        assert len(zoo_animals) == 100
        assert {animal["approval_status"] for animal in zoo_animals} == {"approved"}


def test_exclusive_species_appear_at_only_their_configured_zoo():
    for zoo_id, species in EXCLUSIVE_SPECIES.items():
        exclusive_animals = [
            animal for animal in ANIMALS if animal["species"] in species
        ]

        assert {animal["zoo_id"] for animal in exclusive_animals} == {zoo_id}
        assert {animal["species"] for animal in exclusive_animals} == set(species)


def test_catalog_preserves_original_chicago_demo_animals():
    chicago_animals = [animal for animal in ANIMALS if animal["zoo_id"] == "chicago"]

    assert {animal["name"] for animal in chicago_animals} >= {
        "Asha",
        "Milo",
        "Nala",
        "Kiko",
    }


def test_catalog_validation_rejects_wrong_location_count():
    animals = build_animal_catalog()[1:]

    with pytest.raises(ValueError, match="exactly 100"):
        validate_animal_catalog(animals)