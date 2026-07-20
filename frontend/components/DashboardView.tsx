"use client";

import Link from "next/link";
import { ArrowRight, Brain, ExternalLink, RefreshCw, Sparkles } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { DEFAULT_USER_ID, ENABLE_SCRAPING, fetchRecentActivities, fetchUserData } from "@/lib/api";
import {
  activityTitle,
  compactDate,
  displayName,
  firstName,
  greeting,
  initials,
  previewText,
  sortThreads,
  threadTitle,
} from "@/lib/format";
import type { ActivityResponse, RecentActivitiesResponse, UserDataResponse } from "@/lib/types";
import { AppShell } from "@/components/AppShell";

type LoadState = "loading" | "ready" | "offline";

export function DashboardView() {
  const [userData, setUserData] = useState<UserDataResponse | null>(null);
  const [recentActivities, setRecentActivities] = useState<RecentActivitiesResponse | null>(null);
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;

    async function loadDashboard() {
      setLoadState("loading");
      setError("");
      try {
        const [userResult, recentResult] = await Promise.all([
          fetchUserData(DEFAULT_USER_ID),
          fetchRecentActivities(DEFAULT_USER_ID, 3),
        ]);

        if (cancelled) return;
        setUserData(userResult);
        setRecentActivities(recentResult);
        setLoadState("ready");
      } catch (exc) {
        if (cancelled) return;
        setError(exc instanceof Error ? exc.message : "Could not load dashboard data.");
        setLoadState("offline");
      }
    }

    void loadDashboard();
    return () => {
      cancelled = true;
    };
  }, []);

  const threads = userData?.threads ?? [];
  const creators = userData?.creators ?? [];
  const recent = recentActivities?.activities ?? [];
  const sortedThreads = useMemo(() => sortThreads(threads), [threads]);
  const userName = displayName(userData?.user) || DEFAULT_USER_ID;
  const stats = userData?.dashboard_stats;
  const creatorCount = stats?.creator_count ?? creators.length;
  const threadCount = stats?.thread_count ?? threads.length;
  const newPostsToday = stats?.new_posts_today_count ?? recent.length;
  const hasRecentPosts = recent.length > 0;
  const recentPostThreads = sortedThreads.filter((thread) => thread.topic_source !== "comment_generation");

  return (
    <AppShell
      active="dashboard"
      title="Dashboard"
      subtitle="Manage your LinkedIn workflow from one place."
      userName={userName}
      threads={sortedThreads}
    >
      <section className="page-section hero-row">
        <div>
          <h2>
            {greeting()}, {firstName(userData?.user) || userName}
          </h2>
          {loadState === "offline" ? <p className="status-note">API unavailable: {error}</p> : null}
        </div>
        <div className="action-row">
          <Link className="secondary-button" href="/brainstorm">
            <Brain size={17} />
            Brainstorm Ideas
          </Link>
          <Link className="primary-button" href="/generate">
            <Sparkles size={17} />
            Generate Post
          </Link>
        </div>
      </section>

      <section className="metric-grid" aria-label="Dashboard metrics">
        <MetricCard label="Creators Following" value={creatorCount.toString()} />
        <MetricCard label="Threads Generated" value={threadCount.toString()} />
        <MetricCard label="New Posts Today" value={hasRecentPosts || newPostsToday ? newPostsToday.toString() : "Run scraper"} accent={!hasRecentPosts} />
      </section>

      <div className="dashboard-grid">
        <div className="dashboard-main">
          {loadState === "loading" ? <div className="empty-card slim">Loading dashboard data...</div> : null}

          <section className="page-section section-heading-row">
            <h3>Continue Working</h3>
            <Link className="text-button" href="/content">View all drafts</Link>
          </section>

          <section className="draft-grid">
            {recentPostThreads.length ? (
              recentPostThreads.slice(0, 2).map((thread) => (
                <article className="work-card" key={thread.thread_id}>
                  <div className="pill">{compactDate(thread.updated_at) || "Recent"}</div>
                  <h4>{threadTitle(thread)}</h4>
                  <p>{thread.generation_style || "Generated LinkedIn post"}</p>
                  <Link href={`/generate?thread_id=${encodeURIComponent(thread.thread_id)}`}>
                    Resume Editing <ArrowRight size={15} />
                  </Link>
                </article>
              ))
            ) : (
              <article className="empty-card">
                <h4>No drafts yet</h4>
                <p>Generated posts will show here for quick editing.</p>
                <Link className="primary-button compact" href="/generate">Create first post</Link>
              </article>
            )}
          </section>

          <section className="page-section section-heading-row activity-heading">
            <h3>Latest Creator Activity</h3>
            <Link className="text-button" href="/creators">Manage creators</Link>
          </section>

          <section className="creator-activity-grid">
            {recent.length ? (
              recent.slice(0, 3).map((activity) => (
                <ActivityCard activity={activity} key={`${activity.creator_id}-${activity.post_id}`} />
              ))
            ) : (
              <article className="empty-card wide">
                <h4>No saved posts in the current 24-hour window</h4>
                <p>Run the scraper from the backend workflow to fill this list.</p>
                <button
                  className="secondary-button compact"
                  type="button"
                  disabled={!ENABLE_SCRAPING}
                  title={ENABLE_SCRAPING ? "Run scraper" : "Run scraping locally"}
                >
                  <RefreshCw size={15} />
                  Run scraper
                </button>
              </article>
            )}
          </section>
        </div>

        <aside className="recent-panel">
          <h3>Recent Threads</h3>
          {recentPostThreads.length ? (
            <div className="timeline">
              {recentPostThreads.slice(0, 5).map((thread) => (
                <Link
                  className="timeline-item"
                  href={`/generate?thread_id=${encodeURIComponent(thread.thread_id)}`}
                  key={thread.thread_id}
                >
                  <span />
                  <div>
                    <strong>{threadTitle(thread)}</strong>
                    <small>{compactDate(thread.updated_at) || "Recent"}</small>
                  </div>
                </Link>
              ))}
            </div>
          ) : (
            <div className="empty-mini">Generated posts will show here.</div>
          )}
        </aside>
      </div>

      <div className="sr-only" aria-live="polite">
        {loadState === "loading" ? "Loading dashboard" : "Dashboard loaded"}
      </div>
    </AppShell>
  );
}

function MetricCard({ label, value, accent = false }: { label: string; value: string; accent?: boolean }) {
  return (
    <article className={accent ? "metric-card action-needed" : "metric-card"}>
      <span>{label}</span>
      <strong>{value}</strong>
    </article>
  );
}

function ActivityCard({ activity }: { activity: ActivityResponse }) {
  const name = activityTitle(activity);
  return (
    <article className="creator-card">
      <div className="avatar mini">{initials(name)}</div>
      <div>
        <h4>{name}</h4>
        <p>{previewText(activity.raw_text, 72)}</p>
      </div>
      <a href={activity.post_url || "#"} aria-label={`Open ${name} activity`} title="Open activity">
        <ExternalLink size={15} />
      </a>
    </article>
  );
}
