import type {
  ActivityResponse,
  BulkCreatorImportResponse,
  BulkCreatorPreviewResponse,
  CommentedActivityResponse,
  CommentResponse,
  CreatorProfileDetailsResponse,
  CreatorResponse,
  DeleteResponse,
  RecentActivitiesResponse,
  RecentScrapeCreatorsResponse,
  ScrapeCreatorProfilesResponse,
  ThreadResponse,
  ThreadSummary,
  UserDataResponse,
} from "@/lib/types";

export const DEFAULT_USER_ID = process.env.NEXT_PUBLIC_DEFAULT_USER_ID || "test-user-1";
export const ENABLE_SCRAPING = process.env.NEXT_PUBLIC_ENABLE_SCRAPING !== "false";
const DEFAULT_CACHE_TTL_MS = 5 * 60 * 1000;

type CacheEntry<T> = {
  data?: T;
  promise?: Promise<T>;
  expiresAt: number;
};

const apiCache = new Map<string, CacheEntry<unknown>>();

function formatApiErrorDetail(detail: unknown, fallback: string): string {
  if (typeof detail === "string" && detail.trim()) return detail;
  if (Array.isArray(detail)) {
    const messages = detail.map((item) => {
      if (typeof item === "string") return item;
      if (item && typeof item === "object") {
        const record = item as { loc?: unknown[]; msg?: unknown; message?: unknown };
        const location = Array.isArray(record.loc) ? record.loc.join(".") : "";
        const message = String(record.msg || record.message || JSON.stringify(item));
        return location ? `${location}: ${message}` : message;
      }
      return String(item);
    });
    return messages.filter(Boolean).join("; ") || fallback;
  }
  if (detail && typeof detail === "object") return JSON.stringify(detail);
  return fallback;
}

export function clearApiCache(pathPrefix?: string) {
  if (!pathPrefix) {
    apiCache.clear();
    return;
  }
  for (const key of apiCache.keys()) {
    if (key.startsWith(pathPrefix)) apiCache.delete(key);
  }
}

function clearUserWorkflowCache(userId = DEFAULT_USER_ID) {
  clearApiCache(`/users/${userId}`);
}

function getCachedApiValue<T>(path: string): T | null {
  const entry = apiCache.get(path) as CacheEntry<T> | undefined;
  if (!entry || entry.expiresAt <= Date.now() || entry.data === undefined) return null;
  return entry.data;
}

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api/backend${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers || {}),
    },
    cache: "no-store",
  });

  if (!response.ok) {
    let detail = `Request failed with status ${response.status}`;
    try {
      const body = (await response.json()) as { detail?: unknown };
      detail = formatApiErrorDetail(body.detail, detail);
    } catch {
      // Keep the generic message.
    }
    throw new Error(detail);
  }

  return response.json() as Promise<T>;
}

async function cachedApiFetch<T>(path: string, ttlMs = DEFAULT_CACHE_TTL_MS): Promise<T> {
  const now = Date.now();
  const cached = apiCache.get(path) as CacheEntry<T> | undefined;
  if (cached && cached.expiresAt > now) {
    if (cached.data !== undefined) return cached.data;
    if (cached.promise) return cached.promise;
  }

  const promise = apiFetch<T>(path)
    .then((data) => {
      apiCache.set(path, { data, expiresAt: Date.now() + ttlMs });
      return data;
    })
    .catch((error) => {
      apiCache.delete(path);
      throw error;
    });
  apiCache.set(path, { promise, expiresAt: now + ttlMs });
  return promise;
}

async function apiFormFetch<T>(path: string, formData: FormData): Promise<T> {
  const response = await fetch(`/api/backend${path}`, {
    method: "POST",
    body: formData,
    cache: "no-store",
  });

  if (!response.ok) {
    let detail = `Request failed with status ${response.status}`;
    try {
      const body = (await response.json()) as { detail?: unknown };
      detail = formatApiErrorDetail(body.detail, detail);
    } catch {
      // Keep the generic message.
    }
    throw new Error(detail);
  }

  return response.json() as Promise<T>;
}

export function fetchUserData(userId = DEFAULT_USER_ID) {
  return cachedApiFetch<UserDataResponse>(`/users/${userId}/data?limit=1000`);
}

export function getCachedUserData(userId = DEFAULT_USER_ID) {
  return getCachedApiValue<UserDataResponse>(`/users/${userId}/data?limit=1000`);
}

export function fetchRecentActivities(userId = DEFAULT_USER_ID, limit = 3) {
  return cachedApiFetch<RecentActivitiesResponse>(
    `/users/${userId}/activities/recent-24h?limit=${limit}&window_hours=24`,
  );
}

export function fetchUserActivities(userId = DEFAULT_USER_ID, limit = 100) {
  return cachedApiFetch<ActivityResponse[]>(`/users/${userId}/activities?limit=${limit}`);
}

export function getCachedUserActivities(userId = DEFAULT_USER_ID, limit = 100) {
  return getCachedApiValue<ActivityResponse[]>(`/users/${userId}/activities?limit=${limit}`);
}

