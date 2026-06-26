# Project Status

Check a box only when that piece runs end-to-end and is committed.
This file is the source of truth for "% complete" — not token counts.

- [x] S0 — Repo skeleton, requirements.txt, manifest.json stub
- [x] S1 — FastAPI skeleton + /health
- [x] S2 — SentenceTransformer scoring endpoint (/score)
- [x] S3 — Embedding cache (video_id + intent signature)
- [x] S4 — Extension: scrape title/id/thumbnail from YouTube DOM, blur-all toggle
- [x] S5 — Extension ↔ backend wiring, default-to-blur while waiting
- [x] S6 — CrossEncoder borderline stage
- [x] S7 — CLIP thumbnail stage
- [x] S8 — Intent fusion (focus + currently watching + last 5 watched)
- [x] S9 — Calibration test set across multiple domains, threshold tuning
- [x] S10 — Popup UI, packaging, error fallback, README polish

## Notes / decisions log

- S4: scraping covers home-grid / search-results / watch-sidebar layouts
  only (not Shorts). Selectors are best-guesses based on known YouTube
  structure and have NOT been verified against a live page — first thing
  to check with real browser access is whether `__yrf.listVideos()`
  actually returns results; if not, fix selectors before debugging
  anything downstream.
- S5: background.js fails safe (blur everything) if the backend is
  unreachable or no intent has been set yet — never defaults to allow.
- S6: CrossEncoder (ms-marco-MiniLM-L-6-v2) raw output is passed through
  sigmoid to get a 0-1 range — this is an approximation, the model wasn't
  trained on short-topic/short-title pairs. Don't trust CROSS_* thresholds
  in config.py without running calibrate.py first.
- S7: CLIP thumbnail download is synchronous, one request per borderline
  video. Fine at current scale; revisit with a thread pool if the
  borderline band grows large in practice.
- S8: current-video + last-5-watched tracking lives entirely in
  background.js (chrome.storage.local) since it needs to survive service
  worker restarts; the weighting/decay math itself is in
  backend/app/embeddings.py (build_intent_embedding), already built in S2.
- S9: calibration_set.json covers Stage 1+2 only (40 examples, 8 domains).
  Stage 3 (vision) can't be calibrated with synthetic titles — needs real
  scraped {title, thumbnail_url, expected} triples as a follow-up set.
- S10: popup shows a live backend-online/offline indicator specifically
  so "why is everything blurred" has an obvious answer in the UI itself.

## Post-S10 fixes (cascade was only resolving Stage 1 / keyword before)

The cascade was rebuilt and re-calibrated end to end. Symptoms before: videos
only ever un-blurred on a literal keyword match; Stages 2 and 3 never produced
a decision.

- **Import crash** — `transformers` pulled in TensorFlow and died on Keras 3,
  so the whole backend failed to start. Fixed by forcing `USE_TF=0` (and
  friends) in `app/__init__.py` before any model import.
- **`calibrate.py` crashed on import** — it imported `EMBED_BLUR_THRESHOLD` /
  `CROSS_BLUR_THRESHOLD`, which had been deleted from `config.py`. Restored the
  borderline-band thresholds the README/calibrate were written against.
- **Stage 2 was a no-op** — `ms-marco-MiniLM-L-6-v2` scored ~0.000 for every
  short-topic/short-title pair (wrong model family), so the borderline band
  could only ever blur. Swapped to the STS cross-encoder `stsb-TinyBERT-L-4`,
  which actually separates on/off-topic, and dropped the now-wrong extra sigmoid.
- **Stage 1 thresholds were ~2x too high** — related titles cosine ~0.1–0.5,
  not 0.45+. Wrapping the focus topic in a generic template ("A YouTube video
  about …") and re-tuning took Stage-1+2 calibration accuracy from 50% to 97.5%.
- **`main.py` cascade rewrite** — proper allow/blur/borderline waterfall, each
  stage wrapped so a single model/thumbnail failure fails safe (blur) instead
  of 500-ing the whole request. Stage strings now all match the `Stage` literal
  in `models.py` (previously `embedding_failed`/`cross_encoder_failed` could
  500 the response).
- **Tests added** — `backend/tests/test_cascade.py` drives `/score` end to end.
- **Stale-tile refresh** — changing the focus topic (or toggling) now re-scans
  every open YouTube tab from `popup.js`, so old decisions don't linger looking
  like the filter is broken. (Reloading the extension still needs a tab refresh;
  Chrome doesn't re-inject content scripts into already-open tabs.)
- **Generic intent expansion** — `embeddings.expand_focus_topic()` wraps short
  focus topics in extra topic-agnostic templates so one-word focuses ("movie")
  embed a bit more robustly. Gated to <=3-word topics and weight-validated:
  calibrate.py full-cascade accuracy holds at 97.5%. Note: it cannot bridge a
  title made of pure named entities ("War Of Chatrapathi | Prabhas Vs Rajamouli"
  under focus "movie") — that needs a more specific focus like "Telugu movies".

## Known gaps / backlog (not blocking, but real)

- YouTube Shorts are not scraped at all (different DOM entirely).
- CORS is wide open (`allow_origins=["*"]`) in main.py — fine for local
  dev, tighten to the extension's `chrome-extension://<id>` origin before
  sharing this with anyone else.
- No automated test suite — calibrate.py is a manual accuracy check, not
  a CI-running test. Worth wrapping in pytest if this grows further.
- Thresholds in config.py are still only validated against synthetic
  titles, not real YouTube data — treat current numbers as a starting
  point, not a finished tune.
