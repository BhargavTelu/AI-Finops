"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { KeyRound, Hash, MessageSquare, CreditCard } from "lucide-react";
import type { Route } from "next";

import { cn } from "@/lib/utils";

const NAV_GROUPS = [
  {
    label: "Connected Services",
    links: [
      {
        href: "/settings/integrations" as Route<string>,
        label: "API Integrations",
        icon: KeyRound,
      },
      {
        href: "/settings/slack" as Route<string>,
        label: "Slack",
        icon: MessageSquare,
      },
    ],
  },
  {
    label: "Configuration",
    links: [
      {
        href: "/settings/tags" as Route<string>,
        label: "Tag Rules",
        icon: Hash,
      },
    ],
  },
  {
    label: "Account",
    links: [
      {
        href: "/settings/billing" as Route<string>,
        label: "Billing",
        icon: CreditCard,
      },
    ],
  },
];

export function SettingsSidebar() {
  const pathname = usePathname();

  return (
    <nav className="w-52 shrink-0" aria-label="Settings navigation">
      <div className="flex flex-col gap-5">
        {NAV_GROUPS.map((group) => (
          <div key={group.label}>
            <p className="mb-1.5 px-2 text-[10px] font-semibold uppercase tracking-widest text-muted-foreground/60">
              {group.label}
            </p>
            <div className="flex flex-col gap-0.5">
              {group.links.map(({ href, label, icon: Icon }) => {
                const isActive =
                  pathname === href || pathname.startsWith(href + "/");
                return (
                  <Link
                    key={href}
                    href={href}
                    aria-current={isActive ? "page" : undefined}
                    className={cn(
                      "flex items-center gap-2.5 rounded-lg px-2 py-2 text-sm transition-colors duration-150",
                      isActive
                        ? "bg-primary/10 font-medium text-foreground"
                        : "text-muted-foreground hover:bg-accent hover:text-foreground"
                    )}
                  >
                    <Icon
                      className={cn(
                        "h-4 w-4 shrink-0 transition-colors",
                        isActive ? "text-primary" : "text-muted-foreground"
                      )}
                      strokeWidth={isActive ? 2.5 : 2}
                    />
                    {label}
                  </Link>
                );
              })}
            </div>
          </div>
        ))}
      </div>
    </nav>
  );
}

// Keep the old name exported so any existing imports don't break during transition
export { SettingsSidebar as SettingsTabs };
