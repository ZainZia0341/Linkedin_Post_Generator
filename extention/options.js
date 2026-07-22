const DEFAULT_SETTINGS = {
  backendUrl: "http://localhost:7860",
  userId: "test-user-1",
  apiToken: ""
};

const backendUrl = document.getElementById("backendUrl");
const userId = document.getElementById("userId");
const apiToken = document.getElementById("apiToken");
const message = document.getElementById("message");
const save = document.getElementById("save");
const testConnection = document.getElementById("testConnection");

function normalizedUrl(value) {
  return value.trim().replace(/\/+$/, "");
}

async function load() {
  const settings = await chrome.storage.local.get(DEFAULT_SETTINGS);
  backendUrl.value = settings.backendUrl;
  userId.value = settings.userId;
  apiToken.value = settings.apiToken;
}

async function persist() {
  const url = normalizedUrl(backendUrl.value);
  if (!/^https?:\/\//i.test(url)) throw new Error("Enter a complete HTTP or HTTPS backend URL.");
  const owner = userId.value.trim();
  if (!owner) throw new Error("Enter the application user ID.");
  await chrome.storage.local.set({ backendUrl: url, userId: owner, apiToken: apiToken.value.trim() });
  return { backendUrl: url, userId: owner, apiToken: apiToken.value.trim() };
}

async function check(settings) {
  const headers = settings.apiToken ? { "X-Extension-Token": settings.apiToken } : {};
  const query = new URLSearchParams({ user_id: settings.userId });
  const response = await fetch(`${settings.backendUrl}/extension/status?${query}`, { headers });
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const body = await response.json();
      detail = body.detail || detail;
    } catch (_) {
      // Use the HTTP status text.
    }
    throw new Error(detail);
  }
  return response.json();
}

save.addEventListener("click", async () => {
  message.textContent = "";
  try {
    await persist();
    await chrome.runtime.sendMessage({ type: "CHECK_NOW" });
    message.textContent = "Settings saved.";
  } catch (error) {
    message.textContent = error instanceof Error ? error.message : String(error);
    message.style.color = "#b42318";
  }
});

testConnection.addEventListener("click", async () => {
  message.textContent = "Checking...";
  message.style.color = "#627086";
  try {
    const settings = await persist();
    await check(settings);
    message.textContent = "Backend reached successfully.";
    message.style.color = "#16885f";
  } catch (error) {
    message.textContent = error instanceof Error ? error.message : String(error);
    message.style.color = "#b42318";
  }
});

load();
