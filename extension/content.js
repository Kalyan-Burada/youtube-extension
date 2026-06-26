// content.js — Session 4 (scraping) + Session 5 (backend wiring) +
// Session 8 (currently-watching detection)
//
// KNOWN FRAGILITY: YouTube's DOM/class names change over time and differ
// by page (home feed, search, watch-page sidebar, Shorts). The LAYOUTS
// list below covers the three most common non-Shorts layouts as of
// mid-2026. If __yrf.listVideos() returns [], inspect a real video tile
// in devtools and update the selectors here — nothing else in the
// pipeline needs to change.

(function () {
  const PROCESSED_ATTR = "data-yrf-processed";
  const VIDEO_ID_ATTR = "data-yrf-id";

  const LAYOUTS = [
    { name: "home-grid", container: "ytd-rich-item-renderer, ytd-grid-video-renderer", link: "a#thumbnail", title: "[id*='video-title']" },
    { name: "search-results", container: "ytd-video-renderer", link: "a#thumbnail", title: "[id*='video-title']" },
    { name: "watch-sidebar", container: "ytd-compact-video-renderer", link: "a#thumbnail", title: "[id*='video-title']" },
  ];

  // videoId -> DOM element. Cleared on SPA navigation since YouTube reuses
  // its document without a full page reload.
  const videoRegistry = new Map();
  let lastReportedVideoId = null;

  function extractVideoId(href) {
    if (!href) return null;
    try {
      const url = new URL(href, window.location.origin);
      return url.searchParams.get("v");
    } catch {
      return null;
    }
  }

  function blurElement(el) {
    el.classList.add("yt-relevance-blur");
  }

  function unblurElement(el) {
    el.classList.remove("yt-relevance-blur");
  }

  // Every container type that wraps a single video tile across YouTube's
  // layouts. Order doesn't matter — closest() walks up to the nearest match.
  //  - ytd-rich-item-renderer / ytd-grid-video-renderer : home feed
  //  - ytd-video-renderer                                : search results
  //  - ytd-compact-video-renderer                        : watch-page sidebar (classic)
  //  - yt-lockup-view-model                              : NEW unified tile used in
  //    the watch sidebar / "Up next" and rolling out elsewhere
  const TILE_CONTAINERS =
    "ytd-rich-item-renderer, ytd-video-renderer, ytd-compact-video-renderer, " +
    "ytd-grid-video-renderer, yt-lockup-view-model";

  // Tag-name patterns for a single video tile. Used as a fallback when the
  // exact container above isn't matched, so a YouTube DOM rename (e.g. the
  // watch sidebar moving to yt-lockup-view-model, or any future *-renderer)
  // doesn't silently leave a whole section unfiltered.
  const TILE_TAG_PATTERN = /lockup|compact-video|video-renderer|rich-item|grid-video|playlist-video/;

  // The closest ancestor that represents ONE video tile. Walks up from the
  // link: exact known containers first, then any custom element whose tag
  // looks like a tile. Capped in depth so we never blur a whole shelf/column.
  function findTile(link) {
    const known = link.closest(TILE_CONTAINERS);
    if (known) return known;
    let el = link.parentElement;
    for (let depth = 0; el && depth < 12; depth++, el = el.parentElement) {
      if (TILE_TAG_PATTERN.test(el.tagName.toLowerCase())) return el;
    }
    return null;
  }

  function scrapeVisibleVideos() {
    const found = [];

    // Find all YouTube watch links, avoiding shorts
    const links = document.querySelectorAll("a[href*='/watch?v=']");

    links.forEach((link) => {
      // Traverse up to the main video tile (exact match, then pattern fallback)
      const container = findTile(link);

      // Skip if not a video tile, or if we've already scored/processed it
      if (!container || container.hasAttribute(PROCESSED_ATTR)) {
        return;
      }

      // Title location varies by layout. Try the classic id-based node, then
      // the new lockup title node, then fall back to the link's own
      // title/aria-label/text so a new layout never silently yields "".
      const titleEl = container.querySelector(
        "[id*='video-title'], .yt-lockup-metadata-view-model__title, " +
          "[class*='lockup'][class*='title'], h3 a"
      );
      let title = titleEl ? titleEl.textContent.trim() : "";
      if (!title) {
        title =
          link.getAttribute("title") ||
          link.getAttribute("aria-label") ||
          link.textContent.trim() ||
          "";
      }

      const href = link.href || link.getAttribute("href");
      const videoId = extractVideoId(href);

      const thumbEl = container.querySelector("img");
      const thumbnailUrl = thumbEl ? thumbEl.src : null;

      if (!videoId || !title) {
        // Has not fully hydrated in the DOM. Wait for next mutation.
        return;
      }

      container.setAttribute(PROCESSED_ATTR, "1");
      container.setAttribute(VIDEO_ID_ATTR, videoId);
      videoRegistry.set(videoId, container);
      blurElement(container); // immediately blur

      found.push({ id: videoId, title, thumbnailUrl });
    });

    return found;
  }

  function getCurrentVideoIdFromUrl() {
    const url = new URL(window.location.href);
    return url.pathname === "/watch" ? url.searchParams.get("v") : null;
  }

  function getCurrentVideoTitle() {
    const el = document.querySelector(
      "h1.ytd-watch-metadata yt-formatted-string, #title h1"
    );
    return el ? el.textContent.trim() : null;
  }

  function reportCurrentVideoIfChanged() {
    const id = getCurrentVideoIdFromUrl();
    if (!id || id === lastReportedVideoId) return;
    const title = getCurrentVideoTitle();
    if (!title) return; // title may not have hydrated yet; next tick retries
    lastReportedVideoId = id;
    safeSendMessage({ type: "CURRENT_VIDEO", id, title });
  }

  // chrome.runtime.sendMessage throws if the extension context was
  // invalidated (e.g. mid-reload) — never let that break the page itself.
  function safeSendMessage(message, callback) {
    try {
      chrome.runtime.sendMessage(message, callback);
    } catch (err) {
      console.warn("[YT Relevance Firewall] could not reach background:", err);
    }
  }

  function applyDecisions(decisions) {
    decisions.forEach(({ id, decision }) => {
      const el = videoRegistry.get(id);
      if (!el) return;
      if (decision === "allow") {
        unblurElement(el);
      } else {
        // "blur" and "borderline" both stay blurred — fail safe, not open.
        blurElement(el);
      }
    });
  }

  let scanScheduled = false;
  function scheduleScan() {
    if (scanScheduled) return;
    scanScheduled = true;
    setTimeout(async () => {
      scanScheduled = false;

      // Check if extension is toggled ON
      const prefs = await chrome.storage.local.get("yrf_extension_enabled");
      if (prefs.yrf_extension_enabled === false) {
        // Unblur everything on the page and pause scraping until toggled back on
        document.querySelectorAll(".yt-relevance-blur").forEach((el) => {
          el.classList.remove("yt-relevance-blur");
        });
        return;
      }

      reportCurrentVideoIfChanged();

      const videos = scrapeVisibleVideos();
      if (videos.length === 0) return;

      console.log(`[YT Relevance Firewall] scraped ${videos.length} new video(s)`);
      safeSendMessage({ type: "SCRAPED_VIDEOS", videos }, (response) => {
        if (response && response.results) {
          applyDecisions(response.results);
        }
        // If response is undefined, background didn't answer (e.g. it
        // restarted mid-call) — tiles just stay blurred until next scan.
      });
    }, 300);
  }

  const observer = new MutationObserver(() => scheduleScan());
  observer.observe(document.body, { childList: true, subtree: true });

  // YouTube is an SPA — navigating between pages doesn't reload this
  // script, it fires this custom event instead. Reset and rescan.
  document.addEventListener("yt-navigate-finish", () => {
    document.querySelectorAll(`[${PROCESSED_ATTR}]`).forEach((el) =>
      el.removeAttribute(PROCESSED_ATTR)
    );
    videoRegistry.clear();
    scheduleScan();
  });

  // Manual rescan, triggered from the popup's "Rescan this page" button.
  chrome.runtime.onMessage.addListener((message) => {
    if (message.type === "RESCAN") {
      document.querySelectorAll(`[${PROCESSED_ATTR}]`).forEach((el) =>
        el.removeAttribute(PROCESSED_ATTR)
      );
      videoRegistry.clear();
      scheduleScan();
    }
  });

  scheduleScan();

  // --- Manual debug hooks (still useful even with the popup UI) ---------
  window.__yrf = {
    listVideos: () =>
      Array.from(videoRegistry.entries()).map(([id, el]) => ({
        id,
        title: el
          .querySelector(
            "[id*='video-title'], .yt-lockup-metadata-view-model__title, [class*='lockup'][class*='title'], h3 a"
          )
          ?.textContent?.trim(),
      })),
    blurAll: () => videoRegistry.forEach(blurElement),
    unblurAll: () => videoRegistry.forEach(unblurElement),
    applyDecisions,
    getIntent: () => new Promise((resolve) => chrome.runtime.sendMessage({ type: "GET_INTENT_SUMMARY" }, resolve)),
    setFocus: (topic) => new Promise((resolve) => chrome.runtime.sendMessage({ type: "SET_FOCUS_TOPIC", topic }, resolve)),
    // Diagnostic: for every watch link on the page, report whether a tile
    // container was found and the chain of ancestor tag names. Run
    // __yrf.probe() in the console and share the output if a section (e.g. the
    // sidebar) isn't being blurred — it pinpoints the real container tag.
    probe: () =>
      Array.from(document.querySelectorAll("a[href*='/watch?v=']"))
        .slice(0, 12)
        .map((link) => {
          const tile = findTile(link);
          const chain = [];
          let el = link;
          for (let i = 0; el && i < 8; i++, el = el.parentElement) chain.push(el.tagName.toLowerCase());
          return { matched: tile ? tile.tagName.toLowerCase() : null, ancestors: chain.join(" < ") };
        }),
  };

  console.log("[YT Relevance Firewall] content script loaded (S4+S5+S8) — try __yrf.listVideos()");
})();
