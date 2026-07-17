"use client";

import {
  ArrowRight,
  Check,
  Clipboard,
  ExternalLink,
  Lightbulb,
  Link2,
  Loader2,
  Sparkles,
} from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { AppShell } from "@/components/AppShell";
import {
  brainstormIdeas,
  DEFAULT_USER_ID,
  extractContentSource,
  fetchUserData,
  generatePostBuilder,
} from "@/lib/api";
import { displayName } from "@/lib/format";
import type { ContentSourceResponse, ThreadResponse, UserDataResponse } from "@/lib/types";

const variations = ["Actionable", "Storytelling", "Thought-provoking", "Promotional"];
const formats = ["Listicle", "Concise", "Long-form", "Emoji-free", "Numbers", "One-liner"];
const tones = ["Professional", "Assertive", "Enthusiastic", "Friendly", "Humorous", "Formal", "Serious", "Humble", "Persuasive", "Straightforward", "Optimistic"];
const angles = ["Contrarian", "Inspirational", "Story", "Life Experience", "Easy Steps", "Comparison", "Tactical", "My Secret"];
const structures = ["None", "AIDA", "PAS", "BAB", "PPP"];

function ToggleGroup({
  label,
  options,
  selected,
  onToggle,
  single = false,
}: {
  label: string;
  options: string[];
  selected: string[];
  onToggle: (value: string) => void;
  single?: boolean;
}) {
  return (
    <div className="builder-option-group">
      <div className="builder-option-label"><span>{label}</span>{single ? <small>Select one</small> : <small>Select up to 5</small>}</div>
      <div className="choice-chip-row">
        {options.map((option) => (
          <button
            className={selected.includes(option) ? "choice-chip selected" : "choice-chip"}
            type="button"
            key={option}
            onClick={() => onToggle(option)}
          >
            {selected.includes(option) ? <Check size={13} /> : null}{option}
          </button>
        ))}
      </div>
    </div>
  );
}

