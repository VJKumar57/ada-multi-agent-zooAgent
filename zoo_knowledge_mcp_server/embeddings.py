import os
from typing import Any


class VertexEmbeddingProvider:
    """Generate retrieval embeddings through Vertex AI's Gemini SDK client."""

    def __init__(
        self,
        client: Any | None = None,
        model: str | None = None,
        dimensions: int = 768,
    ) -> None:
        self.client = client
        self.model = model or os.getenv("VERTEX_EMBEDDING_MODEL", "text-embedding-005")
        self.dimensions = dimensions

    def embed(self, texts: list[str]) -> list[list[float]]:
        return self._embed(texts, "RETRIEVAL_DOCUMENT")

    def embed_query(self, query: str) -> list[float]:
        embeddings = self._embed([query], "RETRIEVAL_QUERY")
        return embeddings[0]

    def _embed(self, texts: list[str], task_type: str) -> list[list[float]]:
        if not texts:
            return []
        client = self.client or self._create_client()
        response = client.models.embed_content(
            model=self.model,
            contents=texts,
            config={
                "task_type": task_type,
                "output_dimensionality": self.dimensions,
            },
        )
        embeddings = [list(item.values) for item in response.embeddings]
        if len(embeddings) != len(texts) or any(
            len(embedding) != self.dimensions for embedding in embeddings
        ):
            raise ValueError(
                "Vertex AI returned embeddings with unexpected dimensions."
            )
        return embeddings

    def _create_client(self) -> Any:
        project = os.getenv("GOOGLE_CLOUD_PROJECT")
        location = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")
        if not project:
            raise RuntimeError(
                "GOOGLE_CLOUD_PROJECT is required for Vertex AI embeddings."
            )
        try:
            from google import genai
        except ImportError as error:
            raise RuntimeError(
                "Install google-genai to use Vertex AI embeddings."
            ) from error
        return genai.Client(vertexai=True, project=project, location=location)