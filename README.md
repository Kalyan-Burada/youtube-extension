# YouTube Relevance Firewall

A browser extension that blurs YouTube videos unrelated to whatever the
user is currently focused on — without any hand-written keyword lists or
per-topic category dictionaries.

## How it works

```
Intent signals (focus topic / current video / recent history)
        │
        ▼
 SentenceTransformer cosine similarity   (Stage 1 — every video)
        │
   high/low confidence → done
   borderline           ↓
 CrossEncoder rerank                     (Stage 2 — borderline only)
        │
   high/low confidence → done
   still borderline     ↓
 CLIP vision on thumbnail                (Stage 3 — last resort)
        │
        ▼
   allow / blur  (default: blur, never default-open)
```

Every threshold lives in `backend/app/config.py` and gets validated by
`backend/calibrate.py` against a labeled set spanning 8 unrelated domains
— not hand-tuned by eye.

## Repo layout

```
backend/      FastAPI service that does the scoring
extension/    Chrome extension (Manifest V3)
PROJECT_STATUS.md   Checklist-based progress tracker
```

## Run it end to end

1. **Backend** — see `backend/README.md`. Get `/health` returning `ok`
   before touching the extension.
2. **Extension** — `chrome://extensions` → Developer mode → Load unpacked
   → select `extension/`.
3. Open YouTube, click the extension icon, set a focus topic (e.g.
   "Machine Learning"), hit "Rescan this page".
4. Videos that match your topic should sharpen within ~1 second; everything
   else stays blurred.

If nothing ever sharpens: open devtools on the YouTube tab and check
`__yrf.listVideos()` — if that's empty, YouTube's DOM has likely drifted
from the selectors in `extension/content.js` and those need updating
first (see comments at the top of that file).

## Package for distribution

```bash
cd extension
./package.sh
```

Produces `yt-relevance-firewall-extension.zip` containing just the
extension files (no backend, no repo metadata).
