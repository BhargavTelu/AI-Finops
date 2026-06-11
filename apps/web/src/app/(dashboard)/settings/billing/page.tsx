import { auth } from "@clerk/nextjs/server";

import { createApiClient } from "@/lib/api-client";
import type { BillingStatus } from "@/lib/types";
import { BillingClient } from "./billing-client";

export default async function BillingPage({
  searchParams,
}: {
  searchParams: Promise<{ checkout?: string }>;
}) {
  const params = await searchParams;
  const { getToken } = await auth();
  const token = await getToken();

  // noStore: this page is the checkout return URL - it must reflect the
  // webhook's write immediately, not a 2-minute-old cache entry.
  const billing = await createApiClient(token!)
    .get<BillingStatus>("/billing", { noStore: true })
    .catch(() => null);

  return <BillingClient billing={billing} checkoutResult={params.checkout ?? null} />;
}
