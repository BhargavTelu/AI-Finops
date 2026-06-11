"use client";

import { useState } from "react";
import type { Route } from "next";
import Link from "next/link";
import { useAuth } from "@clerk/nextjs";
import { useToast } from "@/hooks/use-toast";
import {
  Copy,
  Check,
  ChevronDown,
  MoreHorizontal,
  RefreshCw,
  ShieldCheck,
  Trash2,
  Plus,
  KeyRound,
  AlertCircle,
} from "lucide-react";

import { createApiClient } from "@/lib/api-client";
import type { IntegrationRead } from "@/lib/types";
import { StatusBadge } from "@/components/ui/status-badge";
import { EmptyState } from "@/components/empty-state";
import { ConfirmDialog } from "@/components/confirm-dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Separator } from "@/components/ui/separator";
import { PageMotion } from "@/components/motion-wrapper";
import { cn } from "@/lib/utils";

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

const PROVIDER_LABELS: Record<IntegrationRead["provider"], string> = {
  openai: "OpenAI",
  anthropic: "Anthropic",
  gemini: "Gemini",
};

/** Map IntegrationRead status → StatusBadge status type */
function toStatusType(status: IntegrationRead["status"]) {
  if (status === "active") return "active" as const;
  if (status === "error") return "error" as const;
  return "inactive" as const; // revoked
}

