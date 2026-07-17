from __future__ import annotations

from html.parser import HTMLParser
import ipaddress
import mimetypes
from pathlib import Path
import re
import socket
from typing import Any
from urllib.parse import urljoin, urlparse
from uuid import uuid4

import httpx

from app.api.schemas import (
    CarouselCreateRequest,
    CarouselGenerateRequest,
    CarouselResponse,
    CarouselSlide,
    CarouselUpdateRequest,
    ContentItemCreateRequest,
    ContentItemResponse,
    ContentItemUpdateRequest,
    ContentSourceResponse,
    GeneratePostRequest,
    ImageAssetResponse,
    ImageGenerationRequest,
    PostBuilderGenerateRequest,
    PostBuilderGenerateResponse,
)
from app.api.services import generate_post, llm_config, now_iso, require_user
from app.config import GENERATED_ASSET_DIR, GEMINI_IMAGE_MODEL, get_env_api_key
from app.db.dynamodb import DynamoRepository
from app.llms.llm import invoke_structured
from app.llms.llm_structure_schema import GeneratedCarousel, GeneratedCarouselSlide

CONTENT_STATUSES = {"idea", "in_progress", "ready", "published"}
CAROUSEL_CREATOR_ID = "__content_carousels__"
IMAGE_ASSET_CREATOR_ID = "__generated_image_assets__"
MAX_SOURCE_BYTES = 2 * 1024 * 1024
MAX_SOURCE_TEXT = 24_000
ALLOWED_ASPECT_RATIOS = {"1:1", "4:5", "3:2", "16:9", "9:16"}


class _ArticleParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.description = ""
        self.canonical_url = ""
        self._in_title = False
        self._skip_depth = 0
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        normalized = tag.lower()
        attributes = {str(key).lower(): str(value or "") for key, value in attrs}
        if normalized in {"script", "style", "noscript", "svg", "nav", "footer"}:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        if normalized == "title":
            self._in_title = True
        if normalized == "meta":
            name = attributes.get("name", "").lower()
            prop = attributes.get("property", "").lower()
            if name == "description" or prop == "og:description":
                self.description = self.description or attributes.get("content", "").strip()
            if prop == "og:title" and not self.title:
                self.title = attributes.get("content", "").strip()
        if normalized == "link" and "canonical" in attributes.get("rel", "").lower():
            self.canonical_url = attributes.get("href", "").strip()
        if normalized in {"p", "h1", "h2", "h3", "li", "blockquote"}:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        normalized = tag.lower()
        if normalized in {"script", "style", "noscript", "svg", "nav", "footer"} and self._skip_depth:
            self._skip_depth -= 1
            return
        if normalized == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        cleaned = re.sub(r"\s+", " ", data).strip()
        if not cleaned:
            return
        if self._in_title and not self.title:
            self.title = cleaned
        self._parts.append(cleaned)

    def readable_text(self) -> str:
        raw = " ".join(self._parts)
        lines = [re.sub(r"\s+", " ", line).strip() for line in raw.split("\n")]
        return "\n\n".join(line for line in lines if len(line) > 20)


def _activity_key(user_id: str, creator_id: str) -> str:
    return f"{user_id}#{creator_id}"


def _validate_public_url(value: str) -> str:
    url = value.strip()
    parsed = urlparse(url)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Use a complete public HTTP or HTTPS URL.")
    if parsed.username or parsed.password:
        raise ValueError("URLs containing credentials are not supported.")
    try:
        addresses = socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80))
    except socket.gaierror as exc:
        raise ValueError("The article host could not be resolved.") from exc
    for address in addresses:
        ip_value = ipaddress.ip_address(address[4][0])
        if (
            ip_value.is_private
            or ip_value.is_loopback
            or ip_value.is_link_local
            or ip_value.is_multicast
            or ip_value.is_reserved
            or ip_value.is_unspecified
        ):
            raise ValueError("Private or local network URLs are not allowed.")
    return url


