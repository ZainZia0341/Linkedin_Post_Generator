const DEFAULT_SETTINGS = {
  backendUrl: "http://localhost:7860",
  apiToken: "",
  enabled: true,
  extensionId: "",
  lastError: "",
  lastTaskAt: "",
  lastHeartbeatAt: ""
};

const POLL_ALARM = "ai-spark-extension-poll";
const VERSION = chrome.runtime.getManifest().version;
let pollTimer = null;
let polling = false;

function createExtensionId() {
  return `chrome-${crypto.randomUUID()}`;
}

async function getSettings() {
  const stored = await chrome.storage.local.get(DEFAULT_SETTINGS);
  if (!stored.extensionId) {
    stored.extensionId = createExtensionId();
    await chrome.storage.local.set({ extensionId: stored.extensionId });
  }
  return stored;
}

async function updateState(values) {
  await chrome.storage.local.set(values);
  chrome.runtime.sendMessage({ type: "STATE_CHANGED", values }).catch(() => undefined);
}

function apiHeaders(settings) {
  const headers = { "Content-Type": "application/json" };
  if (settings.apiToken) headers["X-Extension-Token"] = settings.apiToken;
  return headers;
}

async function apiFetch(settings, path, init = {}) {
  const base = settings.backendUrl.replace(/\/+$/, "");
  const response = await fetch(`${base}${path}`, {
    ...init,
    headers: { ...apiHeaders(settings), ...(init.headers || {}) }
  });
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const body = await response.json();
      detail = body.detail || detail;
    } catch (_) {
      // Keep the HTTP status when the backend did not return JSON.
    }
    throw new Error(detail);
  }
  return response.json();
}

function delay(milliseconds) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

function waitForTab(tabId, timeoutMs = 45000) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => finish(new Error("LinkedIn page load timed out.")), timeoutMs);
    const onUpdated = (updatedTabId, changeInfo) => {
      if (updatedTabId === tabId && changeInfo.status === "complete") finish();
    };
    const onRemoved = (removedTabId) => {
      if (removedTabId === tabId) finish(new Error("The extension scrape tab was closed."));
    };
    const finish = (error) => {
      clearTimeout(timer);
      chrome.tabs.onUpdated.removeListener(onUpdated);
      chrome.tabs.onRemoved.removeListener(onRemoved);
      error ? reject(error) : resolve();
    };
    chrome.tabs.onUpdated.addListener(onUpdated);
    chrome.tabs.onRemoved.addListener(onRemoved);
    chrome.tabs.get(tabId).then((tab) => {
      if (tab.status === "complete") finish();
    }).catch(() => undefined);
  });
}

async function navigate(tabId, url) {
  await chrome.tabs.update(tabId, { url, active: false });
  await waitForTab(tabId);
  await delay(1800);
}

async function askContentScript(tabId, message) {
  let lastError = null;
  for (let attempt = 0; attempt < 5; attempt += 1) {
    try {
      return await chrome.tabs.sendMessage(tabId, message);
    } catch (error) {
      lastError = error;
      await delay(600);
    }
  }
  throw lastError || new Error("Could not reach the LinkedIn extraction script.");
}

async function scrapePosts(tabId, task) {
  const baseUrl = task.profile_url.replace(/\/+$/, "");
  const candidateUrls = [
    `${baseUrl}/recent-activity/all/`,
    `${baseUrl}/recent-activity/shares/`,
    `${baseUrl}/`
  ];
  let lastError = "No visible LinkedIn posts were found for this profile.";
  for (const url of candidateUrls) {
    await navigate(tabId, url);
    const response = await askContentScript(tabId, {
      type: "SCRAPE_POSTS",
      maxPosts: Math.max(1, Number(task.max_posts) || 1)
    });
    if (response?.error) {
      if (response.code === "session_expired_or_challenged") throw new Error(response.error);
      lastError = response.error;
      continue;
    }
    if (Array.isArray(response?.data) && response.data.length) return response.data;
  }
  throw new Error(lastError);
}

async function scrapeProfile(tabId, task) {
  const profileUrl = `${task.profile_url.replace(/\/+$/, "")}/`;
  await navigate(tabId, profileUrl);
  const basic = await askContentScript(tabId, { type: "SCRAPE_PROFILE" });
  if (basic?.error) throw new Error(basic.error);

  await navigate(tabId, `${profileUrl}details/experience/`);
  const experience = await askContentScript(tabId, { type: "SCRAPE_EXPERIENCE" });
  if (experience?.error) throw new Error(experience.error);
  return {
    ...(basic?.data || {}),
    experience: Array.isArray(experience?.data) ? experience.data : [],
    source: "extension",
    fetched_at: new Date().toISOString()
  };
}

async function executeTask(task) {
  const tab = await chrome.tabs.create({ url: "about:blank", active: false });
  try {
    if (task.scrape_type === "posts") return await scrapePosts(tab.id, task);
    if (task.scrape_type === "profile") return await scrapeProfile(tab.id, task);
    throw new Error(`Unsupported scrape type: ${task.scrape_type}`);
  } finally {
    if (tab.id) await chrome.tabs.remove(tab.id).catch(() => undefined);
  }
}

async function reportTask(settings, task, status, data = null, error = "") {
  await apiFetch(settings, `/extension/tasks/${encodeURIComponent(task.task_id)}/result`, {
    method: "POST",
    body: JSON.stringify({
      extension_id: settings.extensionId,
      status,
      data,
      error
    })
  });
}

async function pollBackend() {
  if (polling) return;
  polling = true;
  try {
    const settings = await getSettings();
    if (!settings.enabled) return;
    const query = new URLSearchParams({ extension_id: settings.extensionId, version: VERSION });
    const response = await apiFetch(settings, `/extension/tasks/next?${query.toString()}`);
    await updateState({ lastHeartbeatAt: new Date().toISOString(), lastError: "" });
    if (!response.task) return;

    const task = response.task;
    try {
      const data = await executeTask(task);
      await reportTask(settings, task, "succeeded", data);
      await updateState({ lastTaskAt: new Date().toISOString(), lastError: "" });
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      await reportTask(settings, task, "failed", null, message).catch(() => undefined);
      await updateState({ lastTaskAt: new Date().toISOString(), lastError: message });
    }
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    await updateState({ lastError: message });
  } finally {
    polling = false;
    scheduleFastPoll();
  }
}

function scheduleFastPoll() {
  if (pollTimer) clearTimeout(pollTimer);
  pollTimer = setTimeout(() => pollBackend(), 3000);
}

chrome.runtime.onInstalled.addListener(async () => {
  await getSettings();
  await chrome.alarms.create(POLL_ALARM, { periodInMinutes: 0.5 });
  pollBackend();
});

chrome.runtime.onStartup.addListener(async () => {
  await chrome.alarms.create(POLL_ALARM, { periodInMinutes: 0.5 });
  pollBackend();
});

chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === POLL_ALARM) pollBackend();
});

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type === "CHECK_NOW") {
    pollBackend().then(() => sendResponse({ ok: true }));
    return true;
  }
  if (message?.type === "SET_ENABLED") {
    updateState({ enabled: Boolean(message.enabled) })
      .then(() => pollBackend())
      .then(() => sendResponse({ ok: true }));
    return true;
  }
  if (message?.type === "GET_STATE") {
    getSettings().then((settings) => sendResponse(settings));
    return true;
  }
  return false;
});

getSettings().then(() => chrome.alarms.create(POLL_ALARM, { periodInMinutes: 0.5 }));
pollBackend();
