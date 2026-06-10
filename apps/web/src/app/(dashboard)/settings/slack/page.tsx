import { auth } from "@clerk/nextjs/server";
import { createApiClient } from "@/lib/api-client";
import type { SlackStatus } from "@/lib/types";

import { SlackClient } from "./slack-client";

// Build Slack OAuth URL server-side - SLACK_CLIENT_ID is not a secret
// but we avoid exposing it as a NEXT_PUBLIC_ var unnecessarily.
function buildOAuthUrl(state: string): string {
  const clientId = process.env.SLACK_CLIENT_ID ?? "";
  const redirectUri =
    process.env.SLACK_REDIRECT_URI ?? "http://localhost:3000/settings/slack/callback";

  if (!clientId) return ""; // server not configured - show unconfigured state in UI

  const params = new URLSearchParams({
    client_id: clientId,
    scope: "incoming-webhook,chat:write",
    redirect_uri: redirectUri,
    state,
  });
  return `https://slack.com/oauth/v2/authorize?${params.toString()}`;
}

export default async function SettingsSlackPage({
  searchParams,
}: {
  searchParams: { connected?: string; error?: string };
}) {
  const { getToken } = await auth();
  const token = await getToken();
  const api = createApiClient(token!);

  const status = await api
    .get<SlackStatus>("/slack/status")
    .catch(() => ({ connected: false }) as SlackStatus);

  // Signed CSRF state from the API - the OAuth callback rejects any code
  // exchange whose state was not issued for this org.
  const { state } = await api
    .get<{ state: string }>("/slack/oauth/state")
    .catch(() => ({ state: "" }));

  const oauthUrl = state ? buildOAuthUrl(state) : "";

  return (
    <SlackClient
      status={status}
      oauthUrl={oauthUrl}
      successMsg={
        searchParams.connected === "true"
          ? "Slack connected! Daily digests start tomorrow at 09:00 UTC."
          : null
      }
      errorMsg={searchParams.error ? decodeURIComponent(searchParams.error) : null}
    />
  );
}