def extract_content_source(url: str) -> ContentSourceResponse:
    current_url = _validate_public_url(url)
    response: httpx.Response | None = None
    with httpx.Client(
        timeout=httpx.Timeout(20.0, connect=8.0),
        headers={"User-Agent": "AI-Spark-Content-Extractor/1.0"},
        follow_redirects=False,
    ) as client:
        for _ in range(4):
            response = client.get(current_url)
            if response.status_code in {301, 302, 303, 307, 308}:
                location = response.headers.get("location", "")
                if not location:
                    raise ValueError("The article returned an invalid redirect.")
                current_url = _validate_public_url(urljoin(current_url, location))
                continue
            break
    if response is None:
        raise ValueError("The article could not be loaded.")
    response.raise_for_status()
    content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if content_type not in {"text/html", "application/xhtml+xml", "text/plain"}:
        raise ValueError(f"Unsupported article content type: {content_type or 'unknown'}.")
    raw = response.content
    if len(raw) > MAX_SOURCE_BYTES:
        raise ValueError("The article is larger than the supported 2 MB extraction limit.")
    text_value = response.text
    if content_type == "text/plain":
        title = urlparse(current_url).path.rsplit("/", 1)[-1] or urlparse(current_url).hostname or "Article"
        description = ""
        canonical_url = current_url
        readable = re.sub(r"\n{3,}", "\n\n", text_value).strip()
    else:
        parser = _ArticleParser()
        parser.feed(text_value)
        title = parser.title or urlparse(current_url).hostname or "Article"
        description = parser.description
        canonical_url = urljoin(current_url, parser.canonical_url) if parser.canonical_url else current_url
        readable = parser.readable_text()
    readable = readable[:MAX_SOURCE_TEXT].strip()
    if len(readable.split()) < 30:
        raise ValueError("No readable article body was found at this URL.")
    return ContentSourceResponse(
        url=url,
        canonical_url=canonical_url,
        title=title[:300],
        description=description[:1000],
        text=readable,
        word_count=len(readable.split()),
        content_type=content_type,
    )


def generate_post_builder_variations(
    repo: DynamoRepository,
    request: PostBuilderGenerateRequest,
) -> PostBuilderGenerateResponse:
    require_user(repo, request.user_id)
    source: ContentSourceResponse | None = None
    topic = request.topic.strip()
    if request.source_url.strip():
        source = extract_content_source(request.source_url)
        topic = (
            f"Create an original LinkedIn post based on this article. Attribute ideas when needed and do not copy wording.\n\n"
            f"User direction: {topic}\nArticle title: {source.title}\nSource: {source.canonical_url}\n\n"
            f"Article text:\n{source.text[:12000]}"
        )

    selected_variations = [item.strip() for item in request.variations if item.strip()] or ["Actionable"]
    threads = []
    for index in range(request.post_count):
        variation = selected_variations[index % len(selected_variations)]
        primary_tone = next((item.strip() for item in request.tones if item.strip()), "Professional")
        thread = generate_post(
            repo,
            GeneratePostRequest(
                user_id=request.user_id,
                idea=topic,
                post_length=request.post_length,
                tone=primary_tone,
                writing_style=request.writing_style,
                topic_source="url" if source else "post_builder",
                post_variation=variation,
                format_tags=request.formats,
                tone_tags=request.tones,
                angle_tags=request.angles,
                structure=request.structure,
            ),
        )
        threads.append(thread)
    return PostBuilderGenerateResponse(
        user_id=request.user_id,
        source_url=source.canonical_url if source else "",
        source_title=source.title if source else "",
        threads=threads,
    )


def _content_item_from_thread(thread: dict[str, Any]) -> ContentItemResponse:
    status = str(thread.get("content_status") or "in_progress")
    if status not in CONTENT_STATUSES:
        status = "in_progress"
    return ContentItemResponse(
        user_id=str(thread.get("user_id", "")),
        content_id=str(thread.get("thread_id", "")),
        thread_id=str(thread.get("thread_id", "")),
        title=str(thread.get("topic", "Untitled content"))[:240],
        body=str(thread.get("current_post", "")),
        status=status,
        topic_source=str(thread.get("topic_source", "manual")),
        source=dict(thread.get("source") or {}),
        assets=[str(item) for item in thread.get("assets", []) if str(item).strip()],
        scheduled_at=str(thread.get("scheduled_at", "")),
        created_at=str(thread.get("created_at", "")),
        updated_at=str(thread.get("updated_at", "")),
    )


def list_content_items(repo: DynamoRepository, user_id: str, limit: int = 500) -> list[ContentItemResponse]:
    require_user(repo, user_id)
    items = [
        _content_item_from_thread(thread)
        for thread in repo.list_threads(user_id, limit)
        if str(thread.get("topic_source", "")) != "comment_generation"
    ]
    items.sort(key=lambda item: item.updated_at, reverse=True)
    return items