export function fetchThreads(userId = DEFAULT_USER_ID, limit = 8) {
  return cachedApiFetch<ThreadSummary[]>(`/users/${userId}/threads?limit=${limit}`);
}

export function fetchCreators(userId = DEFAULT_USER_ID, limit = 1000) {
  return cachedApiFetch<CreatorResponse[]>(`/users/${userId}/creators?limit=${limit}`);
}

export function fetchCreatorProfile(userId: string, creatorId: string) {
  return cachedApiFetch<CreatorProfileDetailsResponse>(
    `/users/${userId}/creators/${encodeURIComponent(creatorId)}/profile-details`,
  );
}

export function fetchCreatorProfiles(userId = DEFAULT_USER_ID, limit = 500) {
  return cachedApiFetch<CreatorProfileDetailsResponse[]>(
    `/users/${userId}/creators/profile-details?limit=${limit}`,
  );
}

export function getCachedCreatorProfiles(userId = DEFAULT_USER_ID, limit = 500) {
  return getCachedApiValue<CreatorProfileDetailsResponse[]>(
    `/users/${userId}/creators/profile-details?limit=${limit}`,
  );
}

export function fetchCreatorActivities(userId: string, creatorId: string, limit = 20) {
  return cachedApiFetch<ActivityResponse[]>(
    `/users/${userId}/creators/${encodeURIComponent(creatorId)}/activities?limit=${limit}`,
  );
}

export function fetchPostTypes() {
  return apiFetch<string[]>("/post-generation-styles");
}

export function generatePost(payload: {
  user_id: string;
  idea: string;
  generation_style: string;
  topic_source?: string;
}) {
  return apiFetch<ThreadResponse>("/posts/generate", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function addCreator(payload: {
  user_id: string;
  profile_url: string;
}) {
  const result = await apiFetch<CreatorResponse>("/creators", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  clearUserWorkflowCache(payload.user_id);
  return result;
}

export async function importCreators(userId: string, file: File) {
  const formData = new FormData();
  formData.append("user_id", userId);
  formData.append("file", file);
  const result = await apiFormFetch<BulkCreatorImportResponse>("/creators/import", formData);
  clearUserWorkflowCache(userId);
  return result;
}

export function previewCreatorImport(userId: string, file: File) {
  const formData = new FormData();
  formData.append("user_id", userId);
  formData.append("file", file);
  return apiFormFetch<BulkCreatorPreviewResponse>("/creators/import/preview", formData);
}

export function scrapeCreatorRecent24h(userId: string, creatorId: string) {
  return runRecentScrape({
    user_id: userId,
    creator_ids: [creatorId],
    max_posts: 5,
    window_hours: 24,
  });
}

export function runRecentScrape(payload: {
  user_id: string;
  creator_ids?: string[];
  max_posts?: number;
  window_hours?: number;
  launch_delay_seconds?: number;
}) {
  return apiFetch<RecentScrapeCreatorsResponse>("/creators/scrape/recent-24h", {
    method: "POST",
    body: JSON.stringify(payload),
  }).then((result) => {
    clearUserWorkflowCache(payload.user_id);
    return result;
  });
}

export function scrapeCreatorProfiles(userId: string, creatorIds?: string[], launchDelaySeconds = 3) {
  return apiFetch<ScrapeCreatorProfilesResponse>("/creators/profile-details/scrape", {
    method: "POST",
    body: JSON.stringify({
      user_id: userId,
      creator_ids: creatorIds,
      launch_delay_seconds: launchDelaySeconds,
    }),
  }).then((result) => {
    clearUserWorkflowCache(userId);
    return result;
  });
}

export function generateFromCreatorActivity(payload: {
  user_id: string;
  creator_id: string;
  post_id: string;
}) {
  return apiFetch<ThreadResponse>("/posts/from-creator-activity", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function generateComment(payload: {
  user_id: string;
  creator_id: string;
  post_id: string;
  comment_topic?: string;
}) {
  return apiFetch<CommentResponse>("/comments/generate", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function markComment(payload: {
  user_id: string;
  creator_id: string;
  post_id: string;
  commented: boolean;
  comment_text?: string;
}) {
  return apiFetch<CommentResponse>("/comments/mark", {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function fetchCommentHistory(userId = DEFAULT_USER_ID, limit = 100) {
  return apiFetch<CommentedActivityResponse[]>(`/users/${userId}/engagements/comments?limit=${limit}`);
}

export function deleteCreator(userId: string, creatorId: string) {
  return apiFetch<DeleteResponse>(`/users/${userId}/creators/${encodeURIComponent(creatorId)}`, {
    method: "DELETE",
  }).then((result) => {
    clearUserWorkflowCache(userId);
    return result;
  });
}

export function refinePost(payload: {
  user_id: string;
  thread_id: string;
  modification_message: string;
}) {
  return apiFetch<ThreadResponse>("/posts/modify", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}
