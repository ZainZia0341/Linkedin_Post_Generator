"use client";

import { ArrowRight, ExternalLink, Image as ImageIcon, Loader2, PenLine, Send, Sparkles } from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import {
  backendAssetUrl,
  DEFAULT_USER_ID,
  fetchThread,
  fetchThreads,
  fetchUserData,
  generateImageAsset,
  generatePost,
  refinePost,
} from "@/lib/api";
import {
  IMAGE_STYLE_OPTIONS,
  LENGTH_OPTIONS,
  REFINE_PRESETS,
  TONE_OPTIONS,
  WRITING_STYLE_OPTIONS,
} from "@/lib/constants";
import { compactDate, displayName, previewText, sortThreads, threadTitle } from "@/lib/format";
import type { ImageAssetResponse, ThreadResponse, ThreadSummary, UserDataResponse } from "@/lib/types";

export function GeneratePostView() {
  const searchParams = useSearchParams();
  const selectedThreadId = searchParams.get("thread_id") || "";
  const [userData, setUserData] = useState<UserDataResponse | null>(null);
  const [threads, setThreads] = useState<ThreadSummary[]>([]);
  const [topic, setTopic] = useState("");
  const [tone, setTone] = useState(TONE_OPTIONS[0]);
  const [length, setLength] = useState(LENGTH_OPTIONS[1]);
  const [writingStyle, setWritingStyle] = useState(WRITING_STYLE_OPTIONS[0]);
  const [customInstruction, setCustomInstruction] = useState("");
  const [thread, setThread] = useState<ThreadResponse | null>(null);
  const [imageStyle, setImageStyle] = useState(IMAGE_STYLE_OPTIONS[0]);
  const [imageAsset, setImageAsset] = useState<ImageAssetResponse | null>(null);
  const [generatingImage, setGeneratingImage] = useState(false);
  const [imageError, setImageError] = useState("");
  const [busy, setBusy] = useState(false);
  const [refining, setRefining] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;

    async function load() {
      const [userResult, threadResult, selectedThreadResult] = await Promise.allSettled([
        fetchUserData(DEFAULT_USER_ID),
        fetchThreads(DEFAULT_USER_ID, 8),
        selectedThreadId ? fetchThread(DEFAULT_USER_ID, selectedThreadId) : Promise.resolve(null),
      ]);

      if (cancelled) return;
      if (userResult.status === "fulfilled") setUserData(userResult.value);
      if (threadResult.status === "fulfilled") setThreads(threadResult.value);
      if (selectedThreadResult.status === "fulfilled" && selectedThreadResult.value) {
        const openedThread = selectedThreadResult.value;
        setThread(openedThread);
        setTopic(openedThread.topic || "");
        setThreads((current) => [
          openedThread,
          ...current.filter((item) => item.thread_id !== openedThread.thread_id),
        ]);
      }
      if (selectedThreadResult.status === "rejected") {
        setError(
          selectedThreadResult.reason instanceof Error
            ? selectedThreadResult.reason.message
            : "Could not load selected thread.",
        );
      }
    }

    void load();
    return () => {
      cancelled = true;
    };
  }, [selectedThreadId]);

  const sortedThreads = useMemo(() => sortThreads(threads), [threads]);
  const recentPostThreads = sortedThreads.filter((item) => item.topic_source !== "comment_generation");
  const userName = displayName(userData?.user) || DEFAULT_USER_ID;

  async function handleGenerate() {
    if (!topic.trim()) {
      setError("Add a topic first.");
      return;
    }
    setError("");
    setBusy(true);

    try {
      const result = await generatePost({
        user_id: DEFAULT_USER_ID,
        idea: topic.trim(),
        post_length: length,
        tone,
        writing_style: writingStyle,
        topic_source: "manual",
      });
      setThread(result);
      setThreads((current) => [result, ...current.filter((item) => item.thread_id !== result.thread_id)]);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Could not generate the post.");
    } finally {
      setBusy(false);
    }
  }

  async function handleRefine(instruction: string) {
    if (!thread || !instruction.trim()) return;
    setError("");
    setRefining(instruction);
    try {
      const result = await refinePost({
        user_id: DEFAULT_USER_ID,
        thread_id: thread.thread_id,
        modification_message: instruction.trim(),
      });
      setThread(result);
      setThreads((current) => [result, ...current.filter((item) => item.thread_id !== result.thread_id)]);
      setCustomInstruction("");
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Could not refine the post.");
    } finally {
      setRefining("");
    }
  }

  async function handleGenerateImage() {
    if (!thread?.current_post.trim()) return;
    setGeneratingImage(true);
    setImageError("");
    try {
      const result = await generateImageAsset({
        user_id: DEFAULT_USER_ID,
        prompt: `Supporting visual for: ${(thread.topic || thread.current_post).trim().slice(0, 240)}`,
        post_text: thread.current_post.trim(),
        aspect_ratio: "4:5",
        style: imageStyle,
      });
      setImageAsset(result);
    } catch (exc) {
      setImageError(exc instanceof Error ? exc.message : "Could not generate the image.");
    } finally {
      setGeneratingImage(false);
    }
  }

  return (
    <AppShell
      active="generate"
      title="Generate"
      subtitle="Create and refine LinkedIn posts."
      userName={userName}
      threads={sortedThreads}
    >
      <div className="generate-layout">
        <section className="generator-panel">
          <div className="section-heading-row">
            <div>
              <h2>Generate Post</h2>
              <p className="muted-copy">Shape the post before the backend writes it.</p>
            </div>
            <Sparkles size={22} />
          </div>

          <label className="field">
            <span>Topic</span>
            <textarea
              value={topic}
              onChange={(event) => setTopic(event.target.value)}
              placeholder="AI agents for SaaS teams"
              rows={5}
            />
          </label>

          <div className="form-grid">
            <label className="field">
              <span>Writing style</span>
              <select value={writingStyle} onChange={(event) => setWritingStyle(event.target.value)}>
                {WRITING_STYLE_OPTIONS.map((option) => (
                  <option key={option}>{option}</option>
                ))}
              </select>
            </label>

            <label className="field">
              <span>Tone</span>
              <select value={tone} onChange={(event) => setTone(event.target.value)}>
                {TONE_OPTIONS.map((option) => (
                  <option key={option}>{option}</option>
                ))}
              </select>
            </label>

            <label className="field">
              <span>Length</span>
              <div className="segmented-control">
                {LENGTH_OPTIONS.map((option) => (
                  <button
                    className={length === option ? "selected" : ""}
                    type="button"
                    onClick={() => setLength(option)}
                    key={option}
                  >
                    {option}
                  </button>
                ))}
              </div>
            </label>
          </div>

          {error ? <div className="error-banner">{error}</div> : null}

          <button className="primary-button full" type="button" onClick={handleGenerate} disabled={busy}>
            {busy ? <Loader2 className="spin" size={17} /> : <Send size={17} />}
            Generate Post
          </button>
        </section>

        <section className="output-panel">
          <div className="section-heading-row">
            <div>
              <h2>Draft Output</h2>
              {thread ? <p className="muted-copy">{previewText(thread.topic || topic, 72)}</p> : null}
            </div>
            <PenLine size={22} />
          </div>

          {thread ? (
            <>
              <textarea className="post-output" value={thread.current_post} readOnly rows={16} />

              <div className="context-image-panel">
                <div className="context-image-heading">
                  <div>
                    <h3>Post image</h3>
                    <p>The current post is used automatically as image context.</p>
                  </div>
                  <ImageIcon size={19} />
                </div>
                <div className="context-image-controls">
                  <label className="field">
                    <span>Style</span>
                    <select value={imageStyle} onChange={(event) => setImageStyle(event.target.value)}>
                      {IMAGE_STYLE_OPTIONS.map((option) => <option value={option} key={option}>{option}</option>)}
                    </select>
                  </label>
                  <button className="primary-button" type="button" onClick={handleGenerateImage} disabled={generatingImage}>
                    {generatingImage ? <Loader2 className="spin" size={17} /> : <Sparkles size={17} />}
                    {generatingImage ? "Generating..." : "Generate image"}
                  </button>
                </div>
                {imageError ? <div className="error-banner">{imageError}</div> : null}
                {imageAsset ? (
                  <div className="context-image-result">
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img src={backendAssetUrl(imageAsset.asset_url)} alt="Generated visual for the current post" />
                    <div>
                      <strong>{imageAsset.style}</strong>
                      <span>Saved to the local image asset library.</span>
                      <a className="secondary-button compact" href={backendAssetUrl(imageAsset.asset_url)} target="_blank" rel="noreferrer">
                        <ExternalLink size={15} /> Open image
                      </a>
                    </div>
                  </div>
                ) : null}
              </div>

              <div className="refine-panel">
                <h3>Refine with AI</h3>
                <div className="preset-grid">
                  {REFINE_PRESETS.map((preset) => (
                    <button
                      className="secondary-button compact"
                      type="button"
                      onClick={() => handleRefine(preset)}
                      disabled={Boolean(refining)}
                      key={preset}
                    >
                      {refining === preset ? <Loader2 className="spin" size={15} /> : null}
                      {preset}
                    </button>
                  ))}
                </div>
                <div className="inline-form">
                  <input
                    value={customInstruction}
                    onChange={(event) => setCustomInstruction(event.target.value)}
                    placeholder="Tell AI what to change"
                  />
                  <button
                    className="primary-button compact"
                    type="button"
                    onClick={() => handleRefine(customInstruction)}
                    disabled={!customInstruction.trim() || Boolean(refining)}
                  >
                    <ArrowRight size={15} />
                    Apply
                  </button>
                </div>
              </div>
            </>
          ) : (
            <div className="empty-card tall">
              <h4>No draft generated yet</h4>
              <p>Your generated post will appear here.</p>
            </div>
          )}
        </section>

        <aside className="recent-panel generate-thread-panel">
          <h3>Recent Threads</h3>
          {recentPostThreads.length ? (
            <div className="thread-list">
              {recentPostThreads.slice(0, 6).map((item) => (
                <Link
                  className="thread-link"
                  href={`/generate?thread_id=${encodeURIComponent(item.thread_id)}`}
                  key={item.thread_id}
                >
                  <span>
                    <strong>{threadTitle(item)}</strong>
                    <small>{compactDate(item.updated_at) || "Recent"}</small>
                  </span>
                </Link>
              ))}
            </div>
          ) : (
            <div className="empty-mini">Generated posts will show here.</div>
          )}
        </aside>
      </div>
    </AppShell>
  );
}