def create_content_item(repo: DynamoRepository, request: ContentItemCreateRequest) -> ContentItemResponse:
    require_user(repo, request.user_id)
    status = request.status.strip().lower()
    if status not in CONTENT_STATUSES:
        raise ValueError(f"Unsupported content status: {request.status}")
    timestamp = now_iso()
    content_id = str(uuid4())
    thread = {
        "user_id": request.user_id,
        "thread_id": content_id,
        "topic": request.title.strip(),
        "topic_source": "content_board",
        "generation_style": "",
        "original_post": request.body,
        "current_post": request.body,
        "conversation": [],
        "provider": "",
        "model": "",
        "source": {"type": "content_item"},
        "created_at": timestamp,
        "updated_at": timestamp,
        "generated_at": "",
        "modified_at": "",
        "modification_count": 0,
        "content_status": status,
        "assets": [],
        "scheduled_at": "",
    }
    repo.put_thread(thread)
    return _content_item_from_thread(thread)


def update_content_item(
    repo: DynamoRepository,
    content_id: str,
    request: ContentItemUpdateRequest,
) -> ContentItemResponse:
    require_user(repo, request.user_id)
    thread = repo.get_thread(request.user_id, content_id)
    if not thread or str(thread.get("topic_source", "")) == "comment_generation":
        raise KeyError(f"Content item not found: {content_id}")
    if request.status is not None:
        status = request.status.strip().lower()
        if status not in CONTENT_STATUSES:
            raise ValueError(f"Unsupported content status: {request.status}")
        thread["content_status"] = status
    if request.title is not None:
        thread["topic"] = request.title.strip() or "Untitled content"
    if request.body is not None:
        thread["current_post"] = request.body
        if not thread.get("original_post"):
            thread["original_post"] = request.body
    if request.scheduled_at is not None:
        thread["scheduled_at"] = request.scheduled_at
    thread["updated_at"] = now_iso()
    repo.put_thread(thread)
    return _content_item_from_thread(thread)


def _carousel_activity(record: dict[str, Any]) -> dict[str, Any]:
    return {
        **record,
        "user_creator_id": _activity_key(str(record["user_id"]), CAROUSEL_CREATOR_ID),
        "creator_id": CAROUSEL_CREATOR_ID,
        "post_id": str(record["carousel_id"]),
    }


def _carousel_response(record: dict[str, Any]) -> CarouselResponse:
    return CarouselResponse(
        user_id=str(record.get("user_id", "")),
        carousel_id=str(record.get("carousel_id") or record.get("post_id", "")),
        title=str(record.get("title", "Untitled carousel")),
        topic=str(record.get("topic", "")),
        audience=str(record.get("audience", "")),
        tone=str(record.get("tone", "")),
        theme=str(record.get("theme", "Signal")),
        slides=[CarouselSlide.model_validate(item) for item in record.get("slides", [])],
        status=str(record.get("status", "draft")),
        created_at=str(record.get("created_at", "")),
        updated_at=str(record.get("updated_at", "")),
    )


def _fallback_carousel(request: CarouselGenerateRequest) -> GeneratedCarousel:
    count = request.slide_count
    slide_templates = [
        ("The signal", f"Why {request.topic} matters now"),
        ("The friction", "The common approach creates more work than expected."),
        ("The shift", "Start with the decision or workflow, then choose the tool."),
        ("Step 1", "Define one clear outcome and the person responsible for it."),
        ("Step 2", "Build the smallest repeatable process that can produce that outcome."),
        ("Step 3", "Measure the result, learn, and improve one constraint at a time."),
        ("Takeaway", f"Make {request.topic} practical, measurable, and easy to repeat."),
    ]
    slides = [
        GeneratedCarouselSlide(eyebrow=f"{index + 1:02d}", title=title, body=body)
        for index, (title, body) in enumerate(slide_templates[:count])
    ]
    while len(slides) < count:
        index = len(slides) + 1
        slides.insert(-1 if slides else 0, GeneratedCarouselSlide(
            eyebrow=f"{index:02d}",
            title=f"Make it useful: point {index}",
            body="Add one concrete example that helps the reader apply the idea.",
        ))
    return GeneratedCarousel(title=request.topic[:120], slides=slides[:count])


def create_carousel(repo: DynamoRepository, request: CarouselCreateRequest) -> CarouselResponse:
    require_user(repo, request.user_id)
    timestamp = now_iso()
    carousel_id = str(uuid4())
    record = _carousel_activity(
        {
            "user_id": request.user_id,
            "carousel_id": carousel_id,
            "title": request.title.strip(),
            "topic": request.title.strip(),
            "audience": "",
            "tone": "",
            "theme": request.theme.strip() or "Signal",
            "slides": [
                {
                    "slide_id": str(uuid4()),
                    "eyebrow": f"{index + 1:02d}",
                    "title": request.title.strip() if index == 0 else f"Slide {index + 1}",
                    "body": "" if index == 0 else "Add one clear idea for this slide.",
                }
                for index in range(request.slide_count)
            ],
            "status": "draft",
            "created_at": timestamp,
            "updated_at": timestamp,
            "raw_text": request.title.strip(),
            "fetched_at": timestamp,
            "source": "manual_carousel",
        }
    )
    repo.put_activity(record)
    return _carousel_response(record)


