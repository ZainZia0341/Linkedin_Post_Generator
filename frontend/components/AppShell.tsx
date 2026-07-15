"use client";

import Link from "next/link";
import {
  Bell,
  Brain,
  Clock,
  LayoutDashboard,
  PenLine,
  Rss,
  Sparkles,
  Users,
} from "lucide-react";
import type { ReactNode } from "react";
import type { ThreadSummary } from "@/lib/types";
import { compactDate, initials, threadTitle } from "@/lib/format";

type AppShellProps = {
  active: "dashboard" | "generate" | "brainstorm" | "creators" | "posts" | "activity" | "engagement" | "history" | "settings";
  title: string;
  subtitle?: string;
  eyebrowLabel?: string | null;
  userName: string;
  userTitle?: string;
  threads?: ThreadSummary[];
  children: ReactNode;
};

const navItems = [
  { key: "dashboard", label: "Dashboard", href: "/dashboard", icon: LayoutDashboard },
  { key: "generate", label: "Generate", href: "/generate", icon: Sparkles },
  { key: "brainstorm", label: "Brainstorm", href: "", icon: Brain },
  { key: "creators", label: "Creators", href: "/creators", icon: Users },
  { key: "posts", label: "Ready to Comment", href: "/posts-scraping", icon: Rss },
] as const;

export function AppShell({
  active,
  title,
  subtitle,
  eyebrowLabel,
  userName,
  userTitle = "",
  threads = [],
  children,
}: AppShellProps) {
  const displayUserName = userName || "User";
  const userInitials = initials(displayUserName);
  const resolvedEyebrow = eyebrowLabel === undefined ? active : eyebrowLabel;
  const recentThreads = threads.filter((thread) => thread.topic_source !== "comment_generation").slice(0, 5);

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">
            <Sparkles size={18} />
          </div>
          <div>
            <div className="brand-name">AI Spark</div>
            <div className="brand-subtitle">LinkedIn Growth</div>
          </div>
        </div>

        <nav className="nav-list" aria-label="Main navigation">
          {navItems.map((item) => {
            const Icon = item.icon;
            const className = item.key === active ? "nav-item active" : "nav-item";
            if (item.href) {
              return (
                <Link className={className} href={item.href} key={item.key}>
                  <Icon size={17} />
                  <span>{item.label}</span>
                </Link>
              );
            }

            return (
              <button className={`${className} muted`} type="button" disabled key={item.key}>
                <Icon size={17} />
                <span>{item.label}</span>
              </button>
            );
          })}
        </nav>

        {recentThreads.length ? (
          <section className="sidebar-section" aria-label="Recent threads">
            <div className="sidebar-section-title">
              <Clock size={14} />
              <span>Recent Threads</span>
            </div>
            <div className="thread-list">
              {recentThreads.map((thread) => (
                <Link
                  className="thread-link"
                  href={`/generate?thread_id=${encodeURIComponent(thread.thread_id)}`}
                  key={thread.thread_id}
                >
                  <span>
                    <strong>{threadTitle(thread)}</strong>
                    <small>{compactDate(thread.updated_at) || "Recent"}</small>
                  </span>
                </Link>
              ))}
            </div>
          </section>
        ) : null}

        <div className="sidebar-user">
          <div className="avatar small">{userInitials}</div>
          <div className="sidebar-user-copy">
            <strong>{displayUserName}</strong>
            <span>{userTitle || "Profile"}</span>
          </div>
        </div>
      </aside>

      <main className="main-area">
        <header className="topbar">
          <div>
            {resolvedEyebrow ? <p className="eyebrow">{resolvedEyebrow}</p> : null}
            <h1>{title}</h1>
            {subtitle ? <p>{subtitle}</p> : null}
          </div>
          <div className="topbar-actions">
            <button className="icon-button" type="button" aria-label="Notifications" title="Notifications">
              <Bell size={17} />
            </button>
            <div className="avatar">{userInitials}</div>
          </div>
        </header>
        {children}
      </main>

      <Link className="floating-compose" href="/generate" title="Generate post" aria-label="Generate post">
        <PenLine size={19} />
      </Link>
    </div>
  );
}
