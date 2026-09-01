from collections import Counter


CANONICAL_ZOO_IDS = ("chicago", "san_diego", "bronx", "washington_dc")
SHARED_SPECIES = (
    "Asian elephant",
    "African elephant",
    "African lion",
    "Red panda",
    "Zebra",
)
EXCLUSIVE_SPECIES = {
    "chicago": (
        "North American bison",
        "Grey wolf",
        "Lynx",
        "Moose",
        "Pronghorn",
    ),
    "san_diego": (
        "California sea lion",
        "Desert bighorn sheep",
        "Roadrunner",
        "Jaguar",
        "Poison dart frog",
    ),
    "bronx": (
        "Eastern diamondback rattlesnake",
        "American black bear",
        "American alligator",
        "White-tailed deer",
        "Barn owl",
    ),
    "washington_dc": (
        "Giant panda",
        "Red wolf",
        "Snowy owl",
        "Komodo dragon",
        "Penguin",
    ),
}
EXHIBITS = {
    "chicago": (
        "Great Plains Savanna",
        "Primate House",
        "Big Cat Territory",
        "Arctic Adventure",
        "Asian Crossing",
    ),
    "san_diego": (
        "Gorilla Forest",
        "Reptile House",
        "Africa Rocks",
        "Panda Canyon",
        "Polar Passage",
    ),
    "bronx": (
        "Congo Gorilla Forest",
        "Wild Asia Monorail",
        "Himalayan Highlands",
        "Jungle World",
        "Madagascar",
    ),
    "washington_dc": (
        "Amazonia",
        "Reptile Discovery",
        "American Trail",
        "Asia Trail",
        "Africa Trail",
    ),
}
LEGACY_ANIMAL_NAMES = {
    ("chicago", "Asian elephant", 1): "Asha",
    ("chicago", "African elephant", 1): "Milo",
    ("chicago", "African lion", 1): "Nala",
    ("chicago", "Red panda", 1): "Kiko",
}


def build_animal_catalog() -> list[dict[str, str | int]]:
    """Build 100 approved demonstration animals for each canonical Zoo."""
    animals = []
    for zoo_id in CANONICAL_ZOO_IDS:
        species_for_zoo = SHARED_SPECIES + EXCLUSIVE_SPECIES[zoo_id]
        for species_index, species in enumerate(species_for_zoo):
            for animal_number in range(1, 11):
                name = LEGACY_ANIMAL_NAMES.get(
                    (zoo_id, species, animal_number),
                    f"{species} {animal_number:02d}",
                )
                animals.append(
                    {
                        "id": f"{zoo_id}-{species_index + 1:02d}-{animal_number:02d}",
                        "name": name,
                        "species": species,
                        "age": (species_index * 7 + animal_number) % 25 + 1,
                        "location": EXHIBITS[zoo_id][
                            species_index % len(EXHIBITS[zoo_id])
                        ],
                        "zoo_id": zoo_id,
                        "approval_status": "approved",
                    }
                )
    validate_animal_catalog(animals)
    return animals


def validate_animal_catalog(animals: list[dict[str, str | int]]) -> None:
    """Reject catalog data that violates location, count, or approval rules."""
    animal_ids = [str(animal["id"]) for animal in animals]
    if len(animal_ids) != len(set(animal_ids)):
        raise ValueError("Animal IDs must be unique.")
    for zoo_id in CANONICAL_ZOO_IDS:
        zoo_animals = [animal for animal in animals if animal["zoo_id"] == zoo_id]
        if len(zoo_animals) != 100:
            raise ValueError(f"{zoo_id} must have exactly 100 animals.")
        if any(animal["approval_status"] != "approved" for animal in zoo_animals):
            raise ValueError(f"{zoo_id} has an unapproved animal record.")
    species_locations: dict[str, set[str]] = {}
    for animal in animals:
        species_locations.setdefault(str(animal["species"]), set()).add(
            str(animal["zoo_id"])
        )
    for zoo_id, species in EXCLUSIVE_SPECIES.items():
        if any(
            species_locations[species_name] != {zoo_id} for species_name in species
        ):
            raise ValueError(f"{zoo_id} exclusive species must not appear elsewhere.")
    counts = Counter(str(animal["species"]) for animal in animals)
    if any(counts[species] != 40 for species in SHARED_SPECIES):
        raise ValueError("Shared species must have ten animals at each Zoo.")


ANIMALS = build_animal_catalog()