import { Lock } from "lucide-react";

import { PaywallRefresher } from "@/components/paywall-refresher";
import { PlanPicker } from "@/components/plan-picker";

/**
 * Rendered by the dashboard layout in place of page content when the org's
 * trial has lapsed with no active subscription. The nav shell stays visible -
 * settings and billing remain reachable; this is a door with a handle, not a
 * dead end. API enforcement (402 on data routes) is the real gate.
 */
export function Paywall() {
  return (
    <div className="mx-auto max-w-2xl py-12">
      {/* Auto-unblocks the post-checkout webhook-lag window */}
      <PaywallRefresher />
      <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-muted">
        <Lock className="h-5 w-5 text-muted-foreground" />
      </div>
      <h1 className="mt-4 text-2xl font-semibold tracking-tight text-foreground">
        Your trial has ended
      </h1>
      <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
        Your spend data is still being collected and is safe - it&apos;s waiting
        behind this screen. Pick a plan to get back to your dashboard, alerts,
        and reports. Every plan includes everything.
      </p>
      <div className="mt-8">
        <PlanPicker />
      </div>
      <p className="mt-6 text-xs text-muted-foreground">
        Questions about pricing? Email{" "}
        <a href="mailto:security@spendopsai.com" className="font-medium text-foreground underline underline-offset-2 hover:no-underline">
          the founders
        </a>{" "}
        - we read everything.
      </p>
    </div>
  );
}
