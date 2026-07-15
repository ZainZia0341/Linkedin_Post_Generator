"use client";

import Link from "next/link";
import {
  ArrowDown,
  ArrowUp,
  CheckCircle2,
  Copy,
  ExternalLink,
  FileUp,
  FileText,
  Info,
  Loader2,
  Plus,
  Search,
  Trash2,
  UploadCloud,
  Users,
  X,
} from "lucide-react";
import type { ReactNode } from "react";
import { useEffect, useMemo, useState } from "react";
import { AppShell } from "@/components/AppShell";
import {
  DEFAULT_USER_ID,
  ENABLE_SCRAPING,
  addCreator,
  deleteCreator,
  fetchCreatorProfiles,
  fetchUserData,
  getCachedCreatorProfiles,
  getCachedUserData,
  importCreators,
  previewCreatorImport,
  scrapeCreatorProfiles,
} from "@/lib/api";
import { compactDate, displayName, initials, sortThreads } from "@/lib/format";
import type {
  BulkCreatorImportResponse,
  BulkCreatorPreviewResponse,
  CreatorProfileDetailsResponse,
  CreatorResponse,
  UserDataResponse,
} from "@/lib/types";

type ModalMode = "single" | "bulk" | null;
type LastCheckedSort = "desc" | "asc";
type CreatorSortBy = "recently_added" | "last_checked_desc" | "last_checked_asc" | "name_asc" | "new_posts_desc";
const PAGE_SIZE = 10;

