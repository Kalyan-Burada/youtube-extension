"""
Session 9 — calibration harness.

Runs calibration_set.json through Stage 1 (embedding) and Stage 2
(cross-encoder) and reports accuracy, broken down per domain. This is
what tells you whether EMBED_*/CROSS_* in config.py need adjusting, or
whether one domain is systematically harder than the others.

Stage 3 (CLIP vision) is NOT covered here — this set uses made-up titles
with no real thumbnails, so there's nothing to download and encode. To
calibrate vision, capture real {title, thumbnail_url, expected} triples
from an actual YouTube session and add that as a second set later.

Run from backend/ (with the venv from S2 active):
    python3 calibrate.py
"""
import json
from collections import defaultdict
from pathlib import Path

from app.config import (
    CROSS_ALLOW_THRESHOLD,
    CROSS_BLUR_THRESHOLD,
    EMBED_ALLOW_THRESHOLD,
    EMBED_BLUR_THRESHOLD,
)
from app.cross_encoder import rerank_batch
from app.embeddings import build_intent_embedding, build_intent_text, cosine_sim, encode


def load_cases():
    path = Path(__file__).parent / "calibration_set.json"
    return json.loads(path.read_text())


def classify_embedding(score: float) -> str:
    if score >= EMBED_ALLOW_THRESHOLD:
        return "allow"
    if score < EMBED_BLUR_THRESHOLD:
        return "blur"
    return "borderline"


def classify_cross(score: float) -> str:
    if score >= CROSS_ALLOW_THRESHOLD:
        return "allow"
    if score < CROSS_BLUR_THRESHOLD:
        return "blur"
    return "borderline"


def main():
    cases = load_cases()

    correct = 0
    borderline_count = 0
    by_domain = defaultdict(lambda: {"correct": 0, "total": 0})

    header = f"{'Domain':<10} {'Title':<42} {'Expect':<7} {'Embed':<7} {'S1':<10} {'Cross':<7} {'Final':<6}"
    print(header)
    print("-" * len(header))

    for case in cases:
        domain = case["domain"]
        focus_topic = case["focus_topic"]
        title = case["title"]
        expected = case["expected"]

        intent_vec = build_intent_embedding(focus_topic, None, [])
        video_vec = encode([title])[0]
        embed_score = cosine_sim(intent_vec, video_vec)
        stage1 = classify_embedding(embed_score)

        final = stage1
        cross_score = None
        if stage1 == "borderline":
            borderline_count += 1
            intent_text = build_intent_text(focus_topic, None, [])
            cross_score = rerank_batch(intent_text, [title])[0]
            final = classify_cross(cross_score)
            if final == "borderline":
                # In production this falls through to CLIP vision (Stage 3).
                # No thumbnail here, so fail safe the same way Stage 3 would
                # for a video with no usable image.
                final = "blur"

        is_correct = final == expected
        correct += is_correct
        by_domain[domain]["total"] += 1
        by_domain[domain]["correct"] += is_correct

        cross_str = f"{cross_score:.3f}" if cross_score is not None else "-"
        print(
            f"{domain:<10} {title[:40]:<42} {expected:<7} {embed_score:<7.3f} "
            f"{stage1:<10} {cross_str:<7} {final:<6}"
        )

    print("-" * len(header))
    print(f"\nOverall accuracy: {correct}/{len(cases)} ({100 * correct / len(cases):.1f}%)")
    print(f"Resolved at Stage 1 alone: {len(cases) - borderline_count}/{len(cases)}")
    print(f"Needed Stage 2 (cross-encoder): {borderline_count}/{len(cases)}")

    print("\nPer-domain accuracy:")
    for domain, stats in sorted(by_domain.items()):
        pct = 100 * stats["correct"] / stats["total"]
        print(f"  {domain:<10} {stats['correct']}/{stats['total']}  ({pct:.0f}%)")

    print(
        "\nIf one domain is consistently wrong, that's a sign EMBED_*/CROSS_* "
        "thresholds in app/config.py need adjusting — try moving them in small "
        "steps (0.05) and re-running rather than guessing."
    )


if __name__ == "__main__":
    main()
