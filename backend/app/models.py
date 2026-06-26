from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class IntentSignals(BaseModel):
    """Everything that defines 'what the user currently cares about'.

    At least one of these three should be present. They get combined into
    a single weighted intent embedding in embeddings.build_intent_embedding.
    """

    focus_topic: Optional[str] = Field(
        None, description="User-selected focus topic, e.g. 'Machine Learning'"
    )
    current_video_title: Optional[str] = Field(
        None, description="Title of the video currently being watched"
    )
    recent_titles: List[str] = Field(
        default_factory=list,
        description="Titles of the last few watched videos, most recent first",
    )


class VideoItem(BaseModel):
    id: str
    title: str
    thumbnail_url: Optional[str] = Field(
        None, description="Used only if Stage 3 (CLIP vision) is reached"
    )


class ScoreRequest(BaseModel):
    intent: IntentSignals
    videos: List[VideoItem]


Decision = Literal["allow", "blur", "borderline"]

# Which stage produced the final decision — useful for debugging and for
# calibrate.py's per-stage accuracy breakdown. Every value main.py can emit
# must be listed here or pydantic will 500 the whole /score response.
Stage = Literal[
    "keyword_match",   # explicit focus keyword found in the title
    "embedding",       # resolved by Stage 1 (SentenceTransformer)
    "cross_encoder",   # resolved by Stage 2 (CrossEncoder rerank)
    "vision",          # resolved by Stage 3 (CLIP thumbnail)
    "no_signal",       # reached Stage 3 but had no thumbnail to check
    "vision_failed",   # reached Stage 3 but the thumbnail could not be fetched
    "stage_error",     # a model failed mid-cascade; failed safe (blur)
]


class VideoScore(BaseModel):
    id: str
    score: float
    decision: Decision
    stage: Stage


class ScoreResponse(BaseModel):
    results: List[VideoScore]
