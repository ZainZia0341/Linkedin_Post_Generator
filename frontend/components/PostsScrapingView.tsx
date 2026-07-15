"use client";

import {
  CheckCircle2,
  Copy,
  ExternalLink,
  MessageSquareText,
  Search,
  Trash2,
  X,
  Zap,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import { RunScrapingDialog } from "@/components/RunScrapingDialog";
import {
  DEFAULT_USER_ID,
  ENABLE_SCRAPING,
  fetchCreatorProfiles,
  fetchUserActivities,
  fetchUserData,
} from "@/lib/api";
import { activityTitle, compactDate, displayName, initials, previewText, sortThreads } from "@/lib/format";
import type { ActivityResponse, CreatorProfileDetailsResponse, CreatorResponse, UserDataResponse } from "@/lib/types";

const POSTS_PAGE_SIZE = 9;

export function PostsScrapingView() {
  const router = useRouter();
  const [userData, setUserData] = useState<UserDataResponse | null>(null);
  const [activities, setActivities] = useState<ActivityResponse[]>([]);
  const [profileMap, setProfileMap] = useState<Map<string, CreatorProfileDetailsResponse>>(new Map());
  const [selectedPost, setSelectedPost] = useState<ActivityResponse | null>(null);
  const [showScrapeDialog, setShowScrapeDialog] = useState(false);
  const [query, setQuery] = useState("");
  const [creatorFilter, setCreatorFilter] = useState("all");
  const [windowHours, setWindowHours] = useState(24);
  const [sortOrder, setSortOrder] = useState<"newest" | "oldest">("newest");
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [successMessage, setSuccessMessage] = useState("");

  function showSuccess(message: string) {
    setSuccessMessage(message);
    window.setTimeout(() => setSuccessMessage(""), 2000);
  }

  async function load() {
    setLoading(true);
    setError("");
    try {
      const [dataResult, activityResult, profileResult] = await Promise.allSettled([
        fetchUserData(DEFAULT_USER_ID),
        fetchUserActivities(DEFAULT_USER_ID, 100),
        fetchCreatorProfiles(DEFAULT_USER_ID, 500),
      ]);
      if (dataResult.status === "rejected") throw dataResult.reason;
      if (activityResult.status === "rejected") throw activityResult.reason;
      setUserData(dataResult.value);
      setActivities(activityResult.value);
      if (profileResult.status === "fulfilled") {
        setProfileMap(new Map(profileResult.value.map((profile) => [profile.creator_id, profile])));
      }
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Could not load scraped posts.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  useEffect(() => {
    setPage(1);
  }, [creatorFilter, query, sortOrder, windowHours]);

  const creators = userData?.creators ?? [];
  const creatorById = useMemo(() => {
    return new Map(creators.map((creator) => [creator.creator_id, creator]));
  }, [creators]);
  const sortedThreads = useMemo(() => sortThreads(userData?.threads ?? []), [userData?.threads]);
  const userName = displayName(userData?.user) || DEFAULT_USER_ID;
  const filteredActivities = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    return activities.filter((activity) => {
      const creator = creatorById.get(activity.creator_id);
      const profile = profileMap.get(activity.creator_id);
      const searchable = `${activity.raw_text} ${activity.creator_id} ${activity.author_name || ""} ${creator?.display_name || ""} ${profile?.name || ""} ${profile?.headline || ""}`.toLowerCase();
      const matchesQuery = !normalized || searchable.includes(normalized);
      const matchesCreator = creatorFilter === "all" || activity.creator_id === creatorFilter;
      const matchesWindow = isWithinWindow(activity.fetched_at, windowHours);
      return matchesQuery && matchesCreator && matchesWindow;
    }).sort((left, right) => {
      const leftTime = new Date(left.fetched_at).getTime();
      const rightTime = new Date(right.fetched_at).getTime();
      if (Number.isNaN(leftTime) || Number.isNaN(rightTime)) return 0;
      return sortOrder === "newest" ? rightTime - leftTime : leftTime - rightTime;
    });
  }, [activities, creatorById, creatorFilter, profileMap, query, sortOrder, windowHours]);
  const visiblePosts = filteredActivities;
  const newPosts = filteredActivities.filter(isFetchedWithinLastDay);
  const totalPages = Math.max(1, Math.ceil(visiblePosts.length / POSTS_PAGE_SIZE));
  const safePage = Math.min(page, totalPages);
  const pageStart = visiblePosts.length ? (safePage - 1) * POSTS_PAGE_SIZE : 0;
  const pageEnd = Math.min(pageStart + POSTS_PAGE_SIZE, visiblePosts.length);
  const pagedPosts = visiblePosts.slice(pageStart, pageEnd);
  const lastScrapeAt = creators
    .map((creator) => creator.last_checked_at)
    .filter(Boolean)
    .sort((left, right) => new Date(right || "").getTime() - new Date(left || "").getTime())[0];
  const metrics = {
    total: activities.length,
    newPosts: newPosts.length,
    lastScrape: lastScrapeAt ? compactDate(lastScrapeAt) : "No scrape",
  };

  function openCommentGeneration(activity: ActivityResponse) {
    const params = new URLSearchParams({
      creator_id: activity.creator_id,
      post_id: activity.post_id,
    });
    router.push(`/comments/generate?${params.toString()}`);
  }

  return (
    <AppShell
      active="posts"
      title="Ready to Comment"
      subtitle="Browse recent LinkedIn posts from tracked creators."
      eyebrowLabel={null}
      userName={userName}
      threads={sortedThreads}
    >
      <section className="posts-workspace">
        <div className="posts-action-row">
          <button
            className="primary-button compact"
            type="button"
            onClick={() => setShowScrapeDialog(true)}
            disabled={!ENABLE_SCRAPING}
            title={ENABLE_SCRAPING ? "Run scraping" : "Run scraping locally"}
          >
            <Zap size={16} />
            Run Scraping
          </button>
        </div>

        <div className="posts-metric-grid">
          <PostsMetric label="Total Scraped Posts" value={metrics.total.toLocaleString()} />
          <PostsMetric label="New Posts" value={metrics.newPosts.toLocaleString()} />
          <PostsMetric label="Last Scraping" value={metrics.lastScrape} />
        </div>

        <section className="posts-toolbar">
          <label className="creator-search posts-search">
            <Search size={17} />
            <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search scraped posts..." />
          </label>
          <select value={creatorFilter} onChange={(event) => setCreatorFilter(event.target.value)} aria-label="Creator filter">
            <option value="all">All Creators ({creators.length})</option>
            {creators.map((creator) => (
              <option value={creator.creator_id} key={creator.creator_id}>
                {creator.display_name || creator.creator_id}
              </option>
            ))}
          </select>
          <select value={windowHours} onChange={(event) => setWindowHours(Number(event.target.value))} aria-label="Time window filter">
            <option value={12}>Last 12 Hours</option>
            <option value={24}>Last Day</option>
            <option value={48}>Last 2 Days</option>
            <option value={72}>Last 3 Days</option>
          </select>
          <select value={sortOrder} onChange={(event) => setSortOrder(event.target.value as "newest" | "oldest")} aria-label="Sort filter">
            <option value="newest">Newest First</option>
            <option value="oldest">Oldest First</option>
          </select>
        </section>

        {error ? <div className="error-banner">{error}</div> : null}
        {loading ? <div className="empty-card slim">Loading scraped posts...</div> : null}

        <section className="posts-section">
          <div className="scraped-post-list">
            {pagedPosts.length ? (
              pagedPosts.map((activity) => (
                <ScrapedPostCard
                  activity={activity}
                  creator={creatorById.get(activity.creator_id)}
                  profile={profileMap.get(activity.creator_id)}
                  onOpenDetails={setSelectedPost}
                  onGenerateComment={openCommentGeneration}
                  key={`${activity.creator_id}-${activity.post_id}`}
                />
              ))
            ) : (
              <div className="empty-mini">No posts match the current filters.</div>
            )}
          </div>
          {visiblePosts.length ? (
            <div className="posts-pagination">
              <span>
                Showing {pageStart + 1} to {pageEnd} of {visiblePosts.length} posts
              </span>
              <div className="pagination-controls" aria-label="Scraped posts pagination">
                <button
                  className="secondary-button compact"
                  type="button"
                  onClick={() => setPage((current) => Math.max(1, current - 1))}
                  disabled={safePage <= 1}
                >
                  Previous
                </button>
                <span>Page {safePage} of {totalPages}</span>
                <button
                  className="secondary-button compact"
                  type="button"
                  onClick={() => setPage((current) => Math.min(totalPages, current + 1))}
                  disabled={safePage >= totalPages}
                >
                  Next
                </button>
              </div>
            </div>
          ) : null}
        </section>
      </section>

      {showScrapeDialog ? (
        <RunScrapingDialog
          creators={creators}
          profileMap={profileMap}
          onClose={() => setShowScrapeDialog(false)}
          onComplete={(response) => {
            setShowScrapeDialog(false);
            showSuccess(`${response.activities.length} post${response.activities.length === 1 ? "" : "s"} scraped`);
            void load();
          }}
        />
      ) : null}

      {selectedPost ? (
        <ScrapedPostDetailsDrawer
          activity={selectedPost}
          creator={creatorById.get(selectedPost.creator_id)}
          profile={profileMap.get(selectedPost.creator_id)}
          onClose={() => setSelectedPost(null)}
        />
      ) : null}

      {successMessage ? (
        <div className="success-toast" role="status">
          <CheckCircle2 size={22} />
          <span>{successMessage}</span>
        </div>
      ) : null}
    </AppShell>
  );
}

function PostsMetric({ label, value }: { label: string; value: string }) {
  return (
    <article className="posts-metric-card">
      <span>{label}</span>
      <strong>{value}</strong>
    </article>
  );
}

function ScrapedPostCard({
  activity,
  creator,
  profile,
  onOpenDetails,
  onGenerateComment,
  muted = false,
}: {
  activity: ActivityResponse;
  creator?: CreatorResponse;
  profile?: CreatorProfileDetailsResponse;
  onOpenDetails: (activity: ActivityResponse) => void;
  onGenerateComment: (activity: ActivityResponse) => void;
  muted?: boolean;
}) {
  const name = profile?.name || activity.author_name || creator?.display_name || activityTitle(activity);
  const postedText = cleanLinkedInVisibilityText(activity.posted_at_text || "recently");
  const isNew = isFetchedWithinLastDay(activity);

  async function copyPostText() {
    await navigator.clipboard.writeText(activity.raw_text);
  }

  return (
    <article className={muted ? "scraped-post-card muted" : "scraped-post-card"}>
      <header className="post-card-header">
        <div className="post-author">
          <div className="avatar mini">
            {profile?.profile_image_url ? (
              <img src={profile.profile_image_url} alt={`${name} profile`} />
            ) : (
              initials(name)
            )}
          </div>
          <span>
            <strong>{name}</strong>
            <small>{profile?.headline || creator?.display_name || "Creator"} - Posted {postedText}</small>
          </span>
        </div>
        <div className="post-card-flags">
          <span className={isNew ? "status-pill success" : "status-pill neutral"}>
            {isNew ? "New" : "Old"}
          </span>
        </div>
      </header>
      <button className="post-card-body" type="button" onClick={() => onOpenDetails(activity)}>
        "{previewText(activity.raw_text, 250)}"
      </button>
      <div className="post-card-meta">
        <span>Fetched {compactDate(activity.fetched_at)}</span>
      </div>
      <footer className="post-card-actions">
        <button className="secondary-button compact" type="button" onClick={() => onGenerateComment(activity)}>
          <MessageSquareText size={15} />
          Generate Comment
        </button>
        <button className="icon-button tiny copy-post-button" type="button" onClick={() => void copyPostText()} aria-label="Copy post text">
          <Copy size={15} />
        </button>
        <button className="text-button" type="button" onClick={() => onOpenDetails(activity)}>
          View Details
        </button>
      </footer>
    </article>
  );
}

function ScrapedPostDetailsDrawer({
  activity,
  creator,
  profile,
  onClose,
}: {
  activity: ActivityResponse;
  creator?: CreatorResponse;
  profile?: CreatorProfileDetailsResponse;
  onClose: () => void;
}) {
  const name = profile?.name || activity.author_name || creator?.display_name || activity.creator_id;
  const postedText = cleanLinkedInVisibilityText(activity.posted_at_text || "recently");

  async function copyText(value: string) {
    await navigator.clipboard.writeText(value);
  }

  return (
    <div className="drawer-backdrop" onClick={onClose}>
      <aside
        className="post-detail-panel"
        role="dialog"
        aria-modal="true"
        aria-labelledby="post-detail-title"
        onClick={(event) => event.stopPropagation()}
      >
        <header className="drawer-header compact-header">
          <div>
            <h2 id="post-detail-title">Scraped Post Details</h2>
            <p>Review the scraped LinkedIn post before taking action.</p>
          </div>
          <button className="icon-button" type="button" onClick={onClose} aria-label="Close">
            <X size={19} />
          </button>
        </header>
        <div className="post-detail-body">
          <article className="post-detail-creator-card">
            <div className="post-author">
              <div className="avatar mini">
                {profile?.profile_image_url ? (
                  <img src={profile.profile_image_url} alt={`${name} profile`} />
                ) : (
                  initials(name)
                )}
              </div>
              <span>
                <strong>{name}</strong>
                <small>{profile?.headline || creator?.display_name || "Saved creator"}</small>
                {creator?.profile_url ? (
                  <a className="table-link" href={creator.profile_url} target="_blank" rel="noreferrer">
                    {creator.profile_url.replace(/^https?:\/\//, "")}
                  </a>
                ) : null}
              </span>
            </div>
            <div className="post-card-meta">
              <span>Posted {postedText}</span>
              <span>Fetched {compactDate(activity.fetched_at)}</span>
            </div>
          </article>

          <article className="post-detail-card">
            <div className="post-detail-card-title">
              <strong>Original Post</strong>
            </div>
            <p>{activity.raw_text}</p>
          </article>

          <section className="quick-action-grid">
            <h3>Quick Actions</h3>
            <button className="secondary-button compact" type="button" onClick={() => void copyText(activity.raw_text)}>
              <Copy size={15} />
              Copy Raw Text
            </button>
            <button
              className="secondary-button compact"
              type="button"
              onClick={() => void copyText(activity.post_url || "")}
              disabled={!activity.post_url}
            >
              <Copy size={15} />
              Copy Post URL
            </button>
            {activity.post_url ? (
              <a className="secondary-button compact" href={activity.post_url} target="_blank" rel="noreferrer">
                <ExternalLink size={15} />
                Open LinkedIn
              </a>
            ) : null}
            <button className="danger-button compact" type="button" disabled title="Backend delete endpoint needed">
              <Trash2 size={15} />
              Delete Scraped Post
            </button>
          </section>
        </div>
        <footer className="post-detail-footer">
          <button className="secondary-button" type="button" onClick={onClose}>
            Close
          </button>
        </footer>
      </aside>
    </div>
  );
}

function cleanLinkedInVisibilityText(value: string) {
  return value
    .replace(/\s*(?:-|\u2022)\s*Visible to anyone on or off LinkedIn/gi, "")
    .replace(/\s*Visible to anyone on or off LinkedIn/gi, "")
    .replace(/\s+/g, " ")
    .trim() || "recently";
}

function isWithinWindow(value: string, windowHours: number) {
  const time = new Date(value).getTime();
  if (Number.isNaN(time)) return true;
  return Date.now() - time <= windowHours * 60 * 60 * 1000;
}

function isFetchedWithinLastDay(activity: ActivityResponse) {
  const time = new Date(activity.fetched_at).getTime();
  if (Number.isNaN(time)) return false;
  return Date.now() - time <= 24 * 60 * 60 * 1000;
}