export function CreatorsView() {
  const [userData, setUserData] = useState<UserDataResponse | null>(() => getCachedUserData(DEFAULT_USER_ID));
  const [profileMap, setProfileMap] = useState<Map<string, CreatorProfileDetailsResponse>>(() => {
    const cachedProfiles = getCachedCreatorProfiles(DEFAULT_USER_ID, 500);
    return new Map((cachedProfiles ?? []).map((profile) => [profile.creator_id, profile]));
  });
  const [query, setQuery] = useState("");
  const [lastCheckedSort, setLastCheckedSort] = useState<LastCheckedSort>("desc");
  const [sortBy, setSortBy] = useState<CreatorSortBy>("recently_added");
  const [selectedCreatorIds, setSelectedCreatorIds] = useState<Set<string>>(new Set());
  const [page, setPage] = useState(1);
  const [modalMode, setModalMode] = useState<ModalMode>(null);
  const [loading, setLoading] = useState(() => !getCachedUserData(DEFAULT_USER_ID));
  const [deletingCreatorIds, setDeletingCreatorIds] = useState<Set<string>>(new Set());
  const [error, setError] = useState("");
  const [successMessage, setSuccessMessage] = useState("");

  function showSuccess(message: string) {
    setSuccessMessage(message);
    window.setTimeout(() => setSuccessMessage(""), 2000);
  }

  async function load() {
    if (!getCachedUserData(DEFAULT_USER_ID)) setLoading(true);
    setError("");
    try {
      const [dataResult, profileResult] = await Promise.allSettled([
        fetchUserData(DEFAULT_USER_ID),
        fetchCreatorProfiles(DEFAULT_USER_ID, 500),
      ]);
      if (dataResult.status === "rejected") throw dataResult.reason;
      setUserData(dataResult.value);
      if (profileResult.status === "fulfilled") {
        setProfileMap(new Map(profileResult.value.map((profile) => [profile.creator_id, profile])));
      }
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Could not load creators.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  useEffect(() => {
    setPage(1);
  }, [query, sortBy]);

  const creators = userData?.creators ?? [];
  const sortedThreads = useMemo(() => sortThreads(userData?.threads ?? []), [userData?.threads]);
  const userName = displayName(userData?.user) || DEFAULT_USER_ID;
  const filteredCreators = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    return creators.filter((creator) => {
      const profile = profileMap.get(creator.creator_id);
      const text = [
        safeProfileName(profile, creator),
        safeProfileHeadline(profile, creator),
        creator.display_name,
        creator.creator_id,
        creator.profile_url,
      ].join(" ").toLowerCase();
      const matchesQuery = !normalized || text.includes(normalized);
      return matchesQuery;
    }).sort((left, right) => compareCreators(left, right, sortBy, profileMap));
  }, [creators, profileMap, query, sortBy]);
  const totalPages = Math.max(1, Math.ceil(filteredCreators.length / PAGE_SIZE));
  const safePage = Math.min(page, totalPages);
  const pageStart = filteredCreators.length ? (safePage - 1) * PAGE_SIZE : 0;
  const pageEnd = Math.min(pageStart + PAGE_SIZE, filteredCreators.length);
  const visibleCreators = filteredCreators.slice(pageStart, pageEnd);
  const visibleCreatorIds = visibleCreators.map((creator) => creator.creator_id);
  const allVisibleSelected = visibleCreatorIds.length > 0 && visibleCreatorIds.every((creatorId) => selectedCreatorIds.has(creatorId));
  const someVisibleSelected = visibleCreatorIds.some((creatorId) => selectedCreatorIds.has(creatorId));
  const selectedCreators = creators.filter((creator) => selectedCreatorIds.has(creator.creator_id));

  const stats = userData?.dashboard_stats;

  function toggleVisibleCreators() {
    setSelectedCreatorIds((current) => {
      const next = new Set(current);
      if (allVisibleSelected) {
        visibleCreatorIds.forEach((creatorId) => next.delete(creatorId));
      } else {
        visibleCreatorIds.forEach((creatorId) => next.add(creatorId));
      }
      return next;
    });
  }

  function toggleCreatorSelection(creatorId: string) {
    setSelectedCreatorIds((current) => {
      const next = new Set(current);
      if (next.has(creatorId)) {
        next.delete(creatorId);
      } else {
        next.add(creatorId);
      }
      return next;
    });
  }

  function changeCreatorSort(nextSort: CreatorSortBy) {
    setSortBy(nextSort);
    if (nextSort === "last_checked_desc") setLastCheckedSort("desc");
    if (nextSort === "last_checked_asc") setLastCheckedSort("asc");
  }

  async function copyCreatorProfile(creator: CreatorResponse) {
    await navigator.clipboard.writeText(formatCreatorForClipboard(creator, profileMap.get(creator.creator_id)));
    showSuccess("Creator profile copied");
  }

  async function copySelectedProfiles() {
    if (!selectedCreators.length) return;
    const text = selectedCreators
      .map((creator, index) => formatCreatorForClipboard(creator, profileMap.get(creator.creator_id), index + 1))
      .join("\n\n");
    await navigator.clipboard.writeText(text);
    showSuccess(`${selectedCreators.length} creator profile${selectedCreators.length === 1 ? "" : "s"} copied`);
  }

  function removeCreatorsFromLocalState(creatorIds: string[]) {
    const creatorIdSet = new Set(creatorIds);
    setUserData((current) => {
      if (!current) return current;
      const nextCreators = current.creators.filter((creator) => !creatorIdSet.has(creator.creator_id));
      return {
        ...current,
        creators: nextCreators,
        dashboard_stats: {
          ...current.dashboard_stats,
          creator_count: nextCreators.length,
        },
      };
    });
    setProfileMap((current) => {
      const next = new Map(current);
      creatorIds.forEach((creatorId) => next.delete(creatorId));
      return next;
    });
    setSelectedCreatorIds((current) => {
      const next = new Set(current);
      creatorIds.forEach((creatorId) => next.delete(creatorId));
      return next;
    });
  }

  async function deleteCreators(creatorIds: string[]) {
    const uniqueCreatorIds = Array.from(new Set(creatorIds)).filter(Boolean);
    if (!uniqueCreatorIds.length) return;
    const confirmed = window.confirm(
      uniqueCreatorIds.length === 1
        ? "Delete this creator and their saved posts?"
        : `Delete ${uniqueCreatorIds.length} creators and their saved posts?`,
    );
    if (!confirmed) return;

    setDeletingCreatorIds(new Set(uniqueCreatorIds));
    setError("");
    const results = await Promise.allSettled(
      uniqueCreatorIds.map((creatorId) => deleteCreator(DEFAULT_USER_ID, creatorId)),
    );
    const deletedIds = uniqueCreatorIds.filter((_, index) => results[index].status === "fulfilled");
    const failedCount = results.length - deletedIds.length;
    if (deletedIds.length) {
      removeCreatorsFromLocalState(deletedIds);
      showSuccess(`${deletedIds.length} creator${deletedIds.length === 1 ? "" : "s"} deleted`);
    }
    if (failedCount) {
      const firstError = results.find((result) => result.status === "rejected");
      setError(
        firstError?.status === "rejected" && firstError.reason instanceof Error
          ? firstError.reason.message
          : `${failedCount} creator${failedCount === 1 ? "" : "s"} could not be deleted.`,
      );
    }
    setDeletingCreatorIds(new Set());
  }

  return (
    <AppShell
      active="creators"
      title="Creators"
      subtitle="Track LinkedIn creators, monitor activity, and prepare them for scraping."
      userName={userName}
      threads={sortedThreads}
    >
      <section className="creator-page-actions">
        <div />
        <div className="action-row">
          <button className="secondary-button" type="button" onClick={() => setModalMode("bulk")}>
            <FileUp size={17} />
            Import Creators
          </button>
          <button className="primary-button" type="button" onClick={() => setModalMode("single")}>
            <Plus size={17} />
            Add Creator
          </button>
        </div>
      </section>

      <section className="creator-metric-grid">
        <CreatorMetric icon={<Users size={20} />} label="Total Creators" value={(stats?.creator_count ?? 0).toString()} />
        <CreatorMetric icon={<FileText size={20} />} label="New post (last 24 h)" value={(stats?.new_posts_today_count ?? 0).toString()} />
        <CreatorMetric icon={<Plus size={20} />} label="Recently Added" value={(stats?.recently_added_count ?? 0).toString()} />
      </section>

      <section className="creator-table-panel">
        <div className="creator-table-toolbar">
          <label className="creator-search">
            <Search size={18} />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search by name, handle, or URL..."
            />
          </label>

          <label className="sort-control">
            <span>Sort by:</span>
            <select value={sortBy} onChange={(event) => changeCreatorSort(event.target.value as CreatorSortBy)}>
              <option value="recently_added">Recently Added</option>
              <option value="last_checked_desc">Last Checked Newest</option>
              <option value="last_checked_asc">Last Checked Oldest</option>
              <option value="new_posts_desc">New Posts</option>
              <option value="name_asc">Name A-Z</option>
            </select>
          </label>

          <div className="selection-copy-row">
            <span>{selectedCreators.length} selected</span>
            <button
              className="secondary-button compact"
              type="button"
              onClick={() => void copySelectedProfiles()}
              disabled={!selectedCreators.length}
            >
              <Copy size={14} />
              Copy
            </button>
            <button
              className="danger-button compact"
              type="button"
              onClick={() => void deleteCreators(selectedCreators.map((creator) => creator.creator_id))}
              disabled={!selectedCreators.length || deletingCreatorIds.size > 0}
            >
              {deletingCreatorIds.size > 0 ? <Loader2 className="spin" size={14} /> : <Trash2 size={14} />}
              Delete
            </button>
          </div>
        </div>

        {error ? <div className="error-banner">{error}</div> : null}
        {loading ? <div className="empty-card slim">Loading creators...</div> : null}

        <div className="creator-table-wrap">
          <table className="creator-table">
            <thead>
              <tr>
                <th className="select-column">
                  <input
                    type="checkbox"
                    checked={allVisibleSelected}
                    ref={(node) => {
                      if (node) node.indeterminate = !allVisibleSelected && someVisibleSelected;
                    }}
                    onChange={toggleVisibleCreators}
                    aria-label="Select visible creators"
                  />
                </th>
                <th>Creator</th>
                <th>Headline</th>
                <th>LinkedIn URL</th>
                <th>
                  <button
                    className="sortable-heading"
                    type="button"
                    onClick={() => {
                      const nextSort = lastCheckedSort === "desc" ? "asc" : "desc";
                      setLastCheckedSort(nextSort);
                      changeCreatorSort(nextSort === "desc" ? "last_checked_desc" : "last_checked_asc");
                    }}
                    aria-label={`Sort last checked ${lastCheckedSort === "desc" ? "ascending" : "descending"}`}
                  >
                    Last Checked
                    {lastCheckedSort === "desc" ? <ArrowDown size={13} /> : <ArrowUp size={13} />}
                  </button>
                </th>
                <th>New post (last 24 h)</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {visibleCreators.length ? (
                visibleCreators.map((creator) => (
                  <CreatorRow
                    creator={creator}
                    profile={profileMap.get(creator.creator_id)}
                    selected={selectedCreatorIds.has(creator.creator_id)}
                    deleting={deletingCreatorIds.has(creator.creator_id)}
                    onToggleSelected={toggleCreatorSelection}
                    onCopyProfile={copyCreatorProfile}
                    onDeleteCreator={(creatorId) => void deleteCreators([creatorId])}
                    key={creator.creator_id}
                  />
                ))
              ) : (
                <tr>
                  <td colSpan={7}>
                    <div className="empty-mini">No creators found.</div>
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        <div className="table-footer">
          <span>
            Showing {filteredCreators.length ? pageStart + 1 : 0} to {pageEnd} of {filteredCreators.length} creators
          </span>
          <div className="pagination-controls" aria-label="Creator pagination">
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
      </section>

      {modalMode === "single" ? (
        <AddCreatorDialog
          onClose={() => setModalMode(null)}
          onAdded={(message) => {
            setModalMode(null);
            showSuccess(message);
            void load();
          }}
        />
      ) : null}

      {modalMode === "bulk" ? (
        <BulkImportDialog
          onClose={() => setModalMode(null)}
          onImported={(message) => {
            setModalMode(null);
            showSuccess(message);
            void load();
          }}
          onDataChanged={() => {
            void load();
          }}
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

function CreatorMetric({
  icon,
  label,
  value,
  urgent = false,
}: {
  icon: ReactNode;
  label: string;
  value: string;
  urgent?: boolean;
}) {
  return (
    <article className="creator-metric-card">
      <div className={urgent ? "metric-icon urgent" : "metric-icon"}>{icon}</div>
      <span>{label}</span>
      <strong>{value}</strong>
    </article>
  );
}

function compareCreators(
  left: CreatorResponse,
  right: CreatorResponse,
  sortBy: CreatorSortBy,
  profileMap: Map<string, CreatorProfileDetailsResponse>,
) {
  if (sortBy === "recently_added") {
    return compareNewestFirst(left.added_at, right.added_at, () => compareNames(left, right, profileMap));
  }
  if (sortBy === "last_checked_asc") {
    return compareLastChecked(left, right, "asc");
  }
  if (sortBy === "last_checked_desc") {
    return compareLastChecked(left, right, "desc");
  }
  if (sortBy === "new_posts_desc") {
    const countDiff = (right.new_count ?? 0) - (left.new_count ?? 0);
    return countDiff || compareLastChecked(left, right, "desc");
  }
  return compareNames(left, right, profileMap);
}

function compareLastChecked(left: CreatorResponse, right: CreatorResponse, direction: LastCheckedSort) {
  const leftTime = lastCheckedTime(left);
  const rightTime = lastCheckedTime(right);
  if (leftTime === null && rightTime === null) {
    return left.creator_id.localeCompare(right.creator_id);
  }
  if (leftTime === null) return 1;
  if (rightTime === null) return -1;
  return direction === "desc" ? rightTime - leftTime : leftTime - rightTime;
}

function compareNames(
  left: CreatorResponse,
  right: CreatorResponse,
  profileMap: Map<string, CreatorProfileDetailsResponse>,
) {
  return safeProfileName(profileMap.get(left.creator_id), left).localeCompare(
    safeProfileName(profileMap.get(right.creator_id), right),
  );
}

function compareNewestFirst(leftValue: string | null | undefined, rightValue: string | null | undefined, fallback: () => number) {
  const leftTime = parseSortableTime(leftValue);
  const rightTime = parseSortableTime(rightValue);
  if (leftTime === null && rightTime === null) return fallback();
  if (leftTime === null) return 1;
  if (rightTime === null) return -1;
  return rightTime - leftTime;
}

function parseSortableTime(value: string | null | undefined) {
  if (!value) return null;
  const time = new Date(value).getTime();
  return Number.isNaN(time) ? null : time;
}

function lastCheckedTime(creator: CreatorResponse) {
  if (!creator.last_checked_at) return null;
  const time = new Date(creator.last_checked_at).getTime();
  return Number.isNaN(time) ? null : time;
}

function profileLooksUnavailable(profile?: CreatorProfileDetailsResponse) {
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

function safeProfileName(profile: CreatorProfileDetailsResponse | undefined, creator: CreatorResponse) {
  if (profile?.name && !isBadScrapedText(profile.name)) return profile.name;
  return creator.display_name || creator.creator_id;
}

function safeProfileHeadline(profile: CreatorProfileDetailsResponse | undefined, creator: CreatorResponse) {
  if (profileLooksUnavailable(profile)) return "Profile not found or unavailable";
  if (profile?.headline && !isBadScrapedText(profile.headline)) return profile.headline;
  return creator.display_name ? "Saved creator profile" : "Profile details not scraped";
}

function safeProfileImageUrl(profile?: CreatorProfileDetailsResponse) {
  if (!profile || profileLooksUnavailable(profile)) return "";
  return profile.profile_image_url;
}

function normalizeLinkedInProfileUrl(value: string) {
  const trimmed = value.trim();
  if (!trimmed) return "";
  if (/\s/.test(trimmed)) return "";
  const candidate = /^https?:\/\//i.test(trimmed) ? trimmed : `https://${trimmed}`;
  try {
    const parsed = new URL(candidate);
    const host = parsed.hostname.toLowerCase().replace(/^www\./, "");
    const parts = parsed.pathname.split("/").filter(Boolean);
    if (host !== "linkedin.com" || parts[0]?.toLowerCase() !== "in" || !parts[1]) {
      return "";
    }
    parsed.protocol = "https:";
    parsed.hostname = "www.linkedin.com";
    parsed.pathname = `/in/${parts[1]}/`;
    parsed.search = "";
    parsed.hash = "";
    return parsed.toString();
  } catch {
    return "";
  }
}

function CreatorRow({
  creator,
  profile,
  selected,
  deleting,
  onToggleSelected,
  onCopyProfile,
  onDeleteCreator,
}: {
  creator: CreatorResponse;
  profile?: CreatorProfileDetailsResponse;
  selected: boolean;
  deleting: boolean;
  onToggleSelected: (creatorId: string) => void;
  onCopyProfile: (creator: CreatorResponse) => void;
  onDeleteCreator: (creatorId: string) => void;
}) {
  const label = safeProfileName(profile, creator);
  const headline = safeProfileHeadline(profile, creator);
  const profileImageUrl = safeProfileImageUrl(profile);
  return (
    <tr>
      <td className="select-column">
        <input
          type="checkbox"
          checked={selected}
          onChange={() => onToggleSelected(creator.creator_id)}
          aria-label={`Select ${label}`}
        />
      </td>
      <td>
        <Link className="creator-identity" href={`/creators/${encodeURIComponent(creator.creator_id)}`}>
          <div className="avatar mini">
            {profileImageUrl ? (
              <img src={profileImageUrl} alt={`${label} profile`} />
            ) : (
              initials(label)
            )}
          </div>
          <span>
            <strong>{label}</strong>
            <small>@{creator.creator_id}</small>
          </span>
        </Link>
      </td>
      <td>{headline}</td>
      <td>
        <a className="table-link" href={creator.profile_url} target="_blank" rel="noreferrer">
          {creator.profile_url.replace(/^https?:\/\//, "")}
          <ExternalLink size={13} />
        </a>
      </td>
      <td>{creator.last_checked_at ? compactDate(creator.last_checked_at) : "Never"}</td>
      <td>{creator.new_count ? `${creator.new_count} New` : "0 Posts"}</td>
      <td>
        <div className="creator-row-actions">
          <button className="icon-button tiny" type="button" onClick={() => onCopyProfile(creator)} aria-label={`Copy ${label} profile`}>
            <Copy size={15} />
          </button>
          <button
            className="icon-button tiny danger-icon-button"
            type="button"
            onClick={() => onDeleteCreator(creator.creator_id)}
            disabled={deleting}
            aria-label={`Delete ${label}`}
          >
            {deleting ? <Loader2 className="spin" size={15} /> : <Trash2 size={15} />}
          </button>
        </div>
      </td>
    </tr>
  );
}

function formatCreatorForClipboard(
  creator: CreatorResponse,
  profile?: CreatorProfileDetailsResponse,
  index?: number,
) {
  const name = safeProfileName(profile, creator);
  const about = profileLooksUnavailable(profile)
    ? "Profile not found or unavailable"
    : profile?.about || "Not saved";
  const experience = profileLooksUnavailable(profile)
    ? "Profile not found or unavailable"
    : profile?.experience?.length
      ? profile.experience.join("\n")
      : "Not saved";
  const lines = [
    index ? String(index) : "",
    "Name",
    name,
    "",
    "Headline",
    safeProfileHeadline(profile, creator),
    "",
    "About",
    about,
    "",
    "Experience",
    experience,
    "",
    "Location",
    profileLooksUnavailable(profile) ? "Profile not found" : profile?.location || "Not saved",
    "",
    "LinkedIn",
    creator.profile_url || profile?.profile_url || "Not saved",
  ];
  return lines.join("\n").trim();
}

function AddCreatorDialog({
  onClose,
  onAdded,
}: {
  onClose: () => void;
  onAdded: (message: string) => void;
}) {
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit() {
    const normalizedUrl = normalizeLinkedInProfileUrl(url);
    if (!url.trim()) {
      setError("LinkedIn profile URL is required.");
      return;
    }
    if (!normalizedUrl) {
      setError("Enter a valid LinkedIn profile URL like https://www.linkedin.com/in/creator.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const creator = await addCreator({ user_id: DEFAULT_USER_ID, profile_url: normalizedUrl });
      if (ENABLE_SCRAPING) {
        const profileResult = await scrapeCreatorProfiles(DEFAULT_USER_ID, [creator.creator_id]);
        if (profileResult.errors.length) {
          const firstError = profileResult.errors[0];
          throw new Error(firstError.message || "Creator was added, but profile scraping failed.");
        }
      }
      onAdded(
        ENABLE_SCRAPING
          ? `${creator.display_name || creator.creator_id} added and profile scraped`
          : `${creator.display_name || creator.creator_id} added`,
      );
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Could not add creator.");
    } finally {
      setBusy(false);
    }
  }

  function requestClose() {
    if (!busy) onClose();
  }

  return (
    <div className="drawer-backdrop" onClick={requestClose}>
      <aside
        className="side-drawer no-tabs"
        aria-modal="true"
        role="dialog"
        aria-labelledby="add-creator-title"
        onClick={(event) => event.stopPropagation()}
      >
        <header className="drawer-header">
          <div>
            <h2 id="add-creator-title">Add Creator</h2>
            <p>Track a creator by adding their LinkedIn profile.</p>
          </div>
          <button className="icon-button" type="button" onClick={requestClose} disabled={busy} aria-label="Close">
            <X size={20} />
          </button>
        </header>

        <div className="drawer-body">
          <label className="field">
            <span>LinkedIn Profile URL</span>
            <input
              value={url}
              onChange={(event) => setUrl(event.target.value)}
              placeholder="https://linkedin.com/in/creator"
            />
          </label>

          <div className="sync-info-card">
            <Info size={18} />
            <p>
              {ENABLE_SCRAPING
                ? "Adding this creator will start historical data sync. This usually takes 2-5 minutes to complete."
                : "Adding this creator saves the profile. Run local scraping to sync LinkedIn details."}
            </p>
          </div>

          {error ? <div className="error-banner">{error}</div> : null}
        </div>

        <footer className="drawer-footer">
          <button className="primary-button" type="button" onClick={submit} disabled={busy}>
            {busy ? <Loader2 className="spin" size={17} /> : null}
            {busy ? (ENABLE_SCRAPING ? "Adding and scraping..." : "Adding...") : "Add Creator"}
          </button>
          <button className="secondary-button" type="button" onClick={requestClose} disabled={busy}>Cancel</button>
        </footer>
      </aside>
    </div>
  );
}

function BulkImportDialog({
  onClose,
  onImported,
  onDataChanged,
}: {
  onClose: () => void;
  onImported: (message: string) => void;
  onDataChanged: () => void;
}) {
  const [locked, setLocked] = useState(false);

  function requestClose() {
    if (!locked) onClose();
  }

  return (
    <div className="drawer-backdrop" onClick={requestClose}>
      <aside
        className="side-drawer no-tabs"
        aria-modal="true"
        role="dialog"
        aria-labelledby="bulk-import-title"
        onClick={(event) => event.stopPropagation()}
      >
        <header className="drawer-header">
          <div>
            <h2 id="bulk-import-title">Bulk Import Creators</h2>
            <p>Upload CSV, Excel or TXT files containing LinkedIn profile URLs.</p>
          </div>
          <button className="icon-button" type="button" onClick={requestClose} disabled={locked} aria-label="Close">
            <X size={20} />
          </button>
        </header>

        <BulkImportForm
          onClose={requestClose}
          onImported={onImported}
          onDataChanged={onDataChanged}
          onBusyChange={setLocked}
        />
      </aside>
    </div>
  );
}

function BulkImportForm({
  onClose,
  onImported,
  onDataChanged,
  onBusyChange,
}: {
  onClose: () => void;
  onImported: (message: string) => void;
  onDataChanged: () => void;
  onBusyChange: (busy: boolean) => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [previewBusy, setPreviewBusy] = useState(false);
  const [busy, setBusy] = useState(false);
  const [preview, setPreview] = useState<BulkCreatorPreviewResponse | null>(null);
  const [result, setResult] = useState<BulkCreatorImportResponse | null>(null);
  const [error, setError] = useState("");

  const skippedExisting = result?.skipped_existing_creators ?? [];
  const skippedDuplicates = result?.skipped_duplicate_creators ?? [];
  const newRows = preview?.new_creators ?? [];
  const existingRows = preview?.existing_creators ?? [];
  const duplicateRows = preview?.duplicate_creators ?? [];
  const previewErrors = preview?.errors ?? [];
  const canImport = Boolean(file && preview && newRows.length > 0 && !previewBusy && !busy);

  useEffect(() => {
    onBusyChange(previewBusy || busy);
  }, [busy, onBusyChange, previewBusy]);

  async function handleFileChange(nextFile: File | null) {
    setFile(nextFile);
    setPreview(null);
    setResult(null);
    setError("");
    if (!nextFile) return;

    setPreviewBusy(true);
    try {
      const response = await previewCreatorImport(DEFAULT_USER_ID, nextFile);
      setPreview(response);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Could not read the uploaded file.");
    } finally {
      setPreviewBusy(false);
    }
  }

  async function submit() {
    if (!file) {
      setError("Choose a CSV, XLSX, or TXT file first.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const response = await importCreators(DEFAULT_USER_ID, file);
      setResult(response);
      if (response.added_creators.length) {
        onDataChanged();
      }
      if (response.errors.length) {
        setError("Import completed with errors. Review the rows below.");
        return;
      }
      const addedCount = response.added_creators.length;
      if (addedCount > 0 && ENABLE_SCRAPING) {
        const profileResult = await scrapeCreatorProfiles(
          DEFAULT_USER_ID,
          response.added_creators.map((creator) => creator.creator_id),
        );
        if (profileResult.errors.length) {
          const firstError = profileResult.errors[0];
          throw new Error(firstError.message || "Creators were imported, but profile scraping failed.");
        }
      }
      onImported(
        ENABLE_SCRAPING
          ? `${addedCount} new creator${addedCount === 1 ? "" : "s"} added and profile scraped`
          : `${addedCount} new creator${addedCount === 1 ? "" : "s"} added`,
      );
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Could not import creators.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <div className="drawer-body import-body">
        <label className="upload-dropzone">
          <span className="upload-icon-bubble">
            {previewBusy ? <Loader2 className="spin" size={24} /> : <UploadCloud size={25} />}
          </span>
          <strong>Drag & Drop your file here</strong>
          <span>Supported formats: CSV, XLSX, TXT</span>
          <span className="browse-file-button">Browse Files</span>
          <input
            type="file"
            accept=".csv,.txt,.xlsx"
            onChange={(event) => {
              void handleFileChange(event.target.files?.[0] ?? null);
            }}
          />
        </label>

        {preview && !result ? (
          <div className="import-result-summary">
            <div className="import-status-line">
              <strong>File parsed</strong>
              <span>{preview.total_urls} URL{preview.total_urls === 1 ? "" : "s"} checked</span>
            </div>
            <div className="import-stats">
              <MiniStat label="New URLs" value={newRows.length.toString()} />
              <MiniStat label="Duplicates" value={duplicateRows.length.toString()} />
              <MiniStat label="Already in DB" value={existingRows.length.toString()} />
              <MiniStat label="Errors" value={previewErrors.length.toString()} danger />
            </div>
          </div>
        ) : null}

        {previewErrors.length && !result ? (
          <ImportResultTable title="Error Log" rows={previewErrors} danger />
        ) : null}

        {result ? (
          <div className="import-result-summary">
            <div className="import-status-line">
              <strong>Import complete</strong>
              <span>{result.total_urls} URL{result.total_urls === 1 ? "" : "s"} checked</span>
            </div>
            <div className="import-stats">
              <MiniStat label="Added" value={result.added_creators.length.toString()} />
              <MiniStat label="Skipped" value={skippedExisting.length.toString()} />
              <MiniStat label="Duplicates" value={skippedDuplicates.length.toString()} />
              <MiniStat label="Errors" value={result.errors.length.toString()} danger />
            </div>
          </div>
        ) : null}

        {result?.errors.length ? (
          <ImportResultTable title="Error Log" rows={result.errors} danger />
        ) : null}

        {error ? <div className="error-banner">{error}</div> : null}
      </div>

      <footer className="drawer-footer">
        <button className="secondary-button" type="button" onClick={onClose} disabled={previewBusy || busy}>Cancel</button>
        <button className="primary-button" type="button" onClick={submit} disabled={!canImport}>
          {busy ? <Loader2 className="spin" size={17} /> : null}
          {busy ? (ENABLE_SCRAPING ? "Importing and scraping..." : "Importing...") : "Import Creators"}
        </button>
      </footer>
    </>
  );
}

function MiniStat({ label, value, danger = false }: { label: string; value: string; danger?: boolean }) {
  return (
    <article className={danger ? "mini-stat danger" : "mini-stat"}>
      <span>{label}</span>
      <strong>{value}</strong>
    </article>
  );
}

function ImportResultTable({
  title,
  rows,
  danger = false,
}: {
  title: string;
  rows: Array<{ row?: string; url?: string; normalized_url?: string; creator_id?: string; reason?: string; message?: string }>;
  danger?: boolean;
}) {
  return (
    <div className={danger ? "import-result-table danger" : "import-result-table"}>
      <h3>{title}</h3>
      <table>
        <thead>
          <tr>
            <th>Row</th>
            <th>Profile URL</th>
            <th>Reason</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((item, index) => (
            <tr key={`${item.row || "row"}-${item.creator_id || item.url || index}`}>
              <td>{item.row || "-"}</td>
              <td>{item.normalized_url || item.url || "-"}</td>
              <td>{item.reason || item.message || "Ready to import"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
