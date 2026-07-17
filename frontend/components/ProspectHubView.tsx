"use client";

import {
  ExternalLink,
  Loader2,
  MessageCircle,
  RefreshCw,
  Search,
  ThumbsUp,
  UserPlus,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { AppShell } from "@/components/AppShell";
import {
  DEFAULT_USER_ID,
  fetchLinkedInProspects,
  fetchOwnLinkedInPosts,
  fetchUserData,
  scrapeOwnPostEngagement,
  syncOwnLinkedInPosts,
  trackOwnLinkedInPost,
} from "@/lib/api";
import { compactDate, displayName, previewText } from "@/lib/format";
import type { LinkedInProspectResponse, OwnPostResponse, UserDataResponse } from "@/lib/types";

export function ProspectHubView() {
  const [userData, setUserData] = useState<UserDataResponse | null>(null);
  const [posts, setPosts] = useState<OwnPostResponse[]>([]);
  const [prospects, setProspects] = useState<LinkedInProspectResponse[]>([]);
  const [selectedPostId, setSelectedPostId] = useState("");
  const [search, setSearch] = useState("");
  const [engagementType, setEngagementType] = useState("");
  const [profileUrl, setProfileUrl] = useState("");
  const [postUrl, setPostUrl] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  async function loadWorkspace() {
    const [postsResult, prospectResult] = await Promise.all([
      fetchOwnLinkedInPosts(DEFAULT_USER_ID),
      fetchLinkedInProspects(DEFAULT_USER_ID),
    ]);
    setPosts(postsResult);
    setProspects(prospectResult);
    setSelectedPostId((current) => current || postsResult[0]?.post_id || "");
  }

  useEffect(() => {
    let cancelled = false;
    fetchUserData(DEFAULT_USER_ID)
      .then((result) => { if (!cancelled) setUserData(result); })
      .catch(() => undefined);
    loadWorkspace()
      .catch((exc) => {
        if (!cancelled) setError(exc instanceof Error ? exc.message : "Could not load Prospect Hub.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const visibleProspects = useMemo(() => {
    const query = search.trim().toLowerCase();
    return prospects.filter((prospect) => {
      if (engagementType && !prospect.engagement_types.includes(engagementType)) return false;
      if (!query) return true;
      return `${prospect.name} ${prospect.headline} ${prospect.profile_url}`.toLowerCase().includes(query);
    });
  }, [engagementType, prospects, search]);

  const selectedPost = posts.find((post) => post.post_id === selectedPostId) || null;
  const commenterCount = prospects.filter((item) => item.engagement_types.includes("comment")).length;
  const likerCount = prospects.filter((item) => item.engagement_types.includes("like")).length;
  const userName = displayName(userData?.user) || DEFAULT_USER_ID;

  async function refreshProspects() {
    const [postResult, prospectResult] = await Promise.all([
      fetchOwnLinkedInPosts(DEFAULT_USER_ID),
      fetchLinkedInProspects(DEFAULT_USER_ID),
    ]);
    setPosts(postResult);
    setProspects(prospectResult);
    setSelectedPostId((current) => current || postResult[0]?.post_id || "");
  }

  async function handleSync() {
    setBusy("sync");
    setError("");
    setNotice("");
    try {
      const result = await syncOwnLinkedInPosts({
        user_id: DEFAULT_USER_ID,
        profile_url: profileUrl.trim() || undefined,
        window_hours: 72,
        max_posts: 30,
        launch_delay_seconds: 3,
      });
      await refreshProspects();
      setNotice(`Checked ${result.checked_count} posts and saved ${result.saved_count}.`);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Could not sync LinkedIn posts.");
    } finally {
      setBusy("");
    }
  }

  async function handleTrack() {
    if (!postUrl.trim()) return;
    setBusy("track");
    setError("");
    try {
      const result = await trackOwnLinkedInPost({
        user_id: DEFAULT_USER_ID,
        post_url: postUrl.trim(),
        source: "direct",
      });
      await refreshProspects();
      setSelectedPostId(result.post_id);
      setPostUrl("");
      setNotice("Post added to engagement tracking.");
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Could not track this post.");
    } finally {
      setBusy("");
    }
  }

  async function handleScrapeEngagement() {
    if (!selectedPostId) return;
    setBusy("engagement");
    setError("");
    setNotice("");
    try {
      const result = await scrapeOwnPostEngagement(selectedPostId, DEFAULT_USER_ID);
      await refreshProspects();
      const warning = result.warnings[0] ? ` ${result.warnings[0]}` : "";
      setNotice(`Saved ${result.engagers_saved} engagers.${warning}`);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Could not scrape post engagement.");
    } finally {
      setBusy("");
    }
  }

  return (
    <AppShell
      active="prospects"
      title="Prospect Hub"
      subtitle="People who engaged with your tracked LinkedIn posts."
      userName={userName}
      threads={userData?.threads || []}
    >
      <div className="page-section prospect-workspace">
        <section className="metric-strip" aria-label="Prospect summary">
          <div><span>Total prospects</span><strong>{prospects.length}</strong></div>
          <div><span>Commenters</span><strong>{commenterCount}</strong></div>
          <div><span>Likers</span><strong>{likerCount}</strong></div>
          <div><span>Tracked posts</span><strong>{posts.length}</strong></div>
        </section>

        <section className="prospect-control-band">
          <div className="control-group grow">
            <label htmlFor="profile-url">LinkedIn profile URL</label>
            <div className="inline-control">
              <input
                id="profile-url"
                value={profileUrl}
                onChange={(event) => setProfileUrl(event.target.value)}
                placeholder="Optional when saved on your account"
              />
              <button className="primary-button compact" type="button" onClick={handleSync} disabled={Boolean(busy)}>
                {busy === "sync" ? <Loader2 className="spin" size={16} /> : <RefreshCw size={16} />}
                Sync recent posts
              </button>
            </div>
          </div>
          <div className="control-group grow">
            <label htmlFor="post-url">Track a post directly</label>
            <div className="inline-control">
              <input
                id="post-url"
                value={postUrl}
                onChange={(event) => setPostUrl(event.target.value)}
                placeholder="https://www.linkedin.com/feed/update/..."
              />
              <button className="secondary-button compact" type="button" onClick={handleTrack} disabled={!postUrl.trim() || Boolean(busy)}>
                {busy === "track" ? <Loader2 className="spin" size={16} /> : <UserPlus size={16} />}
                Track
              </button>
            </div>
          </div>
        </section>

        {error ? <div className="error-banner">{error}</div> : null}
        {notice ? <div className="success-banner">{notice}</div> : null}

        <section className="tracked-post-band">
          <div className="section-heading-row">
            <div>
              <h2>Engagement source</h2>
              <p className="muted-copy">Choose one tracked post before refreshing its engagement list.</p>
            </div>
            <button
              className="primary-button compact"
              type="button"
              onClick={handleScrapeEngagement}
              disabled={!selectedPostId || Boolean(busy)}
            >
              {busy === "engagement" ? <Loader2 className="spin" size={16} /> : <RefreshCw size={16} />}
              Scrape engagement
            </button>
          </div>
          {posts.length ? (
            <div className="tracked-post-list">
              {posts.map((post) => (
                <button
                  className={post.post_id === selectedPostId ? "tracked-post-option selected" : "tracked-post-option"}
                  type="button"
                  onClick={() => setSelectedPostId(post.post_id)}
                  key={post.post_id}
                >
                  <strong>{previewText(post.text || post.post_id, 72)}</strong>
                  <span>{post.reaction_count} reactions | {post.comment_count} comments</span>
                </button>
              ))}
            </div>
          ) : (
            <div className="empty-mini">Sync recent posts or track a post URL to begin.</div>
          )}
          {selectedPost?.post_url ? (
            <a className="text-link" href={selectedPost.post_url} target="_blank" rel="noreferrer">
              <ExternalLink size={14} /> Open selected post
            </a>
          ) : null}
        </section>

        <section className="prospect-list-section">
          <div className="prospect-toolbar">
            <label className="search-field">
              <Search size={16} />
              <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search prospects" />
            </label>
            <select value={engagementType} onChange={(event) => setEngagementType(event.target.value)}>
              <option value="">All engagement</option>
              <option value="comment">Commented</option>
              <option value="like">Liked</option>
            </select>
            <span className="result-count">{visibleProspects.length} people</span>
          </div>

          {loading ? (
            <div className="loading-state"><Loader2 className="spin" size={20} /> Loading prospects...</div>
          ) : visibleProspects.length ? (
            <div className="prospect-table-wrap">
              <table className="prospect-table">
                <thead><tr><th>Prospect</th><th>Engagement</th><th>Posts</th><th>Eligibility</th><th>Last seen</th></tr></thead>
                <tbody>
                  {visibleProspects.map((prospect) => (
                    <tr key={prospect.prospect_id}>
                      <td>
                        <div className="person-cell">
                          <div className="avatar small">{(prospect.name || "?").slice(0, 1).toUpperCase()}</div>
                          <span>
                            <a href={prospect.profile_url} target="_blank" rel="noreferrer">{prospect.name || "Unknown member"}</a>
                            <small>{previewText(prospect.headline || "Headline unavailable", 100)}</small>
                          </span>
                        </div>
                      </td>
                      <td><div className="tag-row">{prospect.engagement_types.map((type) => <span className="status-chip" key={type}>{type}</span>)}</div></td>
                      <td>{prospect.source_post_count}</td>
                      <td>
                        <div className="eligibility-icons">
                          <span className={prospect.can_reply ? "eligible" : ""} title="Reply"><MessageCircle size={15} /></span>
                          <span className={prospect.can_dm ? "eligible" : ""} title="Direct message"><ThumbsUp size={15} /></span>
                          <span className={prospect.can_connect ? "eligible" : ""} title="Connect"><UserPlus size={15} /></span>
                        </div>
                      </td>
                      <td>{compactDate(prospect.last_engaged_at) || "Unknown"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="empty-card"><h4>No prospects found</h4><p>Scrape engagement for a tracked post, then refresh this list.</p></div>
          )}
        </section>
      </div>
    </AppShell>
  );
}
