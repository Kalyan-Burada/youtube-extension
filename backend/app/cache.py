import hashlib
import sqlite3
from pathlib import Path
from threading import Lock
from typing import Optional

import numpy as np

DB_PATH = Path(__file__).parent.parent / "cache.db"
_lock = Lock()


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS video_embeddings (
            video_id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            embedding BLOB NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS intent_cache (
            signature TEXT PRIMARY KEY,
            embedding BLOB NOT NULL
        )
        """
    )
    conn.commit()
    return conn


def _to_blob(vec: np.ndarray) -> bytes:
    return vec.astype(np.float32).tobytes()


def _from_blob(blob: bytes) -> np.ndarray:
    return np.frombuffer(blob, dtype=np.float32)


def make_signature(*parts: str) -> str:
    """Stable hash of the intent inputs, used as a cache key.

    Recomputing the intent embedding is the only thing that should happen
    on every change of focus topic / current video / history — everything
    else should hit the cache.
    """
    joined = "||".join(parts)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


class EmbeddingCache:
    def __init__(self):
        self.conn = _get_conn()

    # --- video titles never change for a given video_id, so a cache hit ---
    # --- means "never re-embed this video again" -----------------------
    def get_video_embedding(self, video_id: str, title: str) -> Optional[np.ndarray]:
        with _lock:
            row = self.conn.execute(
                "SELECT title, embedding FROM video_embeddings WHERE video_id = ?",
                (video_id,),
            ).fetchone()
        if row and row[0] == title:
            return _from_blob(row[1])
        return None

    def set_video_embedding(self, video_id: str, title: str, embedding: np.ndarray) -> None:
        with _lock:
            self.conn.execute(
                "INSERT OR REPLACE INTO video_embeddings (video_id, title, embedding) "
                "VALUES (?, ?, ?)",
                (video_id, title, _to_blob(embedding)),
            )
            self.conn.commit()

    # --- intent embedding is recomputed only when the signature (focus ---
    # --- topic + current video + history) actually changes ---------------
    def get_intent_embedding(self, signature: str) -> Optional[np.ndarray]:
        with _lock:
            row = self.conn.execute(
                "SELECT embedding FROM intent_cache WHERE signature = ?",
                (signature,),
            ).fetchone()
        return _from_blob(row[0]) if row else None

    def set_intent_embedding(self, signature: str, embedding: np.ndarray) -> None:
        with _lock:
            self.conn.execute(
                "INSERT OR REPLACE INTO intent_cache (signature, embedding) VALUES (?, ?)",
                (signature, _to_blob(embedding)),
            )
            self.conn.commit()
