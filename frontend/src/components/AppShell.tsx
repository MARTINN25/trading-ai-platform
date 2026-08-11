"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

/**
 * Persistent application shell (Phase 1, task scope §4) — mounted once
 * in `app/layout.tsx` (a Server Component) around `{children}`. Only
 * this component carries `"use client"`: `usePathname()` is the sole
 * reason it needs to be a Client Component (ADR-0003 §21.1 — the
 * directive goes on the specific interactive piece, not the whole
 * layout). `children` crosses the server/client boundary as ordinary
 * React nodes, which is serializable by construction (ADR-0003 §21.1).
 *
 * Four primary destinations only (task scope §4) — Notes and Settings
 * are deliberately absent from navigation in this package
 * (`INFORMATION_ARCHITECTURE.md` §2.7/§2.8: Notes has no CRUD yet,
 * Settings isn't approved for this package). Instrument Workspace is
 * reached contextually (search, watchlist, insight/journal links),
 * never as a top-level nav item (`INFORMATION_ARCHITECTURE.md` §2.3).
 */

interface NavItem {
  href: string;
  label: string;
}

const NAV_ITEMS: NavItem[] = [
  { href: "/", label: "Обзор" },
  { href: "/markets", label: "Рынки" },
  { href: "/insights", label: "История" },
  { href: "/journal", label: "Дневник" },
];

function isActiveRoute(pathname: string, href: string): boolean {
  if (href === "/") {
    return pathname === "/";
  }
  return pathname === href || pathname.startsWith(`${href}/`);
}

export default function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();

  return (
    <div className="app-shell">
      <header className="app-header">
        <div className="app-header-inner">
          <Link href="/" className="app-brand">
            AI Trading Assistant
          </Link>
          <nav className="app-nav" aria-label="Основная навигация">
            <ul className="app-nav-list">
              {NAV_ITEMS.map((item) => {
                const active = isActiveRoute(pathname, item.href);
                return (
                  <li key={item.href}>
                    <Link
                      href={item.href}
                      className={active ? "app-nav-link app-nav-link-active" : "app-nav-link"}
                      aria-current={active ? "page" : undefined}
                    >
                      {item.label}
                    </Link>
                  </li>
                );
              })}
            </ul>
          </nav>
        </div>
      </header>
      <div className="app-content">{children}</div>
    </div>
  );
}
