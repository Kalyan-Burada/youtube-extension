// popup.js — Session 10
//
// Talks to background.js (never to the backend directly for intent data —
// background.js owns that state) except for the /health check, which is
// just a UI nicety so "everything is blurred" doesn't look unexplained.

const BACKEND_URL = "http://localhost:8000";

const focusInput = document.getElementById("focusInput");
const saveBtn = document.getElementById("saveBtn");
const rescanBtn = document.getElementById("rescanBtn");
const currentVideoEl = document.getElementById("currentVideo");
const recentTitlesEl = document.getElementById("recentTitles");
const statusDot = document.getElementById("statusDot");
const statusText = document.getElementById("statusText");
const toggleExtension = document.getElementById("toggleExtension");

function sendMessage(message) {
  return new Promise((resolve) => chrome.runtime.sendMessage(message, resolve));
}

// Re-scan every open YouTube tab so a focus/topic change re-blurs and
// re-scores tiles that were already decided under the OLD intent. Without
// this, changing the focus topic leaves previously-allowed tiles sharp until
// the user manually rescans — which looks exactly like "the filter is broken".
async function rescanAllYouTubeTabs() {
  const tabs = await chrome.tabs.query({ url: ["*://*.youtube.com/*"] });
  await Promise.all(
    tabs.map(
      (tab) =>
        new Promise((resolve) => {
          try {
            chrome.tabs.sendMessage(tab.id, { type: "RESCAN" }, () => {
              void chrome.runtime.lastError; // tab without the content script yet — ignore
              resolve();
            });
          } catch {
            resolve();
          }
        })
    )
  );
}

async function loadSettings() {
  const data = await chrome.storage.local.get("yrf_extension_enabled");
  // Default to true if not set
  toggleExtension.checked = data.yrf_extension_enabled !== false;
}

toggleExtension.addEventListener("change", async () => {
  const enabled = toggleExtension.checked;
  await chrome.storage.local.set({ yrf_extension_enabled: enabled });
  // Unblur (off) or re-blur+re-score (on) instantly across open YouTube tabs.
  await rescanAllYouTubeTabs();
});

async function loadIntentSummary() {
  const intent = await sendMessage({ type: "GET_INTENT_SUMMARY" });
  if (!intent) return;
  focusInput.value = intent.focus_topic || "";
  currentVideoEl.textContent = intent.current_video_title || "—";
  recentTitlesEl.textContent =
    intent.recent_titles && intent.recent_titles.length
      ? intent.recent_titles.join(", ")
      : "—";
}

async function checkBackendHealth() {
  try {
    const res = await fetch(`${BACKEND_URL}/health`);
    if (!res.ok) throw new Error(`status ${res.status}`);
    statusDot.className = "dot ok";
    statusText.textContent = "Backend online";
  } catch {
    statusDot.className = "dot bad";
    statusText.textContent = "Backend offline — everything stays blurred";
  }
}

saveBtn.addEventListener("click", async () => {
  const topic = focusInput.value.trim();
  await sendMessage({ type: "SET_FOCUS_TOPIC", topic: topic || null });
  // Immediately re-filter open YouTube tabs with the new topic.
  await rescanAllYouTubeTabs();
  saveBtn.textContent = "Saved ✓";
  setTimeout(() => (saveBtn.textContent = "Save focus topic"), 1200);
});

rescanBtn.addEventListener("click", async () => {
  await rescanAllYouTubeTabs();
  rescanBtn.textContent = "Rescanning…";
  setTimeout(() => (rescanBtn.textContent = "Rescan this page"), 1000);
});

loadSettings();
loadIntentSummary();
checkBackendHealth();
