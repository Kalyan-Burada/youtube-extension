from typing import List, Optional

import numpy as np
from sentence_transformers import SentenceTransformer

_MODEL_NAME = "all-mpnet-base-v2"
_model: Optional[SentenceTransformer] = None


def get_model() -> SentenceTransformer:
    """Lazy-load the model once per process, not once per request."""
    global _model
    if _model is None:
        _model = SentenceTransformer(_MODEL_NAME)
    return _model

def encode(texts: List[str]) -> np.ndarray:
    """Encode a batch of strings into L2-normalized embedding vectors.

    Normalizing here means cosine_sim() below can just be a dot product.
    """
    model = get_model()
    return model.encode(texts, convert_to_numpy=True, normalize_embeddings=True)


def cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b))


def build_intent_embedding(
    focus_topic: Optional[str],
    current_video_title: Optional[str],
    recent_titles: List[str],
) -> np.ndarray:
    """Weighted average of focus topic / current video / watch history.

    Focus topic carries the most weight (it's an explicit, deliberate
    choice). Current video matters a lot but can drift. Watch history
    matters less the further back it goes, hence the decay.
    """
    texts: List[str] = []
    weights: List[float] = []

    if focus_topic:
        texts.append(focus_topic)
        weights.append(1.0)

    if current_video_title:
        texts.append(current_video_title)
        weights.append(0.8)

    decay = 0.7
    for i, title in enumerate(recent_titles):
        texts.append(title)
        weights.append(0.5 * (decay**i))

    if not texts:
        raise ValueError(
            "No intent signal provided (need focus_topic, current_video_title, "
            "or at least one recent_title)."
        )

    vectors = encode(texts)
    weights_arr = np.array(weights, dtype=np.float32).reshape(-1, 1)
    weighted_sum = (vectors * weights_arr).sum(axis=0)

    norm = np.linalg.norm(weighted_sum)
    if norm > 0:
        weighted_sum = weighted_sum / norm
    return weighted_sum


def build_intent_text(
    focus_topic: Optional[str],
    current_video_title: Optional[str],
    recent_titles: List[str],
) -> str:
    """Plain-text version of intent for stages that need raw text rather
    than an embedding (CrossEncoder, CLIP's text tower). Same priority
    order as build_intent_embedding: focus topic first, then current
    video, then a few recent titles for extra context."""
    parts: List[str] = []
    if focus_topic:
        parts.append(focus_topic)
    if current_video_title:
        parts.append(current_video_title)
    parts.extend(recent_titles[:3])
    return " | ".join(parts)
