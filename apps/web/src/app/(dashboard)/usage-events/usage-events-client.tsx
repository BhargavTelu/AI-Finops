"use client";

import { useState, useTransition } from "react";
import { useAuth } from "@clerk/nextjs";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { createApiClient } from "@/lib/api-client";
import type { Tag, UsageEventRead } from "@/lib/types";

// ── Helpers ────────────────────────────────────────────────────────────────────

function fmtCost(raw: string): string {
  const n = parseFloat(raw);
  if (n === 0) return "$0.00";
  if (n < 0.01) return `$${n.toFixed(6)}`;
  return `$${n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function fmtDate(iso: string): string {
  return new Date(iso).toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    timeZoneName: "short",
  });
}

const TAG_NONE = "__none__";

// ── Tag override drawer ────────────────────────────────────────────────────────

interface OverrideDrawerProps {
  event: UsageEventRead | null;
  tags: Tag[];
  onClose: () => void;
  onSaved: (updated: UsageEventRead) => void;
}

function tagNamesFor(tags: Tag[], type: string): string[] {
  return tags.filter((t) => t.type === type).map((t) => t.name);
}

function OverrideDrawer({ event, tags, onClose, onSaved }: OverrideDrawerProps) {
  const { getToken } = useAuth();
  const [featureTag, setFeatureTag] = useState(event?.feature_tag ?? TAG_NONE);
  const [teamTag, setTeamTag] = useState(event?.team_tag ?? TAG_NONE);
  const [customerTag, setCustomerTag] = useState(event?.customer_tag ?? TAG_NONE);
  const [envTag, setEnvTag] = useState(event?.env_tag ?? TAG_NONE);
  const [error, setError] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  if (!event) return null;

  function buildPatch() {
    const patch: Record<string, string | null> = {};
    if (featureTag !== event!.feature_tag)
      patch.feature_tag = featureTag === TAG_NONE ? null : featureTag;
    if (teamTag !== event!.team_tag)
      patch.team_tag = teamTag === TAG_NONE ? null : teamTag;
    if (customerTag !== event!.customer_tag)
      patch.customer_tag = customerTag === TAG_NONE ? null : customerTag;
    if (envTag !== event!.env_tag)
      patch.env_tag = envTag === TAG_NONE ? null : envTag;
    return patch;
  }

  function handleSave() {
    const patch = buildPatch();
    if (Object.keys(patch).length === 0) {
      onClose();
      return;
    }
    setError(null);
    startTransition(async () => {
      try {
        const token = await getToken();
        const api = createApiClient(token!);
        const updated = await api.patch<UsageEventRead>(
          `/usage/events/${event!.id}/tags`,
          patch,
        );
        onSaved(updated);
        onClose();
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to save override");
      }
    });
  }

  return (
    <Dialog open={!!event} onOpenChange={(open: boolean) => !open && onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Override Tags</DialogTitle>
          <DialogDescription>
            Manually pin tag values for this event. This survives re-ingestion.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-1 rounded-md border bg-muted/40 px-3 py-2 text-xs text-muted-foreground">
          <p><span className="font-medium">Provider:</span> {event.provider}</p>
          <p><span className="font-medium">Model:</span> {event.model}</p>
          {event.api_key_label && (
            <p><span className="font-medium">Key label:</span> {event.api_key_label}</p>
          )}
          <p><span className="font-medium">Hour:</span> {fmtDate(event.bucket_hour)}</p>
        </div>

        <div className="space-y-4">
          {(
            [
              { type: "feature", label: "Feature tag", value: featureTag, set: setFeatureTag },
              { type: "team", label: "Team tag", value: teamTag, set: setTeamTag },
              { type: "customer", label: "Customer tag", value: customerTag, set: setCustomerTag },
              { type: "env", label: "Env tag", value: envTag, set: setEnvTag },
            ] as const
          ).map(({ type, label, value, set }) => {
            const names = tagNamesFor(tags, type);
            return (
              <div key={type} className="space-y-1.5">
                <label className="text-sm font-medium">{label}</label>
                <Select value={value} onValueChange={set}>
                  <SelectTrigger className="w-full">
                    <SelectValue placeholder="(untagged)" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value={TAG_NONE}>
                      <span className="text-muted-foreground">(untagged)</span>
                    </SelectItem>
                    {names.map((n) => (
                      <SelectItem key={n} value={n}>
                        {n}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            );
          })}
        </div>

        {error && (
          <p className="text-sm text-destructive">{error}</p>
        )}

        <div className="flex gap-2">
          <Button onClick={handleSave} disabled={isPending} className="flex-1">
            {isPending ? "Saving…" : "Save override"}
          </Button>
          <Button variant="outline" onClick={onClose} disabled={isPending}>
            Cancel
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

// ── Main client component ──────────────────────────────────────────────────────

interface Props {
  events: UsageEventRead[];
  tags: Tag[];
}

export function UsageEventsClient({ events: initialEvents, tags }: Props) {
  const [events, setEvents] = useState<UsageEventRead[]>(initialEvents);
  const [editing, setEditing] = useState<UsageEventRead | null>(null);

  function handleSaved(updated: UsageEventRead) {
    setEvents((prev) => prev.map((e) => (e.id === updated.id ? updated : e)));
  }

  if (events.length === 0) {
    return (
      <div className="rounded-lg border bg-card p-12 text-center text-sm text-muted-foreground">
        No usage events found. Connect an integration and wait for the first sync.
      </div>
    );
  }

  return (
    <>
      <div className="overflow-x-auto rounded-lg border">
        <table className="w-full text-sm">
          <thead className="border-b bg-muted/40">
            <tr>
              {["Time (UTC)", "Provider", "Model", "Key label", "Tags", "Cost", "Requests", ""].map(
                (h) => (
                  <th key={h} className="px-4 py-3 text-left font-medium text-muted-foreground">
                    {h}
                  </th>
                )
              )}
            </tr>
          </thead>
          <tbody className="divide-y">
            {events.map((ev) => (
              <tr key={ev.id} className="hover:bg-muted/20">
                <td className="px-4 py-3 tabular-nums text-xs text-muted-foreground whitespace-nowrap">
                  {fmtDate(ev.bucket_hour)}
                </td>
                <td className="px-4 py-3">{ev.provider}</td>
                <td className="px-4 py-3 font-mono text-xs">{ev.model}</td>
                <td className="px-4 py-3 font-mono text-xs text-muted-foreground">
                  {ev.api_key_label ?? <span className="italic">(none)</span>}
                </td>
                <td className="px-4 py-3">
                  <div className="flex flex-wrap gap-1">
                    {ev.manual_override && (
                      <span className="rounded-full border bg-muted px-2 py-0.5 text-[10px] font-medium">
                        pinned
                      </span>
                    )}
                    {ev.feature_tag && (
                      <span className="rounded-full border px-2 py-0.5 text-xs">{ev.feature_tag}</span>
                    )}
                    {ev.team_tag && (
                      <span className="rounded-full border px-2 py-0.5 text-xs">{ev.team_tag}</span>
                    )}
                    {ev.customer_tag && (
                      <span className="rounded-full border px-2 py-0.5 text-xs">{ev.customer_tag}</span>
                    )}
                    {ev.env_tag && (
                      <span className="rounded-full border px-2 py-0.5 text-xs">{ev.env_tag}</span>
                    )}
                    {!ev.feature_tag && !ev.team_tag && !ev.customer_tag && !ev.env_tag && (
                      <span className="italic text-muted-foreground text-xs">(untagged)</span>
                    )}
                  </div>
                </td>
                <td className="px-4 py-3 tabular-nums">{fmtCost(ev.cost_usd)}</td>
                <td className="px-4 py-3 tabular-nums">{ev.request_count.toLocaleString()}</td>
                <td className="px-4 py-3">
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => setEditing(ev)}
                  >
                    Override tags
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <OverrideDrawer
        event={editing}
        tags={tags}
        onClose={() => setEditing(null)}
        onSaved={handleSaved}
      />
    </>
  );
}

export function UsageEventsSkeleton() {
  return (
    <div className="space-y-2">
      {Array.from({ length: 8 }).map((_, i) => (
        <Skeleton key={i} className="h-12 w-full rounded-lg" />
      ))}
    </div>
  );
}
