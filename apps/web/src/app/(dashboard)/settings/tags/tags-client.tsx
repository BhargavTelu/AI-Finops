"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Plus, Tag as TagIcon, Trash2, Layers } from "lucide-react";

import { useToast } from "@/hooks/use-toast";
import { createApiClient } from "@/lib/api-client";
import type { MatchType, PreviewMatch, Tag, TagRule, TagType } from "@/lib/types";
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
import { Separator } from "@/components/ui/separator";

interface Props {
  tags: Tag[];
  rules: TagRule[];
  token: string;
}

const TAG_TYPE_LABELS: Record<TagType, string> = {
  feature: "Feature",
  team: "Team",
  customer: "Customer",
  env: "Env",
};

const TAG_TYPE_COLORS: Record<TagType, string> = {
  feature: "bg-blue-100 text-blue-700 border-blue-200",
  team: "bg-purple-100 text-purple-700 border-purple-200",
  customer: "bg-emerald-100 text-emerald-700 border-emerald-200",
  env: "bg-orange-100 text-orange-700 border-orange-200",
};

const MATCH_TYPE_LABELS: Record<MatchType, string> = {
  exact: "Exact",
  substring: "Substring",
  regex: "Regex",
};

export function TagsClient({ tags: initialTags, rules: initialRules, token }: Props) {
  const router = useRouter();
  const { toast } = useToast();
  const api = createApiClient(token);

  const [tags, setTags] = useState<Tag[]>(initialTags);
  const [rules, setRules] = useState<TagRule[]>(initialRules);

  // Tag dialog state
  const [tagDialogOpen, setTagDialogOpen] = useState(false);
  const [newTagType, setNewTagType] = useState<TagType>("feature");
  const [newTagName, setNewTagName] = useState("");
  const [newTagColor, setNewTagColor] = useState("#6366f1");
  const [tagError, setTagError] = useState("");
  const [tagSubmitting, setTagSubmitting] = useState(false);

  // Rule dialog state
  const [ruleDialogOpen, setRuleDialogOpen] = useState(false);
  const [ruleTagId, setRuleTagId] = useState("");
  const [ruleMatchType, setRuleMatchType] = useState<MatchType>("substring");
  const [rulePattern, setRulePattern] = useState("");
  const [rulePriority, setRulePriority] = useState(100);
  const [ruleError, setRuleError] = useState("");
  const [ruleSubmitting, setRuleSubmitting] = useState(false);

  // Preview state
  const [previewMatches, setPreviewMatches] = useState<PreviewMatch[] | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);

  // Delete confirm
  const [deleteTagTarget, setDeleteTagTarget] = useState<Tag | null>(null);
  const [deleteRuleTarget, setDeleteRuleTarget] = useState<TagRule | null>(null);
  const [deleting, setDeleting] = useState(false);

  function openTagDialog() {
    setNewTagType("feature");
    setNewTagName("");
    setNewTagColor("#6366f1");
    setTagError("");
    setTagDialogOpen(true);
  }

  function openRuleDialog() {
    setRuleTagId(tags.length > 0 ? (tags[0]?.id ?? "") : "");
    setRuleMatchType("substring");
    setRulePattern("");
    setRulePriority(100);
    setRuleError("");
    setPreviewMatches(null);
    setRuleDialogOpen(true);
  }

  async function handleCreateTag(e: React.FormEvent) {
    e.preventDefault();
    setTagError("");
    setTagSubmitting(true);
    try {
      const created = await api.post<Tag>("/tags", {
        type: newTagType,
        name: newTagName.trim(),
        color: newTagColor,
      });
      setTags((prev) => [...prev, created]);
      setTagDialogOpen(false);
      router.refresh();
    } catch (err: unknown) {
      setTagError(err instanceof Error ? err.message : "Failed to create tag");
    } finally {
      setTagSubmitting(false);
    }
  }

  async function handleDeleteTag() {
    if (!deleteTagTarget) return;
    setDeleting(true);
    try {
      await api.delete(`/tags/${deleteTagTarget.id}`);
      setTags((prev) => prev.filter((t) => t.id !== deleteTagTarget.id));
      setRules((prev) => prev.filter((r) => r.tag_id !== deleteTagTarget.id));
      router.refresh();
    } catch (err: unknown) {
      toast({
        title: "Failed to delete tag",
        description: err instanceof Error ? err.message : "Please try again.",
        variant: "destructive",
      });
    } finally {
      setDeleting(false);
      setDeleteTagTarget(null);
    }
  }

  async function handleCreateRule(e: React.FormEvent) {
    e.preventDefault();
    setRuleError("");
    if (!ruleTagId) {
      setRuleError("Select a tag first");
      return;
    }
    setRuleSubmitting(true);
    try {
      const created = await api.post<TagRule>("/tag-rules", {
        tag_id: ruleTagId,
        match_type: ruleMatchType,
        match_pattern: rulePattern.trim(),
        priority: rulePriority,
        enabled: true,
      });
      setRules((prev) =>
        [...prev, created].sort((a, b) => a.priority - b.priority)
      );
      setRuleDialogOpen(false);
      setPreviewMatches(null);
      router.refresh();
    } catch (err: unknown) {
      setRuleError(err instanceof Error ? err.message : "Failed to create rule");
    } finally {
      setRuleSubmitting(false);
    }
  }

  async function handleDeleteRule() {
    if (!deleteRuleTarget) return;
    setDeleting(true);
    try {
      await api.delete(`/tag-rules/${deleteRuleTarget.id}`);
      setRules((prev) => prev.filter((r) => r.id !== deleteRuleTarget.id));
      router.refresh();
    } catch (err: unknown) {
      toast({
        title: "Failed to delete rule",
        description: err instanceof Error ? err.message : "Please try again.",
        variant: "destructive",
      });
    } finally {
      setDeleting(false);
      setDeleteRuleTarget(null);
    }
  }

  async function handlePreview() {
    if (!rulePattern.trim()) return;
    setPreviewLoading(true);
    setPreviewMatches(null);
    try {
      const matches = await api.post<PreviewMatch[]>("/tag-rules/preview", {
        match_type: ruleMatchType,
        match_pattern: rulePattern.trim(),
      });
      setPreviewMatches(matches);
    } catch {
      setPreviewMatches([]);
    } finally {
      setPreviewLoading(false);
    }
  }

  return (
    <div className="space-y-10">
      {/* ── Tags section ──────────────────────────────────────────────────── */}
      <section className="space-y-4">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 className="text-base font-semibold text-foreground">Tags</h2>
            <p className="mt-0.5 text-sm text-muted-foreground">
              Categorize spend by feature, team, customer, or environment.
            </p>
          </div>
          <Button size="sm" onClick={openTagDialog} className="gap-1.5 shrink-0">
            <Plus className="h-4 w-4" />
            New Tag
          </Button>
        </div>

        {tags.length === 0 ? (
          <EmptyState
            icon={TagIcon}
            title="No tags yet"
            description="Create a tag and add rules to automatically attribute spend to features, teams, or customers."
            action={{ label: "Create tag", onClick: openTagDialog }}
          />
        ) : (
          <div className="rounded-xl border border-border/60 bg-card overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border/60 bg-muted/40 text-left text-xs font-medium uppercase tracking-wide text-muted-foreground">
                  <th className="px-4 py-3">Name</th>
                  <th className="px-4 py-3">Type</th>
                  <th className="px-4 py-3">Color</th>
                  <th className="px-4 py-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/40">
                {tags.map((tag) => (
                  <tr key={tag.id} className="hover:bg-muted/30 transition-colors duration-150">
                    <td className="px-4 py-3 font-medium text-foreground">{tag.name}</td>
                    <td className="px-4 py-3">
                      <span
                        className={`inline-flex items-center rounded border px-1.5 py-0.5 text-xs font-medium ${TAG_TYPE_COLORS[tag.type]}`}
                      >
                        {TAG_TYPE_LABELS[tag.type]}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      {tag.color ? (
                        <span
                          className="inline-block h-4 w-4 rounded-full border border-border/40 shadow-sm"
                          style={{ backgroundColor: tag.color }}
                          title={tag.color}
                        />
                      ) : (
                        <span className="text-muted-foreground">—</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <button
                        onClick={() => setDeleteTagTarget(tag)}
                        className="inline-flex items-center gap-1 text-xs text-destructive hover:text-destructive/80 transition-colors duration-150 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring rounded"
                        aria-label={`Delete tag ${tag.name}`}
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                        Delete
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <Separator />

      {/* ── Tag Rules section ─────────────────────────────────────────────── */}
      <section className="space-y-4">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 className="text-base font-semibold text-foreground">Tag Rules</h2>
            <p className="mt-0.5 text-sm text-muted-foreground">
              Auto-tag usage events by matching the API key label. Lower priority
              number = evaluated first.
            </p>
          </div>
          <Button
            size="sm"
            onClick={openRuleDialog}
            disabled={tags.length === 0}
            title={tags.length === 0 ? "Create a tag first" : undefined}
            className="gap-1.5 shrink-0"
          >
            <Plus className="h-4 w-4" />
            New Rule
          </Button>
        </div>

        {rules.length === 0 ? (
          <EmptyState
            icon={Layers}
            title="No tag rules yet"
            description={
              tags.length > 0
                ? "Add a rule to start auto-tagging usage events based on patterns."
                : "Create a tag first, then add rules to auto-tag your usage."
            }
            action={
              tags.length > 0
                ? { label: "Add rule", onClick: openRuleDialog }
                : undefined
            }
          />
        ) : (
          <div className="rounded-xl border border-border/60 bg-card overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border/60 bg-muted/40 text-left text-xs font-medium uppercase tracking-wide text-muted-foreground">
                  <th className="px-4 py-3 w-20">Priority</th>
                  <th className="px-4 py-3">Tag</th>
                  <th className="px-4 py-3 w-24">Match</th>
                  <th className="px-4 py-3">Pattern</th>
                  <th className="px-4 py-3 w-12 text-center">On</th>
                  <th className="px-4 py-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/40">
                {rules.map((rule) => {
                  const linkedTag = tags.find((t) => t.id === rule.tag_id);
                  const tagInfo =
                    rule.tags ??
                    (linkedTag
                      ? { type: linkedTag.type, name: linkedTag.name }
                      : null);
                  return (
                    <tr
                      key={rule.id}
                      className="hover:bg-muted/30 transition-colors duration-150"
                    >
                      <td className="px-4 py-3 text-mono text-muted-foreground">
                        {rule.priority}
                      </td>
                      <td className="px-4 py-3">
                        {tagInfo ? (
                          <div className="flex items-center gap-1.5">
                            <span className="font-medium text-foreground">
                              {tagInfo.name}
                            </span>
                            <span
                              className={`inline-flex items-center rounded border px-1.5 py-0.5 text-xs font-medium ${
                                TAG_TYPE_COLORS[tagInfo.type as TagType] ??
                                "bg-muted text-muted-foreground border-border"
                              }`}
                            >
                              {TAG_TYPE_LABELS[tagInfo.type as TagType] ??
                                tagInfo.type}
                            </span>
                          </div>
                        ) : (
                          <span className="text-muted-foreground">—</span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-xs text-muted-foreground">
                        {MATCH_TYPE_LABELS[rule.match_type]}
                      </td>
                      <td className="px-4 py-3">
                        <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-xs text-foreground">
                          {rule.match_pattern}
                        </code>
                      </td>
                      <td className="px-4 py-3 text-center">
                        {rule.enabled ? (
                          <span className="text-success text-xs font-medium">✓</span>
                        ) : (
                          <span className="text-muted-foreground text-xs">—</span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-right">
                        <button
                          onClick={() => setDeleteRuleTarget(rule)}
                          className="inline-flex items-center gap-1 text-xs text-destructive hover:text-destructive/80 transition-colors duration-150 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring rounded"
                          aria-label="Delete rule"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                          Delete
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* ── Create Tag dialog ─────────────────────────────────────────────── */}
      <Dialog
        open={tagDialogOpen}
        onOpenChange={(v) => {
          if (!v && !tagSubmitting) setTagDialogOpen(false);
        }}
      >
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Create Tag</DialogTitle>
            <DialogDescription>
              Tags categorize your LLM spend for cost attribution and reporting.
            </DialogDescription>
          </DialogHeader>

          <form onSubmit={handleCreateTag} className="space-y-4 pt-1">
            <div className="space-y-1.5">
              <Label htmlFor="tagType">Type</Label>
              <Select
                value={newTagType}
                onValueChange={(v) => setNewTagType(v as TagType)}
                disabled={tagSubmitting}
              >
                <SelectTrigger id="tagType">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {(["feature", "team", "customer", "env"] as TagType[]).map(
                    (t) => (
                      <SelectItem key={t} value={t}>
                        {TAG_TYPE_LABELS[t]}
                      </SelectItem>
                    )
                  )}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="tagName">Name</Label>
              <Input
                id="tagName"
                placeholder="e.g. chat-service"
                required
                maxLength={64}
                value={newTagName}
                onChange={(e) => setNewTagName(e.target.value)}
                disabled={tagSubmitting}
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="tagColor">Color</Label>
              <div className="flex items-center gap-3">
                <input
                  id="tagColor"
                  type="color"
                  value={newTagColor}
                  onChange={(e) => setNewTagColor(e.target.value)}
                  className="h-9 w-16 cursor-pointer rounded-md border border-input bg-background p-1"
                />
                <span className="text-mono text-xs text-muted-foreground">
                  {newTagColor}
                </span>
              </div>
            </div>

            {tagError && (
              <p className="text-sm text-destructive">{tagError}</p>
            )}

            <DialogFooter className="pt-2">
              <Button
                type="button"
                variant="outline"
                onClick={() => setTagDialogOpen(false)}
                disabled={tagSubmitting}
              >
                Cancel
              </Button>
              <Button
                type="submit"
                disabled={tagSubmitting || !newTagName.trim()}
              >
                {tagSubmitting ? "Creating…" : "Create Tag"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* ── Create Rule dialog ────────────────────────────────────────────── */}
      <Dialog
        open={ruleDialogOpen}
        onOpenChange={(v) => {
          if (!v && !ruleSubmitting) {
            setRuleDialogOpen(false);
            setPreviewMatches(null);
          }
        }}
      >
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>Create Tag Rule</DialogTitle>
            <DialogDescription>
              Auto-tag usage events by matching the API key label. Lower priority
              = evaluated first.
            </DialogDescription>
          </DialogHeader>

          <form onSubmit={handleCreateRule} className="space-y-4 pt-1">
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-1.5">
                <Label htmlFor="ruleTag">Tag</Label>
                <Select
                  value={ruleTagId}
                  onValueChange={setRuleTagId}
                  disabled={ruleSubmitting}
                  required
                >
                  <SelectTrigger id="ruleTag">
                    <SelectValue placeholder="Select a tag…" />
                  </SelectTrigger>
                  <SelectContent>
                    {tags.map((t) => (
                      <SelectItem key={t.id} value={t.id}>
                        {t.name}{" "}
                        <span className="text-muted-foreground">
                          ({TAG_TYPE_LABELS[t.type]})
                        </span>
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="ruleMatchType">Match type</Label>
                <Select
                  value={ruleMatchType}
                  onValueChange={(v) => setRuleMatchType(v as MatchType)}
                  disabled={ruleSubmitting}
                >
                  <SelectTrigger id="ruleMatchType">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="substring">Substring</SelectItem>
                    <SelectItem value="exact">Exact</SelectItem>
                    <SelectItem value="regex">Regex</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="rulePattern">Pattern</Label>
              <Input
                id="rulePattern"
                value={rulePattern}
                onChange={(e) => setRulePattern(e.target.value)}
                placeholder={
                  ruleMatchType === "regex" ? "e.g. ^prod-" : "e.g. prod"
                }
                required
                className="font-mono"
                disabled={ruleSubmitting}
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="rulePriority">Priority</Label>
              <Input
                id="rulePriority"
                type="number"
                value={rulePriority}
                onChange={(e) => setRulePriority(Number(e.target.value))}
                min={1}
                max={9999}
                className="w-28"
                disabled={ruleSubmitting}
              />
              <p className="text-xs text-muted-foreground">
                Lower number = evaluated first. Default: 100.
              </p>
            </div>

            {/* Pattern preview */}
            <div className="space-y-2">
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={handlePreview}
                disabled={!rulePattern.trim() || previewLoading}
                className="gap-1.5"
              >
                {previewLoading ? "Checking…" : "Preview matches"}
              </Button>

              {previewMatches !== null && (
                <div className="rounded-lg border border-border/60 bg-muted/30 p-3 text-sm">
                  {previewMatches.length === 0 ? (
                    <span className="text-muted-foreground text-xs">
                      No matches found in recent usage events.
                    </span>
                  ) : (
                    <div className="space-y-1">
                      <p className="text-xs font-medium text-muted-foreground">
                        {previewMatches.length} match
                        {previewMatches.length !== 1 ? "es" : ""} (up to 20
                        shown)
                      </p>
                      {previewMatches.map((m, i) => (
                        <div key={i} className="font-mono text-xs">
                          <span className="text-success">
                            {m.api_key_label || "(empty)"}
                          </span>
                          <span className="ml-2 text-muted-foreground">
                            {m.provider} / {m.model}
                          </span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>

            {ruleError && (
              <p className="text-sm text-destructive">{ruleError}</p>
            )}

            <DialogFooter className="pt-2">
              <Button
                type="button"
                variant="outline"
                onClick={() => {
                  setRuleDialogOpen(false);
                  setPreviewMatches(null);
                }}
                disabled={ruleSubmitting}
              >
                Cancel
              </Button>
              <Button
                type="submit"
                disabled={ruleSubmitting || !rulePattern.trim() || !ruleTagId}
              >
                {ruleSubmitting ? "Creating…" : "Create Rule"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* ── Delete confirm dialogs ────────────────────────────────────────── */}
      <ConfirmDialog
        open={deleteTagTarget !== null}
        onClose={() => setDeleteTagTarget(null)}
        onConfirm={handleDeleteTag}
        title="Delete tag"
        description={`Deleting "${deleteTagTarget?.name}" will also remove all tag rules associated with it. This cannot be undone.`}
        confirmLabel="Delete tag"
        variant="destructive"
        isLoading={deleting}
      />

      <ConfirmDialog
        open={deleteRuleTarget !== null}
        onClose={() => setDeleteRuleTarget(null)}
        onConfirm={handleDeleteRule}
        title="Delete rule"
        description={`Delete the rule matching "${deleteRuleTarget?.match_pattern}"? This cannot be undone.`}
        confirmLabel="Delete rule"
        variant="destructive"
        isLoading={deleting}
      />
    </div>
  );
}
