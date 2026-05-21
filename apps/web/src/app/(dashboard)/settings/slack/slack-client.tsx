"use client";

import { useState } from "react";
import { useAuth } from "@clerk/nextjs";

import { createApiClient } from "@/lib/api-client";
import { PageMotion } from "@/components/motion-wrapper";
import type { SlackStatus } from "@/lib/types";

interface Props {
  status: SlackStatus;
  /** Pre-built Slack OAuth URL (empty string = server not configured). */
  oauthUrl: string;
  successMsg: string | null;
  errorMsg: string | null;
}

export function SlackClient({ status: initialStatus, oauthUrl, successMsg, errorMsg }: Props) {
  const { getToken } = useAuth();
  const [status, setStatus] = useState<SlackStatus>(initialStatus);
  const [disconnecting, setDisconnecting] = useState(false);
  const [disconnectError, setDisconnectError] = useState("");

  async function handleDisconnect() {
    setDisconnecting(true);
    setDisconnectError("");
    try {
      const token = await getToken();
      // POST /slack/disconnect returns 204 — no body expected.
      await createApiClient(token!).post<void>("/slack/disconnect", null);
      setStatus({ connected: false });
    } catch (err: unknown) {
      setDisconnectError(err instanceof Error ? err.message : "Disconnect failed. Please try again.");
    } finally {
      setDisconnecting(false);
    }
  }

  return (
    <PageMotion>
      <div className="space-y-8">
        {/* Page heading */}
        <div>
          <h1 className="text-2xl font-semibold">Slack</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Receive daily cost digests and real-time anomaly &amp; budget alerts in Slack.
          </p>
        </div>

        {/* Flash messages passed from OAuth callback redirect */}
        {successMsg && (
          <div className="rounded-md bg-green-50 px-4 py-3 text-sm text-green-800">
            {successMsg}
          </div>
        )}
        {(errorMsg || disconnectError) && (
          <div className="rounded-md bg-destructive/10 px-4 py-3 text-sm text-destructive">
            {errorMsg ?? disconnectError}
          </div>
        )}

        {status.connected ? (
          /* ── Connected state ─────────────────────────────────────────────── */
          <div className="rounded-lg border bg-card p-6">
            <div className="mb-4 flex items-center gap-2">
              <span className="inline-flex h-2 w-2 rounded-full bg-green-500" />
              <h2 className="text-base font-medium">Connected</h2>
            </div>

            <dl className="mb-6 space-y-2 text-sm">
              {status.workspace_id && (
                <div className="flex gap-2">
                  <dt className="w-28 shrink-0 text-muted-foreground">Workspace</dt>
                  <dd className="font-medium">{status.workspace_id}</dd>
                </div>
              )}
              {status.channel_name && (
                <div className="flex gap-2">
                  <dt className="w-28 shrink-0 text-muted-foreground">Channel</dt>
                  <dd className="font-medium">{status.channel_name}</dd>
                </div>
              )}
              {status.installed_at && (
                <div className="flex gap-2">
                  <dt className="w-28 shrink-0 text-muted-foreground">Connected</dt>
                  <dd className="text-muted-foreground">
                    {new Date(status.installed_at).toLocaleDateString()}
                  </dd>
                </div>
              )}
            </dl>

            <div className="flex items-center gap-3">
              {oauthUrl && (
                <a
                  href={oauthUrl}
                  className="inline-flex h-9 items-center rounded-md border px-4 text-sm font-medium transition-colors hover:bg-accent"
                >
                  Reconnect to a different channel
                </a>
              )}
              <button
                onClick={handleDisconnect}
                disabled={disconnecting}
                className="inline-flex h-9 items-center rounded-md bg-destructive px-4 text-sm font-medium text-destructive-foreground transition-opacity disabled:opacity-50"
              >
                {disconnecting ? "Disconnecting…" : "Disconnect"}
              </button>
            </div>
          </div>
        ) : (
          /* ── Not connected / empty state ─────────────────────────────────── */
          <div className="rounded-lg border bg-card px-8 py-12 text-center">
            <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-xl bg-muted text-xl font-bold text-muted-foreground">
              #
            </div>
            <h2 className="mb-2 text-base font-medium">Connect Slack</h2>
            <p className="mb-6 max-w-sm mx-auto text-sm text-muted-foreground">
              Get daily AI cost digests and instant anomaly alerts delivered to your Slack channel.
            </p>
            {oauthUrl ? (
              <a
                href={oauthUrl}
                className="inline-flex h-9 items-center rounded-md bg-primary px-5 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90"
              >
                Connect Slack
              </a>
            ) : (
              <p className="text-sm text-destructive">
                Slack integration is not configured on this server. Set{" "}
                <code className="rounded bg-muted px-1 py-0.5 font-mono text-xs">SLACK_CLIENT_ID</code>{" "}
                to enable.
              </p>
            )}
          </div>
        )}

        {/* Feature list */}
        <div>
          <h2 className="mb-3 text-base font-medium">What you&apos;ll receive</h2>
          <ul className="space-y-2 text-sm text-muted-foreground">
            <li className="flex gap-2">
              <span className="shrink-0">•</span>
              <span>
                Daily cost digest at 09:00 UTC — yesterday spend, 7-day avg, top cost drivers,
                open anomalies
              </span>
            </li>
            <li className="flex gap-2">
              <span className="shrink-0">•</span>
              <span>Real-time anomaly alerts when spend spikes &gt;2σ above your 7-day baseline</span>
            </li>
            <li className="flex gap-2">
              <span className="shrink-0">•</span>
              <span>Budget alerts when spend crosses your configured thresholds (80% and 100%)</span>
            </li>
          </ul>
        </div>
      </div>
    </PageMotion>
  );
}