export function IntegrationsPage({ integrations: initial }: Props) {
  const { getToken } = useAuth();
  const { toast } = useToast();
  const [list, setList] = useState<IntegrationRead[]>(initial);

  // Add dialog
  const [addOpen, setAddOpen] = useState(false);
  const [provider, setProvider] = useState("openai");
  const [displayName, setDisplayName] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [submitState, setSubmitState] = useState<SubmitState>("idle");
  const [errorMsg, setErrorMsg] = useState("");

  // Revoke confirm dialog
  const [revokeTarget, setRevokeTarget] = useState<IntegrationRead | null>(null);
  const [revokingId, setRevokingId] = useState<string | null>(null);

  // Copy-key feedback per integration
  const [copiedId, setCopiedId] = useState<string | null>(null);

  function openAddDialog() {
    setProvider("openai");
    setDisplayName("");
    setApiKey("");
    setSubmitState("idle");
    setErrorMsg("");
    setAddOpen(true);
  }

  async function handleConnect(e: React.FormEvent) {
    e.preventDefault();
    setSubmitState("loading");
    setErrorMsg("");
    try {
      const token = await getToken();
      const api = createApiClient(token!);
      const created = await api.post<IntegrationRead>("/integrations", {
        provider,
        display_name: displayName,
        api_key: apiKey,
      });
      setList((prev) => [created, ...prev]);
      setSubmitState("success");
      setTimeout(() => {
        setAddOpen(false);
        setSubmitState("idle");
      }, 1800);
    } catch (err: unknown) {
      setErrorMsg(
        err instanceof Error ? err.message : "Connection failed. Please try again."
      );
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
      console.error("Revoke failed:", err);
    } finally {
      setRevokingId(null);
      setRevokeTarget(null);
    }
  }

  function handleCopyMasked(id: string) {
    // Visual feedback only - actual key is not returned by API (security)
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 1500);
  }

  async function handleForceSync(id: string) {
    try {
      const token = await getToken();
      await createApiClient(token!).post<void>(`/integrations/${id}/test`, null);
      toast({ title: "Sync triggered", description: "Data will refresh within 5 minutes." });
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "";
      // Backend stub returns 501 until M4 - show informational message instead of error
      if (msg.includes("Not yet implemented") || msg.includes("501")) {
        toast({
          title: "Syncs run automatically",
          description: "Data refreshes every 24h. On-demand sync is coming in a future update.",
        });
      } else {
        toast({
          title: "Sync failed",
          description: msg || "Could not trigger sync. Please try again.",
          variant: "destructive",
        });
      }
    }
  }

  return (
    <PageMotion>
      <div className="space-y-6">
        {/* Section header - lives inside Settings layout content panel */}
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 className="text-base font-semibold text-foreground">
              API Integrations
            </h2>
            <p className="mt-0.5 text-sm text-muted-foreground">
              Connect your LLM provider Admin API keys to start tracking spend.{" "}
              <Link
                href={"/security" as Route}
                className="font-medium text-foreground underline underline-offset-2 hover:no-underline"
              >
                How we protect your keys
              </Link>
            </p>
          </div>
          <Button onClick={openAddDialog} size="sm" className="gap-1.5 shrink-0">
            <Plus className="h-4 w-4" />
            Add Integration
          </Button>
        </div>

        {/* ── Connected integrations ─────────────────────────────────────── */}
        {list.length === 0 ? (
          <EmptyState
            icon={KeyRound}
            title="No integrations connected"
            description="Connect your first LLM provider key to start seeing spend data on the dashboard."
            action={{ label: "Add integration", onClick: openAddDialog }}
          />
        ) : (
          <div className="space-y-4">
            {list.map((integration) => (
              <IntegrationCard
                key={integration.id}
                integration={integration}
                copiedId={copiedId}
                revokingId={revokingId}
                onCopy={handleCopyMasked}
                onRevoke={(i) => setRevokeTarget(i)}
                onForceSync={handleForceSync}
              />
            ))}
          </div>
        )}

        {/* ── Add integration dialog ─────────────────────────────────────── */}
        <Dialog
          open={addOpen}
          onOpenChange={(v) => {
            if (!v && submitState !== "loading") setAddOpen(false);
          }}
        >
          <DialogContent className="sm:max-w-md">
            <DialogHeader>
              <DialogTitle>Add Integration</DialogTitle>
              <DialogDescription>
                Connect an LLM provider Admin API key. Keys are encrypted
                server-side and never returned to the browser.
              </DialogDescription>
            </DialogHeader>

            <form onSubmit={handleConnect} className="space-y-4 pt-1">
              <div className="space-y-1.5">
                <Label htmlFor="provider">Provider</Label>
                <Select
                  value={provider}
                  onValueChange={setProvider}
                  disabled={submitState === "loading"}
                >
                  <SelectTrigger id="provider" className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="openai">OpenAI</SelectItem>
                    <SelectItem value="anthropic">Anthropic</SelectItem>
                    {/* Gemini hidden until cost ingestion ships (AI Studio has
                        no billing endpoint; Cloud Billing OAuth deferred).
                        Connecting it today would silently ingest $0. */}
                    <SelectItem value="gemini" disabled>
                      Gemini (coming soon)
                    </SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="displayName">Display name</Label>
                <Input
                  id="displayName"
                  placeholder="e.g. Production"
                  required
                  minLength={1}
                  maxLength={100}
                  value={displayName}
                  onChange={(e) => setDisplayName(e.target.value)}
                  disabled={submitState === "loading"}
                />
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="apiKey">Admin API key</Label>
                <Input
                  id="apiKey"
                  type="password"
                  placeholder={provider === "anthropic" ? "sk-ant-admin..." : "sk-admin-..."}
                  required
                  minLength={10}
                  value={apiKey}
                  onChange={(e) => setApiKey(e.target.value)}
                  disabled={submitState === "loading"}
                  autoComplete="off"
                  className="font-mono"
                />
                <p className="text-xs text-muted-foreground">
                  Requires an{" "}
                  <span className="font-medium">Organization Admin API key</span>{" "}
                  - not a project key.
                </p>
              </div>

              <KeyScopeGuide provider={provider} />

              {submitState === "error" && (
                <div role="alert" className="flex items-start gap-2 rounded-md bg-critical-subtle border border-critical/20 px-3 py-2 text-sm text-critical">
                  <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
                  {errorMsg}
                </div>
              )}

              {submitState === "success" && (
                <div className="flex items-center gap-2 rounded-md bg-success-subtle border border-success/20 px-3 py-2 text-sm text-success">
                  <Check className="h-4 w-4 shrink-0" />
                  Connected! Data syncing - numbers appear within 5 minutes.
                </div>
              )}

              <DialogFooter className="pt-2">
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => setAddOpen(false)}
                  disabled={submitState === "loading"}
                >
                  Cancel
                </Button>
                <Button
                  type="submit"
                  disabled={
                    submitState === "loading" ||
                    submitState === "success" ||
                    !displayName ||
                    !apiKey
                  }
                >
                  {submitState === "loading" ? "Connecting…" : "Connect"}
                </Button>
              </DialogFooter>
            </form>
          </DialogContent>
        </Dialog>

        {/* ── Revoke confirm dialog ──────────────────────────────────────── */}
        <ConfirmDialog
          open={revokeTarget !== null}
          onClose={() => setRevokeTarget(null)}
          onConfirm={() => revokeTarget && handleRevoke(revokeTarget.id)}
          title="Revoke integration"
          description={`This will permanently revoke the "${revokeTarget?.display_name}" key. Syncing will stop immediately and this cannot be undone.`}
          confirmLabel="Revoke key"
          variant="destructive"
          isLoading={revokingId !== null}
        />
      </div>
    </PageMotion>
  );
}

/**
 * Per-provider least-privilege key guidance, collapsed by default.
 * Scope facts verified against provider docs 2026-06: OpenAI Admin keys
 * support a read-only "Usage API" scope; Anthropic Admin keys cannot be
 * scoped, so we state what we actually call instead of implying a scope.
 */
