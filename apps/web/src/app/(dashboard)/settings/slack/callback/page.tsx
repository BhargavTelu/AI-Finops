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

  // redirect() works by throwing - it must stay OUTSIDE the try block,
  // otherwise the catch swallows the control-flow exception and the success
  // path lands on the error banner.
  let failure: string | null = null;
  try {
    const { getToken } = await auth();
    const token = await getToken();
    await createApiClient(token!).post<SlackStatus>("/slack/oauth/callback", { code, state });
  } catch (err: unknown) {
    failure = err instanceof Error ? err.message : "connection_failed";
  }

  if (failure) {
    redirect(`/settings/slack?error=${encodeURIComponent(failure)}`);
  }
  redirect("/settings/slack?connected=true");
}
