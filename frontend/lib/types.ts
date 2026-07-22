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
  is_repost?: boolean;
  repost_text?: string;
  original_post_text?: string;
  original_author_name?: string;
  original_author_url?: string;
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
  total_scraped_posts_count: number;
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

export type ScrapeJobStartResponse = {
  job_id: string;
  job_type: string;
  user_id: string;
  status: string;
  status_url: string;
  total_creators: number;
  created_at: string;
};

export type ScrapeJobStatusResponse = {
  job_id: string;
  job_type: string;
  user_id: string;
  status: "queued" | "running" | "succeeded" | "failed" | string;
  created_at: string;
  started_at?: string;
  updated_at?: string;
  completed_at?: string;
  total_creators: number;
  scraped_creators: number;
  total_posts: number;
  scraped_profiles: number;
  current_creator_id?: string;
  message?: string;
  errors: Array<{
    creator_id?: string;
    message?: string;
  }>;
  result: Record<string, unknown>;
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

export type OwnPostResponse = {
  user_id: string;
  post_id: string;
  post_url: string;
  source: string;
  text: string;
  created_at_text?: string;
  estimated_posted_at?: string;
  first_seen_at?: string;
  last_scraped_at?: string;
  reaction_count: number;
  comment_count: number;
  impression_count: number;
  scrape_status: string;
  status: string;
};

export type PostEngagerResponse = {
  user_post_id: string;
  user_id: string;
  post_id: string;
  post_url: string;
  profile_key: string;
  profile_url: string;
  profile_urn: string;
  name: string;
  headline: string;
  connection_degree: string;
  engagement_types: string[];
  comment_text: string;
  comment_permalink: string;
  comment_urn: string;
  comment_text_hash: string;
  comment_timestamp_text: string;
  scraped_at: string;
  source: string;
};

export type LinkedInProspectResponse = {
  prospect_id: string;
  user_id: string;
  profile_key: string;
  profile_url: string;
  profile_urn: string;
  name: string;
  headline: string;
  connection_degree: string;
  engagement_types: string[];
  engagement_count: number;
  source_post_ids: string[];
  source_post_count: number;
  latest_comment_text: string;
  last_engaged_at: string;
  latest_action_type: string;
  latest_action_status: string;
  can_reply: boolean;
  can_dm: boolean;
  can_connect: boolean;
};

export type PostEngagementScrapeResponse = {
  user_id: string;
  post_id: string;
  like_count: number;
  comment_count: number;
  engagers_saved: number;
  warnings: string[];
  errors: Array<{ message?: string }>;
  engagers: PostEngagerResponse[];
};

export type LinkedInActionResult = {
  profile_url: string;
  profile_key: string;
  action_id: string;
  action_type: string;
  status: string;
  skip_reason: string;
  error_message: string;
  final_text: string;
};

export type LinkedInActionBatchResponse = {
  user_id: string;
  post_id: string;
  action_type: string;
  results: LinkedInActionResult[];
};

export type LinkedInActionLogResponse = LinkedInActionResult & {
  user_id: string;
  post_id: string;
  requested_text: string;
  created_at: string;
  started_at: string;
  finished_at: string;
};

export type ContentItemStatus = "idea" | "in_progress" | "ready" | "published";

export type ContentItemResponse = {
  user_id: string;
  content_id: string;
  thread_id: string;
  title: string;
  body: string;
  status: ContentItemStatus;
  topic_source: string;
  source: Record<string, unknown>;
  assets: string[];
  scheduled_at: string;
  created_at: string;
  updated_at: string;
};

export type ContentSourceResponse = {
  url: string;
  canonical_url: string;
  title: string;
  description: string;
  text: string;
  word_count: number;
  content_type: string;
};

export type PostBuilderGenerateResponse = {
  user_id: string;
  source_url: string;
  source_title: string;
  threads: ThreadResponse[];
};

export type CarouselSlide = {
  slide_id: string;
  eyebrow: string;
  title: string;
  body: string;
};

export type CarouselResponse = {
  user_id: string;
  carousel_id: string;
  title: string;
  topic: string;
  audience: string;
  tone: string;
  theme: string;
  slides: CarouselSlide[];
  status: string;
  created_at: string;
  updated_at: string;
};

export type ImageAssetResponse = {
  user_id: string;
  asset_id: string;
  prompt: string;
  revised_prompt: string;
  model: string;
  mime_type: string;
  aspect_ratio: string;
  style: string;
  asset_url: string;
  created_at: string;
};

export type BrainstormResponse = {
  user_id: string;
  action: string;
  topic: string;
  ideas: Array<{
    title: string;
    summary: string;
    post_angle: string;
    source_url: string;
  }>;
  research_suggestions: string[];
  provider: string;
  model: string;
};

export type BrainstormJobStartResponse = {
  job_id: string;
  user_id: string;
  status: "queued";
  created_at: string;
};

export type BrainstormJobStatusResponse = {
  job_id: string;
  user_id: string;
  status: "queued" | "running" | "succeeded" | "failed";
  created_at: string;
  started_at: string;
  completed_at: string;
  elapsed_seconds: number | null;
  error: string;
  result: BrainstormResponse | null;
};