function KeyScopeGuide({ provider }: { provider: string }) {
  const [open, setOpen] = useState(false);

  return (
    <div className="rounded-md border bg-muted/40">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-2 px-3 py-2 text-left text-xs font-medium text-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
        aria-expanded={open}
      >
        <ShieldCheck className="h-3.5 w-3.5 shrink-0 text-muted-foreground" aria-hidden />
        How to create a least-privilege key
        <ChevronDown
          className={cn(
            "ml-auto h-3.5 w-3.5 shrink-0 text-muted-foreground transition-transform",
            open && "rotate-180"
          )}
          aria-hidden
        />
      </button>

      {open && (
        <div className="space-y-2 border-t px-3 py-2.5 text-xs text-muted-foreground">
          {provider === "openai" && (
            <ol className="list-decimal space-y-1 pl-4">
              <li>
                On platform.openai.com, open{" "}
                <span className="font-medium text-foreground">
                  Settings &rarr; Organization &rarr; Admin keys
                </span>{" "}
                (requires the Organization Owner role).
              </li>
              <li>
                Create a new Admin key and choose{" "}
                <span className="font-medium text-foreground">Restricted</span>.
              </li>
              <li>
                Grant <span className="font-medium text-foreground">Read</span>{" "}
                on the <span className="font-medium text-foreground">Usage API</span>{" "}
                scope only - that covers the costs and usage endpoints we read.
                Leave every other scope at None.
              </li>
            </ol>
          )}
          {provider === "anthropic" && (
            <>
              <p>
                Create an Admin key in the{" "}
                <span className="font-medium text-foreground">
                  Claude Console &rarr; Settings &rarr; Admin keys
                </span>{" "}
                (requires the org admin role).
              </p>
              <p>
                Anthropic Admin keys can&apos;t be scoped down. We only ever call
                the read-only usage-report endpoint - never any endpoint that
                changes your org.
              </p>
            </>
          )}
          <p>
            Your key is AES-256 encrypted at rest, never returned to the
            browser, and never written to logs.{" "}
            <Link
              href={"/security" as Route}
              className="font-medium text-foreground underline underline-offset-2 hover:no-underline"
            >
              Security details
            </Link>
          </p>
        </div>
      )}
    </div>
  );
}

/** Individual integration card - shows provider, masked key, status, metrics, actions */
function IntegrationCard({
  integration,
  copiedId,
  revokingId,
  onCopy,
  onRevoke,
  onForceSync,
}: {
  integration: IntegrationRead;
  copiedId: string | null;
  revokingId: string | null;
  onCopy: (id: string) => void;
  onRevoke: (i: IntegrationRead) => void;
  onForceSync: (id: string) => void;
}) {
  const isRevoked = integration.status === "revoked";
  const isError = integration.status === "error";
  const isCopied = copiedId === integration.id;

  return (
    <div
      className={cn(
        "rounded-xl border border-transparent bg-card shadow-card transition-shadow hover:shadow-card-hover",
        isError && "border-critical/30",
        isRevoked && "opacity-60"
      )}
    >
      {/* Card header row */}
      <div className="flex items-start justify-between gap-4 p-6">
        <div className="flex items-start gap-3 min-w-0">
          {/* Provider label */}
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-muted">
            <span className="text-xs font-bold text-muted-foreground">
              {PROVIDER_LABELS[integration.provider].slice(0, 2).toUpperCase()}
            </span>
          </div>

          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-sm font-semibold text-foreground">
                {integration.display_name}
              </span>
              <span className="text-xs text-muted-foreground">
                {PROVIDER_LABELS[integration.provider]}
              </span>
            </div>

            {/* Masked key + copy */}
            <div className="mt-1 flex items-center gap-1.5">
              <span className="text-mono text-xs text-muted-foreground tracking-wider">
                ••••••••••••••••
                <span className="ml-0.5 text-foreground">
                  {integration.id.slice(-4)}
                </span>
              </span>
              <button
                onClick={() => onCopy(integration.id)}
                className="rounded p-0.5 text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                aria-label="Copy key identifier"
              >
                {isCopied ? (
                  <Check className="h-3.5 w-3.5 text-success" />
                ) : (
                  <Copy className="h-3.5 w-3.5" />
                )}
              </button>
            </div>
          </div>
        </div>

        <div className="flex shrink-0 items-center gap-2">
          <StatusBadge status={toStatusType(integration.status)} />

          {/* Actions dropdown */}
          {!isRevoked && (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-8 w-8"
                  aria-label="More actions"
                >
                  <MoreHorizontal className="h-4 w-4" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-44">
                <DropdownMenuItem
                  className="gap-2 text-xs"
                  onClick={() => onForceSync(integration.id)}
                >
                  <RefreshCw className="h-3.5 w-3.5" />
                  Force sync
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem
                  className="gap-2 text-xs text-destructive focus:text-destructive"
                  onClick={() => onRevoke(integration)}
                >
                  <Trash2 className="h-3.5 w-3.5" />
                  Revoke key
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          )}
        </div>
      </div>

      <Separator className="opacity-60" />

      {/* Metrics row */}
      <div className="flex items-center gap-6 px-6 py-4">
        <div>
          <p className="text-xs text-muted-foreground">Last synced</p>
          <p className="mt-0.5 text-sm font-medium text-mono">
            {formatRelativeTime(integration.last_synced_at)}
          </p>
        </div>

        <div>
          <p className="text-xs text-muted-foreground">Status</p>
          <p className="mt-0.5 text-sm font-medium capitalize">
            {integration.status}
          </p>
        </div>

        {/* Error message inline for error state */}
        {isError && integration.last_error && (
          <div className="flex items-start gap-1.5 ml-auto max-w-xs">
            <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-critical" />
            <p className="text-xs text-critical line-clamp-2">
              {integration.last_error}
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
