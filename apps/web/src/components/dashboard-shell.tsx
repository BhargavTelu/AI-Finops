"use client";

import { useState } from "react";
import { Zap, Menu, X } from "lucide-react";
import { OrganizationSwitcher, UserButton } from "@clerk/nextjs";

import { NavLinks } from "@/components/nav-links";

interface Props {
  children: React.ReactNode;
}

export function DashboardShell({ children }: Props) {
  const [sidebarOpen, setSidebarOpen] = useState(false);

  return (
    <div className="flex h-screen overflow-hidden bg-background">
      {/* Mobile overlay - tap outside to close sidebar */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/50 backdrop-blur-sm lg:hidden"
          onClick={() => setSidebarOpen(false)}
          aria-hidden="true"
        />
      )}

      {/* Sidebar - tinted chrome surface so content cards stay dominant */}
      <aside
        className={`fixed inset-y-0 left-0 z-50 flex w-60 shrink-0 flex-col border-r border-border/70 bg-sidebar transition-transform duration-200 ease-in-out lg:static lg:translate-x-0 ${
          sidebarOpen ? "translate-x-0" : "-translate-x-full"
        }`}
        aria-label="Main navigation"
      >
        {/* Brand lockup */}
        <div className="flex h-14 items-center gap-2.5 px-4">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-gradient-to-br from-primary to-chart-2 shadow-card">
            <Zap className="h-4 w-4 text-primary-foreground" strokeWidth={2.5} aria-hidden />
          </div>
          <span className="text-sm font-semibold tracking-tight text-sidebar-foreground">
            SpendOps
            <span className="ml-1 text-muted-foreground/80">AI</span>
          </span>
          {/* Close button - mobile only */}
          <button
            className="ml-auto rounded-md p-1 text-muted-foreground transition-colors duration-150 hover:bg-accent hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring lg:hidden"
            onClick={() => setSidebarOpen(false)}
            aria-label="Close navigation"
          >
            <X className="h-4 w-4" aria-hidden />
          </button>
        </div>

        {/* Nav links */}
        <div className="flex-1 overflow-y-auto scrollbar-thin px-3 py-2">
          <NavLinks />
        </div>

        {/* Org switcher */}
        <div className="border-t border-border/70 p-3">
          <OrganizationSwitcher
            hidePersonal
            appearance={{
              elements: {
                rootBox: "w-full",
                organizationSwitcherTrigger:
                  "w-full rounded-lg px-2 py-1.5 text-sm hover:bg-accent transition-colors duration-150",
              },
            }}
          />
        </div>
      </aside>

      {/* Main */}
      <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
        {/* Top bar - translucent, blurs page content scrolling beneath */}
        <header className="flex h-14 shrink-0 items-center justify-between border-b border-border/70 bg-background/85 px-5 backdrop-blur-md">
          {/* Hamburger - mobile only */}
          <button
            className="rounded-md p-1.5 text-muted-foreground transition-colors duration-150 hover:bg-accent hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring lg:hidden"
            onClick={() => setSidebarOpen(true)}
            aria-label="Open navigation"
            aria-expanded={sidebarOpen}
          >
            <Menu className="h-5 w-5" aria-hidden />
          </button>
          {/* Spacer on desktop */}
          <div className="hidden lg:block" aria-hidden />

          <UserButton
            appearance={{
              elements: {
                avatarBox: "h-8 w-8 ring-1 ring-border",
              },
            }}
          />
        </header>

        {/* Page content - max-w-7xl keeps wide monitors comfortable */}
        <main className="flex-1 overflow-auto scrollbar-thin">
          <div className="mx-auto max-w-7xl px-6 py-8 lg:px-10">
            {children}
          </div>
        </main>
      </div>
    </div>
  );
}
