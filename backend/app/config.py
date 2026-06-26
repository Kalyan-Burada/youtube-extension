"""Single source of truth for every cascade threshold.
Updated for a strict waterfall architecture."""

# Stage 1 — SentenceTransformer cosine similarity
EMBED_ALLOW_THRESHOLD = 0.40

# Stage 2 — CrossEncoder (sigmoid-normalized), runs on S1 failures
CROSS_ALLOW_THRESHOLD = 0.50

# Stage 3 — CLIP image/text cosine similarity, last resort
CLIP_ALLOW_THRESHOLD = 0.22