import type {
  ActivityResponse,
  BulkCreatorImportResponse,
  BulkCreatorPreviewResponse,
  BrainstormResponse,
  CarouselResponse,
  CommentedActivityResponse,
  CommentResponse,
  ContentItemResponse,
  ContentItemStatus,
  ContentSourceResponse,
  CreatorProfileDetailsResponse,
  CreatorResponse,
  DeleteResponse,
  ImageAssetResponse,
  LinkedInActionBatchResponse,
  LinkedInActionLogResponse,
  LinkedInProspectResponse,
  OwnPostResponse,
  PostBuilderGenerateResponse,
  PostEngagementScrapeResponse,
  PostEngagerResponse,
  RecentActivitiesResponse,
  RecentScrapeCreatorsResponse,
  ScrapeCreatorProfilesResponse,
  ScrapeJobStartResponse,
  ScrapeJobStatusResponse,
  ThreadResponse,
  ThreadSummary,
  UserDataResponse,
} from "@/lib/types";

export const DEFAULT_USER_ID = process.env.NEXT_PUBLIC_DEFAULT_USER_ID || "test-user-1";
export const ENABLE_SCRAPING = process.env.NEXT_PUBLIC_ENABLE_SCRAPING !== "false";
const DEFAULT_CACHE_TTL_MS = 5 * 60 * 1000;
const SCRAPE_JOB_POLL_INTERVAL_MS = 3 * 60 * 1000;

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

export function fetchUserActivities(userId = DEFAULT_USER_ID, limit = 500) {
  return cachedApiFetch<ActivityResponse[]>(`/users/${userId}/activities?limit=${limit}`);
}

export function getCachedUserActivities(userId = DEFAULT_USER_ID, limit = 500) {
  return getCachedApiValue<ActivityResponse[]>(`/users/${userId}/activities?limit=${limit}`);
}

export function fetchThreads(userId = DEFAULT_USER_ID, limit = 8) {
  return cachedApiFetch<ThreadSummary[]>(`/users/${userId}/threads?limit=${limit}`);
}

