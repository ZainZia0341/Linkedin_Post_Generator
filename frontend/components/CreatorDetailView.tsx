"use client";

import Link from "next/link";
import {
  Calendar,
  Copy,
  ExternalLink,
  Info,
  Loader2,
  MapPin,
  RefreshCw,
  ShieldCheck,
  Trash2,
} from "lucide-react";
import type { ReactNode } from "react";
import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import {
  DEFAULT_USER_ID,
  deleteCreator,
  fetchCreatorActivities,
  fetchCreatorProfile,
  fetchUserData,
  scrapeCreatorRecent24h,
} from "@/lib/api";
import { compactDate, displayName, initials, previewText, sortThreads } from "@/lib/format";
import type { ActivityResponse, CreatorProfileDetailsResponse, CreatorResponse, UserDataResponse } from "@/lib/types";

export function CreatorDetailView({ creatorId }: { creatorId: string }) {
  const router = useRouter();
  const [userData, setUserData] = useState<UserDataResponse | null>(null);
  const [profile, setProfile] = useState<CreatorProfileDetailsResponse | null>(null);
  const [activities, setActivities] = useState<ActivityResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [busyAction, setBusyAction] = useState("");
  const [error, setError] = useState("");

  async function load() {
    setLoading(true);
    setError("");
    try {
      const [data, profileResult, activityResult] = await Promise.allSettled([
        fetchUserData(DEFAULT_USER_ID),
        fetchCreatorProfile(DEFAULT_USER_ID, creatorId),
        fetchCreatorActivities(DEFAULT_USER_ID, creatorId, 20),
      ]);
      if (data.status === "fulfilled") setUserData(data.value);
      if (profileResult.status === "fulfilled") setProfile(profileResult.value);
      if (activityResult.status === "fulfilled") setActivities(activityResult.value);
      if (data.status === "rejected") throw data.reason;
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Could not load creator.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, [creatorId]);

  const creator = useMemo<CreatorResponse | undefined>(() => {
    return userData?.creators.find((item) => item.creator_id === creatorId);
  }, [creatorId, userData?.creators]);
  const sortedThreads = useMemo(() => sortThreads(userData?.threads ?? []), [userData?.threads]);
  const userName = displayName(userData?.user) || DEFAULT_USER_ID;
  const creatorName = profile?.name || creator?.display_name || creatorId;
  const profileUrl = creator?.profile_url || profile?.profile_url || "";
  const profileImageUrl = profile?.profile_image_url || "";
  const latestActivity = activities[0];

  async function runScrape() {
    setBusyAction("scrape");
    setError("");
    try {
      await scrapeCreatorRecent24h(DEFAULT_USER_ID, creatorId);
      await load();
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Could not run scraper.");
    } finally {
      setBusyAction("");
    }
  }

  async function removeCreator() {
    const confirmed = window.confirm(`Delete ${creatorName}?`);
    if (!confirmed) return;
    setBusyAction("delete");
    setError("");
    try {
      await deleteCreator(DEFAULT_USER_ID, creatorId);
      router.push("/creators");
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Could not delete creator.");
      setBusyAction("");
    }
  }

  async function copyUrl() {
    if (!profileUrl) return;
    await navigator.clipboard.writeText(profileUrl);
  }

  return (
    <AppShell
      active="creators"
      title="Creators"
      subtitle=""
      userName={userName}
      threads={sortedThreads}
    >
      <section className="creator-detail-header">
        <div className="breadcrumb">
          <Link href="/creators">Creators</Link>
          <span>/</span>
          <strong>{creatorName}</strong>
        </div>
        <div className="creator-profile-line">
          <div className="creator-photo">
            {profileImageUrl ? (
              <img src={profileImageUrl} alt={`${creatorName} profile`} />
            ) : (
              initials(creatorName)
            )}
          </div>
          <div>
            <h2>{creatorName}</h2>
            <p>{profile?.headline || "Profile details are not scraped yet."}</p>
            {profileUrl ? (
              <a className="secondary-button compact" href={profileUrl} target="_blank" rel="noreferrer">
                <ExternalLink size={15} />
                Open LinkedIn
              </a>
            ) : null}
          </div>
          <span className={creator?.last_checked_at ? "status-pill success" : "status-pill neutral"}>
            {creator?.last_checked_at ? "Up To Date" : "Never Scraped"}
          </span>
        </div>
        <div className="creator-detail-actions">
          <button className="primary-button" type="button" onClick={runScrape} disabled={Boolean(busyAction)}>
            {busyAction === "scrape" ? <Loader2 className="spin" size={17} /> : <RefreshCw size={17} />}
            Run 24h Scrape
          </button>
          <button className="danger-button" type="button" onClick={removeCreator} disabled={Boolean(busyAction)}>
            <Trash2 size={17} />
            Delete Creator
          </button>
        </div>
      </section>

      {error ? <div className="detail-error error-banner">{error}</div> : null}
      {loading ? <div className="detail-error empty-card slim">Loading creator...</div> : null}

      <section className="creator-detail-grid">
        <article className="detail-card profile-info-card">
          <div className="section-heading-row">
            <h3>Profile Info</h3>
            <Info size={18} />
          </div>
          <div className="profile-field">
            <span>Headline</span>
            <strong>{profile?.headline || "No headline saved"}</strong>
          </div>
          <div className="detail-two-col">
            <div className="profile-field">
              <span>Location</span>
              <strong><MapPin size={16} /> {profile?.location || "Location not saved"}</strong>
            </div>
            <div className="profile-field">
              <span>Creator Since</span>
              <strong><Calendar size={16} /> {creator?.added_at ? compactDate(creator.added_at) : "Unknown"}</strong>
            </div>
          </div>
          <div className="profile-field">
            <span>URL</span>
            {profileUrl ? (
              <a className="table-link" href={profileUrl} target="_blank" rel="noreferrer">
                {profileUrl.replace(/^https?:\/\//, "")}
              </a>
            ) : (
              <strong>No URL</strong>
            )}
          </div>
          <div className="profile-footer-row">
            <span>Last Checked</span>
            <strong>{creator?.last_checked_at ? compactDate(creator.last_checked_at) : "Never"}</strong>
          </div>
        </article>

        <article className="detail-card tracking-card">
          <div className="section-heading-row">
            <h3>Tracking Status</h3>
            <span className="status-pill success">Active</span>
          </div>
          <div className="tracking-grid">
            <StatusTile label="Next Scrape" value="API needed" />
            <StatusTile label="Latest Activity" value={latestActivity ? compactDate(latestActivity.fetched_at) : "No activity"} />
            <StatusTile label="Posts Found 24h" value={(creator?.new_count ?? 0).toString()} large />
            <StatusTile label="Tracking Enabled" value="Encrypted" dark icon={<ShieldCheck size={18} />} />
          </div>
        </article>

        <article className="detail-card quick-actions-card">
          <h3>Quick Actions</h3>
          <button type="button" onClick={runScrape} disabled={Boolean(busyAction)}>
            <RefreshCw size={18} />
            Run Scrape
          </button>
          {profileUrl ? (
            <a href={profileUrl} target="_blank" rel="noreferrer">
              <ExternalLink size={18} />
              Open LinkedIn
            </a>
          ) : null}
          <button type="button" onClick={copyUrl} disabled={!profileUrl}>
            <Copy size={18} />
            Copy URL
          </button>
          <button className="danger-action" type="button" onClick={removeCreator}>
            <Trash2 size={18} />
            Delete
          </button>
        </article>
      </section>

      <section className="scrape-history-section">
        <div className="section-heading-row">
          <h2>Scrape History</h2>
          <div className="filter-tabs compact-tabs">
            <button className="selected" type="button">All Time</button>
            <button type="button" disabled>Last 30 Days</button>
          </div>
        </div>

        <div className="creator-table-panel">
          <div className="empty-card slim">
            Scrape history needs a backend history endpoint. Recent saved posts for this creator are shown below.
          </div>
          <div className="creator-table-wrap">
            <table className="creator-table">
              <thead>
                <tr>
                  <th>Fetched</th>
                  <th>Post</th>
                  <th>Posted</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {activities.length ? (
                  activities.slice(0, 5).map((activity) => (
                    <tr key={activity.post_id}>
                      <td>{compactDate(activity.fetched_at)}</td>
                      <td>{previewText(activity.raw_text, 110)}</td>
                      <td>{activity.posted_at_text || "-"}</td>
                      <td>
                        {activity.post_url ? (
                          <a className="text-button" href={activity.post_url} target="_blank" rel="noreferrer">Open</a>
                        ) : (
                          "-"
                        )}
                      </td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={4}>
                      <div className="empty-mini">No saved creator posts yet.</div>
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </section>
    </AppShell>
  );
}

function StatusTile({
  label,
  value,
  large = false,
  dark = false,
  icon,
}: {
  label: string;
  value: string;
  large?: boolean;
  dark?: boolean;
  icon?: ReactNode;
}) {
  return (
    <div className={dark ? "status-tile dark" : "status-tile"}>
      <span>{label}</span>
      <strong className={large ? "large" : ""}>
        {icon}
        {value}
      </strong>
    </div>
  );
}
