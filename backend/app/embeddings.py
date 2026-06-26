from typing import List, Optional

import numpy as np
from sentence_transformers import SentenceTransformer

_MODEL_NAME = "all-mpnet-base-v2"
_model: Optional[SentenceTransformer] = None

# Bump this whenever the embedding model OR the intent-construction logic
# (expand_focus_topic, weights, templates) changes. It is mixed into the cache
# signature so old cached vectors are never silently reused after an update —
# the #1 cause of "I changed the code but the behavior didn't change".
INTENT_EMBED_VERSION = "v3-expand"


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


def expand_focus_topic(focus_topic: str) -> List[tuple]:
    """Generic intent expansion for the focus topic — returns (text, weight)
    pairs whose embeddings get averaged into the intent vector.

    This is NOT a per-topic keyword/synonym dictionary: the same templates wrap
    whatever the user typed. A bare topic ("movie", "cricket") embeds weakly
    against real titles, so we pair the raw topic with a generic
    "A YouTube video about {topic}" template, and — only for SHORT, generic
    topics (<= 3 words) — add one broader paraphrase to widen the topic's
    semantic footprint a little. Long, already-specific focus topics
    ("telugu movie trailers 2026") are left precise: broadening them only
    pulls in unrelated content. Weights and the word-count gate are validated
    by calibrate.py (full-cascade accuracy holds at 97.5%); re-run it if you
    touch them.
    """
    parts = [(focus_topic, 0.5), (f"A YouTube video about {focus_topic}", 0.35)]
    word_count = len(focus_topic.split())
    if 1 <= word_count <= 3:
        parts.append((f"Videos, clips and discussion related to {focus_topic}", 0.15))
    else:
        # No broad paraphrase — give the template its weight back instead.
        parts[1] = (parts[1][0], 0.5)
    return parts


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
        # A bare topic ("Python Programming") embeds weakly against real video
        # titles that never spell the topic out ("Django REST Framework Crash
        # Course"). expand_focus_topic() pairs the raw topic with generic,
        # topic-agnostic templates to widen its semantic footprint — NOT a
        # per-topic keyword list. The focus topic's combined weight stays ~1.0
        # so the current-video / history weighting below is unchanged.
        for text, weight in expand_focus_topic(focus_topic):
            texts.append(text)
            weights.append(weight)

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
