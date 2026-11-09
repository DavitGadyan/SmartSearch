"""Text embeddings for semantic retrieval."""

from functools import lru_cache

import numpy as np

from app.core.config import settings


class Embedder:
    def __init__(self, model_name: str = settings.embedding_model) -> None:
        from model2vec import StaticModel

        self.model = StaticModel.from_pretrained(model_name)
        self.name = model_name
        self.dim = int(self.model.dim)

    def encode(self, texts: list[str], batch_size: int = 1024) -> np.ndarray:
        vecs = self.model.encode(texts, batch_size=batch_size, show_progress_bar=False).astype(np.float32)
        norms = np.linalg.norm(vecs, axis=1, keepdims=True)
        return vecs / np.clip(norms, 1e-8, None)

    def encode_one(self, text: str) -> np.ndarray:
        return self.encode([text])[0]


@lru_cache
def get_embedder() -> Embedder:
    return Embedder()


def product_text(name: str, product_class: str | None, attrs: dict | None) -> str:
    """Canonical text embedded per product; keep it short and attribute-rich (titles dominate relevance)."""
    attrs = attrs or {}
    bits = [name, product_class or ""]
    bits += [str(attrs[k]) for k in ("product_type", "style", "material", "color") if attrs.get(k)]
    return " . ".join(b for b in bits if b)
