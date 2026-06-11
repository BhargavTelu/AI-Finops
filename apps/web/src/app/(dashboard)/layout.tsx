import type { Route } from "next";
import Link from "next/link";
import { auth } from "@clerk/nextjs/server";
import { redirect } from "next/navigation";
import { Clock } from "lucide-react";

import { createApiClient } from "@/lib/api-client";
import type { BillingStatus } from "@/lib/types";
import { DashboardShell } from "@/components/dashboard-shell";
import { Paywall } from "@/components/paywall";

function TrialBanner({ daysLeft }: { daysLeft: number }) {
  return (
    <div className="mb-6 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-warning/30 bg-warning-subtle px-4 py-3">
      <p className="flex items-center gap-2 text-sm text-foreground">
        <Clock className="h-4 w-4 shrink-0 text-warning" />
        <span>
          <span className="font-semibold">
            {daysLeft === 0 ? "Your trial ends today." : `${daysLeft} day${daysLeft === 1 ? "" : "s"} left in your trial.`}
          </span>{" "}
          Pick a plan to keep your alerts and reports running.
        </span>
      </p>
      <Link
        href={"/settings/billing" as Route}
        className="rounded-lg bg-primary px-3.5 py-1.5 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90"
      >
        Choose a plan
      </Link>
    </div>
  );
}

export default async function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const { userId, orgId, getToken } = await auth();
  if (!userId) redirect("/sign-in");
  if (!orgId) redirect("/create-org");

  // Fresh on every navigation (noStore): a paywall that lingers for two
  // cached minutes right after someone PAID is the worst possible moment
  // for staleness. Fail open on error - the API's 402s are the real gate.
  const token = await getToken();
  const billing = await createApiClient(token!)
    .get<BillingStatus>("/billing", { noStore: true })
    .catch(() => null);

  if (billing?.access_blocked) {
    return (
      <DashboardShell>
        <Paywall />
      </DashboardShell>
    );
  }

  const showTrialBanner =
    billing !== null &&
    !billing.has_subscription &&
    billing.trial_days_left !== null &&
    billing.trial_days_left <= 7;

  return (
    <DashboardShell>
      {showTrialBanner && <TrialBanner daysLeft={billing.trial_days_left!} />}
      {children}
    </DashboardShell>
  );
}
