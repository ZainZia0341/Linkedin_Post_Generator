"use client";

import {
  Check,
  Clipboard,
  Download,
  Eye,
  GalleryHorizontalEnd,
  LayoutTemplate,
  Loader2,
  Palette,
  PenLine,
  Plus,
  Save,
  Sparkles,
  Trash2,
} from "lucide-react";
import { forwardRef, useEffect, useRef, useState } from "react";
import { AppShell } from "@/components/AppShell";
import {
  createCarousel,
  DEFAULT_USER_ID,
  fetchCarousels,
  fetchUserData,
  generateCarousel,
  saveCarousel,
} from "@/lib/api";
import { compactDate, displayName } from "@/lib/format";
import type { CarouselResponse, CarouselSlide, UserDataResponse } from "@/lib/types";

type CreationMode = "manual" | "ai";
type EditorTab = "content" | "theme" | "preview";

const templates = [
  { id: "Signal", label: "Signal", description: "Clean cobalt frame with a strong reading rhythm." },
  { id: "Field Notes", label: "Field Notes", description: "Editorial paper treatment for practical stories." },
  { id: "Blueprint", label: "Blueprint", description: "Technical grid for systems and how-to content." },
  { id: "Punch", label: "Punch", description: "High contrast blocks for concise, direct ideas." },
];

const tones = ["Clear and practical", "Professional", "Conversational", "Bold", "Educational"];

function templateClass(theme: string) {
  return `template-${theme.toLowerCase().replace(/\s+/g, "-")}`;
}

function emptySlide(position: number): CarouselSlide {
  return {
    slide_id: `slide-${Date.now()}-${position + 1}`,
    eyebrow: String(position + 1).padStart(2, "0"),
    title: `Slide ${position + 1}`,
    body: "Add one clear idea for this slide.",
  };
}

type SlideCanvasProps = {
  carousel: CarouselResponse;
  slide: CarouselSlide;
  index: number;
  total: number;
  exportMode?: boolean;
};

const SlideCanvas = forwardRef<HTMLDivElement, SlideCanvasProps>(function SlideCanvas(
  { carousel, slide, index, total, exportMode = false },
  ref,
) {
  const position = index === 0 ? "cover" : index === total - 1 ? "closing" : "content";
  return (
    <div
      className={`carousel-slide-canvas ${templateClass(carousel.theme)} slide-${position} ${exportMode ? "export-mode" : ""}`}
      ref={ref}
    >
      <div className="carousel-template-band" />
      <div className="carousel-template-mark" aria-hidden="true"><i /><i /><i /><i /><i /><i /></div>
      <header>
        <span>{slide.eyebrow || String(index + 1).padStart(2, "0")}</span>
        <b>{String(index + 1).padStart(2, "0")}</b>
      </header>
      <main>
        <h3>{slide.title || "Untitled slide"}</h3>
        {slide.body ? <p>{slide.body}</p> : null}
      </main>
      <footer>
        <span>AI Spark</span>
        <b>{index + 1}/{total}</b>
      </footer>
    </div>
  );
});