export function fetchThread(userId: string, threadId: string) {
  return apiFetch<ThreadResponse>(`/users/${userId}/threads/${encodeURIComponent(threadId)}`);
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

export function generatePost(payload: {
  user_id: string;
  idea: string;
  post_length?: string;
  tone?: string;
  writing_style?: string;
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
}, onStatus?: (status: ScrapeJobStatusResponse) => void) {
  return apiFetch<ScrapeJobStartResponse>("/scrape-jobs/creators/recent-24h", {
    method: "POST",
    body: JSON.stringify(payload),
  }).then((job) => pollScrapeJobUntilDone(job.job_id, onStatus))
    .then((status) => {
      if (status.status === "failed") {
        throw new Error(status.message || status.errors[0]?.message || "Scraping failed.");
      }
      return status.result as RecentScrapeCreatorsResponse;
    })
    .then((result) => {
    clearUserWorkflowCache(payload.user_id);
    return result;
  });
}

export function scrapeCreatorProfiles(
  userId: string,
  creatorIds?: string[],
  launchDelaySeconds = 3,
  onStatus?: (status: ScrapeJobStatusResponse) => void,
) {
  return apiFetch<ScrapeJobStartResponse>("/scrape-jobs/creators/profile-details", {
    method: "POST",
    body: JSON.stringify({
      user_id: userId,
      creator_ids: creatorIds,
      launch_delay_seconds: launchDelaySeconds,
    }),
  }).then((job) => pollScrapeJobUntilDone(job.job_id, onStatus))
    .then((status) => {
      if (status.status === "failed") {
        throw new Error(status.message || status.errors[0]?.message || "Profile scraping failed.");
      }
      return status.result as ScrapeCreatorProfilesResponse;
    })
    .then((result) => {
    clearUserWorkflowCache(userId);
    return result;
  });
}

export function fetchScrapeJobStatus(jobId: string) {
  return apiFetch<ScrapeJobStatusResponse>(`/scrape-jobs/${encodeURIComponent(jobId)}`);
}

function isTerminalScrapeJob(status: ScrapeJobStatusResponse) {
  return status.status === "succeeded" || status.status === "failed";
}

async function pollScrapeJobUntilDone(
  jobId: string,
  onStatus?: (status: ScrapeJobStatusResponse) => void,
  intervalMs = SCRAPE_JOB_POLL_INTERVAL_MS,
): Promise<ScrapeJobStatusResponse> {
  for (;;) {
    const status = await fetchScrapeJobStatus(jobId);
    onStatus?.(status);
    if (isTerminalScrapeJob(status)) return status;
    await new Promise((resolve) => window.setTimeout(resolve, intervalMs));
  }
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
  style?: string;
  tone?: string;
  length?: string;
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

export function modifyComment(payload: {
  user_id: string;
  thread_id: string;
  modification_message: string;
  style?: string;
  tone?: string;
  length?: string;
}) {
  return apiFetch<CommentResponse>("/comments/modify", {
    method: "POST",
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

export function brainstormIdeas(payload: { user_id: string; topic?: string; action?: string }) {
  return apiFetch<BrainstormResponse>("/ideas/brainstorm", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function generatePostBuilder(payload: {
  user_id: string;
  topic: string;
  source_url?: string;
  post_length?: string;
  writing_style?: string;
  variations?: string[];
  formats?: string[];
  tones?: string[];
  angles?: string[];
  structure?: string;
  post_count?: number;
}) {
  return apiFetch<PostBuilderGenerateResponse>("/posts/builder/generate", {
    method: "POST",
    body: JSON.stringify(payload),
  }).then((result) => {
    clearUserWorkflowCache(payload.user_id);
    clearApiCache(`/users/${payload.user_id}/content-items`);
    return result;
  });
}

export function extractContentSource(url: string) {
  return apiFetch<ContentSourceResponse>("/content-sources/extract", {
    method: "POST",
    body: JSON.stringify({ url }),
  });
}

export function fetchContentItems(userId = DEFAULT_USER_ID, limit = 200) {
  return cachedApiFetch<ContentItemResponse[]>(`/users/${userId}/content-items?limit=${limit}`);
}

export function createContentItem(payload: {
  user_id: string;
  title: string;
  body?: string;
  status?: ContentItemStatus;
}) {
  return apiFetch<ContentItemResponse>("/content-items", {
    method: "POST",
    body: JSON.stringify(payload),
  }).then((result) => {
    clearUserWorkflowCache(payload.user_id);
    clearApiCache(`/users/${payload.user_id}/content-items`);
    return result;
  });
}

export function updateContentItem(
  contentId: string,
  payload: {
    user_id: string;
    title?: string;
    body?: string;
    status?: ContentItemStatus;
    scheduled_at?: string;
  },
) {
  return apiFetch<ContentItemResponse>(`/content-items/${encodeURIComponent(contentId)}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  }).then((result) => {
    clearUserWorkflowCache(payload.user_id);
    clearApiCache(`/users/${payload.user_id}/content-items`);
    return result;
  });
}

export function fetchOwnLinkedInPosts(userId = DEFAULT_USER_ID, limit = 100) {
  return cachedApiFetch<OwnPostResponse[]>(
    `/users/${userId}/linkedin/posts?limit=${limit}&window_hours=72`,
  );
}

export function trackOwnLinkedInPost(payload: {
  user_id: string;
  post_url: string;
  post_text?: string;
  post_id?: string;
  source?: string;
}) {
  return apiFetch<OwnPostResponse>("/linkedin/posts/publish", {
    method: "POST",
    body: JSON.stringify(payload),
  }).then((result) => {
    clearApiCache(`/users/${payload.user_id}/linkedin`);
    return result;
  });
}

export function syncOwnLinkedInPosts(payload: {
  user_id: string;
  profile_url?: string;
  window_hours?: number;
  max_posts?: number;
  launch_delay_seconds?: number;
}) {
  return apiFetch<{
    user_id: string;
    checked_count: number;
    saved_count: number;
    skipped_count: number;
    posts: OwnPostResponse[];
    skipped_posts: Array<Record<string, string>>;
    errors: Array<Record<string, string>>;
  }>("/linkedin/posts/sync-recent", {
    method: "POST",
    body: JSON.stringify(payload),
  }).then((result) => {
    clearApiCache(`/users/${payload.user_id}/linkedin`);
    return result;
  });
}

export function scrapeOwnPostEngagement(postId: string, userId = DEFAULT_USER_ID) {
  return apiFetch<PostEngagementScrapeResponse>(
    `/linkedin/posts/${encodeURIComponent(postId)}/engagement/scrape`,
    {
      method: "POST",
      body: JSON.stringify({
        user_id: userId,
        include_likes: true,
        include_comments: true,
        launch_delay_seconds: 3,
      }),
    },
  ).then((result) => {
    clearApiCache(`/linkedin/posts/${encodeURIComponent(postId)}/engagers`);
    clearApiCache(`/users/${userId}/linkedin/prospects`);
    return result;
  });
}

export function fetchPostEngagers(postId: string, userId = DEFAULT_USER_ID) {
  return cachedApiFetch<PostEngagerResponse[]>(
    `/linkedin/posts/${encodeURIComponent(postId)}/engagers?user_id=${encodeURIComponent(userId)}&limit=500`,
  );
}

export function fetchLinkedInProspects(
  userId = DEFAULT_USER_ID,
  filters?: { engagementType?: string; connectionDegree?: string; search?: string },
) {
  const params = new URLSearchParams({ limit: "500" });
  if (filters?.engagementType) params.set("engagement_type", filters.engagementType);
  if (filters?.connectionDegree) params.set("connection_degree", filters.connectionDegree);
  if (filters?.search) params.set("search", filters.search);
  return cachedApiFetch<LinkedInProspectResponse[]>(
    `/users/${userId}/linkedin/prospects?${params.toString()}`,
  );
}

export function fetchLinkedInActionLogs(userId = DEFAULT_USER_ID, limit = 200) {
  return cachedApiFetch<LinkedInActionLogResponse[]>(
    `/users/${userId}/linkedin/action-logs?limit=${limit}`,
  );
}

export function sendCommentReplies(payload: {
  user_id: string;
  post_id: string;
  profile_urls: string[];
  reply_text: string;
  dry_run: boolean;
}) {
  return apiFetch<LinkedInActionBatchResponse>("/linkedin/actions/comment-replies", {
    method: "POST",
    body: JSON.stringify({ ...payload, launch_delay_seconds: 3 }),
  }).then((result) => {
    clearApiCache(`/users/${payload.user_id}/linkedin/action-logs`);
    return result;
  });
}

export function sendConnectionRequests(payload: {
  user_id: string;
  post_id: string;
  profile_urls: string[];
  engagement_types: string[];
  note: string;
  dry_run: boolean;
}) {
  return apiFetch<LinkedInActionBatchResponse>("/linkedin/actions/connection-requests", {
    method: "POST",
    body: JSON.stringify({ ...payload, launch_delay_seconds: 3 }),
  }).then((result) => {
    clearApiCache(`/users/${payload.user_id}/linkedin/action-logs`);
    return result;
  });
}

export function sendDirectMessages(payload: {
  user_id: string;
  post_id: string;
  profile_urls: string[];
  message: string;
  dry_run: boolean;
}) {
  return apiFetch<LinkedInActionBatchResponse>("/linkedin/actions/dms", {
    method: "POST",
    body: JSON.stringify({ ...payload, launch_delay_seconds: 3 }),
  }).then((result) => {
    clearApiCache(`/users/${payload.user_id}/linkedin/action-logs`);
    return result;
  });
}

export function generateCarousel(payload: {
  user_id: string;
  topic: string;
  audience: string;
  tone: string;
  theme: string;
  slide_count: number;
}) {
  return apiFetch<CarouselResponse>("/carousels/generate", {
    method: "POST",
    body: JSON.stringify(payload),
  }).then((result) => {
    clearApiCache(`/users/${payload.user_id}/carousels`);
    return result;
  });
}

export function createCarousel(payload: {
  user_id: string;
  title: string;
  theme: string;
  slide_count: number;
}) {
  return apiFetch<CarouselResponse>("/carousels", {
    method: "POST",
    body: JSON.stringify(payload),
  }).then((result) => {
    clearApiCache(`/users/${payload.user_id}/carousels`);
    return result;
  });
}

export function fetchCarousels(userId = DEFAULT_USER_ID, limit = 100) {
  return cachedApiFetch<CarouselResponse[]>(`/users/${userId}/carousels?limit=${limit}`);
}

export function saveCarousel(carousel: CarouselResponse) {
  return apiFetch<CarouselResponse>(`/carousels/${encodeURIComponent(carousel.carousel_id)}`, {
    method: "PATCH",
    body: JSON.stringify({
      user_id: carousel.user_id,
      title: carousel.title,
      theme: carousel.theme,
      slides: carousel.slides,
    }),
  }).then((result) => {
    clearApiCache(`/users/${carousel.user_id}/carousels`);
    return result;
  });
}

export function generateImageAsset(payload: {
  user_id: string;
  prompt: string;
  post_text?: string;
  aspect_ratio?: string;
  style?: string;
}) {
  return apiFetch<ImageAssetResponse>("/images/generate", {
    method: "POST",
    body: JSON.stringify(payload),
  }).then((result) => {
    clearApiCache(`/users/${payload.user_id}/image-assets`);
    return result;
  });
}

export function fetchImageAssets(userId = DEFAULT_USER_ID, limit = 100) {
  return cachedApiFetch<ImageAssetResponse[]>(`/users/${userId}/image-assets?limit=${limit}`);
}

export function deleteImageAsset(userId: string, assetId: string) {
  return apiFetch<DeleteResponse>(
    `/users/${userId}/image-assets/${encodeURIComponent(assetId)}`,
    { method: "DELETE" },
  ).then((result) => {
    clearApiCache(`/users/${userId}/image-assets`);
    return result;
  });
}

export function backendAssetUrl(assetUrl: string) {
  return `/api/backend${assetUrl.startsWith("/") ? assetUrl : `/${assetUrl}`}`;
}
