import type { ActivityResponse, ThreadSummary, UserResponse } from "@/lib/types";

export function displayName(user?: UserResponse) {
  const profile = user?.profile || {};
  const fullName = String(profile.full_name || profile.name || user?.user_id || "");
  return fullName.trim();
}

export function firstName(user?: UserResponse) {
  const name = displayName(user);
  return name.split(/\s+/)[0] || name;
}

export function greeting() {
  const hour = new Date().getHours();
  if (hour < 12) return "Good Morning";
  if (hour < 18) return "Good Afternoon";
  return "Good Evening";
}

export function initials(name: string) {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join("") || "U";
}

export function compactDate(value?: string) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(date);
}

export function sortThreads(threads: ThreadSummary[]) {
  return [...threads].sort((left, right) => {
    return new Date(right.updated_at).getTime() - new Date(left.updated_at).getTime();
  });
}

export function threadTitle(thread: ThreadSummary) {
  return thread.topic || thread.generation_style || "Untitled post";
}

export function activityTitle(activity: ActivityResponse) {
  return activity.author_name || activity.creator_id || "Creator";
}

export function previewText(value: string, limit = 128) {
  const text = value.replace(/\s+/g, " ").trim();
  if (text.length <= limit) return text;
  return `${text.slice(0, limit - 1).trim()}...`;
}