def generate_carousel(repo: DynamoRepository, request: CarouselGenerateRequest) -> CarouselResponse:
    require_user(repo, request.user_id)
    config = llm_config()
    generated = invoke_structured(
        config=config,
        schema=GeneratedCarousel,
        system_prompt=(
            "You create concise, high-signal LinkedIn carousel outlines. Return structured slide data only. "
            "Each slide needs a short title and no more than 45 words of body text. Do not invent facts."
        ),
        user_prompt=(
            f"Topic: {request.topic}\nAudience: {request.audience}\nTone: {request.tone}\n"
            f"Create exactly {request.slide_count} slides. The first slide is a clear cover, middle slides teach one idea each, "
            "and the last slide gives a useful takeaway without a generic sales CTA."
        ),
        fallback_factory=lambda: _fallback_carousel(request),
    )
    normalized_slides = list(generated.slides[: request.slide_count])
    fallback_slides = _fallback_carousel(request).slides
    while len(normalized_slides) < request.slide_count:
        normalized_slides.append(fallback_slides[len(normalized_slides)])
    timestamp = now_iso()
    carousel_id = str(uuid4())
    record = _carousel_activity(
        {
            "user_id": request.user_id,
            "carousel_id": carousel_id,
            "title": generated.title.strip() or request.topic[:120],
            "topic": request.topic,
            "audience": request.audience,
            "tone": request.tone,
            "theme": request.theme,
            "slides": [
                {
                    "slide_id": str(uuid4()),
                    "eyebrow": slide.eyebrow[:40],
                    "title": slide.title[:140],
                    "body": slide.body[:800],
                }
                for slide in normalized_slides
            ],
            "status": "draft",
            "created_at": timestamp,
            "updated_at": timestamp,
            "raw_text": request.topic,
            "fetched_at": timestamp,
            "source": "ai_carousel",
        }
    )
    repo.put_activity(record)
    return _carousel_response(record)


def list_carousels(repo: DynamoRepository, user_id: str, limit: int = 100) -> list[CarouselResponse]:
    require_user(repo, user_id)
    items = [
        _carousel_response(item)
        for item in repo.list_creator_activities(user_id, CAROUSEL_CREATOR_ID, limit)
    ]
    items.sort(key=lambda item: item.updated_at, reverse=True)
    return items


def update_carousel(
    repo: DynamoRepository,
    carousel_id: str,
    request: CarouselUpdateRequest,
) -> CarouselResponse:
    require_user(repo, request.user_id)
    record = repo.get_activity(request.user_id, CAROUSEL_CREATOR_ID, carousel_id)
    if not record:
        raise KeyError(f"Carousel not found: {carousel_id}")
    if request.title is not None:
        record["title"] = request.title.strip() or "Untitled carousel"
    if request.theme is not None:
        record["theme"] = request.theme.strip() or "Signal"
    if request.slides is not None:
        record["slides"] = [slide.model_dump() for slide in request.slides]
    record["updated_at"] = now_iso()
    repo.put_activity(record)
    return _carousel_response(record)


def _asset_response(record: dict[str, Any]) -> ImageAssetResponse:
    return ImageAssetResponse(
        user_id=str(record.get("user_id", "")),
        asset_id=str(record.get("asset_id") or record.get("post_id", "")),
        prompt=str(record.get("prompt", "")),
        revised_prompt=str(record.get("revised_prompt", "")),
        model=str(record.get("model", "")),
        mime_type=str(record.get("mime_type", "image/png")),
        aspect_ratio=str(record.get("aspect_ratio", "1:1")),
        style=str(record.get("style", "Editorial")),
        asset_url=f"/assets/{record.get('asset_id') or record.get('post_id')}/content",
        created_at=str(record.get("created_at", "")),
    )


