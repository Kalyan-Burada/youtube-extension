// background.js — Session 5 (backend wiring) + Session 8 (intent fusion)
//
// Responsibilities:
//   1. Hold focus topic / currently-watching / last-5-watched in
//      chrome.storage.local (survives service worker restarts, which MV3
//      does periodically — don't rely on in-memory state surviving).
//   2. Batch-score videos that content.js scrapes, by calling the
//      backend's /score endpoint.
//   3. Fail safe: if the backend is unreachable, or no intent has been
//      set yet, every video stays blurred rather than defaulting open.

const BACKEND_URL = "http://localhost:8000"; // move to an options page if you ever deploy the backend elsewhere

const STORAGE_KEYS = {
  FOCUS_TOPIC: "yrf_focus_topic",
  CURRENT_VIDEO: "yrf_current_video", // { id, title }
  RECENT_TITLES: "yrf_recent_titles", // string[], most recent first
};

const MAX_RECENT_TITLES = 5;

async function getFocusTopic() {
  const data = await chrome.storage.local.get(STORAGE_KEYS.FOCUS_TOPIC);
  return data[STORAGE_KEYS.FOCUS_TOPIC] || null;
}

async function setFocusTopic(topic) {
  await chrome.storage.local.set({ [STORAGE_KEYS.FOCUS_TOPIC]: topic || null });
}

async function getCurrentVideo() {
  const data = await chrome.storage.local.get(STORAGE_KEYS.CURRENT_VIDEO);
  return data[STORAGE_KEYS.CURRENT_VIDEO] || null;
}

async function getRecentTitles() {
  const data = await chrome.storage.local.get(STORAGE_KEYS.RECENT_TITLES);
  return data[STORAGE_KEYS.RECENT_TITLES] || [];
}

async function setCurrentVideo(id, title) {
  const previous = await getCurrentVideo();
  // Only push into history once the video actually changes — repeated
  // CURRENT_VIDEO messages for the same video (DOM re-renders, etc.)
  // shouldn't flood the history.
  if (previous && previous.id !== id && previous.title) {
    const recent = await getRecentTitles();
    const updated = [previous.title, ...recent.filter((t) => t !== previous.title)].slice(
      0,
      MAX_RECENT_TITLES
    );
    await chrome.storage.local.set({ [STORAGE_KEYS.RECENT_TITLES]: updated });
  }
  await chrome.storage.local.set({ [STORAGE_KEYS.CURRENT_VIDEO]: { id, title } });
}

async function getIntentSignals() {
  const [focus_topic, current, recent_titles] = await Promise.all([
    getFocusTopic(),
    getCurrentVideo(),
    getRecentTitles(),
  ]);
  return {
    focus_topic: focus_topic || null,
    current_video_title: current ? current.title : null,
    recent_titles,
  };
}

async function scoreVideos(videos) {
  const intent = await getIntentSignals();

  if (!intent.focus_topic && !intent.current_video_title && intent.recent_titles.length === 0) {
    // No intent set yet at all — fail safe rather than guess.
    return videos.map((v) => ({ id: v.id, decision: "blur", score: null, stage: "no_signal" }));
  }

  try {
    const res = await fetch(`${BACKEND_URL}/score`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        intent,
        videos: videos.map((v) => ({
          id: v.id,
          title: v.title,
          thumbnail_url: v.thumbnailUrl || null,
        })),
      }),
    });
    if (!res.ok) throw new Error(`Backend returned ${res.status}`);
    const data = await res.json();
    return data.results;
  } catch (err) {
    console.warn("[YT Relevance Firewall] backend unreachable, failing safe (blur):", err);
    return videos.map((v) => ({ id: v.id, decision: "blur", score: null, stage: "backend_unreachable" }));
  }
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === "SCRAPED_VIDEOS") {
    scoreVideos(message.videos).then((results) => sendResponse({ results }));
    return true; // keep the message channel open for the async response
  }

  if (message.type === "CURRENT_VIDEO") {
    setCurrentVideo(message.id, message.title).then(() => sendResponse({ ok: true }));
    return true;
  }

  if (message.type === "GET_INTENT_SUMMARY") {
    getIntentSignals().then((intent) => sendResponse(intent));
    return true;
  }

  if (message.type === "SET_FOCUS_TOPIC") {
    setFocusTopic(message.topic).then(() => sendResponse({ ok: true }));
    return true;
  }

  return false;
});

console.log("[YT Relevance Firewall] background worker loaded (S5 + S8)");
