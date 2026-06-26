from typing import List, Optional

import numpy as np
from sentence_transformers import CrossEncoder

_CROSS_MODEL_NAME = "cross-encoder/ms-marco-MiniLM-L-6-v2"
_cross_model: Optional[CrossEncoder] = None


def get_cross_encoder() -> CrossEncoder:
    global _cross_model
    if _cross_model is None:
        _cross_model = CrossEncoder(_CROSS_MODEL_NAME)
    return _cross_model

def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + np.exp(-x))


def rerank_batch(query: str, candidates: List[str]) -> List[float]:
    """Returns one 0-1 relevance score per candidate.

    NOTE: ms-marco-MiniLM-L-6-v2 was trained on query->passage pairs, not
    short-topic->short-title pairs, and its raw output is an unbounded
    logit, not a probability. The sigmoid below gives it a 0-1 range but
    is an approximation — re-check CROSS_ALLOW/BLUR thresholds in
    calibrate.py rather than trusting this scale blindly.
    """
    if not candidates:
        return []
    pairs = [(query, c) for c in candidates]
    model = get_cross_encoder()
    raw_scores = model.predict(pairs)
    return [float(_sigmoid(s)) for s in raw_scores]
