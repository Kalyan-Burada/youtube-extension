# Extension

Manifest V3 Chrome extension. Scrapes video tiles on YouTube, asks the
backend (`http://localhost:8000/score`) whether each is relevant to your
current focus, and blurs everything that isn't. Fails safe: a tile stays
blurred until the backend explicitly says "allow", so an offline backend or
unset focus topic means everything stays blurred — never default-open.

## Load it

1. Start the backend first (see `../backend/README.md`) — `/health` should
   return `ok`.
2. `chrome://extensions` → toggle **Developer mode** (top right).
3. **Load unpacked** → select this `extension/` folder.
4. Open `https://www.youtube.com`, click the extension icon, set a focus
   topic (e.g. "Machine Learning"), then **Rescan this page**.

Relevant videos sharpen within ~1s; everything else stays blurred.

## Popup

- **Focus topic** — the main intent signal. Saved to `chrome.storage.local`.
- **Rescan this page** — re-scrapes and re-scores the current tab.
- **On/Off toggle** — off un-blurs everything and pauses scoring.
- **Backend indicator** — green = online, red = offline (and so everything
  stays blurred, which is why the dot is there: it explains the blur).

## Debugging (devtools console on the YouTube tab)

```js
__yrf.listVideos()      // every tracked tile as { id, title }
__yrf.unblurAll()       // sharpen all (sanity-check the blur class)
__yrf.blurAll()         // re-blur all
__yrf.setFocus("Music") // set focus topic without the popup
```

If `__yrf.listVideos()` returns `[]`, YouTube's DOM drifted from the
selectors at the top of `content.js` — inspect a tile and update them.
Nothing downstream needs to change.

## Package for distribution

```bash
./package.sh   # -> ../yt-relevance-firewall-extension.zip
```

## Not handled

- Shorts shelf (different DOM entirely) — backlog, not blocking.
