import re
from collections import defaultdict
from collections.abc import Iterable
from hashlib import sha256
from typing import Protocol


class EmbeddingProvider(Protocol):
    """Generate one embedding for each supplied retrieval text."""

    def embed(self, texts: list[str]) -> list[list[float]]: ...


def chunk_document(
    content: str,
    chunk_size: int = 400,
    overlap: int = 80,
) -> list[str]:
    """Split text by sentence boundaries into overlapping retrieval chunks."""
    if chunk_size <= 0 or overlap < 0 or overlap >= chunk_size:
        raise ValueError("chunk_size must be positive and overlap must be smaller.")
    sentences = [
        sentence.strip()
        for sentence in re.split(r"(?<=[.!?])\s+", content.strip())
        if sentence.strip()
    ]
    chunks = []
    current = ""
    for sentence in sentences:
        if current and len(current) + len(sentence) + 1 > chunk_size:
            chunks.append(current)
            overlap_text = current[-overlap:] if overlap else ""
            first_space = overlap_text.find(" ")
            current = (
                overlap_text[first_space + 1 :].lstrip()
                if first_space >= 0
                else overlap_text.lstrip()
            )
        current = f"{current} {sentence}".strip()
    if current:
        chunks.append(current)
    return chunks


def reciprocal_rank_fusion(
    rankings: Iterable[Iterable[str]], rank_constant: int = 60
) -> list[str]:
    """Merge ordered semantic and keyword candidates without score coupling."""
    if rank_constant <= 0:
        raise ValueError("rank_constant must be positive.")
    scores: defaultdict[str, float] = defaultdict(float)
    for ranking in rankings:
        for rank, candidate_id in enumerate(ranking, start=1):
            scores[candidate_id] += 1 / (rank_constant + rank)
    return sorted(
        scores,
        key=lambda candidate_id: (-scores[candidate_id], candidate_id),
    )


def build_chunk_records(
    document: dict[str, str], embedding_provider: EmbeddingProvider
) -> list[dict[str, object]]:
    """Validate an approved document and prepare stable records for database storage."""
    required_fields = {
        "id",
        "title",
        "source",
        "updated_at",
        "version",
        "approval_status",
        "zoo_id",
        "content",
    }
    missing_fields = required_fields - document.keys()
    if missing_fields:
        raise ValueError(
            f"Document is missing required fields: {sorted(missing_fields)}"
        )
    if document["approval_status"] != "approved":
        raise ValueError("Only approved documents may be ingested.")
    chunks = chunk_document(document["content"])
    embeddings = embedding_provider.embed(chunks)
    if len(embeddings) != len(chunks):
        raise ValueError("Embedding provider returned an unexpected result count.")
    records = []
    for ordinal, (content, embedding) in enumerate(zip(chunks, embeddings), start=1):
        content_hash = sha256(content.encode()).hexdigest()
        records.append(
            {
                "chunk_id": f"{document['id']}:{document['version']}:{ordinal}",
                "document_id": document["id"],
                "title": document["title"],
                "source": document["source"],
                "zoo_id": document["zoo_id"] or None,
                "version": document["version"],
                "approval_status": document["approval_status"],
                "updated_at": document["updated_at"],
                "ordinal": ordinal,
                "content": content,
                "content_hash": content_hash,
                "embedding": embedding,
            }
        )
    return records