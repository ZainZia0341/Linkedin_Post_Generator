"use client";

import Link from "next/link";
import { CheckCircle2, Copy, Download, Filter, Loader2, Pencil, Plus, Search, Trash2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { CommentEditorDrawer } from "@/components/CommentEditorDrawer";
import {
  DEFAULT_USER_ID,
  fetchCommentHistory,
  fetchCreatorProfiles,
  fetchUserData,
  markComment,
} from "@/lib/api";
import { compactDate, displayName, initials, previewText, sortThreads } from "@/lib/format";
import type { CommentedActivityResponse, CreatorProfileDetailsResponse, UserDataResponse } from "@/lib/types";

const PAGE_SIZE = 10;

export function CommentHistoryView() {
  const [userData, setUserData] = useState<UserDataResponse | null>(null);
  const [comments, setComments] = useState<CommentedActivityResponse[]>([]);
  const [profileMap, setProfileMap] = useState<Map<string, CreatorProfileDetailsResponse>>(new Map());
  const [editing, setEditing] = useState<CommentedActivityResponse | null>(null);
  const [query, setQuery] = useState("");
  const [creatorFilter, setCreatorFilter] = useState("all");
  const [styleFilter, setStyleFilter] = useState("all");
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
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
      const [dataResult, commentResult, profileResult] = await Promise.allSettled([
        fetchUserData(DEFAULT_USER_ID),
        fetchCommentHistory(DEFAULT_USER_ID, 200),
        fetchCreatorProfiles(DEFAULT_USER_ID, 500),
      ]);
      if (dataResult.status === "rejected") throw dataResult.reason;
      if (commentResult.status === "rejected") throw commentResult.reason;
      setUserData(dataResult.value);
      setComments(commentResult.value);
      if (profileResult.status === "fulfilled") {
        setProfileMap(new Map(profileResult.value.map((profile) => [profile.creator_id, profile])));
      }
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Could not load comment history.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  useEffect(() => {
    setPage(1);
  }, [creatorFilter, query, styleFilter]);

  const sortedThreads = useMemo(() => sortThreads(userData?.threads ?? []), [userData?.threads]);
  const userName = displayName(userData?.user) || DEFAULT_USER_ID;
  const styleOptions = useMemo(() => {
    return Array.from(new Set(comments.map((comment) => styleLabel(comment.comment_topic)))).sort();
  }, [comments]);
  const creatorOptions = useMemo(() => {
    return Array.from(new Set(comments.map((comment) => comment.creator_id))).sort();
  }, [comments]);
  const filteredComments = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    return comments.filter((comment) => {
      const profile = profileMap.get(comment.creator_id);
      const creatorName = profile?.name || comment.author_name || comment.creator_id;
      const searchable = `${comment.comment} ${comment.raw_text} ${comment.comment_topic} ${creatorName} ${profile?.headline || ""}`.toLowerCase();
      const matchesQuery = !normalized || searchable.includes(normalized);
      const matchesCreator = creatorFilter === "all" || comment.creator_id === creatorFilter;
      const matchesStyle = styleFilter === "all" || styleLabel(comment.comment_topic) === styleFilter;
      return matchesQuery && matchesCreator && matchesStyle;
    });
  }, [comments, creatorFilter, profileMap, query, styleFilter]);
  const totalPages = Math.max(1, Math.ceil(filteredComments.length / PAGE_SIZE));
  const visibleComments = filteredComments.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  async function copyComment(comment: string) {
    await navigator.clipboard.writeText(comment);
    showSuccess("Comment copied");
  }

  async function saveComment(row: CommentedActivityResponse, comment: string) {
    setBusy(`${row.creator_id}:${row.post_id}`);
    setError("");
    try {
      await markComment({
        user_id: DEFAULT_USER_ID,
        creator_id: row.creator_id,
        post_id: row.post_id,
        commented: true,
        comment_text: comment,
      });
      setComments((current) =>
        current.map((item) =>
          item.creator_id === row.creator_id && item.post_id === row.post_id
            ? { ...item, comment, commented_at: new Date().toISOString() }
            : item,
        ),
      );
      setEditing(null);
      showSuccess("Comment updated");
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Could not save comment.");
    } finally {
      setBusy("");
    }
  }

  return (
    <AppShell
      active="history"
      title="Content Library"
      subtitle="Manage and reuse finalized LinkedIn comments."
      userName={userName}
      threads={sortedThreads}
    >
      <section className="comment-history-page">
        <div className="comment-history-actions">
          <button className="secondary-button compact" type="button" disabled title="CSV export can be added once needed">
            <Download size={16} />
            Export CSV
          </button>
          <Link className="primary-button compact" href="/posts-scraping">
            <Plus size={16} />
            New Comment
          </Link>
        </div>

        <div className="comment-library-summary">
          <article className="comment-total-card">
            <span>Total Saved</span>
            <strong>{comments.length.toLocaleString()}</strong>
            <small>Comments marked complete</small>
          </article>
          <section className="comment-filter-card">
            <label>
              <span>Filter by Creator</span>
              <select value={creatorFilter} onChange={(event) => setCreatorFilter(event.target.value)}>
                <option value="all">All Creators</option>
                {creatorOptions.map((creatorId) => {
                  const profile = profileMap.get(creatorId);
                  return (
                    <option value={creatorId} key={creatorId}>
                      {profile?.name || creatorId}
                    </option>
                  );
                })}
              </select>
            </label>
            <label>
              <span>Filter by Style</span>
              <select value={styleFilter} onChange={(event) => setStyleFilter(event.target.value)}>
                <option value="all">All Styles</option>
                {styleOptions.map((styleName) => (
                  <option value={styleName} key={styleName}>
                    {styleName}
                  </option>
                ))}
              </select>
            </label>
            <label>
              <span>Date Range</span>
              <select disabled>
                <option>Last 30 Days</option>
              </select>
            </label>
            <button className="icon-button" type="button" disabled title="More filters need backend fields">
              <Filter size={17} />
            </button>
          </section>
        </div>

        <section className="comment-history-table-panel">
          <div className="comment-history-toolbar">
            <label className="creator-search posts-search">
              <Search size={17} />
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Search comments, creators, or tags..."
              />
            </label>
          </div>

          {error ? <div className="error-banner">{error}</div> : null}
          {loading ? <div className="empty-card slim">Loading comment history...</div> : null}

          <div className="creator-table-wrap">
            <table className="creator-table comment-history-table">
              <thead>
                <tr>
                  <th>Comment Preview</th>
                  <th>Target Creator</th>
                  <th>Style</th>
                  <th>Status</th>
                  <th>Last Modified</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {visibleComments.length ? (
                  visibleComments.map((comment) => (
                    <CommentHistoryRow
                      comment={comment}
                      profile={profileMap.get(comment.creator_id)}
                      busy={busy === `${comment.creator_id}:${comment.post_id}`}
                      onOpen={setEditing}
                      onCopy={copyComment}
                      key={`${comment.creator_id}-${comment.post_id}`}
                    />
                  ))
                ) : (
                  <tr>
                    <td colSpan={6}>
                      <div className="empty-mini">No finalized comments match the current filters.</div>
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          <div className="comment-history-footer">
            <span>
              Showing {visibleComments.length ? (page - 1) * PAGE_SIZE + 1 : 0} to {Math.min(page * PAGE_SIZE, filteredComments.length)} of{" "}
              {filteredComments.length} entries
            </span>
            <div className="pager">
              <button type="button" disabled={page <= 1} onClick={() => setPage((current) => Math.max(1, current - 1))}>
                Previous
              </button>
              <strong>{page}</strong>
              <button
                type="button"
                disabled={page >= totalPages}
                onClick={() => setPage((current) => Math.min(totalPages, current + 1))}
              >
                Next
              </button>
            </div>
          </div>
        </section>
      </section>

      {editing ? (
        <CommentEditorDrawer
          activity={editing}
          profile={profileMap.get(editing.creator_id)}
          initialComment={editing.comment}
          styleLabel={styleLabel(editing.comment_topic)}
          mode="saved"
          onClose={() => setEditing(null)}
          onSave={(comment) => void saveComment(editing, comment)}
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

function CommentHistoryRow({
  comment,
  profile,
  busy,
  onOpen,
  onCopy,
}: {
  comment: CommentedActivityResponse;
  profile?: CreatorProfileDetailsResponse;
  busy: boolean;
  onOpen: (comment: CommentedActivityResponse) => void;
  onCopy: (comment: string) => void;
}) {
  const creatorName = profile?.name || comment.author_name || comment.creator_id;

  return (
    <tr className="clickable-row" onClick={() => onOpen(comment)}>
      <td className="comment-preview-cell">"{previewText(comment.comment, 118)}"</td>
      <td>
        <div className="creator-identity">
          <div className="avatar mini">
            {profile?.profile_image_url ? (
              <img src={profile.profile_image_url} alt={`${creatorName} profile`} />
            ) : (
              initials(creatorName)
            )}
          </div>
          <span>
            <strong>{creatorName}</strong>
            <small>{profile?.headline || comment.creator_id}</small>
          </span>
        </div>
      </td>
      <td>
        <span className="status-pill neutral">{styleLabel(comment.comment_topic)}</span>
      </td>
      <td>
        <span className="status-pill success">Finalized</span>
      </td>
      <td>{compactDate(comment.commented_at || comment.fetched_at)}</td>
      <td>
        <div className="history-action-buttons">
          <button
            className="icon-button tiny"
            type="button"
            onClick={(event) => {
              event.stopPropagation();
              void onCopy(comment.comment);
            }}
            aria-label="Copy comment"
          >
            <Copy size={15} />
          </button>
          <button
            className="icon-button tiny"
            type="button"
            onClick={(event) => {
              event.stopPropagation();
              onOpen(comment);
            }}
            aria-label="Edit comment"
          >
            {busy ? <Loader2 className="spin" size={15} /> : <Pencil size={15} />}
          </button>
          <button className="icon-button tiny danger-icon" type="button" disabled aria-label="Delete comment">
            <Trash2 size={15} />
          </button>
        </div>
      </td>
    </tr>
  );
}

function styleLabel(value?: string) {
  return (value || "Saved").split(".")[0].trim() || "Saved";
}
