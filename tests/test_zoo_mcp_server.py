from zoo_mcp_server.server import find_animals, list_animals


def test_find_animals_matches_species_case_insensitively():
    animals = find_animals("ELEPHANTS")

    assert [animal["name"] for animal in animals] == ["Asha", "Milo"]


def test_find_animals_returns_no_results_for_an_unknown_animal():
    assert find_animals("giraffe") == []


def test_list_animals_returns_the_complete_directory():
    assert [animal["name"] for animal in list_animals()] == [
        "Asha",
        "Milo",
        "Nala",
        "Kiko",
    ]
