"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { Route } from "next";

import { cn } from "@/lib/utils";

const links: { href: Route<string>; label: string }[] = [
  { href: "/dashboard", label: "Dashboard" },
  { href: "/cost-explorer", label: "Cost Explorer" },
  { href: "/settings", label: "Settings" },
];

export function NavLinks() {
  const pathname = usePathname();
  return (
    <nav className="flex flex-col gap-1">
      {links.map(({ href, label }) => (
        <Link
          key={href}
          href={href}
          className={cn(
            "rounded-md px-2 py-1.5 text-sm hover:bg-accent",
            pathname.startsWith(href) && "bg-accent font-medium"
          )}
        >
          {label}
        </Link>
      ))}
    </nav>
  );
}
