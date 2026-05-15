"""SQLite-backed embedding cache."""

import hashlib
import json
import sqlite3
from collections.abc import Callable
from contextlib import closing
from pathlib import Path


class EmbeddingCache:
    """Cache embedding vectors by model and text hash."""

    def __init__(self, path: Path | str, model: str):
        self.path = Path(path)
        self.model = model
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def get(self, text: str) -> list[float] | None:
        """Return a cached embedding if present."""
        with closing(sqlite3.connect(self.path)) as connection:
            row = connection.execute(
                "SELECT vector_json FROM embeddings WHERE cache_key = ?",
                (self._cache_key(text),),
            ).fetchone()
        if row is None:
            return None
        values = json.loads(row[0])
        return [float(value) for value in values]

    def set(self, text: str, vector: list[float]) -> None:
        """Store an embedding vector."""
        text_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
        with closing(sqlite3.connect(self.path)) as connection:
            with connection:
                connection.execute(
                    """
                    INSERT OR REPLACE INTO embeddings
                        (cache_key, model, text_hash, vector_json)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        self._cache_key(text),
                        self.model,
                        text_hash,
                        json.dumps(vector),
                    ),
                )

    def get_or_create(
        self,
        text: str,
        embedder: Callable[[str], list[float]],
    ) -> list[float]:
        """Return a cached vector or create and store it."""
        cached = self.get(text)
        if cached is not None:
            return cached
        vector = embedder(text)
        self.set(text, vector)
        return vector

    def _cache_key(self, text: str) -> str:
        """Return a stable cache key for model and text."""
        raw = f"{self.model}\n{text}".encode()
        return hashlib.sha256(raw).hexdigest()

    def _ensure_schema(self) -> None:
        """Create the embedding cache table."""
        with closing(sqlite3.connect(self.path)) as connection:
            with connection:
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS embeddings (
                        cache_key TEXT PRIMARY KEY,
                        model TEXT NOT NULL,
                        text_hash TEXT NOT NULL,
                        vector_json TEXT NOT NULL
                    )
                    """
                )
