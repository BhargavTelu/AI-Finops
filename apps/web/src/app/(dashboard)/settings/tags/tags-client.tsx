"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

import { createApiClient } from "@/lib/api-client";
import type { MatchType, PreviewMatch, Tag, TagRule, TagType } from "@/lib/types";

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
  feature: "bg-blue-100 text-blue-800",
  team: "bg-purple-100 text-purple-800",
  customer: "bg-green-100 text-green-800",
  env: "bg-orange-100 text-orange-800",
};

const MATCH_TYPE_LABELS: Record<MatchType, string> = {
  exact: "exact",
  substring: "sub",
  regex: "regex",
};

export function TagsClient({ tags: initialTags, rules: initialRules, token }: Props) {
  const router = useRouter();
  const api = createApiClient(token);

  const [tags, setTags] = useState<Tag[]>(initialTags);
  const [rules, setRules] = useState<TagRule[]>(initialRules);

  // Tag form state
  const [showTagForm, setShowTagForm] = useState(false);
  const [newTagType, setNewTagType] = useState<TagType>("feature");
  const [newTagName, setNewTagName] = useState("");
  const [newTagColor, setNewTagColor] = useState("#6366f1");
  const [tagError, setTagError] = useState("");
  const [tagSubmitting, setTagSubmitting] = useState(false);

  // Rule form state
  const [showRuleForm, setShowRuleForm] = useState(false);
  const [ruleTagId, setRuleTagId] = useState("");
  const [ruleMatchType, setRuleMatchType] = useState<MatchType>("substring");
  const [rulePattern, setRulePattern] = useState("");
  const [rulePriority, setRulePriority] = useState(100);
  const [ruleError, setRuleError] = useState("");
  const [ruleSubmitting, setRuleSubmitting] = useState(false);

  // Preview state
  const [previewMatches, setPreviewMatches] = useState<PreviewMatch[] | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);

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
      setNewTagName("");
      setShowTagForm(false);
      router.refresh();
    } catch (err: unknown) {
      setTagError(err instanceof Error ? err.message : "Failed to create tag");
    } finally {
      setTagSubmitting(false);
    }
  }

  async function handleDeleteTag(tagId: string) {
    try {
      await api.delete(`/tags/${tagId}`);
      setTags((prev) => prev.filter((t) => t.id !== tagId));
      setRules((prev) => prev.filter((r) => r.tag_id !== tagId));
      router.refresh();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to delete tag");
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
      setRules((prev) => [...prev, created].sort((a, b) => a.priority - b.priority));
      setRulePattern("");
      setRulePriority(100);
      setPreviewMatches(null);
      setShowRuleForm(false);
      router.refresh();
    } catch (err: unknown) {
      setRuleError(err instanceof Error ? err.message : "Failed to create rule");
    } finally {
      setRuleSubmitting(false);
    }
  }

  async function handleDeleteRule(ruleId: string) {
    try {
      await api.delete(`/tag-rules/${ruleId}`);
      setRules((prev) => prev.filter((r) => r.id !== ruleId));
      router.refresh();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to delete rule");
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

  const hasNoData = tags.length === 0 && rules.length === 0;

  return (
    <div className="space-y-8">
      {/* ── Tags section ───────────────────────────────────────────────────── */}
      <section>
        <div className="mb-4 flex items-center justify-between">
          <div>
            <h2 className="text-lg font-semibold">Tags</h2>
            <p className="text-sm text-muted-foreground">
              Categorize spend by feature, team, customer, or environment.
            </p>
          </div>
          <button
            onClick={() => setShowTagForm((v) => !v)}
            className="rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground hover:bg-primary/90"
          >
            {showTagForm ? "Cancel" : "+ New Tag"}
          </button>
        </div>

        {showTagForm && (
          <form
            onSubmit={handleCreateTag}
            className="mb-4 rounded-md border p-4 space-y-3 bg-muted/30"
          >
            <div className="flex flex-wrap gap-3">
              <div className="flex flex-col gap-1">
                <label className="text-xs font-medium">Type</label>
                <select
                  value={newTagType}
                  onChange={(e) => setNewTagType(e.target.value as TagType)}
                  className="rounded border px-2 py-1 text-sm bg-background"
                >
                  {(["feature", "team", "customer", "env"] as TagType[]).map((t) => (
                    <option key={t} value={t}>{TAG_TYPE_LABELS[t]}</option>
                  ))}
                </select>
              </div>
              <div className="flex flex-col gap-1 flex-1 min-w-32">
                <label className="text-xs font-medium">Name</label>
                <input
                  type="text"
                  value={newTagName}
                  onChange={(e) => setNewTagName(e.target.value)}
                  placeholder="e.g. chat-service"
                  required
                  maxLength={64}
                  className="rounded border px-2 py-1 text-sm bg-background"
                />
              </div>
              <div className="flex flex-col gap-1">
                <label className="text-xs font-medium">Color</label>
                <input
                  type="color"
                  value={newTagColor}
                  onChange={(e) => setNewTagColor(e.target.value)}
                  className="h-8 w-16 rounded border cursor-pointer"
                />
              </div>
            </div>
            {tagError && <p className="text-sm text-destructive">{tagError}</p>}
            <button
              type="submit"
              disabled={tagSubmitting || !newTagName.trim()}
              className="rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
            >
              {tagSubmitting ? "Creating..." : "Create Tag"}
            </button>
          </form>
        )}

        {hasNoData && !showTagForm ? (
          <div className="rounded-md border border-dashed p-8 text-center text-sm text-muted-foreground">
            No tags yet. Create a tag and add rules to automatically attribute spend.
          </div>
        ) : tags.length === 0 && showTagForm ? null : (
          <div className="rounded-md border overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-muted/50">
                <tr>
                  <th className="px-4 py-2 text-left font-medium">Name</th>
                  <th className="px-4 py-2 text-left font-medium">Type</th>
                  <th className="px-4 py-2 text-left font-medium">Color</th>
                  <th className="px-4 py-2 text-right font-medium">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {tags.map((tag) => (
                  <tr key={tag.id} className="hover:bg-muted/20">
                    <td className="px-4 py-2 font-medium">{tag.name}</td>
                    <td className="px-4 py-2">
                      <span
                        className={`inline-block rounded px-1.5 py-0.5 text-xs font-medium ${TAG_TYPE_COLORS[tag.type]}`}
                      >
                        {TAG_TYPE_LABELS[tag.type]}
                      </span>
                    </td>
                    <td className="px-4 py-2">
                      {tag.color ? (
                        <span
                          className="inline-block h-4 w-4 rounded-full border"
                          style={{ backgroundColor: tag.color }}
                        />
                      ) : (
                        <span className="text-muted-foreground">—</span>
                      )}
                    </td>
                    <td className="px-4 py-2 text-right">
                      <button
                        onClick={() => handleDeleteTag(tag.id)}
                        className="text-destructive hover:underline text-xs"
                      >
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

      {/* ── Tag Rules section ───────────────────────────────────────────────── */}
      <section>
        <div className="mb-4 flex items-center justify-between">
          <div>
            <h2 className="text-lg font-semibold">Tag Rules</h2>
            <p className="text-sm text-muted-foreground">
              Auto-tag usage events by matching the API key label. Lower priority number = evaluated first.
            </p>
          </div>
          <button
            onClick={() => { setShowRuleForm((v) => !v); setPreviewMatches(null); }}
            className="rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground hover:bg-primary/90"
            disabled={tags.length === 0}
            title={tags.length === 0 ? "Create a tag first" : undefined}
          >
            {showRuleForm ? "Cancel" : "+ New Rule"}
          </button>
        </div>

        {showRuleForm && (
          <form
            onSubmit={handleCreateRule}
            className="mb-4 rounded-md border p-4 space-y-3 bg-muted/30"
          >
            <div className="flex flex-wrap gap-3">
              <div className="flex flex-col gap-1 flex-1 min-w-40">
                <label className="text-xs font-medium">Tag</label>
                <select
                  value={ruleTagId}
                  onChange={(e) => setRuleTagId(e.target.value)}
                  className="rounded border px-2 py-1 text-sm bg-background"
                  required
                >
                  <option value="">Select a tag...</option>
                  {tags.map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.name} ({TAG_TYPE_LABELS[t.type]})
                    </option>
                  ))}
                </select>
              </div>
              <div className="flex flex-col gap-1">
                <label className="text-xs font-medium">Match type</label>
                <select
                  value={ruleMatchType}
                  onChange={(e) => setRuleMatchType(e.target.value as MatchType)}
                  className="rounded border px-2 py-1 text-sm bg-background"
                >
                  <option value="substring">Substring</option>
                  <option value="exact">Exact</option>
                  <option value="regex">Regex</option>
                </select>
              </div>
              <div className="flex flex-col gap-1 flex-1 min-w-40">
                <label className="text-xs font-medium">Pattern</label>
                <input
                  type="text"
                  value={rulePattern}
                  onChange={(e) => setRulePattern(e.target.value)}
                  placeholder={ruleMatchType === "regex" ? "e.g. ^prod-" : "e.g. prod"}
                  required
                  className="rounded border px-2 py-1 text-sm bg-background font-mono"
                />
              </div>
              <div className="flex flex-col gap-1 w-24">
                <label className="text-xs font-medium">Priority</label>
                <input
                  type="number"
                  value={rulePriority}
                  onChange={(e) => setRulePriority(Number(e.target.value))}
                  min={1}
                  max={9999}
                  className="rounded border px-2 py-1 text-sm bg-background"
                />
              </div>
            </div>

            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={handlePreview}
                disabled={!rulePattern.trim() || previewLoading}
                className="rounded-md border px-3 py-1.5 text-sm hover:bg-muted disabled:opacity-50"
              >
                {previewLoading ? "Checking..." : "Preview"}
              </button>
              <span className="text-xs text-muted-foreground">
                Test this pattern against recent usage events
              </span>
            </div>

            {previewMatches !== null && (
              <div className="rounded border bg-background p-3 text-sm">
                {previewMatches.length === 0 ? (
                  <span className="text-muted-foreground">No matches in recent usage events</span>
                ) : (
                  <div className="space-y-1">
                    <p className="text-xs text-muted-foreground font-medium">
                      {previewMatches.length} match{previewMatches.length !== 1 ? "es" : ""} (up to 20 shown)
                    </p>
                    {previewMatches.map((m, i) => (
                      <div key={i} className="font-mono text-xs">
                        <span className="text-green-700">{m.api_key_label || "(empty)"}</span>
                        <span className="text-muted-foreground ml-2">
                          {m.provider} / {m.model}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {ruleError && <p className="text-sm text-destructive">{ruleError}</p>}
            <button
              type="submit"
              disabled={ruleSubmitting || !rulePattern.trim() || !ruleTagId}
              className="rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
            >
              {ruleSubmitting ? "Creating..." : "Create Rule"}
            </button>
          </form>
        )}

        {rules.length === 0 && !showRuleForm ? (
          <div className="rounded-md border border-dashed p-6 text-center text-sm text-muted-foreground">
            No tag rules yet.{tags.length > 0 ? " Add a rule to start auto-tagging usage." : ""}
          </div>
        ) : rules.length > 0 ? (
          <div className="rounded-md border overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-muted/50">
                <tr>
                  <th className="px-4 py-2 text-left font-medium w-20">Priority</th>
                  <th className="px-4 py-2 text-left font-medium">Tag</th>
                  <th className="px-4 py-2 text-left font-medium w-20">Match</th>
                  <th className="px-4 py-2 text-left font-medium">Pattern</th>
                  <th className="px-4 py-2 text-left font-medium w-12">On</th>
                  <th className="px-4 py-2 text-right font-medium">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {rules.map((rule) => {
                  const linkedTag = tags.find((t) => t.id === rule.tag_id);
                  const tagInfo = rule.tags ?? (linkedTag ? { type: linkedTag.type, name: linkedTag.name } : null);
                  return (
                    <tr key={rule.id} className="hover:bg-muted/20">
                      <td className="px-4 py-2 tabular-nums">{rule.priority}</td>
                      <td className="px-4 py-2">
                        {tagInfo ? (
                          <span>
                            {tagInfo.name}{" "}
                            <span
                              className={`inline-block rounded px-1 py-0.5 text-xs ${TAG_TYPE_COLORS[tagInfo.type as TagType] ?? "bg-gray-100 text-gray-800"}`}
                            >
                              {TAG_TYPE_LABELS[tagInfo.type as TagType] ?? tagInfo.type}
                            </span>
                          </span>
                        ) : (
                          <span className="text-muted-foreground">—</span>
                        )}
                      </td>
                      <td className="px-4 py-2 text-xs text-muted-foreground">
                        {MATCH_TYPE_LABELS[rule.match_type]}
                      </td>
                      <td className="px-4 py-2 font-mono text-xs">{rule.match_pattern}</td>
                      <td className="px-4 py-2">
                        {rule.enabled ? (
                          <span className="text-green-600">✓</span>
                        ) : (
                          <span className="text-muted-foreground">—</span>
                        )}
                      </td>
                      <td className="px-4 py-2 text-right">
                        <button
                          onClick={() => handleDeleteRule(rule.id)}
                          className="text-destructive hover:underline text-xs"
                        >
                          Delete
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : null}
      </section>
    </div>
  );
}
