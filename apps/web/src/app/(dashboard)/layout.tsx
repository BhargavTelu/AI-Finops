import { auth } from "@clerk/nextjs/server";
import { redirect } from "next/navigation";

// Sidebar and header will be implemented in M0.
// For now: auth gate + shell layout.
export default async function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const { userId } = await auth();
  if (!userId) redirect("/sign-in");

  return (
    <div className="flex h-screen overflow-hidden">
      {/* Sidebar placeholder — implement in M0 */}
      <aside className="w-64 shrink-0 border-r bg-background" />
      <div className="flex flex-1 flex-col overflow-hidden">
        {/* Header placeholder — implement in M0 */}
        <header className="h-14 shrink-0 border-b" />
        <main className="flex-1 overflow-auto p-6">{children}</main>
      </div>
    </div>
  );
}
