"""
Jina Embeddings v3 client.

Replaces local SentenceTransformer (all-MiniLM-L6-v2, 384d)
with Jina API (jina-embeddings-v3, 1024d, 89 languages, task adapters).

Task adapters:
  - retrieval.passage: for indexing documents (ingest)
  - retrieval.query:   for search queries (recall)
"""

import os
import logging
from typing import List, Optional

import requests

logger = logging.getLogger("jina-embedder")

JINA_API_URL = "https://api.jina.ai/v1/embeddings"
JINA_MODEL = "jina-embeddings-v3"
JINA_DIMENSIONS = 1024


def _load_jina_key() -> str:
    """Load Jina API key from ~/.accounts"""
    accounts_path = os.path.expanduser("~/.accounts")
    with open(accounts_path) as f:
        for line in f:
            if line.startswith("jina:"):
                return line.strip().split(":", 1)[1]
    raise RuntimeError("Jina API key not found in ~/.accounts")


class JinaEmbedder:
    """Jina Embeddings v3 client with task-specific adapters."""

    def __init__(self, api_key: Optional[str] = None, dimensions: int = JINA_DIMENSIONS):
        self.api_key = api_key or _load_jina_key()
        self.dimensions = dimensions

    def embed(self, texts: List[str], task: str = "retrieval.passage") -> List[List[float]]:
        """Embed one or more texts using Jina API.

        Args:
            texts: List of strings to embed.
            task: Jina task adapter — 'retrieval.passage' for ingest,
                  'retrieval.query' for search.

        Returns:
            List of embedding vectors (each is a list of floats).
        """
        resp = requests.post(
            JINA_API_URL,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": JINA_MODEL,
                "task": task,
                "dimensions": self.dimensions,
                "input": texts,
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        # Sort by index to guarantee order
        sorted_data = sorted(data["data"], key=lambda x: x["index"])
        return [item["embedding"] for item in sorted_data]

    def embed_passage(self, text: str) -> List[float]:
        """Embed a single document for indexing."""
        return self.embed([text], task="retrieval.passage")[0]

    def embed_query(self, text: str) -> List[float]:
        """Embed a single query for search."""
        return self.embed([text], task="retrieval.query")[0]

    def embed_passages_batch(self, texts: List[str], batch_size: int = 64) -> List[List[float]]:
        """Embed multiple documents in batches for indexing."""
        all_embeddings = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            embeddings = self.embed(batch, task="retrieval.passage")
            all_embeddings.extend(embeddings)
        return all_embeddings
