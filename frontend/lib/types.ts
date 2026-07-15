export type UserResponse = {
  user_id: string;
  profile: Record<string, unknown>;
  writing_style?: Record<string, unknown>;
  created_at?: string;
  updated_at?: string;
};

export type CreatorResponse = {
  user_id: string;
  creator_id: string;
  profile_url: string;
  display_name: string;
  added_at: string;
  updated_at: string;
  last_checked_at?: string | null;
  seen_count?: number;
  new_count?: number;
};

export type ThreadSummary = {
  thread_id: string;
  topic: string;
  topic_source?: string;
  generation_style?: string;
  created_at: string;
  updated_at: string;
};

export type ThreadResponse = ThreadSummary & {
  user_id: string;
  current_post: string;
  original_post?: string;
  conversation?: Array<Record<string, unknown>>;
  provider?: string;
  model?: string;
  source?: Record<string, unknown>;
  generated_at?: string;
  modified_at?: string;
  modification_count?: number;
};

export type ActivityResponse = {
  user_id: string;
  creator_id: string;
  post_id: string;
  post_url?: string;
  raw_text: string;
  author_name?: string;
  posted_at_text?: string;
  fetched_at: string;
  content_hash?: string;
  source?: string;
  is_new?: boolean;
  engagement?: Record<string, unknown>;
};

export type DashboardStats = {
  creator_count: number;
  thread_count: number;
  activity_count: number;
  new_posts_today_count: number;
  new_posts_from_last_scrape_count: number;
  needs_scraping_count: number;
  recently_added_count: number;
  recently_added_window_days: number;
  scraping_stale_after_hours: number;
  updated_at: string;
};

export type UserDataResponse = {
  user: UserResponse;
  dashboard_stats: DashboardStats;
  creators: CreatorResponse[];
  threads: ThreadSummary[];
  recent_activities: ActivityResponse[];
};

export type RecentActivitiesResponse = {
  user_id: string;
  window_hours: number;
  activities: ActivityResponse[];
};

export type CreatorProfileDetailsResponse = {
  user_id: string;
  creator_id: string;
  profile_url: string;
  name: string;
  headline: string;
  about: string;
  location: string;
  email?: string;
  profile_image_url: string;
  experience: string[];
  fetched_at: string;
  source: string;
};

export type BulkCreatorImportResponse = {
  user_id: string;
  total_urls: number;
  added_creators: CreatorResponse[];
  skipped_existing_creator_ids: string[];
  skipped_duplicate_creator_ids: string[];
  skipped_existing_creators: Array<{
    row?: string;
    url?: string;
    normalized_url?: string;
    creator_id?: string;
    reason?: string;
  }>;
  skipped_duplicate_creators: Array<{
    row?: string;
    url?: string;
    normalized_url?: string;
    creator_id?: string;
    reason?: string;
  }>;
  errors: Array<{
    row?: string;
    url?: string;
    message?: string;
  }>;
};

export type BulkCreatorPreviewResponse = {
  user_id: string;
  total_urls: number;
  corrected_creators: Array<{
    row?: string;
    url?: string;
    normalized_url?: string;
    creator_id?: string;
  }>;
  new_creators: Array<{
    row?: string;
    url?: string;
    normalized_url?: string;
    creator_id?: string;
  }>;
  existing_creators: Array<{
    row?: string;
    url?: string;
    normalized_url?: string;
    creator_id?: string;
    reason?: string;
  }>;
  duplicate_creators: Array<{
    row?: string;
    url?: string;
    normalized_url?: string;
    creator_id?: string;
    reason?: string;
  }>;
  errors: Array<{
    row?: string;
    url?: string;
    message?: string;
  }>;
};

export type RecentScrapeCreatorsResponse = {
  user_id: string;
  checked_creator_ids: string[];
  window_hours: number;
  activities: ActivityResponse[];
  errors: Array<{
    creator_id?: string;
    message?: string;
  }>;
};

export type ScrapeCreatorProfilesResponse = {
  user_id: string;
  checked_creator_ids: string[];
  profiles: CreatorProfileDetailsResponse[];
  errors: Array<{
    creator_id?: string;
    message?: string;
  }>;
};

export type CommentResponse = {
  user_id: string;
  creator_id: string;
  post_id: string;
  thread_id?: string;
  comment_topic: string;
  style?: string;
  tone?: string;
  length?: string;
  comment: string;
  provider?: string;
  model?: string;
  generated_at?: string;
  commented?: boolean;
  modification_count?: number;
  conversation?: Array<Record<string, unknown>>;
};

export type CommentedActivityResponse = ActivityResponse & {
  comment_topic: string;
  comment: string;
  commented_at: string;
};

export type DeleteResponse = {
  ok: boolean;
  message: string;
};