def generate_image_asset(repo: DynamoRepository, request: ImageGenerationRequest) -> ImageAssetResponse:
    require_user(repo, request.user_id)
    api_key = get_env_api_key("gemini")
    if not api_key:
        raise RuntimeError("GOOGLE_API_KEY is required for image generation.")
    aspect_ratio = request.aspect_ratio if request.aspect_ratio in ALLOWED_ASPECT_RATIOS else "1:1"
    model = (request.model or GEMINI_IMAGE_MODEL).strip()
    if not re.fullmatch(r"gemini-[a-z0-9.-]+", model):
        raise ValueError("Unsupported Gemini image model name.")
    prompt = (
        "Create a polished LinkedIn post visual. Keep the composition clear at feed size. "
        "Do not render long paragraphs, logos, watermarks, or UI screenshots. "
        f"Visual style: {request.style}. User prompt: {request.prompt.strip()}"
    )
    if request.post_text.strip():
        prompt += f"\nPost context: {request.post_text.strip()[:3000]}"
    url = f"https://generativelanguage.googleapis.com/v1/models/{model}:generateContent"
    response = httpx.post(
        url,
        headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
        json={
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "responseModalities": ["IMAGE"],
                "responseFormat": {"image": {"aspectRatio": aspect_ratio}},
            },
        },
        timeout=120,
    )
    if response.status_code >= 400:
        detail = response.text[:1000]
        raise RuntimeError(f"Gemini image generation failed ({response.status_code}): {detail}")
    payload = response.json()
    parts = (
        payload.get("candidates", [{}])[0]
        .get("content", {})
        .get("parts", [])
    )
    image_part = next((part.get("inlineData") for part in parts if part.get("inlineData")), None)
    if not image_part or not image_part.get("data"):
        raise RuntimeError("Gemini returned no generated image data.")
    import base64

    image_bytes = base64.b64decode(image_part["data"])
    mime_type = str(image_part.get("mimeType") or "image/png")
    extension = mimetypes.guess_extension(mime_type) or ".png"
    if extension == ".jpe":
        extension = ".jpg"
    GENERATED_ASSET_DIR.mkdir(parents=True, exist_ok=True)
    asset_id = str(uuid4())
    path = (GENERATED_ASSET_DIR / f"{asset_id}{extension}").resolve()
    path.write_bytes(image_bytes)
    revised_prompt = " ".join(str(part.get("text", "")).strip() for part in parts if part.get("text")).strip()
    timestamp = now_iso()
    record = {
        "user_creator_id": _activity_key(request.user_id, IMAGE_ASSET_CREATOR_ID),
        "user_id": request.user_id,
        "creator_id": IMAGE_ASSET_CREATOR_ID,
        "post_id": asset_id,
        "asset_id": asset_id,
        "prompt": request.prompt.strip(),
        "revised_prompt": revised_prompt,
        "model": model,
        "mime_type": mime_type,
        "aspect_ratio": aspect_ratio,
        "style": request.style,
        "local_path": str(path),
        "created_at": timestamp,
        "raw_text": request.prompt.strip(),
        "fetched_at": timestamp,
        "source": "gemini_image",
    }
    repo.put_activity(record)
    return _asset_response(record)


def list_image_assets(repo: DynamoRepository, user_id: str, limit: int = 100) -> list[ImageAssetResponse]:
    require_user(repo, user_id)
    assets = [
        _asset_response(item)
        for item in repo.list_creator_activities(user_id, IMAGE_ASSET_CREATOR_ID, limit)
    ]
    assets.sort(key=lambda item: item.created_at, reverse=True)
    return assets


def get_image_asset_path(repo: DynamoRepository, asset_id: str) -> tuple[Path, str]:
    for user in repo.list_users(500):
        user_id = str(user.get("user_id", ""))
        record = repo.get_activity(user_id, IMAGE_ASSET_CREATOR_ID, asset_id)
        if not record:
            continue
        path = Path(str(record.get("local_path", ""))).resolve()
        asset_root = GENERATED_ASSET_DIR.resolve()
        if asset_root not in path.parents or not path.exists():
            raise FileNotFoundError(asset_id)
        return path, str(record.get("mime_type", "image/png"))
    raise FileNotFoundError(asset_id)


def delete_image_asset(repo: DynamoRepository, user_id: str, asset_id: str) -> None:
    require_user(repo, user_id)
    record = repo.get_activity(user_id, IMAGE_ASSET_CREATOR_ID, asset_id)
    if not record:
        raise KeyError(f"Image asset not found: {asset_id}")
    path = Path(str(record.get("local_path", ""))).resolve()
    asset_root = GENERATED_ASSET_DIR.resolve()
    if asset_root in path.parents and path.exists():
        path.unlink()
    repo.delete_activity(user_id, IMAGE_ASSET_CREATOR_ID, asset_id)
