from io import BytesIO
from typing import Optional

import numpy as np
import requests
from PIL import Image
from sentence_transformers import SentenceTransformer

_CLIP_MODEL_NAME = "clip-ViT-B-32"
_clip_model: Optional[SentenceTransformer] = None


def get_clip_model() -> SentenceTransformer:
    global _clip_model
    if _clip_model is None:
        _clip_model = SentenceTransformer(_CLIP_MODEL_NAME)
    return _clip_model

def encode_text(text: str) -> np.ndarray:
    """Encode with CLIP's own text tower — NOT interchangeable with the
    all-mpnet-base-v2 embeddings used elsewhere. Image and text embeddings
    only compare meaningfully within CLIP's own joint space."""
    model = get_clip_model()
    return model.encode([text], convert_to_numpy=True, normalize_embeddings=True)[0]


def encode_image_from_url(url: str, timeout: float = 5.0) -> Optional[np.ndarray]:
    """Downloads and encodes a thumbnail. Returns None on any failure
    (bad URL, timeout, broken image) so the caller can fail safe rather
    than crash the whole /score request over one bad thumbnail.

    NOTE: this is a synchronous per-video download. Fine for the handful
    of videos that actually reach Stage 3, but if that count grows,
    parallelize with e.g. a thread pool or asyncio + httpx instead.
    """
    try:
        resp = requests.get(url, timeout=timeout)
        resp.raise_for_status()
        image = Image.open(BytesIO(resp.content)).convert("RGB")
    except Exception:
        return None

    model = get_clip_model()
    return model.encode([image], convert_to_numpy=True, normalize_embeddings=True)[0]


def cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b))
