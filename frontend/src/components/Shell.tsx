// App shell shared by the admin and client portals: fixed dark sidebar with
// brand, portal-specific nav, and the signed-in identity + sign-out pinned to
// the bottom; content scrolls in the light main column.

import type { ReactNode } from "react";
import { LogoutButton } from "@/components/LogoutButton";
import { NavItem, SidebarNav } from "@/components/SidebarNav";
import type { Me } from "@/lib/api";

export function Shell({ me, portalLabel, nav, children }: {
  me: Me;
  portalLabel: string;
  nav: NavItem[];
  children: ReactNode;
}) {
  return (
    <div className="flex min-h-screen">
      <aside className="fixed inset-y-0 flex w-56 flex-col bg-slate-900 px-3 py-5">
        <div className="mb-6 px-3">
          <p className="text-base font-semibold tracking-tight text-white">
            NEXUS <span className="text-indigo-400">PM</span>
          </p>
          <p className="mt-0.5 text-xs text-slate-500">{portalLabel}</p>
        </div>
        <SidebarNav items={nav} />
        <div className="mt-auto border-t border-slate-800 px-3 pt-4">
          <p className="truncate text-xs font-medium text-slate-200">{me.display_name}</p>
          <p className="mb-2 truncate text-xs text-slate-500">{me.role}</p>
          <LogoutButton />
        </div>
      </aside>
      <main className="ml-56 min-w-0 flex-1 bg-slate-100">
        <div className="mx-auto max-w-6xl px-8 py-8">{children}</div>
      </main>
    </div>
  );
}
