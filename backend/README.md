# Backend

## Setup

```bash
cd backend
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

First run downloads three models — `all-mpnet-base-v2` (~420MB),
`cross-encoder/ms-marco-MiniLM-L-6-v2` (~90MB), and `clip-ViT-B-32`
(~600MB). All are cached locally after that.

## Run

```bash
uvicorn app.main:app --reload --port 8000
```

## Test it

```bash
curl http://localhost:8000/health
```

```bash
curl -X POST http://localhost:8000/score \
  -H "Content-Type: application/json" \
  -d '{
    "intent": { "focus_topic": "Machine Learning" },
    "videos": [
      { "id": "v1", "title": "PyTorch Tutorial for Beginners" },
      { "id": "v2", "title": "Neural Network Explained Simply" },
      { "id": "v3", "title": "IPL Highlights Today" }
    ]
  }'
```

Response now includes which stage resolved each video:

```json
{
  "results": [
    { "id": "v1", "score": 0.61, "decision": "allow", "stage": "embedding" },
    { "id": "v2", "score": 0.58, "decision": "allow", "stage": "embedding" },
    { "id": "v3", "score": 0.08, "decision": "blur",  "stage": "embedding" }
  ]
}
```

A title that lands in the 0.25–0.50 band won't resolve at the embedding
stage — it'll show `"stage": "cross_encoder"` or `"stage": "vision"`
instead, depending on how far down the cascade it had to go.

## The cascade (app/main.py)

```
Stage 1: SentenceTransformer cosine similarity   (every video, cheap)
              │
   score ≥ EMBED_ALLOW_THRESHOLD  → allow
   score <  EMBED_BLUR_THRESHOLD  → blur
   else                            ↓
Stage 2: CrossEncoder rerank        (only the borderline band)
              │
   ≥ CROSS_ALLOW_THRESHOLD → allow
   <  CROSS_BLUR_THRESHOLD → blur
   else                     ↓
Stage 3: CLIP vision on thumbnail   (only what's still unresolved)
              │
   ≥ CLIP_ALLOW_THRESHOLD → allow
   else                    → blur (fail-safe default)
```

All thresholds live in `app/config.py` — nowhere else. Don't hand-edit a
number in `main.py`; it'll drift from what `calibrate.py` is testing
against.

## Calibration

```bash
python3 calibrate.py
```

Runs `calibration_set.json` (40 labeled examples across 8 unrelated
domains: python, cricket, cooking, medicine, anime, history, music,
finance) through Stages 1–2 and prints per-domain accuracy. Use this —
not intuition — to decide whether `EMBED_*`/`CROSS_*` thresholds need
moving. Stage 3 (vision) isn't covered by this set since it needs real
thumbnail URLs; that calibration pass comes once the extension has
actually scraped some real videos.

## Files

- `app/main.py` — FastAPI app, `/health` and `/score`, orchestrates the cascade
- `app/config.py` — every threshold, in one place
- `app/models.py` — request/response schemas
- `app/embeddings.py` — SentenceTransformer loading, encoding, weighted intent embedding
- `app/cross_encoder.py` — Stage 2 reranking
- `app/vision.py` — Stage 3 CLIP text + image encoding
- `app/cache.py` — SQLite cache for video + intent embeddings
- `calibrate.py` / `calibration_set.json` — Stage 1–2 accuracy harness
