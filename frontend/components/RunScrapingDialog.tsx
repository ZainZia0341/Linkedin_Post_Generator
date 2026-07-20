"use client";

import { Check, Loader2, Minus, Plus, Search, UserCheck, Users, X, Zap } from "lucide-react";
import { useMemo, useState } from "react";
import { DEFAULT_USER_ID, ENABLE_SCRAPING, runRecentScrape } from "@/lib/api";
import { initials } from "@/lib/format";
import type {
  CreatorProfileDetailsResponse,
  CreatorResponse,
  RecentScrapeCreatorsResponse,
  ScrapeJobStatusResponse,
} from "@/lib/types";

type Scope = "all" | "never_scraped" | "selected";

type RunScrapingDialogProps = {
  creators: CreatorResponse[];
  profileMap?: Map<string, CreatorProfileDetailsResponse>;
  initialCreatorIds?: string[];
  lockSelection?: boolean;
  onClose: () => void;
  onComplete: (response: RecentScrapeCreatorsResponse) => void;
};

const WINDOW_OPTIONS = [
  { label: "Last 12h", value: 12 },
  { label: "Last Day", value: 24 },
  { label: "Last 2 Days", value: 48 },
  { label: "Last 3 Days", value: 72 },
];

export function RunScrapingDialog({
  creators,
  profileMap,
  initialCreatorIds = [],
  lockSelection = false,
  onClose,
  onComplete,
}: RunScrapingDialogProps) {
  const [scope, setScope] = useState<Scope>(initialCreatorIds.length ? "selected" : "all");
  const [selectedIds, setSelectedIds] = useState<string[]>(initialCreatorIds);
  const [query, setQuery] = useState("");
  const [windowHours, setWindowHours] = useState(24);
  const [maxPosts, setMaxPosts] = useState(5);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [jobStatus, setJobStatus] = useState<ScrapeJobStatusResponse | null>(null);

  const selectedSet = useMemo(() => new Set(selectedIds), [selectedIds]);
  const neverScrapedIds = useMemo(
    () => creators.filter((creator) => !creator.last_checked_at).map((creator) => creator.creator_id),
    [creators],
  );
  const filteredCreators = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    if (!normalized) return creators.slice(0, 80);
    return creators
      .filter((creator) => {
        const text = `${creator.display_name} ${creator.creator_id} ${creator.profile_url}`.toLowerCase();
        return text.includes(normalized);
      })
      .slice(0, 80);
  }, [creators, query]);
  const selectedCreators = creators.filter((creator) => selectedSet.has(creator.creator_id));
  const targetCreatorIds = scope === "selected" ? selectedIds : scope === "never_scraped" ? neverScrapedIds : undefined;
  const targetCount = targetCreatorIds?.length ?? creators.length;
  const canRun = ENABLE_SCRAPING && targetCount > 0 && !busy;

  function toggleCreator(creatorId: string) {
    if (lockSelection) return;
    setSelectedIds((current) => {
      if (current.includes(creatorId)) {
        return current.filter((item) => item !== creatorId);
      }
      return [...current, creatorId];
    });
  }

  function updateMaxPosts(nextValue: number) {
    if (!Number.isFinite(nextValue)) return;
    setMaxPosts(Math.min(50, Math.max(1, Math.round(nextValue))));
  }

  async function runScrape() {
    if (!canRun) return;
    setBusy(true);
    setError("");
    setJobStatus(null);
    try {
      const response = await runRecentScrape({
        user_id: DEFAULT_USER_ID,
        creator_ids: targetCreatorIds,
        max_posts: maxPosts,
        window_hours: windowHours,
        launch_delay_seconds: 3,
      }, setJobStatus);
      if (response.errors.length) {
        throw new Error(`Scraping completed with ${response.errors.length} creator error${response.errors.length === 1 ? "" : "s"}.`);
      }
      onComplete(response);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Could not run scraping.");
    } finally {
      setBusy(false);
    }
  }

  function requestClose() {
    if (!busy) onClose();
  }

  return (
    <div className="modal-backdrop" onClick={requestClose}>
      <section
        className="scrape-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="run-scraping-title"
        onClick={(event) => event.stopPropagation()}
      >
        <header className="scrape-modal-header">
          <div>
            <h2 id="run-scraping-title">Run Scraping</h2>
            <p>Select creators and the supported scraping configuration for this job.</p>
          </div>
          <button className="icon-button" type="button" onClick={requestClose} disabled={busy} aria-label="Close">
            <X size={19} />
          </button>
        </header>

        <div className="scrape-modal-body">
          <div className="scrape-field-group">
            <span className="scrape-label">Scraping Scope</span>
            <div className="scrape-scope-grid">
              <button
                className={scope === "all" ? "scope-card selected" : "scope-card"}
                type="button"
                onClick={() => setScope("all")}
                disabled={lockSelection}
              >
                <Users size={18} />
                <span>
                  <strong>All Active Creators</strong>
                  <small>{creators.length} creators tracked</small>
                </span>
              </button>
              <button
                className={scope === "never_scraped" ? "scope-card selected" : "scope-card"}
                type="button"
                onClick={() => setScope("never_scraped")}
                disabled={lockSelection}
              >
                <Search size={18} />
                <span>
                  <strong>Never Scraped</strong>
                  <small>{neverScrapedIds.length} creators not checked yet</small>
                </span>
              </button>
              <button
                className={scope === "selected" ? "scope-card selected" : "scope-card"}
                type="button"
                onClick={() => setScope("selected")}
              >
                <UserCheck size={18} />
                <span>
                  <strong>Selected Creators</strong>
                  <small>{lockSelection ? "Current creator" : "Choose creators manually"}</small>
                </span>
              </button>
            </div>
          </div>

          {scope === "selected" ? (
            <div className="scrape-field-group">
              <div className="scrape-row-heading">
                <span className="scrape-label">Creator Selector</span>
                <strong>{selectedIds.length} selected</strong>
              </div>
              {!lockSelection ? (
                <label className="creator-search scrape-search">
                  <Search size={17} />
                  <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search creators..." />
                </label>
              ) : null}
              <div className="selected-chip-row">
                {selectedCreators.map((creator) => (
                  <span className="selected-chip" key={creator.creator_id}>
                    {creator.display_name || creator.creator_id}
                    {!lockSelection ? (
                      <button type="button" onClick={() => toggleCreator(creator.creator_id)} aria-label={`Remove ${creator.creator_id}`}>
                        <X size={12} />
                      </button>
                    ) : null}
                  </span>
                ))}
              </div>
              {!lockSelection ? (
                <div className="creator-selector-list">
                  {filteredCreators.map((creator) => {
                    const profile = profileMap?.get(creator.creator_id);
                    const label = profile?.name || creator.display_name || creator.creator_id;
                    const checked = selectedSet.has(creator.creator_id);
                    return (
                      <button
                        className={checked ? "creator-select-row selected" : "creator-select-row"}
                        type="button"
                        onClick={() => toggleCreator(creator.creator_id)}
                        key={creator.creator_id}
                      >
                        <span className="checkbox-mark">{checked ? <Check size={13} /> : null}</span>
                        <span className="avatar mini">
                          {profile?.profile_image_url ? (
                            <img src={profile.profile_image_url} alt={`${label} profile`} />
                          ) : (
                            initials(label)
                          )}
                        </span>
                        <span>
                          <strong>{label}</strong>
                          <small>{profile?.headline || `@${creator.creator_id}`}</small>
                        </span>
                        <em>{creator.last_checked_at ? "Scraped before" : "Never scraped"}</em>
                      </button>
                    );
                  })}
                </div>
              ) : null}
            </div>
          ) : null}

          <div className="scrape-config-grid">
            <div className="scrape-field-group">
              <span className="scrape-label">Scraping Time Window</span>
              <div className="time-window-row">
                {WINDOW_OPTIONS.map((option) => (
                  <button
                    className={windowHours === option.value ? "selected" : ""}
                    type="button"
                    onClick={() => setWindowHours(option.value)}
                    key={option.value}
                  >
                    {option.label}
                  </button>
                ))}
              </div>
            </div>

            <div className="scrape-field-group scrape-max-field">
              <span className="scrape-label">Max Posts Per Creator</span>
              <div className="number-stepper">
                <button type="button" onClick={() => updateMaxPosts(maxPosts - 1)} disabled={maxPosts <= 1} aria-label="Decrease max posts">
                  <Minus size={14} />
                </button>
                <input
                  type="number"
                  min={1}
                  max={50}
                  value={maxPosts}
                  onChange={(event) => updateMaxPosts(Number(event.target.value))}
                  aria-label="Max posts per creator"
                />
                <button type="button" onClick={() => updateMaxPosts(maxPosts + 1)} disabled={maxPosts >= 50} aria-label="Increase max posts">
                  <Plus size={14} />
                </button>
              </div>
            </div>
          </div>

          <div className="scrape-summary-card">
            <div className="scrape-summary-title">
              <Zap size={15} />
              Job Summary
            </div>
            <div className="summary-grid">
              <span>Creators</span>
              <strong>{targetCount}</strong>
              <span>Time Window</span>
              <strong>{WINDOW_OPTIONS.find((option) => option.value === windowHours)?.label}</strong>
              <span>Max Posts</span>
              <strong>{maxPosts} per creator</strong>
            </div>
          </div>

          {error ? <div className="error-banner">{error}</div> : null}
          {jobStatus ? (
            <div className="scrape-progress-card">
              <div>
                <strong>{jobStatus.status === "succeeded" ? "Scrape complete" : "Scrape job running"}</strong>
                <span>{jobStatus.message || "Waiting for backend progress..."}</span>
              </div>
              <div className="scrape-progress-grid">
                <div>
                  <span>Creators</span>
                  <strong>{Math.min(jobStatus.scraped_creators, jobStatus.total_creators)} / {jobStatus.total_creators}</strong>
                </div>
                <div>
                  <span>Posts found</span>
                  <strong>{jobStatus.total_posts}</strong>
                </div>
                <div>
                  <span>Errors</span>
                  <strong>{jobStatus.errors.length}</strong>
                </div>
              </div>
              {jobStatus.errors.length ? (
                <div className="scrape-error-list" role="list" aria-label="Scraping errors">
                  {jobStatus.errors.map((item, index) => (
                    <p role="listitem" key={`${item.creator_id || "error"}-${index}`}>
                      <strong>{item.creator_id || `Error ${index + 1}`}</strong>
                      <span>{item.message || "Unknown scraping error."}</span>
                    </p>
                  ))}
                </div>
              ) : null}
            </div>
          ) : null}
          {!ENABLE_SCRAPING ? (
            <div className="error-banner">Scraping is disabled for this deployed frontend. Run scraping locally.</div>
          ) : null}
        </div>

        <footer className="scrape-modal-footer">
          <button className="secondary-button" type="button" onClick={requestClose} disabled={busy}>
            Cancel
          </button>
          <button className="primary-button" type="button" onClick={runScrape} disabled={!canRun}>
            {busy ? <Loader2 className="spin" size={17} /> : <Zap size={16} />}
            {busy ? "Running..." : "Run Scraping"}
          </button>
        </footer>
      </section>
    </div>
  );
}
