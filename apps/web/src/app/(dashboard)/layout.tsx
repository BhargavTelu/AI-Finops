import { auth } from "@clerk/nextjs/server";
import { redirect } from "next/navigation";

import { DashboardShell } from "@/components/dashboard-shell";

export default async function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const { userId, orgId } = await auth();
  if (!userId) redirect("/sign-in");
  if (!orgId) redirect("/create-org");

  return <DashboardShell>{children}</DashboardShell>;
}
