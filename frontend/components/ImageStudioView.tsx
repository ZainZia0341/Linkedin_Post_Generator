"use client";

import { ExternalLink, Image as ImageIcon, Loader2, Sparkles, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { AppShell } from "@/components/AppShell";
import {
  backendAssetUrl,
  DEFAULT_USER_ID,
  deleteImageAsset,
  fetchImageAssets,
  fetchUserData,
  generateImageAsset,
} from "@/lib/api";
import { IMAGE_STYLE_OPTIONS } from "@/lib/constants";
import { compactDate, displayName } from "@/lib/format";
import type { ImageAssetResponse, UserDataResponse } from "@/lib/types";

export function ImageStudioView() {
  const [userData, setUserData] = useState<UserDataResponse | null>(null);
  const [assets, setAssets] = useState<ImageAssetResponse[]>([]);
  const [postText, setPostText] = useState("");
  const [style, setStyle] = useState(IMAGE_STYLE_OPTIONS[0]);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [deletingId, setDeletingId] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    fetchUserData(DEFAULT_USER_ID)
      .then((userResult) => {
        if (!cancelled) setUserData(userResult);
      })
      .catch(() => undefined);
    fetchImageAssets(DEFAULT_USER_ID)
      .then((assetResult) => {
        if (cancelled) return;
        setAssets(assetResult);
      })
      .catch((exc) => { if (!cancelled) setError(exc instanceof Error ? exc.message : "Could not load image assets."); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, []);

  const userName = displayName(userData?.user) || DEFAULT_USER_ID;

  async function handleGenerate() {
    if (postText.trim().length < 3) return;
    setGenerating(true);
    setError("");
    try {
      const result = await generateImageAsset({
        user_id: DEFAULT_USER_ID,
        prompt: `Supporting visual for: ${postText.trim().slice(0, 240)}`,
        post_text: postText.trim(),
        aspect_ratio: "4:5",
        style,
      });
      setAssets((current) => [result, ...current]);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Image generation failed.");
    } finally {
      setGenerating(false);
    }
  }

  async function handleDelete(asset: ImageAssetResponse) {
    if (!window.confirm("Delete this generated image?")) return;
    setDeletingId(asset.asset_id);
    setError("");
    try {
      await deleteImageAsset(DEFAULT_USER_ID, asset.asset_id);
      setAssets((current) => current.filter((item) => item.asset_id !== asset.asset_id));
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Could not delete image.");
    } finally {
      setDeletingId("");
    }
  }

  return (
    <AppShell active="images" title="Image Studio" subtitle="Generate a visual that supports the post instead of repeating it." userName={userName} threads={userData?.threads || []}>
      <div className="page-section image-studio-page">
        {error ? <div className="error-banner">{error}</div> : null}
        <div className="image-studio-layout">
          <section className="image-generator-panel">
            <div className="section-heading-row"><div><h2>Create from post</h2><p>The post supplies the subject and context. You only choose its visual treatment.</p></div><ImageIcon size={22} /></div>
            <label className="field"><span>Post content</span><textarea rows={10} value={postText} onChange={(event) => setPostText(event.target.value)} placeholder="Paste the LinkedIn post that needs a supporting image..." /></label>
            <div className="image-controls single-control">
              <label className="field"><span>Style</span><select value={style} onChange={(event) => setStyle(event.target.value)}>{IMAGE_STYLE_OPTIONS.map((item) => <option value={item} key={item}>{item}</option>)}</select></label>
            </div>
            <button className="primary-button image-generate-button" type="button" onClick={handleGenerate} disabled={generating || postText.trim().length < 3}>{generating ? <Loader2 className="spin" size={18} /> : <Sparkles size={18} />} {generating ? "Generating image..." : "Generate image"}</button>
            <p className="generator-note">Uses the backend-configured Gemini image model. Generated files are kept in the local asset store for this development environment.</p>
          </section>

          <section className="image-library-panel">
            <div className="section-heading-row"><div><h2>Generated assets</h2><p>{assets.length} saved image{assets.length === 1 ? "" : "s"}</p></div></div>
            {loading ? <div className="loading-state"><Loader2 className="spin" size={18} /> Loading images...</div> : null}
            {!loading && !assets.length ? <div className="empty-state"><ImageIcon size={28} />Your generated images will appear here.</div> : null}
            <div className="image-asset-grid">
              {assets.map((asset) => (
                <article className="image-asset-card" key={asset.asset_id}>
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src={backendAssetUrl(asset.asset_url)} alt={asset.prompt} />
                  <div className="image-asset-copy"><strong>{asset.prompt}</strong><span>{asset.style} | {asset.aspect_ratio} | {compactDate(asset.created_at)}</span><small>{asset.model}</small></div>
                  <div className="image-asset-actions"><a className="secondary-button compact" href={backendAssetUrl(asset.asset_url)} target="_blank" rel="noreferrer"><ExternalLink size={15} /> Open</a><button className="icon-button danger" type="button" aria-label="Delete image" title="Delete image" disabled={deletingId === asset.asset_id} onClick={() => handleDelete(asset)}>{deletingId === asset.asset_id ? <Loader2 className="spin" size={16} /> : <Trash2 size={16} />}</button></div>
                </article>
              ))}
            </div>
          </section>
        </div>
      </div>
    </AppShell>
  );
}
