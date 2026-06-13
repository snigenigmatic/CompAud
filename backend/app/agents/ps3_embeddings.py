"""Local embeddings for semantic evidence linking (PS3).

Primary path: a local SentenceTransformer (no API cost/latency). If the model
cannot be loaded (e.g. offline demo machine), transparently falls back to a
TF-IDF + cosine similarity over the combined corpus so linking still works.
"""

from __future__ import annotations

import logging
from functools import lru_cache

import numpy as np

from app.config import get_settings

logger = logging.getLogger(__name__)


@lru_cache(maxsize=2)
def get_embedder():
    settings = get_settings()
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(settings.embedding_model_name, device=settings.embedding_device)


def encode(texts: list[str]) -> np.ndarray:
    """Encode texts into L2-normalised embeddings (cosine == dot product)."""
    model = get_embedder()
    return model.encode(
        list(texts),
        batch_size=64,
        normalize_embeddings=True,
        convert_to_numpy=True,
        show_progress_bar=False,
    )


@lru_cache(maxsize=8)
def _encode_cached(texts: tuple[str, ...]) -> np.ndarray:
    """Cache for small, stable corpora (e.g. the 9 requirements)."""
    return encode(list(texts))


def similarity_matrix(
    evidence_texts: list[str],
    requirement_texts: list[str],
) -> np.ndarray:
    """Return cosine similarities, shape [n_evidence, n_requirements] in [0, 1]-ish.

    Requirement embeddings are cached; evidence is encoded in one batch.
    """
    try:
        evidence_emb = encode(evidence_texts)
        requirement_emb = _encode_cached(tuple(requirement_texts))
        return evidence_emb @ requirement_emb.T
    except Exception:
        logger.warning(
            "Embedding model unavailable; falling back to TF-IDF similarity",
            exc_info=True,
        )
        return _tfidf_similarity(evidence_texts, requirement_texts)


def _tfidf_similarity(
    evidence_texts: list[str],
    requirement_texts: list[str],
) -> np.ndarray:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity

    vectorizer = TfidfVectorizer(stop_words="english")
    matrix = vectorizer.fit_transform(list(evidence_texts) + list(requirement_texts))
    split = len(evidence_texts)
    return cosine_similarity(matrix[:split], matrix[split:])


def embedding_mode() -> str:
    """For diagnostics / report provenance."""
    try:
        get_embedder()
        return f"sentence-transformers:{get_settings().embedding_model_name}"
    except Exception:
        return "tfidf-fallback"
