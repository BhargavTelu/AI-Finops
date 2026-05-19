"use client";

import { useState } from "react";
import { useAuth } from "@clerk/nextjs";
import { createApiClient } from "@/lib/api-client";
import type { IntegrationRead } from "@/lib/types";

interface Props {
  integrations: IntegrationRead[];
}

type SubmitState = "idle" | "loading" | "success" | "error";

function formatRelativeTime(iso: string | null): string {
  if (!iso) return "Never";
  const diff = Date.now() - new Date(iso).getTime();
  const minutes = Math.floor(diff / 60_000);
  if (minutes < 2) return "Just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

const STATUS_BADGE: Record<IntegrationRead["status"], string> = {
  active: "bg-green-100 text-green-800",
  error: "bg-yellow-100 text-yellow-800",
  revoked: "bg-red-100 text-red-800",
};

export function IntegrationsPage({ integrations: initial }: Props) {
  const { getToken } = useAuth();
  const [list, setList] = useState<IntegrationRead[]>(initial);
  const [displayName, setDisplayName] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [submitState, setSubmitState] = useState<SubmitState>("idle");
  const [errorMsg, setErrorMsg] = useState("");
  const [revokingId, setRevokingId] = useState<string | null>(null);

  async function handleConnect(e: React.FormEvent) {
    e.preventDefault();
    setSubmitState("loading");
    setErrorMsg("");

    try {
      const token = await getToken();
      const api = createApiClient(token!);
      const created = await api.post<IntegrationRead>("/integrations", {
        provider: "openai",
        display_name: displayName,
        api_key: apiKey,
      });
      setList((prev) => [created, ...prev]);
      setDisplayName("");
      setApiKey("");
      setSubmitState("success");
      // Clear success banner after 6 seconds
      setTimeout(() => setSubmitState("idle"), 6000);
    } catch (err: unknown) {
      setErrorMsg(err instanceof Error ? err.message : "Connection failed. Please try again.");
      setSubmitState("error");
    }
  }

  async function handleRevoke(id: string) {
    setRevokingId(id);
    try {
      const token = await getToken();
      const api = createApiClient(token!);
      await api.delete(`/integrations/${id}`);
      setList((prev) => prev.filter((i) => i.id !== id));
    } catch (err: unknown) {
      // Surface the error inline without blocking the rest of the UI
      console.error("Revoke failed:", err);
    } finally {
      setRevokingId(null);
    }
  }

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-semibold">Integrations</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Connect your LLM provider Admin API keys to start tracking spend.
        </p>
      </div>

      {/* ── Connect form ── */}
      <div className="rounded-lg border bg-card p-6">
        <h2 className="mb-4 text-base font-medium">Connect a provider</h2>
        <form onSubmit={handleConnect} className="space-y-4">
          {/* Provider — static in M1; a select will replace this in M2 */}
          <div>
            <label className="mb-1.5 block text-sm font-medium" htmlFor="provider">
              Provider
            </label>
            <div
              id="provider"
              className="flex h-9 w-full max-w-xs items-center rounded-md border bg-muted px-3 text-sm text-muted-foreground"
            >
              OpenAI
            </div>
          </div>

          <div>
            <label className="mb-1.5 block text-sm font-medium" htmlFor="displayName">
              Display name
            </label>
            <input
              id="displayName"
              type="text"
              placeholder="e.g. Production"
              required
              minLength={1}
              maxLength={100}
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              className="flex h-9 w-full max-w-xs rounded-md border bg-background px-3 text-sm outline-none focus:ring-2 focus:ring-ring disabled:opacity-50"
              disabled={submitState === "loading"}
            />
          </div>

          <div>
            <label className="mb-1.5 block text-sm font-medium" htmlFor="apiKey">
              Admin API key
            </label>
            <input
              id="apiKey"
              type="password"
              placeholder="sk-admin-..."
              required
              minLength={10}
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              className="flex h-9 w-full max-w-xs rounded-md border bg-background px-3 text-sm font-mono outline-none focus:ring-2 focus:ring-ring disabled:opacity-50"
              disabled={submitState === "loading"}
              autoComplete="off"
            />
            <p className="mt-1 text-xs text-muted-foreground">
              Requires an{" "}
              <span className="font-medium">Organization Admin API key</span> — not a project key.
            </p>
          </div>

          {submitState === "error" && (
            <div className="rounded-md bg-destructive/10 px-4 py-2 text-sm text-destructive">
              {errorMsg}
            </div>
          )}
          {submitState === "success" && (
            <div className="rounded-md bg-green-50 px-4 py-2 text-sm text-green-800">
              Connected! Data syncing — numbers appear within 5 minutes.
            </div>
          )}

          <button
            type="submit"
            disabled={submitState === "loading" || !displayName || !apiKey}
            className="inline-flex h-9 items-center rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground transition-opacity disabled:opacity-50"
          >
            {submitState === "loading" ? "Connecting…" : "Connect"}
          </button>
        </form>
      </div>

      {/* ── Connected integrations list ── */}
      <div>
        <h2 className="mb-3 text-base font-medium">Connected integrations</h2>

        {list.length === 0 ? (
          <p className="text-sm text-muted-foreground">No integrations connected yet.</p>
        ) : (
          <div className="rounded-lg border">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b bg-muted/50 text-left text-xs font-medium uppercase tracking-wide text-muted-foreground">
                  <th className="px-4 py-3">Provider</th>
                  <th className="px-4 py-3">Name</th>
                  <th className="px-4 py-3">Status</th>
                  <th className="px-4 py-3">Last synced</th>
                  <th className="px-4 py-3"></th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {list.map((integration) => (
                  <tr key={integration.id} className="hover:bg-muted/20">
                    <td className="px-4 py-3 font-medium capitalize">{integration.provider}</td>
                    <td className="px-4 py-3">{integration.display_name}</td>
                    <td className="px-4 py-3">
                      <span
                        className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium capitalize ${STATUS_BADGE[integration.status]}`}
                      >
                        {integration.status}
                      </span>
                      {integration.status === "error" && integration.last_error && (
                        <p className="mt-0.5 text-xs text-destructive">{integration.last_error}</p>
                      )}
                    </td>
                    <td className="px-4 py-3 text-muted-foreground">
                      {formatRelativeTime(integration.last_synced_at)}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <button
                        onClick={() => handleRevoke(integration.id)}
                        disabled={revokingId === integration.id}
                        className="text-xs text-destructive hover:underline disabled:opacity-50"
                      >
                        {revokingId === integration.id ? "Revoking…" : "Revoke"}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
