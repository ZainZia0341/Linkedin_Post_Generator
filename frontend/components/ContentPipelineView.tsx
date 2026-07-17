"use client";

import { ArrowLeft, ArrowRight, FilePenLine, Loader2, Plus, Save, X } from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { AppShell } from "@/components/AppShell";
import {
  createContentItem,
  DEFAULT_USER_ID,
  fetchContentItems,
  fetchUserData,
  updateContentItem,
} from "@/lib/api";
import { compactDate, displayName, previewText } from "@/lib/format";
import type { ContentItemResponse, ContentItemStatus, UserDataResponse } from "@/lib/types";

const columns: Array<{ status: ContentItemStatus; label: string; description: string }> = [
  { status: "idea", label: "Ideas", description: "Topics worth shaping" },
  { status: "in_progress", label: "In Progress", description: "Drafting and refining" },
  { status: "ready", label: "Ready to Post", description: "Reviewed and approved" },
  { status: "published", label: "Published", description: "Live post archive" },
];

export function ContentPipelineView() {
  const [userData, setUserData] = useState<UserDataResponse | null>(null);
  const [items, setItems] = useState<ContentItemResponse[]>([]);
  const [selected, setSelected] = useState<ContentItemResponse | null>(null);
  const [newTitle, setNewTitle] = useState("");
  const [creating, setCreating] = useState(false);
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    fetchUserData(DEFAULT_USER_ID)
      .then((userResult) => {
        if (!cancelled) setUserData(userResult);
      })
      .catch(() => undefined);
    fetchContentItems(DEFAULT_USER_ID)
      .then((contentResult) => {
        if (cancelled) return;
        setItems(contentResult);
      })
      .catch((exc) => {
        if (!cancelled) setError(exc instanceof Error ? exc.message : "Could not load content pipeline.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const grouped = useMemo(() => Object.fromEntries(columns.map((column) => [
    column.status,
    items.filter((item) => item.status === column.status),
  ])) as Record<ContentItemStatus, ContentItemResponse[]>, [items]);
  const userName = displayName(userData?.user) || DEFAULT_USER_ID;

  async function handleCreate() {
    if (!newTitle.trim()) return;
    setCreating(true);
    setError("");
    try {
      const created = await createContentItem({
        user_id: DEFAULT_USER_ID,
        title: newTitle.trim(),
        status: "idea",
      });
      setItems((current) => [created, ...current]);
      setNewTitle("");
      setSelected(created);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Could not create idea.");
    } finally {
      setCreating(false);
    }
  }

  async function moveItem(item: ContentItemResponse, direction: -1 | 1) {
    const currentIndex = columns.findIndex((column) => column.status === item.status);
    const nextStatus = columns[currentIndex + direction]?.status;
    if (!nextStatus) return;
    setSaving(true);
    try {
      const updated = await updateContentItem(item.content_id, {
        user_id: DEFAULT_USER_ID,
        status: nextStatus,
      });
      setItems((current) => current.map((candidate) => candidate.content_id === updated.content_id ? updated : candidate));
      setSelected((current) => current?.content_id === updated.content_id ? updated : current);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Could not move content.");
    } finally {
      setSaving(false);
    }
  }

  async function saveSelected() {
    if (!selected) return;
    setSaving(true);
    setError("");
    try {
      const updated = await updateContentItem(selected.content_id, {
        user_id: DEFAULT_USER_ID,
        title: selected.title,
        body: selected.body,
        status: selected.status,
      });
      setItems((current) => current.map((candidate) => candidate.content_id === updated.content_id ? updated : candidate));
      setSelected(updated);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Could not save content.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <AppShell
      active="content"
      title="Content Pipeline"
      subtitle="Move ideas from first note to published post."
      userName={userName}
      threads={userData?.threads || []}
    >
      <div className="page-section content-pipeline-page">
        <div className="pipeline-toolbar">
          <div className="inline-control grow">
            <input
              value={newTitle}
              onChange={(event) => setNewTitle(event.target.value)}
              onKeyDown={(event) => { if (event.key === "Enter") void handleCreate(); }}
              placeholder="Capture a new post idea"
            />
            <button className="primary-button compact" type="button" onClick={handleCreate} disabled={creating || !newTitle.trim()}>
              {creating ? <Loader2 className="spin" size={16} /> : <Plus size={16} />} Add idea
            </button>
          </div>
          <Link className="secondary-button compact" href="/content/post-builder"><FilePenLine size={16} /> Open Post Builder</Link>
        </div>
        {error ? <div className="error-banner">{error}</div> : null}
        {loading ? <div className="loading-state"><Loader2 className="spin" size={20} /> Loading pipeline...</div> : null}

        <div className="pipeline-board">
          {columns.map((column, columnIndex) => (
            <section className={`pipeline-column status-${column.status}`} key={column.status}>
              <header>
                <span><strong>{column.label}</strong><small>{column.description}</small></span>
                <b>{grouped[column.status]?.length || 0}</b>
              </header>
              <div className="pipeline-stack">
                {(grouped[column.status] || []).map((item) => (
                  <article className="pipeline-card" key={item.content_id} onClick={() => setSelected(item)}>
                    <span className="content-source">{item.topic_source.replaceAll("_", " ")}</span>
                    <h3>{previewText(item.title, 100)}</h3>
                    <p>{previewText(item.body || "No draft text yet.", 180)}</p>
                    <footer>
                      <small>{compactDate(item.updated_at) || "Recent"}</small>
                      <span className="pipeline-card-actions">
                        <button type="button" aria-label="Move left" title="Move left" disabled={columnIndex === 0 || saving} onClick={(event) => { event.stopPropagation(); void moveItem(item, -1); }}><ArrowLeft size={14} /></button>
                        <button type="button" aria-label="Move right" title="Move right" disabled={columnIndex === columns.length - 1 || saving} onClick={(event) => { event.stopPropagation(); void moveItem(item, 1); }}><ArrowRight size={14} /></button>
                      </span>
                    </footer>
                  </article>
                ))}
                {!grouped[column.status]?.length ? <div className="pipeline-empty">Nothing here yet</div> : null}
              </div>
            </section>
          ))}
        </div>
      </div>

      {selected ? (
        <div className="drawer-backdrop" onMouseDown={() => !saving && setSelected(null)}>
          <aside className="content-editor-drawer" onMouseDown={(event) => event.stopPropagation()}>
            <header className="drawer-header">
              <div><h2>Edit content</h2><p>Update the draft or move it through the pipeline.</p></div>
              <button className="icon-button" type="button" aria-label="Close" onClick={() => setSelected(null)} disabled={saving}><X size={18} /></button>
            </header>
            <div className="drawer-body content-editor-body">
              <label className="field"><span>Title</span><input value={selected.title} onChange={(event) => setSelected({ ...selected, title: event.target.value })} /></label>
              <label className="field"><span>Status</span><select value={selected.status} onChange={(event) => setSelected({ ...selected, status: event.target.value as ContentItemStatus })}>{columns.map((column) => <option value={column.status} key={column.status}>{column.label}</option>)}</select></label>
              <label className="field grow"><span>Post draft</span><textarea className="content-editor-textarea" value={selected.body} onChange={(event) => setSelected({ ...selected, body: event.target.value })} rows={22} placeholder="Write or paste the post draft here." /></label>
              {selected.thread_id ? <Link className="text-link" href={`/generate?thread_id=${encodeURIComponent(selected.thread_id)}`}>Open AI refinement thread <ArrowRight size={14} /></Link> : null}
            </div>
            <footer className="drawer-footer"><button className="secondary-button" type="button" onClick={() => setSelected(null)} disabled={saving}>Cancel</button><button className="primary-button" type="button" onClick={saveSelected} disabled={saving}>{saving ? <Loader2 className="spin" size={16} /> : <Save size={16} />} Save changes</button></footer>
          </aside>
        </div>
      ) : null}
    </AppShell>
  );
}
