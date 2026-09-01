import json
import os
import re
from typing import Any, Protocol


class Reranker(Protocol):
    def rerank(
        self, query: str, candidates: list[dict[str, object]]
    ) -> list[dict[str, object]]: ...


class LexicalReranker:
    """Use token overlap as a deterministic, no-cost reranking baseline."""

    def rerank(
        self, query: str, candidates: list[dict[str, object]]
    ) -> list[dict[str, object]]:
        query_terms = set(_tokenize(query))
        return sorted(
            candidates,
            key=lambda candidate: (
                -len(query_terms.intersection(_tokenize(str(candidate["content"])))),
                str(candidate["chunk_id"]),
            ),
        )


class GeminiReranker:
    """Ask Gemini to order only already approved hybrid-retrieval candidates."""

    def __init__(self, client: Any | None = None, model: str | None = None) -> None:
        self.client = client
        self.model = model or os.getenv("GEMINI_RERANKER_MODEL", "gemini-2.5-flash")

    def rerank(
        self, query: str, candidates: list[dict[str, object]]
    ) -> list[dict[str, object]]:
        client = self.client or self._create_client()
        candidate_ids = {str(candidate["chunk_id"]) for candidate in candidates}
        prompt = {
            "query": query,
            "candidates": [
                {"chunk_id": candidate["chunk_id"], "content": candidate["content"]}
                for candidate in candidates
            ],
            "instruction": (
                "Return a JSON array of all chunk_id values, most relevant first."
            ),
        }
        response = client.models.generate_content(
            model=self.model,
            contents=json.dumps(prompt),
            config={"response_mime_type": "application/json"},
        )
        ordered_ids = json.loads(response.text)
        if (
            not isinstance(ordered_ids, list)
            or set(ordered_ids) != candidate_ids
            or len(ordered_ids) != len(candidate_ids)
        ):
            raise ValueError("Gemini reranker returned invalid candidate IDs.")
        candidate_by_id = {
            str(candidate["chunk_id"]): candidate for candidate in candidates
        }
        return [candidate_by_id[chunk_id] for chunk_id in ordered_ids]

    def _create_client(self) -> Any:
        project = os.getenv("GOOGLE_CLOUD_PROJECT")
        location = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")
        if not project:
            raise RuntimeError("GOOGLE_CLOUD_PROJECT is required for Gemini reranking.")
        from google import genai

        return genai.Client(vertexai=True, project=project, location=location)


def configured_reranker() -> Reranker:
    if os.getenv("GEMINI_RERANKER_ENABLED", "FALSE").upper() == "TRUE":
        return GeminiReranker()
    return LexicalReranker()


def _tokenize(value: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", value.lower())