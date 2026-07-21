const enabled = document.getElementById("enabled");
const statusDot = document.getElementById("statusDot");
const statusLabel = document.getElementById("statusLabel");
const backendUrl = document.getElementById("backendUrl");
const lastHeartbeat = document.getElementById("lastHeartbeat");
const lastTask = document.getElementById("lastTask");
const lastError = document.getElementById("lastError");
const checkNow = document.getElementById("checkNow");
const openOptions = document.getElementById("openOptions");

function formatTime(value) {
  if (!value) return "Never";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString();
}

function isRecent(value) {
  if (!value) return false;
  const parsed = new Date(value);
  return !Number.isNaN(parsed.getTime()) && Date.now() - parsed.getTime() < 60000;
}

function render(settings) {
  enabled.checked = Boolean(settings.enabled);
  backendUrl.textContent = settings.backendUrl || "Not configured";
  lastHeartbeat.textContent = formatTime(settings.lastHeartbeatAt);
  lastTask.textContent = formatTime(settings.lastTaskAt);

  statusDot.className = "status-dot";
  if (!settings.enabled) {
    statusLabel.textContent = "Disabled";
  } else if (settings.lastError) {
    statusLabel.textContent = "Needs attention";
    statusDot.classList.add("error");
  } else if (isRecent(settings.lastHeartbeatAt)) {
    statusLabel.textContent = "Connected";
    statusDot.classList.add("connected");
  } else {
    statusLabel.textContent = "Waiting for backend";
  }

  lastError.textContent = settings.lastError || "";
  lastError.classList.toggle("hidden", !settings.lastError);
}

async function loadState() {
  const state = await chrome.runtime.sendMessage({ type: "GET_STATE" });
  render(state || {});
}

enabled.addEventListener("change", async () => {
  await chrome.runtime.sendMessage({ type: "SET_ENABLED", enabled: enabled.checked });
  await loadState();
});

checkNow.addEventListener("click", async () => {
  checkNow.disabled = true;
  checkNow.textContent = "Checking...";
  try {
    await chrome.runtime.sendMessage({ type: "CHECK_NOW" });
    await loadState();
  } finally {
    checkNow.disabled = false;
    checkNow.textContent = "Check now";
  }
});

openOptions.addEventListener("click", () => chrome.runtime.openOptionsPage());
chrome.runtime.onMessage.addListener((message) => {
  if (message?.type === "STATE_CHANGED") loadState();
});

loadState();
