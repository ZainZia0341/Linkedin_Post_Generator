"use client";

import { Bot, CheckCircle2, Copy, ExternalLink, Save, Sparkles, X } from "lucide-react";
import { useEffect, useState } from "react";
import { initials, previewText } from "@/lib/format";
import type { ActivityResponse, CreatorProfileDetailsResponse } from "@/lib/types";

type CommentEditorDrawerProps = {
  activity: ActivityResponse;
  profile?: CreatorProfileDetailsResponse;
  initialComment: string;
  styleLabel?: string;
  mode?: "assistant" | "saved";
  onClose: () => void;
  onSave: (comment: string) => void;
  onMarkCommented?: (comment: string) => void;
};

export function CommentEditorDrawer({
  activity,
  profile,
  initialComment,
  styleLabel = "Add Value",
  mode = "assistant",
  onClose,
  onSave,
  onMarkCommented,
}: CommentEditorDrawerProps) {
  const [comment, setComment] = useState(initialComment);
  const name = profile?.name || activity.author_name || activity.creator_id;

  useEffect(() => {
    setComment(initialComment);
  }, [initialComment]);

  function applySuggestion(text: string) {
    setComment(text);
  }

  async function copyComment() {
    await navigator.clipboard.writeText(comment);
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
              <div className="assistant-message user">Make this sound more conversational.</div>
              <div className="assistant-message">
                <Bot size={15} />
                <span>Here is a more natural version that keeps the same point.</span>
              </div>
              <blockquote>
                "{makeConversational(comment)}"
                <button type="button" onClick={() => applySuggestion(makeConversational(comment))}>
                  Apply Suggestion
                </button>
              </blockquote>
              <div className="comment-preset-row">
                {[
                  "Make Shorter",
                  "Make Longer",
                  "More Professional",
                  "More Human",
                  "More Engaging",
                  "Ask a Question",
                ].map((label) => (
                  <button type="button" key={label} onClick={() => setComment(`${comment} ${presetTail(label)}`.trim())}>
                    {label}
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

function makeConversational(comment: string) {
  const cleaned = comment.trim();
  if (!cleaned) return "I like this framing. The real unlock is making the idea easier to act on, not just easier to agree with.";
  return cleaned
    .replace(/^One thing I'?d add is that/i, "I would add that")
    .replace(/\btherefore\b/gi, "so")
    .replace(/\butilize\b/gi, "use");
}

function presetTail(label: string) {
  if (label === "Ask a Question") return "What would you watch for first when applying this?";
  if (label === "More Engaging") return "That is the part most teams underestimate.";
  if (label === "More Human") return "I have seen this become very real once ownership gets unclear.";
  if (label === "More Professional") return "This is especially important when execution depends on multiple teams.";
  if (label === "Make Longer") return "The practical test is whether someone can act on it without needing extra context.";
  return "";
}
