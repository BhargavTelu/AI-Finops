"use client";

import { useEffect, useRef, useState } from "react";
import { useAuth } from "@clerk/nextjs";
import { useRouter } from "next/navigation";
import { CalendarClock, CreditCard, ExternalLink, Loader2 } from "lucide-react";

import { createApiClient } from "@/lib/api-client";
import { captureCheckoutCompleted } from "@/lib/posthog";
import type { BillingStatus } from "@/lib/types";
import { useToast } from "@/hooks/use-toast";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/ui/status-badge";
import { PlanPicker } from "@/components/plan-picker";
import { PageMotion } from "@/components/motion-wrapper";

function fmtDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("en-US", {
    month: "long",
    day: "numeric",
    year: "numeric",
  });
}

interface Props {
  billing: BillingStatus | null;
  checkoutResult: string | null;
}

export function BillingClient({ billing, checkoutResult }: Props) {
  const { getToken } = useAuth();
  const { toast } = useToast();
  const router = useRouter();
  const [portalLoading, setPortalLoading] = useState(false);
  const checkoutHandled = useRef(false);

  // Checkout return: toast + funnel event, once. The webhook can lag the
  // redirect by a few seconds - refresh shortly after so the plan card
  // flips from "trial" to the purchased plan without a manual reload.
  useEffect(() => {
    if (!checkoutResult || checkoutHandled.current) return;
    checkoutHandled.current = true;
    if (checkoutResult === "success") {
      captureCheckoutCompleted(billing?.plan ?? "unknown");
      toast({
        title: "Subscription active",
        description: "Welcome aboard. Your plan is now active.",
      });
      const timer = setTimeout(() => router.refresh(), 4000);
      return () => clearTimeout(timer);
    }
    if (checkoutResult === "cancelled") {
      toast({
        title: "Checkout cancelled",
        description: "No charge was made. Your trial continues.",
      });
    }
  }, [checkoutResult, billing?.plan, router, toast]);

  async function handlePortal() {
    setPortalLoading(true);
    try {
      const token = await getToken();
      const { url } = await createApiClient(token!).get<{ url: string }>("/billing/portal", {
        noStore: true,
      });
      window.location.assign(url);
    } catch (err: unknown) {
      toast({
        title: "Could not open billing portal",
        description: err instanceof Error ? err.message : "Try again in a moment.",
        variant: "destructive",
      });
      setPortalLoading(false);
    }
  }

  const subscribed = billing?.has_subscription && !billing.access_blocked;

  return (
    <PageMotion>
      <div className="space-y-6">
        <div>
          <h2 className="text-base font-semibold text-foreground">Billing</h2>
          <p className="mt-0.5 text-sm text-muted-foreground">
            Plan, payment method, and invoices. Card details live with Stripe -
            we never see them.
          </p>
        </div>

        {/* ── Current state card ─────────────────────────────────────────── */}
        <div className="rounded-xl border bg-card p-6 shadow-card">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-muted">
                <CreditCard className="h-4 w-4 text-muted-foreground" />
              </div>
              <div>
                <p className="text-sm font-semibold capitalize text-foreground">
                  {billing?.plan ?? "Unknown"} plan
                </p>
                <p className="mt-0.5 text-xs">
                  <StatusBadge
                    status={billing && !billing.access_blocked ? "active" : "error"}
                    label={(billing?.status ?? "unavailable").replace("_", " ")}
                    className="capitalize"
                  />
                </p>
              </div>
            </div>

            {subscribed ? (
              <Button
                variant="outline"
                size="sm"
                className="gap-1.5"
                onClick={handlePortal}
                disabled={portalLoading}
              >
                {portalLoading ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <ExternalLink className="h-4 w-4" />
                )}
                Manage billing
              </Button>
            ) : null}
          </div>

          <div className="mt-5 flex flex-wrap gap-8 border-t pt-4 text-sm">
            {billing?.trial_days_left !== null && billing?.trial_days_left !== undefined && (
              <div>
                <p className="text-xs text-muted-foreground">Trial remaining</p>
                <p className="mt-0.5 flex items-center gap-1.5 font-medium text-foreground">
                  <CalendarClock className="h-3.5 w-3.5 text-muted-foreground" />
                  {billing.trial_days_left} day{billing.trial_days_left === 1 ? "" : "s"}
                </p>
              </div>
            )}
            {billing?.current_period_end && (
              <div>
                <p className="text-xs text-muted-foreground">Renews</p>
                <p className="mt-0.5 font-medium text-foreground">
                  {fmtDate(billing.current_period_end)}
                </p>
              </div>
            )}
          </div>
        </div>

        {/* ── Plan picker (hidden once subscribed - changes go via portal) ── */}
        {!subscribed && (
          <div>
            <h3 className="text-sm font-semibold text-foreground">Choose a plan</h3>
            <p className="mb-4 mt-0.5 text-xs text-muted-foreground">
              Every plan includes everything - attribution, anomaly alerts,
              budgets, Slack, and the monthly CFO report. 14-day trial included.
            </p>
            <PlanPicker />
          </div>
        )}
      </div>
    </PageMotion>
  );
}
