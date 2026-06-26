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

  function scrapeVisibleVideos() {
    const found = [];

    // Find all YouTube watch links, avoiding shorts
    const links = document.querySelectorAll("a[href*='/watch?v=']");

    links.forEach((link) => {
      // Traverse up to the main video tile
      const container = link.closest("ytd-rich-item-renderer, ytd-video-renderer, ytd-compact-video-renderer, ytd-grid-video-renderer");
      
      // Skip if not a video tile, or if we've already scored/processed it
      if (!container || container.hasAttribute(PROCESSED_ATTR)) {
        return;
      }

      // Title is usually inside an element with 'video-title', or we use the aria-label
      const titleEl = container.querySelector("[id*='video-title']");
      let title = titleEl ? titleEl.textContent.trim() : "";
      if (!title) {
        title = link.getAttribute("title") || link.getAttribute("aria-label") || "";
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
        title: el.querySelector("[id*=video-title]")?.textContent?.trim(),
      })),
    blurAll: () => videoRegistry.forEach(blurElement),
    unblurAll: () => videoRegistry.forEach(unblurElement),
    applyDecisions,
    getIntent: () => new Promise((resolve) => chrome.runtime.sendMessage({ type: "GET_INTENT_SUMMARY" }, resolve)),
    setFocus: (topic) => new Promise((resolve) => chrome.runtime.sendMessage({ type: "SET_FOCUS_TOPIC", topic }, resolve)),
  };

  console.log("[YT Relevance Firewall] content script loaded (S4+S5+S8) — try __yrf.listVideos()");
})();
