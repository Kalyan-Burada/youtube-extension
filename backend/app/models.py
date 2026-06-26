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
# calibrate.py's per-stage accuracy breakdown.
Stage = Literal["keyword_match", "embedding", "cross_encoder", "vision", "no_signal", "vision_failed"]


class VideoScore(BaseModel):
    id: str
    score: float
    decision: Decision
    stage: Stage


class ScoreResponse(BaseModel):
    results: List[VideoScore]
