"use client";

import { Loader2, MessageCircle, Send, ShieldCheck, UserPlus } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { AppShell } from "@/components/AppShell";
import {
  DEFAULT_USER_ID,
  fetchLinkedInActionLogs,
  fetchOwnLinkedInPosts,
  fetchPostEngagers,
  fetchUserData,
  sendCommentReplies,
  sendConnectionRequests,
  sendDirectMessages,
} from "@/lib/api";
import { compactDate, displayName, previewText } from "@/lib/format";
import type {
  LinkedInActionBatchResponse,
  LinkedInActionLogResponse,
  OwnPostResponse,
  PostEngagerResponse,
  UserDataResponse,
} from "@/lib/types";

type ActionType = "reply" | "connect" | "dm";

export function NetworkingView() {
  const [userData, setUserData] = useState<UserDataResponse | null>(null);
  const [posts, setPosts] = useState<OwnPostResponse[]>([]);
  const [engagers, setEngagers] = useState<PostEngagerResponse[]>([]);
  const [logs, setLogs] = useState<LinkedInActionLogResponse[]>([]);
  const [selectedPostId, setSelectedPostId] = useState("");
  const [selectedProfiles, setSelectedProfiles] = useState<Set<string>>(new Set());
  const [actionType, setActionType] = useState<ActionType>("connect");
  const [message, setMessage] = useState("Thanks for engaging with my post. I appreciated your perspective.");
  const [dryRun, setDryRun] = useState(true);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<LinkedInActionBatchResponse | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchUserData(DEFAULT_USER_ID)
      .then((result) => { if (!cancelled) setUserData(result); })
      .catch(() => undefined);
    Promise.all([
      fetchOwnLinkedInPosts(DEFAULT_USER_ID),
      fetchLinkedInActionLogs(DEFAULT_USER_ID),
    ])
      .then(([postResult, logResult]) => {
        if (cancelled) return;
        setPosts(postResult);
        setLogs(logResult);
        setSelectedPostId(postResult[0]?.post_id || "");
      })
      .catch((exc) => {
        if (!cancelled) setError(exc instanceof Error ? exc.message : "Could not load networking workspace.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    setSelectedProfiles(new Set());
    setResult(null);
    if (!selectedPostId) {
      setEngagers([]);
      return;
    }
    fetchPostEngagers(selectedPostId, DEFAULT_USER_ID)
      .then((items) => {
        if (!cancelled) setEngagers(items);
      })
      .catch((exc) => {
        if (!cancelled) setError(exc instanceof Error ? exc.message : "Could not load post engagers.");
      });
    return () => {
      cancelled = true;
    };
  }, [selectedPostId]);

  const eligibleEngagers = useMemo(() => engagers.filter((engager) => {
    if (actionType === "reply") return engager.engagement_types.includes("comment");
    if (actionType === "dm") return engager.connection_degree.toLowerCase().startsWith("1");
    return !engager.connection_degree.toLowerCase().startsWith("1");
  }), [actionType, engagers]);

  const selectedPost = posts.find((post) => post.post_id === selectedPostId);
  const userName = displayName(userData?.user) || DEFAULT_USER_ID;

  function toggleProfile(profileUrl: string) {
    setSelectedProfiles((current) => {
      const next = new Set(current);
      if (next.has(profileUrl)) next.delete(profileUrl);
      else next.add(profileUrl);
      return next;
    });
  }

  function selectAllEligible() {
    if (selectedProfiles.size === eligibleEngagers.length) setSelectedProfiles(new Set());
    else setSelectedProfiles(new Set(eligibleEngagers.map((item) => item.profile_url).filter(Boolean)));
  }

  async function executeAction() {
    if (!selectedPostId || !selectedProfiles.size || !message.trim()) return;
    if (!dryRun && !window.confirm(`Send ${actionType} action to ${selectedProfiles.size} selected people?`)) return;
    setBusy(true);
    setError("");
    setResult(null);
    const profileUrls = Array.from(selectedProfiles);
    try {
      let response: LinkedInActionBatchResponse;
      if (actionType === "reply") {
        response = await sendCommentReplies({
          user_id: DEFAULT_USER_ID,
          post_id: selectedPostId,
          profile_urls: profileUrls,
          reply_text: message.trim(),
          dry_run: dryRun,
        });
      } else if (actionType === "dm") {
        response = await sendDirectMessages({
          user_id: DEFAULT_USER_ID,
          post_id: selectedPostId,
          profile_urls: profileUrls,
          message: message.trim(),
          dry_run: dryRun,
        });
      } else {
        response = await sendConnectionRequests({
          user_id: DEFAULT_USER_ID,
          post_id: selectedPostId,
          profile_urls: profileUrls,
          engagement_types: ["like", "comment"],
          note: message.trim(),
          dry_run: dryRun,
        });
      }
      setResult(response);
      setLogs(await fetchLinkedInActionLogs(DEFAULT_USER_ID));
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Networking action failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <AppShell
      active="networking"
      title="Networking"
      subtitle="Preview and run actions for stored post engagers."
      userName={userName}
      threads={userData?.threads || []}
    >
      <div className="page-section networking-workspace">
        <div className="networking-grid">
          <section className="networking-targets">
            <div className="section-heading-row">
              <div><h2>Recipients</h2><p className="muted-copy">Select a tracked post and eligible people.</p></div>
              <button className="secondary-button compact" type="button" onClick={selectAllEligible} disabled={!eligibleEngagers.length}>
                {selectedProfiles.size === eligibleEngagers.length && eligibleEngagers.length ? "Clear" : "Select all"}
              </button>
            </div>

            <label className="field">
              <span>Tracked post</span>
              <select value={selectedPostId} onChange={(event) => setSelectedPostId(event.target.value)}>
                <option value="">Choose a post</option>
                {posts.map((post) => <option value={post.post_id} key={post.post_id}>{previewText(post.text || post.post_id, 90)}</option>)}
              </select>
            </label>

            <div className="action-tabs" role="tablist" aria-label="Networking action">
              <button className={actionType === "connect" ? "selected" : ""} type="button" onClick={() => setActionType("connect")}><UserPlus size={16} /> Connect</button>
              <button className={actionType === "dm" ? "selected" : ""} type="button" onClick={() => setActionType("dm")}><Send size={16} /> DM</button>
              <button className={actionType === "reply" ? "selected" : ""} type="button" onClick={() => setActionType("reply")}><MessageCircle size={16} /> Reply</button>
            </div>

            {loading ? <div className="loading-state"><Loader2 className="spin" size={20} /> Loading...</div> : null}
            {!loading && !eligibleEngagers.length ? <div className="empty-mini">No eligible engagers for this action.</div> : null}
            <div className="recipient-list">
              {eligibleEngagers.map((engager) => (
                <label className="recipient-row" key={engager.profile_key}>
                  <input
                    type="checkbox"
                    checked={selectedProfiles.has(engager.profile_url)}
                    onChange={() => toggleProfile(engager.profile_url)}
                  />
                  <span className="avatar small">{(engager.name || "?").slice(0, 1).toUpperCase()}</span>
                  <span className="recipient-copy">
                    <strong>{engager.name || "Unknown member"}</strong>
                    <small>{previewText(engager.headline || engager.comment_text || "No details", 100)}</small>
                  </span>
                  <span className="status-chip">{engager.connection_degree || "unknown"}</span>
                </label>
              ))}
            </div>
          </section>

          <section className="networking-compose">
            <div className="section-heading-row">
              <div><h2>Action preview</h2><p className="muted-copy">{selectedProfiles.size} selected for {actionType}.</p></div>
              <ShieldCheck size={21} />
            </div>
            {selectedPost ? <div className="source-preview"><span>Source post</span><p>{previewText(selectedPost.text || selectedPost.post_id, 220)}</p></div> : null}
            <label className="field">
              <span>{actionType === "connect" ? "Connection note" : actionType === "reply" ? "Reply text" : "Message"}</span>
              <textarea value={message} onChange={(event) => setMessage(event.target.value)} rows={8} />
            </label>
            <label className="switch-row">
              <input type="checkbox" checked={dryRun} onChange={(event) => setDryRun(event.target.checked)} />
              <span><strong>Dry run</strong><small>Validate and log without touching LinkedIn.</small></span>
            </label>
            {error ? <div className="error-banner">{error}</div> : null}
            <button className="primary-button full" type="button" onClick={executeAction} disabled={busy || !selectedProfiles.size || !message.trim()}>
              {busy ? <Loader2 className="spin" size={17} /> : dryRun ? <ShieldCheck size={17} /> : <Send size={17} />}
              {dryRun ? "Run preview" : `Send ${actionType}`}
            </button>

            {result ? (
              <div className="action-result-list">
                <h3>Results</h3>
                {result.results.map((item) => (
                  <div className="action-result-row" key={item.action_id || item.profile_key}>
                    <span><strong>{item.profile_url.split("/in/")[1]?.replaceAll("/", "") || item.profile_key}</strong><small>{item.skip_reason || item.error_message || item.action_type}</small></span>
                    <span className={`status-chip ${item.status}`}>{item.status}</span>
                  </div>
                ))}
              </div>
            ) : null}
          </section>
        </div>

        <section className="action-log-section">
          <div className="section-heading-row"><div><h2>Action history</h2><p className="muted-copy">Latest sent, skipped, and failed attempts.</p></div></div>
          {logs.length ? (
            <div className="action-log-table-wrap">
              <table className="prospect-table"><thead><tr><th>Action</th><th>Profile</th><th>Status</th><th>Reason</th><th>Created</th></tr></thead>
                <tbody>{logs.slice(0, 30).map((log) => <tr key={log.action_id}><td>{log.action_type}</td><td>{previewText(log.profile_url, 64)}</td><td><span className={`status-chip ${log.status}`}>{log.status}</span></td><td>{log.skip_reason || log.error_message || "-"}</td><td>{compactDate(log.created_at)}</td></tr>)}</tbody>
              </table>
            </div>
          ) : <div className="empty-mini">No actions have been recorded.</div>}
        </section>
      </div>
    </AppShell>
  );
}
