import { OrganizationSwitcher, UserButton } from "@clerk/nextjs";
import { auth } from "@clerk/nextjs/server";
import { redirect } from "next/navigation";
import { Zap } from "lucide-react";

import { NavLinks } from "@/components/nav-links";

export default async function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const { userId, orgId } = await auth();
  if (!userId) redirect("/sign-in");
  if (!orgId) redirect("/create-org");

  return (
    <div className="flex h-screen overflow-hidden bg-background">
      {/* Sidebar */}
      <aside className="flex w-60 shrink-0 flex-col border-r border-border/60 bg-card">
        {/* Brand */}
        <div className="flex h-14 items-center gap-2.5 border-b border-border/60 px-4">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-primary">
            <Zap className="h-4 w-4 text-primary-foreground" strokeWidth={2.5} />
          </div>
          <span className="text-sm font-semibold tracking-tight">SpendOps AI</span>
        </div>

        {/* Nav */}
        <div className="flex-1 overflow-y-auto scrollbar-thin p-3">
          <NavLinks />
        </div>

        {/* Org switcher */}
        <div className="border-t border-border/60 p-3">
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
      <div className="flex flex-1 flex-col overflow-hidden">
        {/* Top bar */}
        <header className="flex h-14 shrink-0 items-center justify-end border-b border-border/60 bg-card px-5">
          <UserButton
            appearance={{
              elements: {
                avatarBox: "h-8 w-8",
              },
            }}
          />
        </header>

        {/* Page content */}
        <main className="flex-1 overflow-auto scrollbar-thin p-6">{children}</main>
      </div>
    </div>
  );
}
