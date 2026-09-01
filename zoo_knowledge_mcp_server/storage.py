from collections.abc import Sequence
from typing import Protocol


class KnowledgeRepository(Protocol):
    def initialize(self) -> None: ...

    def is_current(
        self, document_id: str, version: str, document_hash: str
    ) -> bool: ...

    def upsert_chunks(
        self, records: Sequence[dict[str, object]], document_hash: str
    ) -> None: ...

    def search_semantic(
        self, query_embedding: list[float], zoo_id: str, limit: int
    ) -> list[dict[str, object]]: ...

    def search_keyword(
        self, query: str, zoo_id: str, limit: int
    ) -> list[dict[str, object]]: ...


class PostgresKnowledgeRepository:
    """Store approved chunks in PostgreSQL with pgvector and full-text indexes."""

    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    def _connect(self):
        try:
            import psycopg
        except ImportError as error:
            raise RuntimeError(
                "Install psycopg to use PostgreSQL knowledge storage."
            ) from error
        return psycopg.connect(self.database_url)

    def initialize(self) -> None:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute("CREATE EXTENSION IF NOT EXISTS vector")
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS knowledge_documents (
                    document_id TEXT NOT NULL,
                    version TEXT NOT NULL,
                    title TEXT NOT NULL,
                    source TEXT NOT NULL,
                    zoo_id TEXT NOT NULL,
                    approval_status TEXT NOT NULL CHECK (approval_status = 'approved'),
                    updated_at DATE NOT NULL,
                    document_hash TEXT NOT NULL,
                    PRIMARY KEY (document_id, version)
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS knowledge_chunks (
                    chunk_id TEXT PRIMARY KEY,
                    document_id TEXT NOT NULL,
                    version TEXT NOT NULL,
                    ordinal INTEGER NOT NULL,
                    content TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    embedding vector(768) NOT NULL,
                    content_tsv TSVECTOR GENERATED ALWAYS AS
                        (to_tsvector('english', content)) STORED,
                    UNIQUE (document_id, version, ordinal)
                )
                """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS knowledge_chunks_embedding_idx
                ON knowledge_chunks USING hnsw (embedding vector_cosine_ops)
                """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS knowledge_chunks_content_tsv_idx
                ON knowledge_chunks USING gin (content_tsv)
                """
            )

    def is_current(
        self, document_id: str, version: str, document_hash: str
    ) -> bool:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT 1 FROM knowledge_documents
                WHERE document_id = %s AND version = %s AND document_hash = %s
                """,
                (document_id, version, document_hash),
            )
            return cursor.fetchone() is not None

    def upsert_chunks(
        self, records: Sequence[dict[str, object]], document_hash: str
    ) -> None:
        if not records:
            return
        first_record = records[0]
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO knowledge_documents (
                    document_id, version, title, source, zoo_id, approval_status,
                    updated_at, document_hash
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (document_id, version) DO UPDATE SET
                    title = EXCLUDED.title, source = EXCLUDED.source,
                    zoo_id = EXCLUDED.zoo_id,
                    approval_status = EXCLUDED.approval_status,
                    updated_at = EXCLUDED.updated_at,
                    document_hash = EXCLUDED.document_hash
                """,
                (
                    first_record["document_id"],
                    first_record["version"],
                    first_record["title"],
                    first_record["source"],
                    first_record["zoo_id"],
                    first_record["approval_status"],
                    first_record["updated_at"],
                    document_hash,
                ),
            )
            cursor.execute(
                "DELETE FROM knowledge_chunks WHERE document_id = %s AND version = %s",
                (first_record["document_id"], first_record["version"]),
            )
            cursor.executemany(
                """
                INSERT INTO knowledge_chunks (
                    chunk_id, document_id, version, ordinal, content, content_hash,
                    embedding
                ) VALUES (%s, %s, %s, %s, %s, %s, %s::vector)
                """,
                [
                    (
                        record["chunk_id"],
                        record["document_id"],
                        record["version"],
                        record["ordinal"],
                        record["content"],
                        record["content_hash"],
                        _vector_literal(record["embedding"]),
                    )
                    for record in records
                ],
            )

    def search_semantic(
        self, query_embedding: list[float], zoo_id: str, limit: int
    ) -> list[dict[str, object]]:
        return self._search(
            """
            ORDER BY knowledge_chunks.embedding <=> %s::vector
            LIMIT %s
            """,
            (zoo_id, _vector_literal(query_embedding), limit),
        )

    def search_keyword(
        self, query: str, zoo_id: str, limit: int
    ) -> list[dict[str, object]]:
        return self._search(
            """
            AND knowledge_chunks.content_tsv @@ websearch_to_tsquery('english', %s)
            ORDER BY ts_rank_cd(
                knowledge_chunks.content_tsv,
                websearch_to_tsquery('english', %s)
            ) DESC
            LIMIT %s
            """,
            (zoo_id, query, query, limit),
        )

    def _search(
        self, order_and_limit_sql: str, parameters: tuple[object, ...]
    ) -> list[dict[str, object]]:
        query = f"""
            SELECT knowledge_chunks.chunk_id, knowledge_chunks.content,
                   knowledge_documents.document_id, knowledge_documents.title,
                   knowledge_documents.source, knowledge_documents.zoo_id,
                   knowledge_documents.version, knowledge_documents.updated_at
            FROM knowledge_chunks
            JOIN knowledge_documents ON (
                knowledge_chunks.document_id = knowledge_documents.document_id
                AND knowledge_chunks.version = knowledge_documents.version
            )
            WHERE knowledge_documents.approval_status = 'approved'
              AND knowledge_documents.zoo_id IN ('global', %s)
            {order_and_limit_sql}
        """
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(query, parameters)
            columns = [column.name for column in cursor.description]
            return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]


def _vector_literal(embedding: object) -> str:
    if not isinstance(embedding, list) or not all(
        isinstance(value, float) for value in embedding
    ):
        raise ValueError("Each embedding must be a list of floats.")
    return "[" + ",".join(str(value) for value in embedding) + "]"