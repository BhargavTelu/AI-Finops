"use client";

import { useState } from "react";
import { useAuth } from "@clerk/nextjs";
import { Loader2 } from "lucide-react";

import { createApiClient } from "@/lib/api-client";
import type { PlanName } from "@/lib/types";
import { useToast } from "@/hooks/use-toast";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const PLANS: { name: PlanName; label: string; price: string; spend: string }[] = [
  { name: "starter", label: "Starter", price: "$299", spend: "Up to $10K/mo tracked spend" },
  { name: "growth", label: "Growth", price: "$599", spend: "Up to $40K/mo tracked spend" },
  { name: "enterprise", label: "Enterprise", price: "$1,500", spend: "Unlimited · priority support" },
];

/**
 * Shared checkout launcher - used by the paywall and the billing settings
 * page. POSTs /billing/checkout and hands the browser to Stripe.
 */
export function PlanPicker({ highlight = "growth" }: { highlight?: PlanName }) {
  const { getToken } = useAuth();
  const { toast } = useToast();
  const [loadingPlan, setLoadingPlan] = useState<PlanName | null>(null);

  async function handleCheckout(plan: PlanName) {
    setLoadingPlan(plan);
    try {
      const token = await getToken();
      const api = createApiClient(token!);
      const { url } = await api.post<{ url: string }>("/billing/checkout", { plan });
      window.location.assign(url);
      // No setLoadingPlan(null) on success - the browser is navigating away.
    } catch (err: unknown) {
      toast({
        title: "Checkout failed",
        description:
          err instanceof Error ? err.message : "Could not start checkout. Try again.",
        variant: "destructive",
      });
      setLoadingPlan(null);
    }
  }

  return (
    <div className="grid gap-3 sm:grid-cols-3">
      {PLANS.map((plan) => {
        const featured = plan.name === highlight;
        return (
          <div
            key={plan.name}
            className={cn(
              "rounded-xl border bg-card p-4 shadow-card",
              featured && "border-2 border-primary"
            )}
          >
            <p className="text-sm font-semibold text-foreground">{plan.label}</p>
            <p className="mt-1.5 flex items-baseline gap-1">
              <span className="tabular-nums text-2xl font-semibold tracking-tight text-foreground">
                {plan.price}
              </span>
              <span className="text-xs text-muted-foreground">/mo</span>
            </p>
            <p className="mt-1 text-xs text-muted-foreground">{plan.spend}</p>
            <Button
              size="sm"
              variant={featured ? "default" : "outline"}
              className="mt-4 w-full"
              disabled={loadingPlan !== null}
              onClick={() => handleCheckout(plan.name)}
            >
              {loadingPlan === plan.name && (
                <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
              )}
              Choose {plan.label}
            </Button>
          </div>
        );
      })}
    </div>
  );
}
