import { auth } from "@clerk/nextjs/server";
import { redirect } from "next/navigation";

import { createApiClient } from "@/lib/api-client";
import type { SlackStatus } from "@/lib/types";

/**
 * Handles Slack's OAuth redirect.
 * Slack sends: /settings/slack/callback?code=...&state=...
 * On success → redirect to /settings/slack?connected=true
 * On failure → redirect to /settings/slack?error=<message>
 */
export default async function SlackCallbackPage({
  searchParams,
}: {
  searchParams: { code?: string; state?: string; error?: string };
}) {
  const { code, state, error } = searchParams;

  if (error) {
    redirect(`/settings/slack?error=${encodeURIComponent(error)}`);
  }

  if (!code || !state) {
    redirect("/settings/slack?error=missing_code");
  }

  try {
    const { getToken } = await auth();
    const token = await getToken();
    await createApiClient(token!).post<SlackStatus>("/slack/oauth/callback", { code, state });
    redirect("/settings/slack?connected=true");
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : "connection_failed";
    redirect(`/settings/slack?error=${encodeURIComponent(msg)}`);
  }
}
