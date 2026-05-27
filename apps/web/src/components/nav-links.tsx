"use client";

import { useEffect } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { LayoutDashboard, BarChart3, Settings, AlertTriangle, Lightbulb, Wallet, List } from "lucide-react";
import { motion } from "framer-motion";
import type { Route } from "next";

import { cn } from "@/lib/utils";

const NAV_SECTIONS = [
  {
    label: "Analytics",
    links: [
      { href: "/dashboard" as Route<string>, label: "Dashboard", icon: LayoutDashboard },
      { href: "/cost-explorer" as Route<string>, label: "Cost Explorer", icon: BarChart3 },
    ],
  },
  {
    label: "Insights",
    links: [
      { href: "/anomalies" as Route<string>, label: "Anomalies", icon: AlertTriangle },
      { href: "/budgets" as Route<string>, label: "Budgets", icon: Wallet },
      { href: "/recommendations" as Route<string>, label: "Recommendations", icon: Lightbulb },
    ],
  },
  {
    label: "Config",
    links: [
      { href: "/settings" as Route<string>, label: "Settings", icon: Settings },
      { href: "/usage-events" as Route<string>, label: "Usage Events", icon: List },
    ],
  },
];

export function NavLinks() {
  const pathname = usePathname();
  const router = useRouter();

  // Pre-warm the RSC payload cache for every route on mount so loading
  // skeletons appear instantly instead of after a network delay.
  useEffect(() => {
    for (const section of NAV_SECTIONS) {
      for (const { href } of section.links) {
        router.prefetch(href);
      }
    }
  }, [router]);

  return (
    <nav className="flex flex-col gap-4">
      {NAV_SECTIONS.map((section) => (
        <div key={section.label}>
          <p className="mb-1 px-2 text-[10px] font-semibold uppercase tracking-widest text-muted-foreground/60">
            {section.label}
          </p>
          <div className="flex flex-col gap-0.5">
            {section.links.map(({ href, label, icon: Icon }) => {
              const isActive = pathname === href || pathname.startsWith(href + "/");
              return (
                <Link
                  key={href}
                  href={href}
                  className={cn(
                    "group relative flex items-center gap-2.5 rounded-lg px-2 py-2 text-sm transition-colors duration-150",
                    isActive
                      ? "font-medium text-foreground"
                      : "text-muted-foreground hover:text-foreground hover:bg-accent"
                  )}
                >
                  {/* Animated active background pill */}
                  {isActive && (
                    <motion.span
                      layoutId="nav-active"
                      className="absolute inset-0 rounded-lg bg-primary/10"
                      transition={{ type: "spring", stiffness: 380, damping: 30 }}
                    />
                  )}
                  <Icon
                    className={cn(
                      "relative h-4 w-4 shrink-0 transition-colors",
                      isActive ? "text-primary" : "text-muted-foreground group-hover:text-foreground"
                    )}
                    strokeWidth={isActive ? 2.5 : 2}
                  />
                  <span className="relative">{label}</span>
                  {/* Active left bar accent */}
                  {isActive && (
                    <motion.span
                      layoutId="nav-bar"
                      className="absolute left-0 top-1 h-[calc(100%-8px)] w-0.5 rounded-full bg-primary"
                      transition={{ type: "spring", stiffness: 380, damping: 30 }}
                    />
                  )}
                </Link>
              );
            })}
          </div>
        </div>
      ))}
    </nav>
  );
}
