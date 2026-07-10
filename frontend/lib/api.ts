import type {
  ActivityResponse,
  BulkCreatorImportResponse,
  BulkCreatorPreviewResponse,
  CreatorProfileDetailsResponse,
  CreatorResponse,
  DeleteResponse,
  RecentActivitiesResponse,
  RecentScrapeCreatorsResponse,
  ThreadResponse,
  ThreadSummary,
  UserDataResponse,
} from "@/lib/types";

export const DEFAULT_USER_ID = process.env.NEXT_PUBLIC_DEFAULT_USER_ID || "test-user-1";

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
      const body = (await response.json()) as { detail?: string };
      detail = body.detail || detail;
    } catch {
      // Keep the generic message.
    }
    throw new Error(detail);
  }

  return response.json() as Promise<T>;
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
      const body = (await response.json()) as { detail?: string };
      detail = body.detail || detail;
    } catch {
      // Keep the generic message.
    }
    throw new Error(detail);
  }

  return response.json() as Promise<T>;
}

export function fetchUserData(userId = DEFAULT_USER_ID) {
  return apiFetch<UserDataResponse>(`/users/${userId}/data?limit=1000`);
}

export function fetchRecentActivities(userId = DEFAULT_USER_ID, limit = 3) {
  return apiFetch<RecentActivitiesResponse>(
    `/users/${userId}/activities/recent-24h?limit=${limit}&window_hours=24`,
  );
}

export function fetchThreads(userId = DEFAULT_USER_ID, limit = 8) {
  return apiFetch<ThreadSummary[]>(`/users/${userId}/threads?limit=${limit}`);
}

export function fetchCreators(userId = DEFAULT_USER_ID, limit = 1000) {
  return apiFetch<CreatorResponse[]>(`/users/${userId}/creators?limit=${limit}`);
}

export function fetchCreatorProfile(userId: string, creatorId: string) {
  return apiFetch<CreatorProfileDetailsResponse>(
    `/users/${userId}/creators/${encodeURIComponent(creatorId)}/profile-details`,
  );
}

export function fetchCreatorActivities(userId: string, creatorId: string, limit = 20) {
  return apiFetch<ActivityResponse[]>(
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

export function addCreator(payload: {
  user_id: string;
  profile_url: string;
}) {
  return apiFetch<CreatorResponse>("/creators", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function importCreators(userId: string, file: File) {
  const formData = new FormData();
  formData.append("user_id", userId);
  formData.append("file", file);
  return apiFormFetch<BulkCreatorImportResponse>("/creators/import", formData);
}

export function previewCreatorImport(userId: string, file: File) {
  const formData = new FormData();
  formData.append("user_id", userId);
  formData.append("file", file);
  return apiFormFetch<BulkCreatorPreviewResponse>("/creators/import/preview", formData);
}

export function scrapeCreatorRecent24h(userId: string, creatorId: string) {
  return apiFetch<RecentScrapeCreatorsResponse>("/creators/scrape/recent-24h", {
    method: "POST",
    body: JSON.stringify({
      user_id: userId,
      creator_ids: [creatorId],
      max_posts: 5,
      window_hours: 24,
    }),
  });
}

export function deleteCreator(userId: string, creatorId: string) {
  return apiFetch<DeleteResponse>(`/users/${userId}/creators/${encodeURIComponent(creatorId)}`, {
    method: "DELETE",
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
