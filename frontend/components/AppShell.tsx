"use client";

import Link from "next/link";
import {
  Rss,
  Sparkles,
  Users,
} from "lucide-react";
import type { ReactNode } from "react";
import type { ThreadSummary } from "@/lib/types";

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
  { key: "creators", label: "Creators", href: "/creators", icon: Users },
  { key: "posts", label: "Ready to Comment", href: "/posts-scraping", icon: Rss },
] as const;

export function AppShell({
  active,
  title,
  subtitle,
  eyebrowLabel,
  children,
}: AppShellProps) {
  const resolvedEyebrow = eyebrowLabel === undefined ? active : eyebrowLabel;

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
            return (
              <Link className={className} href={item.href} key={item.key}>
                <Icon size={17} />
                <span>{item.label}</span>
              </Link>
            );
          })}
        </nav>
      </aside>

      <main className="main-area">
        <header className="topbar">
          <div>
            {resolvedEyebrow ? <p className="eyebrow">{resolvedEyebrow}</p> : null}
            <h1>{title}</h1>
            {subtitle ? <p>{subtitle}</p> : null}
          </div>
        </header>
        {children}
      </main>
    </div>
  );
}
