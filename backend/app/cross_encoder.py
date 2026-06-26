from typing import List, Optional

from sentence_transformers import CrossEncoder

# Stage 2 reranker. We deliberately use a semantic-textual-similarity (STS)
# cross-encoder, NOT a passage-retrieval one. The old ms-marco-MiniLM model
# scored ~0.000 for every short-topic/short-title pair (it expects long
# query->passage inputs), so Stage 2 could only ever blur — it added latency
# and zero signal. This STS model actually discriminates: unrelated pairs
# cluster near ~0.02 while on-topic pairs spread up to ~0.4+, which is exactly
# the second opinion Stage 1's borderline band needs. It's also BERT-based and
# tiny (~50MB), so it loads fast and avoids the roberta tokenizer-format
# incompatibility that newer STS models hit on this environment.
_CROSS_MODEL_NAME = "cross-encoder/stsb-TinyBERT-L-4"
_cross_model: Optional[CrossEncoder] = None


def get_cross_encoder() -> CrossEncoder:
    global _cross_model
    if _cross_model is None:
        _cross_model = CrossEncoder(_CROSS_MODEL_NAME)
    return _cross_model


def rerank_batch(query: str, candidates: List[str]) -> List[float]:
    """Returns one similarity score per candidate, already in the 0-1 range.

    The stsb cross-encoder's predict() output is a normalized similarity, so
    (unlike a raw-logit retrieval model) it must NOT be passed through another
    sigmoid — doing so would compress every score toward 0.5 and destroy the
    separation. Re-validate CROSS_ALLOW/BLUR with calibrate.py if you swap the
    model, since the output scale is model-specific.
    """
    if not candidates:
        return []
    pairs = [(query, c) for c in candidates]
    model = get_cross_encoder()
    raw_scores = model.predict(pairs)
    return [float(s) for s in raw_scores]
