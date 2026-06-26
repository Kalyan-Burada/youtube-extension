"""Single source of truth for every cascade threshold.

The cascade is a borderline-band waterfall: each stage can ALLOW (score at
or above its ALLOW threshold), BLUR (score below its BLUR threshold), or
defer the borderline middle band to the next, more expensive stage. Only
Stage 3 (CLIP) has no "defer" — it is the last resort and makes a final
allow/blur call.

Every number here is validated by `calibrate.py` against the labeled set —
do not hand-tune these by eye, and never copy a threshold into another file.
"""

# Stage 1 — SentenceTransformer (all-mpnet-base-v2) cosine similarity, with a
# generic template wrapped around the focus topic (see embeddings.py).
# Above ALLOW -> allow. Below BLUR -> blur. In between -> defer to Stage 2.
#
# BLUR is deliberately very low. The bi-encoder UNDER-estimates relevance for
# generic focus words ("food" vs "Easy Vanilla Sponge Cake Recipe" embeds at
# ~0.06), but the Stage-2 cross-encoder rates that same pair ~0.18 and nails it.
# So Stage 1 is only a fast-path for CONFIDENT allows; anything not clearly
# unrelated falls through to the more accurate cross-encoder rather than being
# hard-blurred here. calibrate.py confirms BLUR anywhere in 0.0-0.11 holds 97.5%
# with zero false-allows (irrelevant cross-domain pairs score <=0.03 at Stage 2),
# so lowering it only recovers real false-blurs — it costs no precision.
EMBED_ALLOW_THRESHOLD = 0.20
EMBED_BLUR_THRESHOLD = 0.05

# Stage 2 — STS CrossEncoder (stsb-TinyBERT-L-4), output already 0-1.
# Runs only on Stage 1's borderline band. Unrelated pairs sit near ~0.02-0.05,
# so this mostly acts as a promoter: clear topical matches get rescued (allow),
# clear non-matches blur, and the thin uncertain band defers to Stage 3.
CROSS_ALLOW_THRESHOLD = 0.08
CROSS_BLUR_THRESHOLD = 0.05

# Stage 3 — CLIP (clip-ViT-B-32) image/text cosine similarity, last resort.
# Above ALLOW -> allow, otherwise blur (fail-safe default, never default-open).
CLIP_ALLOW_THRESHOLD = 0.22
