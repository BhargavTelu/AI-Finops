"use client";

import { useEffect, useRef } from "react";
import { useAuth } from "@clerk/nextjs";
import { useRouter } from "next/navigation";

import { createApiClient } from "@/lib/api-client";
import type { BillingStatus } from "@/lib/types";

const POLL_INTERVAL_MS = 5_000;
const POLL_MAX_ATTEMPTS = 12; // ~1 minute

/**
 * Invisible escape hatch for the checkout race: the Stripe success redirect
 * can beat the webhook, so someone who JUST paid may briefly land on the
 * paywall. Poll /billing for up to a minute; the moment access unblocks,
 * refresh so the real page (including /settings/billing?checkout=success
 * with its toast) renders. Stops quietly after the budget - a genuinely
 * expired org just sees the paywall.
 */
export function PaywallRefresher() {
  const { getToken } = useAuth();
  const router = useRouter();
  const stopped = useRef(false);

  useEffect(() => {
    let attempts = 0;
    const timer = setInterval(async () => {
      attempts += 1;
      try {
        const token = await getToken();
        const billing = await createApiClient(token!).get<BillingStatus>("/billing", {
          noStore: true,
        });
        if (!billing.access_blocked && !stopped.current) {
          stopped.current = true;
          clearInterval(timer);
          router.refresh();
          return;
        }
      } catch {
        // transient - keep polling until the attempt budget runs out
      }
      if (attempts >= POLL_MAX_ATTEMPTS) clearInterval(timer);
    }, POLL_INTERVAL_MS);

    return () => {
      stopped.current = true;
      clearInterval(timer);
    };
  }, [getToken, router]);

  return null;
}