export function CarouselGeneratorView() {
  const [userData, setUserData] = useState<UserDataResponse | null>(null);
  const [carousels, setCarousels] = useState<CarouselResponse[]>([]);
  const [active, setActive] = useState<CarouselResponse | null>(null);
  const [activeSlide, setActiveSlide] = useState(0);
  const [creationMode, setCreationMode] = useState<CreationMode>("ai");
  const [editorTab, setEditorTab] = useState<EditorTab>("content");
  const [topic, setTopic] = useState("");
  const [audience, setAudience] = useState("LinkedIn professionals");
  const [tone, setTone] = useState(tones[0]);
  const [theme, setTheme] = useState(templates[0].id);
  const [slideCount, setSlideCount] = useState(7);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [saving, setSaving] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState("");
  const exportRefs = useRef<Array<HTMLDivElement | null>>([]);

  useEffect(() => {
    let cancelled = false;
    fetchUserData(DEFAULT_USER_ID)
      .then((userResult) => { if (!cancelled) setUserData(userResult); })
      .catch(() => undefined);
    fetchCarousels(DEFAULT_USER_ID)
      .then((carouselResult) => {
        if (cancelled) return;
        setCarousels(carouselResult);
        setActive(carouselResult[0] || null);
      })
      .catch((exc) => { if (!cancelled) setError(exc instanceof Error ? exc.message : "Could not load carousels."); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, []);

  const userName = displayName(userData?.user) || DEFAULT_USER_ID;
  const currentSlide = active?.slides[activeSlide];

  function openCarousel(carousel: CarouselResponse) {
    setActive(carousel);
    setActiveSlide(0);
    setTheme(carousel.theme);
    setEditorTab("content");
  }

  async function handleGenerate() {
    if (topic.trim().length < 3) return;
    setGenerating(true);
    setError("");
    try {
      const result = creationMode === "ai"
        ? await generateCarousel({
            user_id: DEFAULT_USER_ID,
            topic: topic.trim(),
            audience: audience.trim(),
            tone: tone.trim(),
            theme,
            slide_count: slideCount,
          })
        : await createCarousel({
            user_id: DEFAULT_USER_ID,
            title: topic.trim(),
            theme,
            slide_count: slideCount,
          });
      setCarousels((current) => [result, ...current.filter((item) => item.carousel_id !== result.carousel_id)]);
      openCarousel(result);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Carousel creation failed.");
    } finally {
      setGenerating(false);
    }
  }

  function updateSlide(patch: Partial<CarouselSlide>) {
    if (!active) return;
    setActive({
      ...active,
      slides: active.slides.map((slide, index) => index === activeSlide ? { ...slide, ...patch } : slide),
    });
  }

  function applyTheme(nextTheme: string) {
    setTheme(nextTheme);
    if (active) setActive({ ...active, theme: nextTheme });
  }

  function addSlide() {
    if (!active || active.slides.length >= 12) return;
    const slides = [...active.slides, emptySlide(active.slides.length)];
    setActive({ ...active, slides });
    setActiveSlide(slides.length - 1);
    setEditorTab("content");
  }

  function removeSlide() {
    if (!active || active.slides.length <= 1) return;
    const slides = active.slides.filter((_, index) => index !== activeSlide);
    setActive({ ...active, slides });
    setActiveSlide(Math.min(Math.max(0, activeSlide - 1), slides.length - 1));
  }

  async function handleSave() {
    if (!active) return;
    setSaving(true);
    setError("");
    try {
      const result = await saveCarousel(active);
      setActive(result);
      setCarousels((current) => current.map((item) => item.carousel_id === result.carousel_id ? result : item));
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Could not save carousel.");
    } finally {
      setSaving(false);
    }
  }

  async function copyOutline() {
    if (!active) return;
    const text = active.slides.map((slide, index) => `${index + 1}. ${slide.title}\n${slide.body}`).join("\n\n");
    await navigator.clipboard.writeText(text);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1600);
  }

  async function handleDownloadPdf() {
    if (!active) return;
    setDownloading(true);
    setError("");
    try {
      await document.fonts.ready;
      const [{ toPng }, { jsPDF }] = await Promise.all([import("html-to-image"), import("jspdf")]);
      const pdf = new jsPDF({ orientation: "portrait", unit: "px", format: [1080, 1350], hotfixes: ["px_scaling"] });
      for (let index = 0; index < active.slides.length; index += 1) {
        const node = exportRefs.current[index];
        if (!node) throw new Error(`Slide ${index + 1} could not be rendered.`);
        const image = await toPng(node, { cacheBust: true, pixelRatio: 2, backgroundColor: "#ffffff" });
        if (index > 0) pdf.addPage([1080, 1350], "portrait");
        pdf.addImage(image, "PNG", 0, 0, 1080, 1350, undefined, "FAST");
      }
      const filename = (active.title || "linkedin-carousel").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
      pdf.save(`${filename || "linkedin-carousel"}.pdf`);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Could not export the carousel PDF.");
    } finally {
      setDownloading(false);
    }
  }

  return (
    <AppShell active="carousels" title="Carousel Studio" subtitle="Use one reusable design across every slide, then write manually or let AI fill the copy." userName={userName} threads={userData?.threads || []}>
      <div className="page-section carousel-page">
        {error ? <div className="error-banner">{error}</div> : null}
        <div className="carousel-layout">
          <aside className="carousel-library">
            <h2>Carousels</h2>
            <p>Saved editable designs</p>
            {loading ? <div className="loading-state"><Loader2 className="spin" size={18} /> Loading...</div> : null}
            <div className="carousel-library-list">
              {carousels.map((carousel) => (
                <button className={active?.carousel_id === carousel.carousel_id ? "selected" : ""} type="button" key={carousel.carousel_id} onClick={() => openCarousel(carousel)}>
                  <GalleryHorizontalEnd size={17} />
                  <span><strong>{carousel.title}</strong><small>{carousel.slides.length} slides | {compactDate(carousel.updated_at)}</small></span>
                </button>
              ))}
              {!loading && !carousels.length ? <div className="pipeline-empty">Create your first carousel.</div> : null}
            </div>
          </aside>

          <section className="carousel-workspace">
            <div className="carousel-creation-panel">
              <div className="carousel-mode-switch" aria-label="Carousel creation mode">
                <button className={creationMode === "manual" ? "selected" : ""} type="button" onClick={() => setCreationMode("manual")}><PenLine size={16} /> Write manually</button>
                <button className={creationMode === "ai" ? "selected" : ""} type="button" onClick={() => setCreationMode("ai")}><Sparkles size={16} /> Fill with AI</button>
              </div>
              <div className="carousel-creation-fields">
                <label className="field grow"><span>{creationMode === "ai" ? "Carousel topic" : "Carousel title"}</span><input value={topic} onChange={(event) => setTopic(event.target.value)} placeholder={creationMode === "ai" ? "Five lessons from shipping an AI product" : "Untitled carousel"} /></label>
                {creationMode === "ai" ? <label className="field"><span>Audience</span><input value={audience} onChange={(event) => setAudience(event.target.value)} /></label> : null}
                {creationMode === "ai" ? <label className="field"><span>Tone</span><select value={tone} onChange={(event) => setTone(event.target.value)}>{tones.map((item) => <option value={item} key={item}>{item}</option>)}</select></label> : null}
                <label className="field compact-field"><span>Slides</span><select value={slideCount} onChange={(event) => setSlideCount(Number(event.target.value))}>{[3, 4, 5, 6, 7, 8, 9, 10].map((count) => <option value={count} key={count}>{count}</option>)}</select></label>
                <label className="field compact-field"><span>Template</span><select value={theme} onChange={(event) => applyTheme(event.target.value)}>{templates.map((item) => <option value={item.id} key={item.id}>{item.label}</option>)}</select></label>
                <button className="primary-button carousel-create-button" type="button" onClick={handleGenerate} disabled={generating || topic.trim().length < 3}>
                  {generating ? <Loader2 className="spin" size={17} /> : creationMode === "ai" ? <Sparkles size={17} /> : <Plus size={17} />}
                  {generating ? "Creating..." : creationMode === "ai" ? "Generate copy" : "Create blank"}
                </button>
              </div>
            </div>

            {active && currentSlide ? (
              <>
                <div className="carousel-editor-toolbar">
                  <div className="carousel-editor-tabs">
                    <button className={editorTab === "content" ? "selected" : ""} type="button" onClick={() => setEditorTab("content")}><PenLine size={16} /> Content</button>
                    <button className={editorTab === "theme" ? "selected" : ""} type="button" onClick={() => setEditorTab("theme")}><Palette size={16} /> Theme</button>
                    <button className={editorTab === "preview" ? "selected" : ""} type="button" onClick={() => setEditorTab("preview")}><Eye size={16} /> Preview</button>
                  </div>
                  <div className="carousel-toolbar-actions">
                    <button className="secondary-button compact" type="button" onClick={handleDownloadPdf} disabled={downloading}>{downloading ? <Loader2 className="spin" size={16} /> : <Download size={16} />} PDF</button>
                    <button className="primary-button compact" type="button" onClick={handleSave} disabled={saving}>{saving ? <Loader2 className="spin" size={16} /> : <Save size={16} />} Save</button>
                  </div>
                </div>

                <div className="carousel-template-editor">
                  <div className="carousel-stage-wrap">
                    <SlideCanvas carousel={active} slide={currentSlide} index={activeSlide} total={active.slides.length} />
                    <div className="carousel-thumbnails">
                      {active.slides.map((slide, index) => (
                        <button className={index === activeSlide ? "selected" : ""} type="button" key={slide.slide_id} onClick={() => setActiveSlide(index)}>
                          <div className={`carousel-thumb-preview ${templateClass(active.theme)}`}><b>{index + 1}</b><span>{slide.title}</span></div>
                        </button>
                      ))}
                      <button className="add-slide" type="button" onClick={addSlide} disabled={active.slides.length >= 12}><Plus size={18} /><span>Add slide</span></button>
                    </div>
                  </div>

                  <aside className="carousel-inspector">
                    {editorTab === "content" ? (
                      <>
                        <div className="section-heading-row"><div><h2>Edit slide {activeSlide + 1}</h2><p>The selected template is applied automatically.</p></div><button className="icon-button danger" type="button" title="Delete slide" aria-label="Delete slide" onClick={removeSlide} disabled={active.slides.length <= 1}><Trash2 size={16} /></button></div>
                        <label className="field"><span>Carousel title</span><input value={active.title} onChange={(event) => setActive({ ...active, title: event.target.value })} /></label>
                        <label className="field"><span>Label</span><input value={currentSlide.eyebrow} onChange={(event) => updateSlide({ eyebrow: event.target.value })} /></label>
                        <label className="field"><span>Headline</span><textarea rows={3} value={currentSlide.title} onChange={(event) => updateSlide({ title: event.target.value })} /></label>
                        <label className="field"><span>Supporting text</span><textarea rows={8} value={currentSlide.body} onChange={(event) => updateSlide({ body: event.target.value })} /></label>
                      </>
                    ) : null}

                    {editorTab === "theme" ? (
                      <>
                        <div className="section-heading-row"><div><h2>Choose template</h2><p>Changing it updates every slide at once.</p></div><LayoutTemplate size={20} /></div>
                        <div className="carousel-template-grid">
                          {templates.map((item) => (
                            <button className={active.theme === item.id ? "selected" : ""} type="button" key={item.id} onClick={() => applyTheme(item.id)}>
                              <div className={`template-swatch ${templateClass(item.id)}`}><span>Aa</span><i /></div>
                              <strong>{item.label}</strong>
                              <small>{item.description}</small>
                            </button>
                          ))}
                        </div>
                      </>
                    ) : null}

                    {editorTab === "preview" ? (
                      <div className="carousel-preview-summary">
                        <Eye size={24} />
                        <h2>Ready to review</h2>
                        <p>{active.slides.length} slides use the <strong>{active.theme}</strong> template. Select any thumbnail to inspect it before exporting.</p>
                        <button className="secondary-button" type="button" onClick={copyOutline}>{copied ? <Check size={16} /> : <Clipboard size={16} />} {copied ? "Copied" : "Copy text outline"}</button>
                        <button className="primary-button" type="button" onClick={handleDownloadPdf} disabled={downloading}>{downloading ? <Loader2 className="spin" size={16} /> : <Download size={16} />} Download PDF</button>
                      </div>
                    ) : null}
                  </aside>
                </div>

                <div className="carousel-export-stack" aria-hidden="true">
                  {active.slides.map((slide, index) => (
                    <SlideCanvas
                      carousel={active}
                      slide={slide}
                      index={index}
                      total={active.slides.length}
                      exportMode
                      key={slide.slide_id}
                      ref={(node) => { exportRefs.current[index] = node; }}
                    />
                  ))}
                </div>
              </>
            ) : <div className="empty-state">Create a blank carousel or let AI fill the first draft.</div>}
          </section>
        </div>
      </div>
    </AppShell>
  );
}
