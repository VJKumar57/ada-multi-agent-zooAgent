from collections.abc import Sequence
from typing import Protocol


class AnimalCatalogRepository(Protocol):
    def initialize(self) -> None: ...

    def upsert_animals(self, animals: Sequence[dict[str, str | int]]) -> None: ...

    def list_animals(self, zoo_id: str) -> list[dict[str, str | int]]: ...

    def find_animals(self, query: str, zoo_id: str) -> list[dict[str, str | int]]: ...

    def get_animal_count(self, zoo_id: str) -> int: ...


class PostgresAnimalCatalogRepository:
    """Store approved Zoo animal records in PostgreSQL."""

    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    def _connect(self):
        try:
            import psycopg
        except ImportError as error:
            raise RuntimeError(
                "Install psycopg to use PostgreSQL animal catalog storage."
            ) from error
        return psycopg.connect(self.database_url)

    def initialize(self) -> None:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS animals (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    species TEXT NOT NULL,
                    age INTEGER NOT NULL CHECK (age > 0),
                    location TEXT NOT NULL,
                    zoo_id TEXT NOT NULL,
                    approval_status TEXT NOT NULL CHECK (approval_status = 'approved')
                )
                """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS animals_zoo_species_idx
                ON animals (zoo_id, species)
                """
            )

    def upsert_animals(self, animals: Sequence[dict[str, str | int]]) -> None:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.executemany(
                """
                INSERT INTO animals (
                    id, name, species, age, location, zoo_id, approval_status
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    name = EXCLUDED.name,
                    species = EXCLUDED.species,
                    age = EXCLUDED.age,
                    location = EXCLUDED.location,
                    zoo_id = EXCLUDED.zoo_id,
                    approval_status = EXCLUDED.approval_status
                """,
                [
                    (
                        animal["id"],
                        animal["name"],
                        animal["species"],
                        animal["age"],
                        animal["location"],
                        animal["zoo_id"],
                        animal["approval_status"],
                    )
                    for animal in animals
                ],
            )

    def list_animals(self, zoo_id: str) -> list[dict[str, str | int]]:
        return self._select(
            "WHERE zoo_id = %s AND approval_status = 'approved' ORDER BY id",
            (zoo_id,),
        )

    def find_animals(self, query: str, zoo_id: str) -> list[dict[str, str | int]]:
        singular_query = query[:-1] if query.endswith("s") else query
        return self._select(
            """
            WHERE zoo_id = %s AND approval_status = 'approved'
              AND (
                name ILIKE %s OR species ILIKE %s
                OR name ILIKE %s OR species ILIKE %s
              )
            ORDER BY id
            """,
            (
            zoo_id,
            f"%{query}%",
            f"%{query}%",
            f"%{singular_query}%",
            f"%{singular_query}%",
            ),
        )

    def get_animal_count(self, zoo_id: str) -> int:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT COUNT(*) FROM animals
                WHERE zoo_id = %s AND approval_status = 'approved'
                """,
                (zoo_id,),
            )
            return int(cursor.fetchone()[0])

    def _select(
        self, where_clause: str, parameters: tuple[str, ...]
    ) -> list[dict[str, str | int]]:
        query = f"""
            SELECT id, name, species, age, location, zoo_id, approval_status
            FROM animals
            {where_clause}
        """
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(query, parameters)
            columns = [column.name for column in cursor.description]
            return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]