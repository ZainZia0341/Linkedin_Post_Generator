"use client";

import Link from "next/link";
import {
  Building2,
  Copy,
  ExternalLink,
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
import { RunScrapingDialog } from "@/components/RunScrapingDialog";
import {
  DEFAULT_USER_ID,
  ENABLE_SCRAPING,
  deleteCreator,
  fetchCreatorActivities,
  fetchCreatorProfile,
  fetchUserData,
} from "@/lib/api";
import { compactDate, displayName, initials, previewText, sortThreads } from "@/lib/format";
import type { ActivityResponse, CreatorProfileDetailsResponse, CreatorResponse, UserDataResponse } from "@/lib/types";

export function CreatorDetailView({ creatorId }: { creatorId: string }) {
  const router = useRouter();
  const [userData, setUserData] = useState<UserDataResponse | null>(null);
  const [profile, setProfile] = useState<CreatorProfileDetailsResponse | null>(null);
  const [activities, setActivities] = useState<ActivityResponse[]>([]);
  const [showScrapeDialog, setShowScrapeDialog] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busyAction, setBusyAction] = useState("");
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
      const [data, profileResult, activityResult] = await Promise.allSettled([
        fetchUserData(DEFAULT_USER_ID),
        fetchCreatorProfile(DEFAULT_USER_ID, creatorId),
        fetchCreatorActivities(DEFAULT_USER_ID, creatorId, 1000),
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
  const profileUnavailable = profileLooksUnavailable(profile);
  const creatorName = safeCreatorName(profile, creator, creatorId);
  const profileHeadline = profileUnavailable
    ? "Profile not found or unavailable."
    : profile?.headline || "Profile details are not scraped yet.";
  const profileUrl = creator?.profile_url || profile?.profile_url || "";
  const profileEmail = profile?.email || "";
  const profileImageUrl = profileUnavailable ? "" : profile?.profile_image_url || "";
  const statusLabel = creator?.last_checked_at ? "Active" : "Never Scraped";
  const experienceItems = useMemo(() => parseExperience(profile?.experience ?? []), [profile?.experience]);
  const scrapeHistoryRows = useMemo(() => buildScrapeHistoryRows(creatorId, activities, creator), [activities, creator, creatorId]);

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

  async function copyProfileInfo() {
    await navigator.clipboard.writeText(
      formatCreatorProfileForClipboard({
        name: creatorName,
        headline: profileUnavailable ? "Profile not found or unavailable" : profile?.headline || "Not saved",
        about: profileUnavailable ? "Profile not found or unavailable" : profile?.about || "Not saved",
        experience: profileUnavailable
          ? "Profile not found or unavailable"
          : profile?.experience?.length
            ? profile.experience.join("\n")
            : "Not saved",
        location: profileUnavailable ? "Profile not found" : profile?.location || "Not saved",
        linkedIn: profileUrl || "Not saved",
        email: profileEmail || "Not saved",
      }),
    );
    showSuccess("Creator information copied");
  }

  return (
    <AppShell active="creators" title="Creators" userName={userName} threads={sortedThreads}>
      <section className="creator-profile-hero">
        <div className="breadcrumb">
          <Link href="/creators">Creators</Link>
          <span>/</span>
          <strong>{creatorName}</strong>
        </div>

        <div className="creator-profile-summary">
          <div className="creator-photo-wrap">
            <div className="creator-photo">
              {profileImageUrl ? <img src={profileImageUrl} alt={`${creatorName} profile`} /> : initials(creatorName)}
            </div>
            <span className="profile-online-dot" aria-hidden="true" />
          </div>
          <div className="creator-profile-copy">
            <div className="profile-title-row">
              <h2>{creatorName}</h2>
              <span className={creator?.last_checked_at ? "status-pill success" : "status-pill neutral"}>
                {statusLabel}
              </span>
            </div>
            <p>{profileHeadline}</p>
            <div className="action-row">
              <button
                className="primary-button compact"
                type="button"
                onClick={() => setShowScrapeDialog(true)}
                disabled={!ENABLE_SCRAPING}
                title={ENABLE_SCRAPING ? "Run scraping" : "Run scraping locally"}
              >
                <RefreshCw size={16} />
                Run Scraping
              </button>
              {profileUrl ? (
                <a className="secondary-button compact" href={profileUrl} target="_blank" rel="noreferrer">
                  <ExternalLink size={15} />
                  Open LinkedIn
                </a>
              ) : null}
            </div>
          </div>
          <button className="danger-button" type="button" onClick={removeCreator} disabled={Boolean(busyAction)}>
            {busyAction === "delete" ? <Loader2 className="spin" size={17} /> : <Trash2 size={17} />}
            Delete Creator
          </button>
        </div>
      </section>

      {error ? <div className="detail-error error-banner">{error}</div> : null}
      {loading ? <div className="detail-error empty-card slim">Loading creator...</div> : null}

      <section className="creator-info-layout">
        <article className="creator-info-card">
          <div className="section-heading-row">
            <h3>Creator Information</h3>
            <button className="text-button" type="button" onClick={copyProfileInfo}>
              <Copy size={14} />
              Copy Information
            </button>
          </div>

          <div className="creator-info-grid">
            <div className="creator-bio-column">
              <ProfileBlock label="Headline" value={profileUnavailable ? "Profile not found or unavailable" : profile?.headline || "No headline saved"} />
              <ProfileBlock label="About" value={profileUnavailable ? "LinkedIn did not expose a valid creator profile for this URL." : profile?.about || "No about section saved"} long />
            </div>
            <div className="creator-facts-column">
              <ProfileBlock label="Full Name" value={creatorName} />
              <ProfileBlock label="Location" value={profileUnavailable ? "Profile not found" : profile?.location || "Location not saved"} icon={<MapPin size={15} />} />
              <ProfileBlock label="Email" value={profileEmail || "Email not saved"} href={profileEmail ? `mailto:${profileEmail}` : ""} />
            </div>
          </div>

          <div className="profile-divider" />
          <div className="profile-experience-section">
            <h4>Experience</h4>
            {experienceItems.length ? (
              <div className="profile-experience-list">
                {experienceItems.map((item, index) => (
                  <div className="experience-row" key={`${item.title}-${item.company}-${index}`}>
                    <span><Building2 size={15} /></span>
                    <div>
                      <strong>{item.title}</strong>
                      {item.company ? <em>{item.company}</em> : null}
                      {item.period || item.location ? (
                        <small>
                          {item.period}
                          {item.period && item.location ? " - " : ""}
                          {item.location}
                        </small>
                      ) : null}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="empty-mini">Experience details are not saved yet.</div>
            )}
          </div>
        </article>

        <aside className="creator-detail-side">
          <article className="posts-found-card">
            <span>Posts Found (Last 24 Hours)</span>
            <strong>{creator?.new_count ?? 0}</strong>
            <small>{creator?.last_checked_at ? `Last scraped ${compactDate(creator.last_checked_at)}` : "No scrape yet"}</small>
          </article>
        </aside>
      </section>

      <section className="scrape-history-section">
        <div className="section-heading-row">
          <h2>Scrape History</h2>
        </div>

        <div className="creator-table-panel scrape-history-table">
          <div className="creator-table-wrap">
            <table className="creator-table">
              <thead>
                <tr>
                  <th>Scrape ID</th>
                  <th>Started</th>
                  <th>Completed</th>
                  <th>Time Window</th>
                  <th>Posts Found</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {scrapeHistoryRows.length ? (
                  scrapeHistoryRows.map((row) => (
                    <tr key={row.scrapeId}>
                      <td><span className="table-link">{row.scrapeId}</span></td>
                      <td>{compactDate(row.startedAt)}</td>
                      <td>{compactDate(row.completedAt)}</td>
                      <td>{row.timeWindow}</td>
                      <td><strong>{row.postsFound}</strong></td>
                      <td><span className="status-pill success">{row.status}</span></td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={6}>
                      <div className="empty-mini">No scrape history saved for this creator yet.</div>
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
          <div className="scrape-history-footer">
            <button type="button">Show all history</button>
          </div>
        </div>
      </section>

      {showScrapeDialog ? (
        <RunScrapingDialog
          creators={creator ? [creator] : userData?.creators ?? []}
          initialCreatorIds={[creatorId]}
          lockSelection
          onClose={() => setShowScrapeDialog(false)}
          onComplete={(response) => {
            setShowScrapeDialog(false);
            showSuccess(`${response.activities.length} post${response.activities.length === 1 ? "" : "s"} scraped`);
            void load();
          }}
        />
      ) : null}

      {successMessage ? (
        <div className="success-toast" role="status">
          <ShieldCheck size={22} />
          <span>{successMessage}</span>
        </div>
      ) : null}
    </AppShell>
  );
}

function ProfileBlock({
  label,
  value,
  icon,
  href,
  long = false,
}: {
  label: string;
  value: string;
  icon?: ReactNode;
  href?: string;
  long?: boolean;
}) {
  return (
    <div className={long ? "profile-block long" : "profile-block"}>
      <span>{label}</span>
      {href ? (
        <a href={href} target="_blank" rel="noreferrer">
          {icon}
          {value.replace(/^https?:\/\//, "")}
        </a>
      ) : (
        <strong>
          {icon}
          {value}
        </strong>
      )}
    </div>
  );
}

type ExperienceItem = {
  title: string;
  company: string;
  period: string;
  location: string;
};

function profileLooksUnavailable(profile: CreatorProfileDetailsResponse | null) {
  if (!profile) return false;
  return isBadScrapedText(profile.name) || isBadScrapedText(profile.headline);
}

function isBadScrapedText(value?: string) {
  const text = (value || "").trim().toLowerCase();
  if (!text) return false;
  if (text === "0 notifications" || text === "skip to main content") return true;
  if (/^\d+\s+notifications?$/.test(text)) return true;
  return text.includes("skip to main content") || text.includes("profile not found") || text.includes("page not found");
}

function safeCreatorName(
  profile: CreatorProfileDetailsResponse | null,
  creator: CreatorResponse | undefined,
  creatorId: string,
) {
  if (profile?.name && !isBadScrapedText(profile.name)) return profile.name;
  return creator?.display_name || creatorId;
}

function formatCreatorProfileForClipboard(profile: {
  name: string;
  headline: string;
  about: string;
  experience: string;
  location: string;
  linkedIn: string;
  email: string;
}) {
  return [
    "Name",
    profile.name,
    "",
    "Headline",
    profile.headline,
    "",
    "About",
    profile.about,
    "",
    "Experience",
    profile.experience,
    "",
    "Location",
    profile.location,
    "",
    "LinkedIn",
    profile.linkedIn,
    "",
    "Email",
    profile.email,
  ].join("\n");
}

type ScrapeHistoryRow = {
  scrapeId: string;
  startedAt: string;
  completedAt: string;
  timeWindow: string;
  postsFound: number;
  status: string;
};

function buildScrapeHistoryRows(
  creatorId: string,
  activities: ActivityResponse[],
  creator?: CreatorResponse,
): ScrapeHistoryRow[] {
  const grouped = new Map<string, ActivityResponse[]>();
  activities.forEach((activity) => {
    const date = new Date(activity.fetched_at);
    const key = Number.isNaN(date.getTime())
      ? activity.fetched_at
      : date.toISOString().slice(0, 16);
    grouped.set(key, [...(grouped.get(key) ?? []), activity]);
  });

  const rows = Array.from(grouped.values()).map((items) => {
    const sorted = [...items].sort((left, right) => new Date(left.fetched_at).getTime() - new Date(right.fetched_at).getTime());
    const startedAt = sorted[0]?.fetched_at || "";
    const completedAt = sorted[sorted.length - 1]?.fetched_at || startedAt;
    return {
      scrapeId: scrapeId(creatorId, completedAt),
      startedAt,
      completedAt,
      timeWindow: "24 Hours",
      postsFound: items.length,
      status: "Completed",
    };
  });

  if (!rows.length && creator?.last_checked_at) {
    rows.push({
      scrapeId: scrapeId(creatorId, creator.last_checked_at),
      startedAt: creator.last_checked_at,
      completedAt: creator.last_checked_at,
      timeWindow: "24 Hours",
      postsFound: creator.new_count ?? 0,
      status: "Completed",
    });
  }

  return rows.sort((left, right) => new Date(right.completedAt).getTime() - new Date(left.completedAt).getTime());
}

function scrapeId(creatorId: string, value: string) {
  const date = new Date(value);
  const stamp = Number.isNaN(date.getTime())
    ? "latest"
    : date.toISOString().replace(/\D/g, "").slice(0, 12);
  return `SCR-${creatorId.slice(0, 4).toUpperCase()}-${stamp}`;
}

function parseExperience(experience: string[]): ExperienceItem[] {
  const lines = experience
    .flatMap((item) => item.split(/\n+/))
    .map((item) => item.replace(/\s+/g, " ").trim())
    .filter(Boolean);
  const datePattern = /\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\b|\b(?:19|20)\d{2}\b|Present/i;
  const items: ExperienceItem[] = [];

  for (let index = 0; index < lines.length - 1 && items.length < 8; index += 1) {
    const title = lines[index];
    const company = lines[index + 1] || "";
    const period = lines[index + 2] || "";
    const location = lines[index + 3] || "";
    const looksLikeTitle = title.length <= 90 && !datePattern.test(title) && !title.includes("http") && !title.endsWith(".");
    const looksLikeCompany = company.length <= 100 && !company.includes("http") && !company.endsWith(".");
    const hasDateNearby = datePattern.test(company) || datePattern.test(period);

    if (!looksLikeTitle || !looksLikeCompany || !hasDateNearby) continue;

    items.push({
      title,
      company: datePattern.test(company) ? "" : company,
      period: datePattern.test(company) ? company : period,
      location: !datePattern.test(location) && location.length <= 90 ? location : "",
    });
    index += datePattern.test(company) ? 1 : 2;
  }

  if (items.length) return items;

  return experience
    .map((item) => item.replace(/\s+/g, " ").trim())
    .filter(Boolean)
    .slice(0, 5)
    .map((item) => ({
      title: previewText(item, 90),
      company: "",
      period: "",
      location: "",
    }));
}
