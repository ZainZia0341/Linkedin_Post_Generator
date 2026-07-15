"use client";

import { Bot, CheckCircle2, Copy, ExternalLink, Save, Sparkles, X } from "lucide-react";
import { useEffect, useState } from "react";
import { DEFAULT_USER_ID, fetchThread, modifyComment } from "@/lib/api";
import { initials, previewText } from "@/lib/format";
import type { ActivityResponse, CommentResponse, CreatorProfileDetailsResponse } from "@/lib/types";

type CommentEditorDrawerProps = {
  activity: ActivityResponse;
  profile?: CreatorProfileDetailsResponse;
  initialComment: string;
  threadId?: string;
  styleLabel?: string;
  tone?: string;
  length?: string;
  mode?: "assistant" | "saved";
  onUpdated?: (response: CommentResponse) => void;
  onClose: () => void;
  onSave: (comment: string) => void;
  onMarkCommented?: (comment: string) => void;
};

export function CommentEditorDrawer({
  activity,
  profile,
  initialComment,
  threadId = "",
  styleLabel = "Add Value",
  tone = "Professional",
  length = "Medium",
  mode = "assistant",
  onUpdated,
  onClose,
  onSave,
  onMarkCommented,
}: CommentEditorDrawerProps) {
  const [comment, setComment] = useState(initialComment);
  const [instruction, setInstruction] = useState("");
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const name = profile?.name || activity.author_name || activity.creator_id;

  useEffect(() => {
    setComment(initialComment);
  }, [initialComment]);

  useEffect(() => {
    let cancelled = false;
    async function loadThread() {
      if (!threadId) return;
      try {
        const thread = await fetchThread(DEFAULT_USER_ID, threadId);
        if (!cancelled && thread.current_post) {
          setComment(thread.current_post);
        }
      } catch {
        // Keep the generated comment already passed into the drawer.
      }
    }
    void loadThread();
    return () => {
      cancelled = true;
    };
  }, [threadId]);

  async function copyComment() {
    await navigator.clipboard.writeText(comment);
  }

  async function improveComment(message: string) {
    if (!threadId || !message.trim()) return;
    setBusy(message);
    setError("");
    try {
      const response = await modifyComment({
        user_id: DEFAULT_USER_ID,
        thread_id: threadId,
        modification_message: message.trim(),
        style: styleLabel,
        tone,
        length,
      });
      setComment(response.comment);
      setInstruction("");
      onUpdated?.(response);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Could not improve this comment.");
    } finally {
      setBusy("");
    }
  }

  return (
    <div className="drawer-backdrop">
      <aside className="comment-editor-panel" role="dialog" aria-modal="true" aria-labelledby="comment-editor-title">
        <header className="drawer-header compact-header">
          <div>
            <h2 id="comment-editor-title">AI Comment Editor</h2>
            <p>{mode === "saved" ? `Editing saved comment for ${name}` : "Refine your LinkedIn comment with AI assistance."}</p>
          </div>
          <button className="icon-button" type="button" onClick={onClose} aria-label="Close">
            <X size={19} />
          </button>
        </header>

        <div className="comment-editor-body">
          <article className="comment-target-card">
            <div className="post-author">
              <div className="avatar mini">
                {profile?.profile_image_url ? (
                  <img src={profile.profile_image_url} alt={`${name} profile`} />
                ) : (
                  initials(name)
                )}
              </div>
              <span>
                <strong>{name}</strong>
                <small>{profile?.headline || "Saved creator"}</small>
              </span>
              <em>{mode === "saved" ? "Target" : styleLabel}</em>
            </div>
            <p>"{previewText(activity.raw_text, 130)}"</p>
            {activity.post_url ? (
              <a className="secondary-button compact" href={activity.post_url} target="_blank" rel="noreferrer">
                <ExternalLink size={14} />
                View Original Post
              </a>
            ) : null}
          </article>

          {mode === "saved" ? (
            <section className="comment-style-section">
              <h3>Current Style</h3>
              <div className="comment-style-grid">
                <button className="selected" type="button">
                  <Sparkles size={15} />
                  {styleLabel}
                </button>
                <button type="button">
                  <Bot size={15} />
                  Ask Question
                </button>
              </div>
            </section>
          ) : null}

          <section className="comment-editor-section">
            <div className="comment-editor-label-row">
              <h3>{mode === "saved" ? "Comment Text" : "Current Comment"}</h3>
              <span>{mode === "saved" ? "AI Rewrite" : "Auto-saved locally"}</span>
            </div>
            <textarea value={comment} onChange={(event) => setComment(event.target.value)} />
            <div className="comment-count-row">
              <span>{comment.length} characters</span>
              <span>{comment.split(/\s+/).filter(Boolean).length} words</span>
            </div>
          </section>

          {mode === "saved" ? (
            <section className="comment-tag-section">
              <h3>Context Tags</h3>
              <div className="comment-preset-row">
                <button type="button">Systems</button>
                <button type="button">Strategy</button>
                <button type="button">+ Add Tag</button>
              </div>
            </section>
          ) : (
            <section className="ai-assistant-box">
              <h3><Sparkles size={16} /> AI Assistant</h3>
              {error ? <div className="error-banner">{error}</div> : null}
              <div className="assistant-message">
                <Bot size={15} />
                <span>{threadId ? "Ask AI to refine this comment. Changes are saved to the comment thread." : "Generate this comment again to create an editable thread."}</span>
              </div>
              <div className="comment-improve-row">
                <input
                  value={instruction}
                  onChange={(event) => setInstruction(event.target.value)}
                  placeholder="Tell AI how you want to improve this comment..."
                />
                <button
                  className="primary-button compact"
                  type="button"
                  onClick={() => void improveComment(instruction)}
                  disabled={!threadId || !instruction.trim() || Boolean(busy)}
                >
                  {busy === instruction ? "Improving..." : "Improve"}
                </button>
              </div>
              <div className="comment-preset-row">
                {[
                  "Make Shorter",
                  "Make Longer",
                  "More Professional",
                  "More Human",
                  "More Engaging",
                  "Ask a Question",
                ].map((label) => (
                  <button type="button" key={label} onClick={() => void improveComment(label)} disabled={!threadId || Boolean(busy)}>
                    {busy === label ? "Working..." : label}
                  </button>
                ))}
              </div>
            </section>
          )}
        </div>

        <footer className="comment-editor-footer">
          <button className="secondary-button" type="button" onClick={onClose}>Cancel</button>
          <button className="secondary-button" type="button" onClick={() => void copyComment()}>
            <Copy size={15} />
            Copy Comment
          </button>
          <button className="primary-button" type="button" onClick={() => onSave(comment)}>
            <Save size={15} />
            Save Changes
          </button>
          {onMarkCommented ? (
            <button className="secondary-button" type="button" onClick={() => onMarkCommented(comment)}>
              <CheckCircle2 size={15} />
              Mark Commented
            </button>
          ) : null}
        </footer>
      </aside>
    </div>
  );
}
