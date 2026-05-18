"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { cn } from "@/lib/utils";

const links = [
  { href: "/dashboard", label: "Dashboard" },
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