export function PostBuilderView() {
  const [userData, setUserData] = useState<UserDataResponse | null>(null);
  const [mode, setMode] = useState<"idea" | "url">("idea");
  const [topic, setTopic] = useState("");
  const [sourceUrl, setSourceUrl] = useState("");
  const [source, setSource] = useState<ContentSourceResponse | null>(null);
  const [selectedVariations, setSelectedVariations] = useState(["Actionable"]);
  const [selectedFormats, setSelectedFormats] = useState(["Concise"]);
  const [selectedTones, setSelectedTones] = useState(["Professional"]);
  const [selectedAngles, setSelectedAngles] = useState(["Tactical"]);
  const [structure, setStructure] = useState("None");
  const [length, setLength] = useState("medium");
  const [postCount, setPostCount] = useState(1);
  const [results, setResults] = useState<ThreadResponse[]>([]);
  const [suggestions, setSuggestions] = useState<Array<{ title: string; summary: string }>>([]);
  const [loadingSource, setLoadingSource] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [suggesting, setSuggesting] = useState(false);
  const [copiedId, setCopiedId] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    fetchUserData(DEFAULT_USER_ID).then(setUserData).catch(() => undefined);
    const seededTopic = new URLSearchParams(window.location.search).get("topic");
    if (seededTopic) setTopic(seededTopic);
  }, []);

  const userName = displayName(userData?.user) || DEFAULT_USER_ID;
  const canGenerate = topic.trim().length >= 3 && !generating;
  const selectedSummary = useMemo(() => [
    ...selectedFormats,
    ...selectedTones,
    ...selectedAngles,
    structure !== "None" ? structure : "",
  ].filter(Boolean).join(" | "), [selectedFormats, selectedTones, selectedAngles, structure]);

  function toggle(value: string, values: string[], setter: (value: string[]) => void, max = 5) {
    if (values.includes(value)) setter(values.filter((item) => item !== value));
    else if (values.length < max) setter([...values, value]);
  }

  async function inspectSource() {
    if (!sourceUrl.trim()) return;
    setLoadingSource(true);
    setError("");
    try {
      const result = await extractContentSource(sourceUrl.trim());
      setSource(result);
      if (!topic.trim()) setTopic(result.title || result.description);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Could not read that URL.");
    } finally {
      setLoadingSource(false);
    }
  }

  async function suggestTopics() {
    setSuggesting(true);
    setError("");
    try {
      const result = await brainstormIdeas({ user_id: DEFAULT_USER_ID, topic: topic.trim() || "LinkedIn post ideas" });
      setSuggestions(result.ideas.slice(0, 4));
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Could not suggest topics.");
    } finally {
      setSuggesting(false);
    }
  }

  async function generate() {
    if (!canGenerate) return;
    setGenerating(true);
    setError("");
    try {
      const response = await generatePostBuilder({
        user_id: DEFAULT_USER_ID,
        topic: topic.trim(),
        source_url: mode === "url" ? sourceUrl.trim() : undefined,
        post_length: length,
        writing_style: selectedVariations[0] || "Clear Builder",
        variations: selectedVariations,
        formats: selectedFormats,
        tones: selectedTones,
        angles: selectedAngles,
        structure: structure === "None" ? undefined : structure,
        post_count: postCount,
      });
      setResults(response.threads);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Post generation failed.");
    } finally {
      setGenerating(false);
    }
  }

  async function copyPost(thread: ThreadResponse) {
    await navigator.clipboard.writeText(thread.current_post);
    setCopiedId(thread.thread_id);
    window.setTimeout(() => setCopiedId(""), 1600);
  }

  return (
    <AppShell active="builder" title="Post Builder" subtitle="Shape an idea or source into focused LinkedIn drafts." userName={userName} threads={userData?.threads || []}>
      <div className="page-section builder-page">
        <div className="builder-mode-tabs" role="tablist">
          <button className={mode === "idea" ? "selected" : ""} type="button" onClick={() => setMode("idea")}><Lightbulb size={16} /> From an idea</button>
          <button className={mode === "url" ? "selected" : ""} type="button" onClick={() => setMode("url")}><Link2 size={16} /> From a URL</button>
        </div>

        {error ? <div className="error-banner">{error}</div> : null}
        <div className="builder-layout">
          <section className="builder-topic-panel">
            <div className="section-heading-row"><div><h2>Post topic</h2><p>Give the AI a concrete point of view or source.</p></div><button className="secondary-button compact" type="button" onClick={suggestTopics} disabled={suggesting}>{suggesting ? <Loader2 className="spin" size={15} /> : <Sparkles size={15} />} Suggest</button></div>
            {mode === "url" ? (
              <div className="source-url-row"><input value={sourceUrl} onChange={(event) => setSourceUrl(event.target.value)} placeholder="https://example.com/article" /><button className="secondary-button compact" type="button" onClick={inspectSource} disabled={loadingSource || !sourceUrl.trim()}>{loadingSource ? <Loader2 className="spin" size={15} /> : <ExternalLink size={15} />} Read source</button></div>
            ) : null}
            {source ? <div className="source-preview"><strong>{source.title || source.canonical_url}</strong><p>{source.description || `${source.word_count} words extracted`}</p></div> : null}
            <textarea value={topic} onChange={(event) => setTopic(event.target.value)} rows={7} placeholder="Example: What I learned after automating a workflow my team used every day..." />
            <small className="field-help">Be specific. One to three sentences works best.</small>
            {suggestions.length ? <div className="topic-suggestions">{suggestions.map((idea) => <button type="button" key={idea.title} onClick={() => { setTopic(`${idea.title}\n\n${idea.summary}`); setSuggestions([]); }}><strong>{idea.title}</strong><span>{idea.summary}</span></button>)}</div> : null}
            <ToggleGroup label="Post variations" options={variations} selected={selectedVariations} onToggle={(value) => toggle(value, selectedVariations, setSelectedVariations, 4)} />
            <div className="builder-basic-controls">
              <label className="field"><span>Length</span><select value={length} onChange={(event) => setLength(event.target.value)}><option value="short">Short</option><option value="medium">Medium</option><option value="long">Long</option></select></label>
              <label className="field"><span>Drafts</span><select value={postCount} onChange={(event) => setPostCount(Number(event.target.value))}><option value={1}>1 draft</option><option value={2}>2 drafts</option><option value={3}>3 drafts</option></select></label>
            </div>
          </section>

          <section className="builder-settings-panel">
            <div className="section-heading-row"><div><h2>Format and tone</h2><p>Combine useful constraints without turning the prompt into a checklist.</p></div></div>
            <ToggleGroup label="Format" options={formats} selected={selectedFormats} onToggle={(value) => toggle(value, selectedFormats, setSelectedFormats)} />
            <ToggleGroup label="Tone" options={tones} selected={selectedTones} onToggle={(value) => toggle(value, selectedTones, setSelectedTones)} />
            <ToggleGroup label="Angle" options={angles} selected={selectedAngles} onToggle={(value) => toggle(value, selectedAngles, setSelectedAngles)} />
            <ToggleGroup label="Structure" options={structures} selected={[structure]} single onToggle={setStructure} />
            <div className="builder-selection-summary"><span>Current recipe</span><strong>{selectedSummary || "AI decides"}</strong></div>
            <button className="primary-button builder-generate" type="button" onClick={generate} disabled={!canGenerate}>{generating ? <Loader2 className="spin" size={18} /> : <Sparkles size={18} />} {generating ? "Generating drafts..." : "Generate posts"}</button>
          </section>
        </div>

        <section className="builder-results">
          <div className="section-heading-row"><div><h2>Generated posts</h2><p>Edit and refine a draft in its saved AI thread.</p></div><Link className="text-link" href="/content">Open content pipeline <ArrowRight size={14} /></Link></div>
          {!results.length ? <div className="empty-state compact-empty">Your generated posts will appear here.</div> : (
            <div className="generated-post-grid">
              {results.map((thread, index) => (
                <article className="generated-post-card" key={thread.thread_id}>
                  <header><span>Draft {index + 1}</span><small>{thread.model || "AI generated"}</small></header>
                  <div className="generated-post-copy">{thread.current_post}</div>
                  <footer><button className="icon-button" type="button" title="Copy post" aria-label="Copy post" onClick={() => copyPost(thread)}>{copiedId === thread.thread_id ? <Check size={16} /> : <Clipboard size={16} />}</button><Link className="primary-button compact" href={`/generate?thread_id=${encodeURIComponent(thread.thread_id)}`}>Refine draft <ArrowRight size={15} /></Link></footer>
                </article>
              ))}
            </div>
          )}
        </section>
      </div>
    </AppShell>
  );
}
