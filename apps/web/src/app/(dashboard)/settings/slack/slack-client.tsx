"use client";

import { useState } from "react";
import { useAuth } from "@clerk/nextjs";
import { MessageSquare, Check, AlertCircle, RefreshCw } from "lucide-react";

import { createApiClient } from "@/lib/api-client";
import { PageMotion } from "@/components/motion-wrapper";
import { StatusBadge } from "@/components/ui/status-badge";
import { ConfirmDialog } from "@/components/confirm-dialog";
import { EmptyState } from "@/components/empty-state";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import type { SlackStatus } from "@/lib/types";

interface Props {
  status: SlackStatus;
  oauthUrl: string;
  successMsg: string | null;
  errorMsg: string | null;
}

const FEATURES = [
  {
    title: "Daily cost digest",
    description:
      "Yesterday's spend, 7-day average, top cost drivers, and open anomalies — delivered at 09:00 UTC.",
  },
  {
    title: "Real-time anomaly alerts",
    description:
      "Instant alerts when spend spikes more than 2σ above your 7-day rolling baseline.",
  },
  {
    title: "Budget threshold alerts",
    description:
      "Notifications when spend crosses your configured thresholds (80% and 100% of limit).",
  },
];

export function SlackClient({ status: initialStatus, oauthUrl, successMsg, errorMsg }: Props) {
  const { getToken } = useAuth();
  const [status, setStatus] = useState<SlackStatus>(initialStatus);
  const [disconnecting, setDisconnecting] = useState(false);
  const [disconnectError, setDisconnectError] = useState("");
  const [disconnectDialogOpen, setDisconnectDialogOpen] = useState(false);
  const [mutePending, setMutePending] = useState(false);

  async function handleDisconnect() {
    setDisconnecting(true);
    setDisconnectError("");
    try {
      const token = await getToken();
      await createApiClient(token!).post<void>("/slack/disconnect", null);
      setStatus({ connected: false });
      setDisconnectDialogOpen(false);
    } catch (err: unknown) {
      setDisconnectError(
        err instanceof Error ? err.message : "Disconnect failed. Please try again."
      );
    } finally {
      setDisconnecting(false);
    }
  }

  async function handleMuteToggle() {
    const newMuted = !status.alerts_muted;
    setMutePending(true);
    // Optimistic update
    setStatus((prev) => ({ ...prev, alerts_muted: newMuted }));
    try {
      const token = await getToken();
      await createApiClient(token!).patch<SlackStatus>("/slack/settings", {
        alerts_muted: newMuted,
      });
    } catch {
      // Revert on failure
      setStatus((prev) => ({ ...prev, alerts_muted: !newMuted }));
    } finally {
      setMutePending(false);
    }
  }

  const isMuted = status.alerts_muted ?? false;

  return (
    <PageMotion>
      <div className="space-y-8">
        {/* Section header */}
        <div>
          <h2 className="text-base font-semibold text-foreground">Slack</h2>
          <p className="mt-0.5 text-sm text-muted-foreground">
            Receive daily cost digests and real-time anomaly &amp; budget alerts
            in Slack.
          </p>
        </div>

        {/* Flash messages */}
        {successMsg && (
          <div className="flex items-start gap-2 rounded-lg bg-success-subtle border border-success/20 px-4 py-3 text-sm text-success">
            <Check className="mt-0.5 h-4 w-4 shrink-0" />
            {successMsg}
          </div>
        )}
        {(errorMsg || disconnectError) && (
          <div className="flex items-start gap-2 rounded-lg bg-critical-subtle border border-critical/20 px-4 py-3 text-sm text-critical">
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
            {errorMsg ?? disconnectError}
          </div>
        )}

        {status.connected ? (
          /* ── Connected state ──────────────────────────────────────────── */
          <div className="rounded-xl border bg-card shadow-card">
            {/* Connection status header */}
            <div className="flex items-center justify-between gap-4 p-6">
              <div className="flex items-center gap-3">
                <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-muted text-base font-bold text-muted-foreground">
                  #
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <p className="text-sm font-semibold text-foreground">
                      {status.channel_name ?? "Slack"}
                    </p>
                    <StatusBadge status="active" />
                  </div>
                  {status.workspace_id && (
                    <p className="text-xs text-muted-foreground mt-0.5">
                      Workspace: {status.workspace_id}
                    </p>
                  )}
                </div>
              </div>

              <div className="flex items-center gap-2">
                {oauthUrl && (
                  <Button variant="outline" size="sm" asChild className="gap-1.5">
                    <a href={oauthUrl}>
                      <RefreshCw className="h-3.5 w-3.5" />
                      Reconnect
                    </a>
                  </Button>
                )}
                <Button
                  variant="destructive"
                  size="sm"
                  onClick={() => setDisconnectDialogOpen(true)}
                >
                  Disconnect
                </Button>
              </div>
            </div>

            <Separator className="opacity-60" />

            {/* Connection metadata */}
            {status.installed_at && (
              <div className="px-6 py-4 text-sm text-muted-foreground">
                Connected on{" "}
                <span className="font-medium text-foreground">
                  {new Date(status.installed_at).toLocaleDateString("en-US", {
                    month: "long",
                    day: "numeric",
                    year: "numeric",
                  })}
                </span>
              </div>
            )}

            <Separator className="opacity-60" />

            {/* Mute alerts toggle */}
            <div className="flex items-center justify-between gap-6 px-6 py-5">
              <div>
                <Label
                  htmlFor="mute-alerts"
                  className="text-sm font-medium text-foreground"
                >
                  Mute alert notifications
                </Label>
                <p className="mt-0.5 text-xs text-muted-foreground">
                  Pauses anomaly and budget alerts. The daily digest is
                  unaffected.
                </p>
              </div>
              <Switch
                id="mute-alerts"
                checked={isMuted}
                onCheckedChange={handleMuteToggle}
                disabled={mutePending}
                aria-label="Mute alert notifications"
              />
            </div>
          </div>
        ) : (
          /* ── Not connected state ──────────────────────────────────────── */
          <div className="rounded-xl border bg-card shadow-card">
            {oauthUrl ? (
              <div className="flex flex-col items-center py-14 px-8 text-center">
                <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-xl bg-muted">
                  <MessageSquare
                    className="h-6 w-6 text-muted-foreground"
                    strokeWidth={1.5}
                  />
                </div>
                <p className="text-sm font-semibold text-foreground">
                  Connect Slack
                </p>
                <p className="mt-1.5 mb-6 max-w-sm text-sm text-muted-foreground">
                  Get daily AI cost digests and instant anomaly alerts delivered
                  to your Slack channel.
                </p>
                <Button asChild className="gap-2">
                  <a href={oauthUrl}>
                    <MessageSquare className="h-4 w-4" />
                    Connect Slack
                  </a>
                </Button>
              </div>
            ) : (
              <EmptyState
                icon={MessageSquare}
                title="Slack not configured"
                description="Slack integration requires SLACK_CLIENT_ID to be set on the server."
              />
            )}
          </div>
        )}

        {/* ── Feature list ──────────────────────────────────────────────── */}
        <div className="space-y-3">
          <h3 className="text-sm font-semibold text-foreground">
            What you&apos;ll receive
          </h3>
          <div className="space-y-2">
            {FEATURES.map((feature) => (
              <div
                key={feature.title}
                className="flex gap-3 rounded-lg border border-border/60 bg-card px-4 py-3"
              >
                <Check className="mt-0.5 h-4 w-4 shrink-0 text-success" />
                <div>
                  <p className="text-sm font-medium text-foreground">
                    {feature.title}
                  </p>
                  <p className="mt-0.5 text-xs text-muted-foreground">
                    {feature.description}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* ── Disconnect confirm ─────────────────────────────────────────── */}
        <ConfirmDialog
          open={disconnectDialogOpen}
          onClose={() => setDisconnectDialogOpen(false)}
          onConfirm={handleDisconnect}
          title="Disconnect Slack"
          description="Alerts and daily digests will stop being sent to your Slack channel. You can reconnect at any time."
          confirmLabel="Disconnect"
          variant="destructive"
          isLoading={disconnecting}
        />
      </div>
    </PageMotion>
  );
}
