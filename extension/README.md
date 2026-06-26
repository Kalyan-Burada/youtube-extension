# Extension — testing Session 4

No backend calls yet (that's Session 5). Today's only goal: prove the
scraper finds real video tiles and the blur class actually applies/removes.

## Load it

1. `chrome://extensions`
2. Toggle "Developer mode" (top right)
3. "Load unpacked" → select the `extension/` folder
4. Open `https://www.youtube.com` (home page or search results)

## Manual test (devtools console, on the YouTube tab)

```js
__yrf.listVideos()
```
Should print an array of `{ id, title }` for every video tile currently on
screen. If it returns `[]`, YouTube's DOM changed — inspect a video tile
and update the `LAYOUTS` selectors at the top of `content.js`.

Everything should already look blurred on page load (that's the fail-safe
default — every scraped tile is blurred immediately, before any scoring
exists). To confirm blur/unblur itself works independently of scraping:

```js
__yrf.unblurAll()   // every found tile should sharpen
__yrf.blurAll()     // and re-blur
```

Scroll down to load more videos, then run `__yrf.listVideos()` again — the
count should grow. That confirms the MutationObserver is catching
YouTube's infinite scroll, not just the initial page load.

Click into a video, then click "back" — run `__yrf.listVideos()` once
more. If it returns stale/duplicate entries, the `yt-navigate-finish`
reset isn't firing correctly for that navigation path; flag it in
`PROJECT_STATUS.md` notes rather than debugging deeply today — Session 5
will be touching this same navigation logic anyway when it adds the
"currently watching" signal.

## What's intentionally NOT done yet

- No network calls to the backend (S5)
- No real allow/blur decisions — `applyDecisions()` exists and is wired to
  the registry, but nothing calls it yet except your manual console tests
- Shorts shelf is not scraped (different DOM entirely — backlog item, not
  blocking)
