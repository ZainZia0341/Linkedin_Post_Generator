"use client";

import Link from "next/link";
import { ArrowLeft, CheckCircle2, Copy, ExternalLink, Loader2, Pencil, Sparkles } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import { CommentEditorDrawer } from "@/components/CommentEditorDrawer";
import {
  DEFAULT_USER_ID,
  fetchCreatorActivities,
  fetchCreatorProfiles,
  fetchUserActivities,
  fetchUserData,
  generateComment,
  markComment,
} from "@/lib/api";
import { compactDate, displayName, initials, previewText, sortThreads } from "@/lib/format";
import type { ActivityResponse, CommentResponse, CreatorProfileDetailsResponse, UserDataResponse } from "@/lib/types";

type CommentVariant = {
  id: string;
  label: string;
  topic: string;
  comment: string;
  generatedAt?: string;
};

const VARIANT_TOPICS = [
  { id: "add-value", label: "Add Value", topic: "Add Value" },
  { id: "challenge", label: "Challenge", topic: "Challenge" },
  { id: "expert", label: "Expert Insight", topic: "Expert Insight" },
];

export function CommentGenerationView() {
  const searchParams = useSearchParams();
  const creatorId = searchParams.get("creator_id") || "";
  const postId = searchParams.get("post_id") || "";
  const [userData, setUserData] = useState<UserDataResponse | null>(null);
  const [activity, setActivity] = useState<ActivityResponse | null>(null);
  const [profileMap, setProfileMap] = useState<Map<string, CreatorProfileDetailsResponse>>(new Map());
  const [style, setStyle] = useState("Add Value");
  const [tone, setTone] = useState("Professional");
  const [length, setLength] = useState("Medium");
  const [variants, setVariants] = useState<CommentVariant[]>([]);
  const [selected, setSelected] = useState<CommentVariant | null>(null);
  const [editing, setEditing] = useState<CommentVariant | null>(null);
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
      const [dataResult, activityResult, profileResult] = await Promise.allSettled([
        fetchUserData(DEFAULT_USER_ID),
        fetchUserActivities(DEFAULT_USER_ID, 200),
        fetchCreatorProfiles(DEFAULT_USER_ID, 500),
      ]);
      if (dataResult.status === "rejected") throw dataResult.reason;
      if (activityResult.status === "rejected") throw activityResult.reason;
      setUserData(dataResult.value);
      const found = activityResult.value.find((item) => item.creator_id === creatorId && item.post_id === postId);
      if (found) {
        setActivity(found);
      } else if (creatorId) {
        const creatorActivities = await fetchCreatorActivities(DEFAULT_USER_ID, creatorId, 100);
        setActivity(creatorActivities.find((item) => item.post_id === postId) || null);
      }
      if (profileResult.status === "fulfilled") {
        setProfileMap(new Map(profileResult.value.map((profile) => [profile.creator_id, profile])));
      }
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Could not load comment generation data.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, [creatorId, postId]);

  const sortedThreads = useMemo(() => sortThreads(userData?.threads ?? []), [userData?.threads]);
  const userName = displayName(userData?.user) || DEFAULT_USER_ID;
  const profile = activity ? profileMap.get(activity.creator_id) : undefined;
  const creatorName = profile?.name || activity?.author_name || activity?.creator_id || "Creator";
  const canGenerate = Boolean(activity && !busy);

  async function generateVariants() {
    if (!activity) return;
    setBusy("generate");
    setError("");
    try {
      const orderedTopics = [
        { id: "primary", label: style, topic: style },
        ...VARIANT_TOPICS.filter((topic) => topic.topic !== style),
      ].slice(0, 3);
      const responses = await Promise.all(
        orderedTopics.map((topic) =>
          generateComment({
            user_id: DEFAULT_USER_ID,
            creator_id: activity.creator_id,
            post_id: activity.post_id,
            comment_topic: `${topic.topic}. Tone: ${tone}. Length: ${length}.`,
          }),
        ),
      );
      const nextVariants = responses.map((response: CommentResponse, index) => ({
        id: orderedTopics[index].id,
        label: orderedTopics[index].label,
        topic: response.comment_topic || orderedTopics[index].topic,
        comment: response.comment,
        generatedAt: response.generated_at,
      }));
      setVariants(nextVariants);
      setSelected(nextVariants[0] || null);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Could not generate comment variations.");
    } finally {
      setBusy("");
    }
  }

  async function saveComment(comment: string, commented: boolean) {
    if (!activity) return;
    setBusy(commented ? "mark" : "save");
    setError("");
    try {
      await markComment({
        user_id: DEFAULT_USER_ID,
        creator_id: activity.creator_id,
        post_id: activity.post_id,
        commented,
        comment_text: comment,
      });
      setVariants((current) =>
        current.map((variant) => variant.id === editing?.id ? { ...variant, comment } : variant),
      );
      if (selected?.id === editing?.id || !selected) {
        setSelected(editing ? { ...editing, comment } : { id: "saved", label: style, topic: style, comment });
      }
      setEditing(null);
      showSuccess(commented ? "Comment marked as completed" : "Comment saved");
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Could not save comment.");
    } finally {
      setBusy("");
    }
  }

  async function copySelected() {
    if (!selected) return;
    await navigator.clipboard.writeText(selected.comment);
    showSuccess("Comment copied");
  }

  return (
    <AppShell
      active="posts"
      title="Generate Comment"
      subtitle="Create high-engagement replies for LinkedIn author posts."
      userName={userName}
      threads={sortedThreads}
    >
      <section className="comment-generation-page">
        <div className="comment-page-heading">
          <Link className="icon-button" href="/posts-scraping" aria-label="Back to creator posts">
            <ArrowLeft size={18} />
          </Link>
          <div>
            <p className="breadcrumb-inline">Creator Posts & Scraping / Comment Generation</p>
            <h2>Generate Comment</h2>
            <span>Create high-engagement replies for LinkedIn author posts.</span>
          </div>
          <Link className="secondary-button compact" href="/history">
            View Comment History
          </Link>
        </div>

        {error ? <div className="error-banner">{error}</div> : null}
        {loading ? <div className="empty-card slim">Loading comment workspace...</div> : null}

        {activity ? (
          <>
            <article className="comment-target-card large">
              <div className="post-author">
                <div className="avatar mini">
                  {profile?.profile_image_url ? (
                    <img src={profile.profile_image_url} alt={`${creatorName} profile`} />
                  ) : (
                    initials(creatorName)
                  )}
                </div>
                <span>
                  <strong>{creatorName}</strong>
                  <small>{profile?.headline || "Saved creator post"}</small>
                </span>
              </div>
              {activity.post_url ? (
                <a className="secondary-button compact" href={activity.post_url} target="_blank" rel="noreferrer">
                  <ExternalLink size={14} />
                  View Full Post
                </a>
              ) : null}
              <p>"{previewText(activity.raw_text, 260)}"</p>
            </article>

            <section className="comment-controls-card">
              <label>
                <span>Style</span>
                <select value={style} onChange={(event) => setStyle(event.target.value)}>
                  {["Add Value", "Challenge", "Expert Insight", "Agree", "Congratulate"].map((item) => (
                    <option value={item} key={item}>{item}</option>
                  ))}
                </select>
              </label>
              <label>
                <span>Tone</span>
                <select value={tone} onChange={(event) => setTone(event.target.value)}>
                  {["Professional", "Human", "Founder", "Direct"].map((item) => (
                    <option value={item} key={item}>{item}</option>
                  ))}
                </select>
              </label>
              <div>
                <span>Length</span>
                <div className="length-segments">
                  {["Short", "Medium", "Long"].map((item) => (
                    <button
                      className={length === item ? "selected" : ""}
                      type="button"
                      onClick={() => setLength(item)}
                      key={item}
                    >
                      {item}
                    </button>
                  ))}
                </div>
              </div>
              <button className="primary-button" type="button" onClick={generateVariants} disabled={!canGenerate}>
                {busy === "generate" ? <Loader2 className="spin" size={17} /> : <Sparkles size={17} />}
                Generate Comment Variations
              </button>
            </section>

            <section className="comment-variations-section">
              <div className="section-heading-row">
                <h2>Comment Variations</h2>
                {busy === "generate" ? <span className="muted-copy">AI is refining thoughts...</span> : null}
              </div>
              <div className="comment-variation-grid">
                {variants.length ? (
                  variants.map((variant) => (
                    <article className={selected?.id === variant.id ? "comment-variation-card selected" : "comment-variation-card"} key={variant.id}>
                      <span>{variant.label}</span>
                      <p>{variant.comment}</p>
                      <footer>
                        <button type="button" onClick={() => setSelected(variant)}>Use This</button>
                        <button type="button" onClick={() => void navigator.clipboard.writeText(variant.comment)} aria-label="Copy comment">
                          <Copy size={15} />
                        </button>
                        <button type="button" onClick={() => setEditing(variant)} aria-label="Edit comment">
                          <Pencil size={15} />
                        </button>
                      </footer>
                    </article>
                  ))
                ) : (
                  <div className="empty-mini">Generate variations to review comment options.</div>
                )}
              </div>
            </section>

            <footer className="comment-action-footer">
              <Link className="secondary-button" href="/posts-scraping">Back to Creator Posts</Link>
              <button className="secondary-button" type="button" onClick={generateVariants} disabled={!canGenerate}>
                Regenerate Variations
              </button>
              <button className="secondary-button" type="button" onClick={() => void copySelected()} disabled={!selected}>
                Copy Comment
              </button>
              <button
                className="primary-button"
                type="button"
                disabled={!selected || Boolean(busy)}
                onClick={() => selected ? void saveComment(selected.comment, true) : undefined}
              >
                {busy === "mark" ? <Loader2 className="spin" size={17} /> : <CheckCircle2 size={17} />}
                Mark Commented
              </button>
            </footer>
          </>
        ) : !loading ? (
          <div className="empty-card slim">Select a scraped post before generating comments.</div>
        ) : null}
      </section>

      {editing && activity ? (
        <CommentEditorDrawer
          activity={activity}
          profile={profile}
          initialComment={editing.comment}
          styleLabel={editing.label}
          onClose={() => setEditing(null)}
          onSave={(comment) => void saveComment(comment, false)}
          onMarkCommented={(comment) => void saveComment(comment, true)}
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
