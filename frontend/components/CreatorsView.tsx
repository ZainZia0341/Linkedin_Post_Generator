"use client";

import Link from "next/link";
import {
  CheckCircle2,
  ExternalLink,
  FileUp,
  Grid2X2,
  List,
  Loader2,
  Plus,
  Search,
  UploadCloud,
  Users,
  X,
} from "lucide-react";
import type { ReactNode } from "react";
import { useEffect, useMemo, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { DEFAULT_USER_ID, addCreator, fetchUserData, importCreators, previewCreatorImport } from "@/lib/api";
import { compactDate, displayName, initials, sortThreads } from "@/lib/format";
import type { BulkCreatorImportResponse, BulkCreatorPreviewResponse, CreatorResponse, UserDataResponse } from "@/lib/types";

type ModalMode = "single" | "bulk" | null;
const PAGE_SIZE = 10;
const SCRAPE_STALE_AFTER_MS = 24 * 60 * 60 * 1000;

export function CreatorsView() {
  const [userData, setUserData] = useState<UserDataResponse | null>(null);
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("All");
  const [page, setPage] = useState(1);
  const [modalMode, setModalMode] = useState<ModalMode>(null);
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
      const data = await fetchUserData(DEFAULT_USER_ID);
      setUserData(data);
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
  }, [query, statusFilter]);

  const creators = userData?.creators ?? [];
  const sortedThreads = useMemo(() => sortThreads(userData?.threads ?? []), [userData?.threads]);
  const userName = displayName(userData?.user) || DEFAULT_USER_ID;
  const filteredCreators = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    return creators.filter((creator) => {
      const text = [
        creator.display_name,
        creator.creator_id,
        creator.profile_url,
      ].join(" ").toLowerCase();
      const matchesQuery = !normalized || text.includes(normalized);
      const status = creatorStatus(creator);
      const matchesStatus =
        statusFilter === "All" ||
        statusFilter === status ||
        (statusFilter === "Active" && status === "Up To Date") ||
        (statusFilter === "Needs Scraping" && creatorNeedsScraping(creator));
      return matchesQuery && matchesStatus;
    });
  }, [creators, query, statusFilter]);
  const totalPages = Math.max(1, Math.ceil(filteredCreators.length / PAGE_SIZE));
  const safePage = Math.min(page, totalPages);
  const pageStart = filteredCreators.length ? (safePage - 1) * PAGE_SIZE : 0;
  const pageEnd = Math.min(pageStart + PAGE_SIZE, filteredCreators.length);
  const visibleCreators = filteredCreators.slice(pageStart, pageEnd);

  const stats = userData?.dashboard_stats;

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
        <CreatorMetric icon={<List size={20} />} label="New Posts Last Scrape" value={(stats?.new_posts_from_last_scrape_count ?? 0).toString()} />
        <CreatorMetric icon={<Loader2 size={20} />} label="Needs Scraping" value={(stats?.needs_scraping_count ?? 0).toString()} urgent />
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

          <div className="filter-tabs" aria-label="Creator status filters">
            {["All", "Active", "Needs Scraping", "Never Scraped"].map((filter) => (
              <button
                className={statusFilter === filter ? "selected" : ""}
                type="button"
                onClick={() => setStatusFilter(filter)}
                key={filter}
              >
                {filter}
              </button>
            ))}
          </div>

          <div className="view-toggle" aria-label="View mode">
            <button className="selected" type="button" title="List view">
              <List size={17} />
            </button>
            <button type="button" title="Grid view" disabled>
              <Grid2X2 size={17} />
            </button>
          </div>
        </div>

        {error ? <div className="error-banner">{error}</div> : null}
        {loading ? <div className="empty-card slim">Loading creators...</div> : null}

        <div className="creator-table-wrap">
          <table className="creator-table">
            <thead>
              <tr>
                <th>Creator</th>
                <th>Headline</th>
                <th>LinkedIn URL</th>
                <th>Last Checked</th>
                <th>New Posts</th>
                <th>Status</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {visibleCreators.length ? (
                visibleCreators.map((creator) => (
                  <CreatorRow creator={creator} key={creator.creator_id} />
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

function creatorNeedsScraping(creator: CreatorResponse) {
  if (!creator.last_checked_at) return true;
  const checked = new Date(creator.last_checked_at).getTime();
  if (Number.isNaN(checked)) return true;
  return Date.now() - checked >= SCRAPE_STALE_AFTER_MS;
}

function creatorStatus(creator: CreatorResponse) {
  if (!creator.last_checked_at) return "Never Scraped";
  return creatorNeedsScraping(creator) ? "Needs Scraping" : "Up To Date";
}

function CreatorRow({ creator }: { creator: CreatorResponse }) {
  const label = creator.display_name || creator.creator_id;
  const status = creatorStatus(creator);
  const statusClass = status === "Up To Date" ? "status-pill success" : "status-pill neutral";
  return (
    <tr>
      <td>
        <Link className="creator-identity" href={`/creators/${encodeURIComponent(creator.creator_id)}`}>
          <div className="avatar mini">{initials(label)}</div>
          <span>
            <strong>{label}</strong>
            <small>@{creator.creator_id}</small>
          </span>
        </Link>
      </td>
      <td>{creator.display_name ? "Saved creator profile" : "Profile details not scraped"}</td>
      <td>
        <a className="table-link" href={creator.profile_url} target="_blank" rel="noreferrer">
          {creator.profile_url.replace(/^https?:\/\//, "")}
          <ExternalLink size={13} />
        </a>
      </td>
      <td>{creator.last_checked_at ? compactDate(creator.last_checked_at) : "Never"}</td>
      <td>{creator.new_count ? `${creator.new_count} New` : "0 Posts"}</td>
      <td>
        <span className={statusClass}>{status}</span>
      </td>
      <td>
        <Link className="text-button" href={`/creators/${encodeURIComponent(creator.creator_id)}`}>
          View
        </Link>
      </td>
    </tr>
  );
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
    if (!url.trim()) {
      setError("LinkedIn profile URL is required.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const creator = await addCreator({ user_id: DEFAULT_USER_ID, profile_url: url.trim() });
      onAdded(`${creator.display_name || creator.creator_id} added successfully`);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Could not add creator.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="drawer-backdrop">
      <aside className="side-drawer no-tabs" aria-modal="true" role="dialog" aria-labelledby="add-creator-title">
        <header className="drawer-header">
          <div>
            <h2 id="add-creator-title">Add Creator</h2>
            <p>Track a creator by adding their LinkedIn profile.</p>
          </div>
          <button className="icon-button" type="button" onClick={onClose} aria-label="Close">
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

          <div className="api-needed-card">
            <strong>Live preview needs backend support</strong>
            <p>The current API can add and normalize a creator URL, but it does not validate or preview profile metadata before saving.</p>
          </div>

          {error ? <div className="error-banner">{error}</div> : null}
        </div>

        <footer className="drawer-footer">
          <button className="primary-button" type="button" onClick={submit} disabled={busy}>
            {busy ? <Loader2 className="spin" size={17} /> : null}
            Add Creator
          </button>
          <button className="secondary-button" type="button" onClick={onClose}>Cancel</button>
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
  return (
    <div className="drawer-backdrop">
      <aside className="side-drawer no-tabs" aria-modal="true" role="dialog" aria-labelledby="bulk-import-title">
        <header className="drawer-header">
          <div>
            <h2 id="bulk-import-title">Bulk Import Creators</h2>
            <p>Upload CSV, Excel or TXT files containing LinkedIn profile URLs.</p>
          </div>
          <button className="icon-button" type="button" onClick={onClose} aria-label="Close">
            <X size={20} />
          </button>
        </header>

        <BulkImportForm onClose={onClose} onImported={onImported} onDataChanged={onDataChanged} />
      </aside>
    </div>
  );
}

function BulkImportForm({
  onClose,
  onImported,
  onDataChanged,
}: {
  onClose: () => void;
  onImported: (message: string) => void;
  onDataChanged: () => void;
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
      onImported(`${addedCount} new creator${addedCount === 1 ? "" : "s"} added`);
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
              <MiniStat label="Corrected" value={preview.corrected_creators.length.toString()} />
              <MiniStat label="New URLs" value={newRows.length.toString()} />
              <MiniStat label="In DB" value={existingRows.length.toString()} />
              <MiniStat label="Duplicates" value={duplicateRows.length.toString()} />
              <MiniStat label="Errors" value={previewErrors.length.toString()} danger />
            </div>
          </div>
        ) : null}

        {newRows.length && !result ? (
          <ImportResultTable title="New URLs" rows={newRows} />
        ) : null}

        {existingRows.length && !result ? (
          <ImportResultTable title="Already in database" rows={existingRows} />
        ) : null}

        {preview?.corrected_creators.length && !result ? (
          <ImportResultTable title="Corrected URLs" rows={preview.corrected_creators} />
        ) : null}

        {duplicateRows.length && !result ? (
          <ImportResultTable title="Duplicates in file" rows={duplicateRows} />
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

        {skippedExisting.length ? (
          <ImportResultTable title="Skipped: already in database" rows={skippedExisting} />
        ) : null}

        {skippedDuplicates.length ? (
          <ImportResultTable title="Duplicates in file" rows={skippedDuplicates} />
        ) : null}

        {result?.errors.length ? (
          <ImportResultTable title="Error Log" rows={result.errors} danger />
        ) : null}

        {error ? <div className="error-banner">{error}</div> : null}
      </div>

      <footer className="drawer-footer">
        <button className="secondary-button" type="button" onClick={onClose}>Cancel</button>
        <button className="primary-button" type="button" onClick={submit} disabled={busy || previewBusy || !file}>
          {busy ? <Loader2 className="spin" size={17} /> : null}
          Import Creators
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
