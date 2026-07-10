"use client";

import { ArrowRight, Loader2, PenLine, Send, Sparkles } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { AppShell } from "@/components/AppShell";
import {
  DEFAULT_USER_ID,
  fetchPostTypes,
  fetchThreads,
  fetchUserData,
  generatePost,
  refinePost,
} from "@/lib/api";
import {
  LENGTH_OPTIONS,
  REFINE_PRESETS,
  TONE_OPTIONS,
  WRITING_STYLE_OPTIONS,
} from "@/lib/constants";
import { displayName, previewText, sortThreads } from "@/lib/format";
import type { ThreadResponse, ThreadSummary, UserDataResponse } from "@/lib/types";

export function GeneratePostView() {
  const [userData, setUserData] = useState<UserDataResponse | null>(null);
  const [threads, setThreads] = useState<ThreadSummary[]>([]);
  const [postTypes, setPostTypes] = useState<string[]>([]);
  const [topic, setTopic] = useState("");
  const [postType, setPostType] = useState("");
  const [tone, setTone] = useState(TONE_OPTIONS[0]);
  const [length, setLength] = useState(LENGTH_OPTIONS[1]);
  const [writingStyle, setWritingStyle] = useState(WRITING_STYLE_OPTIONS[0]);
  const [customInstruction, setCustomInstruction] = useState("");
  const [thread, setThread] = useState<ThreadResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [refining, setRefining] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;

    async function load() {
      const [userResult, threadResult, styleResult] = await Promise.allSettled([
        fetchUserData(DEFAULT_USER_ID),
        fetchThreads(DEFAULT_USER_ID, 8),
        fetchPostTypes(),
      ]);

      if (cancelled) return;
      if (userResult.status === "fulfilled") setUserData(userResult.value);
      if (threadResult.status === "fulfilled") setThreads(threadResult.value);
      if (styleResult.status === "fulfilled" && styleResult.value.length) {
        setPostTypes(styleResult.value);
        if (!styleResult.value.includes(postType)) setPostType(styleResult.value[0]);
      }
    }

    void load();
    return () => {
      cancelled = true;
    };
  }, []);

  const sortedThreads = useMemo(() => sortThreads(threads), [threads]);
  const userName = displayName(userData?.user) || DEFAULT_USER_ID;

  async function handleGenerate() {
    if (!topic.trim()) {
      setError("Add a topic first.");
      return;
    }
    setError("");
    setBusy(true);

    const idea = [
      topic.trim(),
      "",
      `Tone: ${tone}.`,
      `Length: ${length}.`,
      `Writing style: ${writingStyle}.`,
    ].join("\n");

    try {
      const result = await generatePost({
        user_id: DEFAULT_USER_ID,
        idea,
        generation_style: postType,
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
              <span>Post type</span>
              <select value={postType} onChange={(event) => setPostType(event.target.value)} disabled={!postTypes.length}>
                {postTypes.length ? (
                  postTypes.map((option) => <option key={option}>{option}</option>)
                ) : (
                  <option>Load post types from API</option>
                )}
              </select>
            </label>

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

          <button className="primary-button full" type="button" onClick={handleGenerate} disabled={busy || !postType}>
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
      </div>
    </AppShell>
  );
}
