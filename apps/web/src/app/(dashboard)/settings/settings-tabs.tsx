"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { Route } from "next";

import { cn } from "@/lib/utils";

const TABS = [
  { href: "/settings/integrations" as Route<string>, label: "Integrations" },
  { href: "/settings/tags" as Route<string>, label: "Tag Rules" },
  { href: "/settings/slack" as Route<string>, label: "Slack" },
];

export function SettingsTabs() {
  const pathname = usePathname();
  return (
    <nav className="flex gap-0 border-b border-border/60">
      {TABS.map(({ href, label }) => {
        const isActive = pathname.startsWith(href);
        return (
          <Link
            key={href}
            href={href}
            className={cn(
              "-mb-px border-b-2 px-4 pb-2.5 pt-0.5 text-sm font-medium transition-colors",
              isActive
                ? "border-primary text-foreground"
                : "border-transparent text-muted-foreground hover:text-foreground"
            )}
          >
            {label}
          </Link>
        );
      })}
    </nav>
  );
}
