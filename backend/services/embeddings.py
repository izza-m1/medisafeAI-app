"""Turns text into vectors (embeddings) so that texts with the same meaning end up close together, even when
they share no words: "always tired" is close to "fatigue from low iron". Used by the knowledge base search and
by the reason matching. The model runs on this computer; it is downloaded once from Hugging Face."""
import threading

import numpy as np

import settings

_model = None
_lock = threading.Lock()


def model():
    global _model
    with _lock:
        if _model is None:
            from sentence_transformers import SentenceTransformer
            _model = SentenceTransformer(settings.EMBEDDING_MODEL)
    return _model


def encode(texts: list, query: bool = False) -> np.ndarray:
    """One row per text, each of length 1, so a dot product between two rows is their cosine similarity.
    query=True adds the instruction bge models expect in front of a search question (not in front of passages)."""
    if not texts:
        return np.zeros((0, 0), dtype=np.float32)
    prompt = settings.EMBEDDING_QUERY_PROMPT if query else None
    vectors = model().encode(list(texts), prompt=prompt, normalize_embeddings=True, convert_to_numpy=True,
                             batch_size=32, show_progress_bar=len(texts) > 200)
    return vectors.astype(np.float32)


def similarity(a: str, b_list: list) -> list:
    """Cosine similarity of one short text to each text in b_list (both sides treated as plain sentences)."""
    if not b_list:
        return []
    vectors = encode([a, *b_list])
    return [float(v) for v in vectors[1:] @ vectors[0]]
