import { NextRequest } from "next/server";

const BACKEND_BASE_URL = (
  process.env.API_BASE_URL ||
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  "http://localhost:7860"
).replace(/\/+$/, "");
const DEFAULT_BACKEND_TIMEOUT_MS = 60000;

function timeoutForPath(path: string): number | null {
  if (
    path.includes("creators/scrape") ||
    path.includes("creators/profile-details/scrape") ||
    path.includes("creators/import") ||
    path.includes("posts/generate") ||
    path.includes("posts/from-creator-activity") ||
    path.includes("posts/modify") ||
    path.includes("comments/generate") ||
    path.includes("ideas/brainstorm")
  ) {
    return null;
  }
  return DEFAULT_BACKEND_TIMEOUT_MS;
}

type RouteContext = {
  params: Promise<{ path?: string[] }>;
};

async function proxy(request: NextRequest, context: RouteContext) {
  const params = await context.params;
  const path = (params.path || []).join("/");
  const targetUrl = new URL(`${BACKEND_BASE_URL}/${path}`);
  targetUrl.search = request.nextUrl.search;

  const headers = new Headers(request.headers);
  headers.delete("host");
  headers.delete("connection");

  const method = request.method.toUpperCase();
  const hasBody = !["GET", "HEAD"].includes(method);
  const controller = new AbortController();
  const timeoutMs = timeoutForPath(path);
  const timeout = timeoutMs ? setTimeout(() => controller.abort(), timeoutMs) : null;

  try {
    const response = await fetch(targetUrl, {
      method,
      headers,
      body: hasBody ? await request.arrayBuffer() : undefined,
      cache: "no-store",
      signal: controller.signal,
    });

    const responseHeaders = new Headers(response.headers);
    responseHeaders.delete("content-encoding");
    responseHeaders.delete("transfer-encoding");

    return new Response(response.body, {
      status: response.status,
      statusText: response.statusText,
      headers: responseHeaders,
    });
  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : "Backend request failed.";
    const message = error instanceof Error && error.name === "AbortError"
      ? timeoutMs
        ? `Backend request timed out after ${timeoutMs / 1000}s.`
        : "Backend request was aborted."
      : `Backend request failed while calling ${targetUrl.origin}. ${errorMessage} Check API_BASE_URL/NEXT_PUBLIC_API_BASE_URL and confirm the FastAPI backend is running.`;
    return Response.json({ detail: message }, { status: 502 });
  } finally {
    if (timeout) clearTimeout(timeout);
  }
}

export async function GET(request: NextRequest, context: RouteContext) {
  return proxy(request, context);
}

export async function POST(request: NextRequest, context: RouteContext) {
  return proxy(request, context);
}

export async function PATCH(request: NextRequest, context: RouteContext) {
  return proxy(request, context);
}

export async function DELETE(request: NextRequest, context: RouteContext) {
  return proxy(request, context);
}
