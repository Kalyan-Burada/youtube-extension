import re
from typing import Dict, Optional, Set

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .cache import EmbeddingCache, make_signature
from .config import (
    CLIP_ALLOW_THRESHOLD,
    CROSS_ALLOW_THRESHOLD,
    EMBED_ALLOW_THRESHOLD,
)
from .cross_encoder import rerank_batch
from .embeddings import build_intent_embedding, build_intent_text, cosine_sim, encode
from .models import ScoreRequest, ScoreResponse, VideoScore
from .vision import cosine_sim as clip_cosine_sim
from .vision import encode_image_from_url
from .vision import encode_text as clip_encode_text

app = FastAPI(title="YouTube Relevance Engine", version="0.2.0")

# Tighten allow_origins to the extension's own origin (chrome-extension://<id>)
# before shipping — wide open "*" is fine for local dev only.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

cache = EmbeddingCache()

FOCUS_STOPWORDS = {
    "a",
    "an",
    "and",
    "for",
    "in",
    "of",
    "on",
    "or",
    "the",
    "to",
    "video",
    "videos",
}


def _tokens(text: str) -> Set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def _singularize(token: str) -> str:
    if len(token) > 3 and token.endswith("ies"):
        return f"{token[:-3]}y"
    if len(token) > 3 and token.endswith("s"):
        return token[:-1]
    return token


def focus_topic_matches_title(focus_topic: Optional[str], title: str) -> bool:
    """Allow obvious explicit focus matches before probabilistic scoring."""
    if not focus_topic or not title:
        return False

    normalized_focus = " ".join(re.findall(r"[a-z0-9]+", focus_topic.lower()))
    normalized_title = " ".join(re.findall(r"[a-z0-9]+", title.lower()))
    if normalized_focus and f" {normalized_focus} " in f" {normalized_title} ":
        return True

    focus_tokens = {
        _singularize(token)
        for token in _tokens(focus_topic)
        if token not in FOCUS_STOPWORDS and (len(token) >= 4 or token in {"ai", "ml"})
    }
    title_tokens = {_singularize(token) for token in _tokens(title)}
    return bool(focus_tokens & title_tokens)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/score", response_model=ScoreResponse)
def score(req: ScoreRequest):
    intent = req.intent
    if not intent.focus_topic and not intent.current_video_title and not intent.recent_titles:
        raise HTTPException(status_code=400, detail="No intent signal provided.")

    if not req.videos:
        return ScoreResponse(results=[])

    outcomes: Dict[str, dict] = {}
    videos_to_score = []
    for video in req.videos:
        if focus_topic_matches_title(intent.focus_topic, video.title):
            outcomes[video.id] = {"score": 1.0, "decision": "allow", "stage": "keyword_match"}
        else:
            videos_to_score.append(video)

    if not videos_to_score:
        return ScoreResponse(
            results=[
                VideoScore(
                    id=video.id,
                    score=round(outcomes[video.id]["score"], 4),
                    decision=outcomes[video.id]["decision"],
                    stage=outcomes[video.id]["stage"],
                )
                for video in req.videos
            ]
        )

    # --- Resolve the intent embedding + intent text (cached unless the ---
    # --- signals actually changed) -----------------------------------------
    signature = make_signature(
        intent.focus_topic or "",
        intent.current_video_title or "",
        "|".join(intent.recent_titles),
    )
    intent_vec = cache.get_intent_embedding(signature)
    if intent_vec is None:
        intent_vec = build_intent_embedding(
            intent.focus_topic, intent.current_video_title, intent.recent_titles
        )
        cache.set_intent_embedding(signature, intent_vec)

    intent_text = build_intent_text(
        intent.focus_topic, intent.current_video_title, intent.recent_titles
    )

    # --- Resolve each video's embedding, batching only the cache misses ---
    video_vecs = {}
    miss_ids, miss_titles = [], []
    for video in videos_to_score:
        cached = cache.get_video_embedding(video.id, video.title)
        if cached is not None:
            video_vecs[video.id] = cached
        else:
            miss_ids.append(video.id)
            miss_titles.append(video.title)

    if miss_titles:
        fresh_vecs = encode(miss_titles)
        for vid, title, vec in zip(miss_ids, miss_titles, fresh_vecs):
            cache.set_video_embedding(vid, title, vec)
            video_vecs[vid] = vec

# --- Stage 1: Cheap embedding cosine similarity, every video --------
    unresolved = []

    for video in videos_to_score:
        sim = cosine_sim(intent_vec, video_vecs[video.id])
        if sim >= EMBED_ALLOW_THRESHOLD:
            outcomes[video.id] = {"score": sim, "decision": "allow", "stage": "embedding"}
        else:
            # S1 Failed: Push to Stage 2 instead of blurring
            outcomes[video.id] = {"score": sim, "decision": "blur", "stage": "embedding_failed"}
            unresolved.append(video)

    # --- Stage 2: CrossEncoder rerank, only on S1 failures --------
    if unresolved and intent_text:
        titles = [v.title for v in unresolved]
        cross_scores = rerank_batch(intent_text, titles)
        still_unresolved = []
        for video, cscore in zip(unresolved, cross_scores):
            if cscore >= CROSS_ALLOW_THRESHOLD:
                outcomes[video.id] = {"score": cscore, "decision": "allow", "stage": "cross_encoder"}
            else:
                # S2 Failed: Push to Stage 3
                outcomes[video.id]["score"] = cscore
                outcomes[video.id]["stage"] = "cross_encoder_failed"
                still_unresolved.append(video)
        unresolved = still_unresolved

    # --- Stage 3: CLIP vision on the thumbnail, last resort --------------
    if unresolved:
        intent_clip_vec = clip_encode_text(intent_text) if intent_text else None
        for video in unresolved:
            if not video.thumbnail_url or intent_clip_vec is None:
                # No image to check, or no usable intent text — fail safe.
                outcomes[video.id]["decision"] = "blur"
                outcomes[video.id]["stage"] = "no_signal"
                continue
            
            img_vec = encode_image_from_url(video.thumbnail_url)
            if img_vec is None:
                outcomes[video.id]["decision"] = "blur"
                outcomes[video.id]["stage"] = "vision_failed"
                continue
            
            vscore = clip_cosine_sim(intent_clip_vec, img_vec)
            if vscore >= CLIP_ALLOW_THRESHOLD:
                outcomes[video.id] = {"score": vscore, "decision": "allow", "stage": "vision"}
            else:
                # S3 Failed: The video is finally blurred.
                outcomes[video.id] = {"score": vscore, "decision": "blur", "stage": "vision"}

    results = [
        VideoScore(
            id=video.id,
            score=round(outcomes[video.id]["score"], 4),
            decision=outcomes[video.id]["decision"],
            stage=outcomes[video.id]["stage"],
        )
        for video in req.videos
    ]
    return ScoreResponse(results=results)