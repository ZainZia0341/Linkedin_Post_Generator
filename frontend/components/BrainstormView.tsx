"use client";

import { ArrowRight, Brain, Check, Clipboard, ExternalLink, Lightbulb, Loader2, Search } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { brainstormIdeas, DEFAULT_USER_ID, fetchUserData } from "@/lib/api";
import { displayName } from "@/lib/format";
import type { BrainstormResponse, UserDataResponse } from "@/lib/types";

const actions = [
  "Brainstorm post topics",
  "Find audience pain points",
  "Find common mistakes around my topic",
  "Find common misconceptions people have about a topic",
  "Brainstorm book recommendation about a topic",
  "Brainstorm documentary recommendations about a topic",
  "Brainstorm useful tools about a topic",
];

export function BrainstormView() {
  const [userData, setUserData] = useState<UserDataResponse | null>(null);
  const [topic, setTopic] = useState("");
  const [action, setAction] = useState(actions[0]);
  const [result, setResult] = useState<BrainstormResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [copiedIndex, setCopiedIndex] = useState<number | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    fetchUserData(DEFAULT_USER_ID).then(setUserData).catch(() => undefined);
  }, []);

  const userName = displayName(userData?.user) || DEFAULT_USER_ID;

  async function generateIdeas() {
    setLoading(true);
    setError("");
    try {
      setResult(await brainstormIdeas({ user_id: DEFAULT_USER_ID, topic: topic.trim() || undefined, action }));
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Could not generate ideas.");
    } finally {
      setLoading(false);
    }
  }

  async function copyIdea(index: number) {
    const idea = result?.ideas[index];
    if (!idea) return;
    await navigator.clipboard.writeText(`${idea.title}\n\n${idea.summary}\n\nAngle\n${idea.post_angle}`);
    setCopiedIndex(index);
    window.setTimeout(() => setCopiedIndex(null), 1600);
  }

  return (
    <AppShell
      active="brainstorm"
      title="Brainstorm"
      subtitle="Research useful angles before turning one into a post."
      userName={userName}
    >
      <div className="brainstorm-page">
        {error ? <div className="error-banner">{error}</div> : null}

        <div className="brainstorm-layout">
          <section className="brainstorm-controls">
            <div className="section-heading-row">
              <div>
                <h2>Find ideas</h2>
                <p>Choose the kind of thinking you need, then give it a subject.</p>
              </div>
              <Brain size={21} />
            </div>

            <label className="field">
              <span>Goal</span>
              <select value={action} onChange={(event) => setAction(event.target.value)}>
                {actions.map((option) => <option value={option} key={option}>{option}</option>)}
              </select>
            </label>

            <label className="field">
              <span>Topic</span>
              <textarea
                value={topic}
                onChange={(event) => setTopic(event.target.value)}
                placeholder="Example: practical AI workflows for small teams"
                rows={7}
              />
            </label>

            <button className="primary-button full" type="button" onClick={generateIdeas} disabled={loading}>
              {loading ? <Loader2 className="spin" size={17} /> : <Search size={17} />}
              {loading ? "Researching..." : "Find ideas"}
            </button>
          </section>

          <section className="brainstorm-results">
            <div className="section-heading-row">
              <div>
                <h2>Ideas</h2>
                <p>{result ? `${result.ideas.length} directions for ${result.topic}` : "Your researched directions will appear here."}</p>
              </div>
              {result ? <span className="status-pill">{result.ideas.length} found</span> : null}
            </div>

            {result?.ideas.length ? (
              <div className="brainstorm-idea-grid">
                {result.ideas.map((idea, index) => (
                  <article className="brainstorm-idea-card" key={`${idea.title}-${index}`}>
                    <div className="brainstorm-idea-number">{String(index + 1).padStart(2, "0")}</div>
                    <h3>{idea.title}</h3>
                    <p>{idea.summary}</p>
                    <div className="brainstorm-angle">
                      <Lightbulb size={15} />
                      <span>{idea.post_angle}</span>
                    </div>
                    <div className="brainstorm-idea-actions">
                      <button className="icon-button" type="button" title="Copy idea" aria-label="Copy idea" onClick={() => void copyIdea(index)}>
                        {copiedIndex === index ? <Check size={16} /> : <Clipboard size={16} />}
                      </button>
                      {idea.source_url ? (
                        <a className="secondary-button compact" href={idea.source_url} target="_blank" rel="noreferrer">
                          <ExternalLink size={15} /> Source
                        </a>
                      ) : null}
                      <Link
                        className="primary-button compact"
                        href={`/content/post-builder?topic=${encodeURIComponent(`${idea.title}\n\n${idea.post_angle}`)}`}
                      >
                        Build post <ArrowRight size={15} />
                      </Link>
                    </div>
                  </article>
                ))}
              </div>
            ) : (
              <div className="brainstorm-empty">
                {loading ? <Loader2 className="spin" size={24} /> : <Lightbulb size={25} />}
                <strong>{loading ? "Looking for useful directions" : "Start with a subject"}</strong>
                <span>{loading ? "Research can take a moment." : "A broad topic is enough. You can narrow the result in Post Builder."}</span>
              </div>
            )}

            {result?.research_suggestions.length ? (
              <div className="brainstorm-followups">
                <span>Explore next</span>
                <div>
                  {result.research_suggestions.map((suggestion) => (
                    <button type="button" key={suggestion} onClick={() => setTopic(suggestion)}>{suggestion}</button>
                  ))}
                </div>
              </div>
            ) : null}
          </section>
        </div>
      </div>
    </AppShell>
  );
}
