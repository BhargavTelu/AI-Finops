"use client";

import { useState, useTransition } from "react";
import {
  Wallet,
  Plus,
  Trash2,
  AlertTriangle,
  AlertCircle,
  Pencil,
  CheckCircle2,
} from "lucide-react";
import { useAuth } from "@clerk/nextjs";

import { createApiClient } from "@/lib/api-client";
import type { BudgetRead, BudgetScopeType } from "@/lib/types";
import { cn } from "@/lib/utils";
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
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Separator } from "@/components/ui/separator";
import { PageHeader } from "@/components/page-header";
import { EmptyState } from "@/components/empty-state";
import { ConfirmDialog } from "@/components/confirm-dialog";
import { StaggerGrid, StaggerItem } from "@/components/motion-wrapper";
import { useToast } from "@/hooks/use-toast";

// ── Scope helpers ─────────────────────────────────────────────────────────────

const SCOPE_LABELS: Record<BudgetScopeType, string> = {
  global: "Global (all spend)",
  provider: "Provider",
  model: "Model",
  feature_tag: "Feature tag",
  team_tag: "Team tag",
  customer_tag: "Customer tag",
  env_tag: "Environment tag",
};

const SCOPE_VALUE_PLACEHOLDER: Partial<Record<BudgetScopeType, string>> = {
  provider: "e.g. openai",
  model: "e.g. gpt-4o",
  feature_tag: "e.g. chat",
  team_tag: "e.g. backend",
  customer_tag: "e.g. acme-corp",
  env_tag: "e.g. production",
};

function scopeLabel(budget: BudgetRead): string {
  if (budget.scope_type === "global") return "Global";
  return `${SCOPE_LABELS[budget.scope_type]}: ${budget.scope_value}`;
}

function fmtUSD(raw: string | number): string {
  const n = typeof raw === "string" ? parseFloat(raw) : raw;
  return `$${n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function daysLeftInMonth(): number {
  const now = new Date();
  const lastDay = new Date(now.getFullYear(), now.getMonth() + 1, 0).getDate();
  return lastDay - now.getDate();
}

// ── Budget status badge ───────────────────────────────────────────────────────

type BudgetStatus = "on-track" | "caution" | "over-budget";

function getBudgetStatus(budget: BudgetRead): BudgetStatus {
  if (budget.spent_pct >= 100) return "over-budget";
  if (budget.spent_pct >= budget.alert_at_pct) return "caution";
  return "on-track";
}

const STATUS_CONFIG: Record<
  BudgetStatus,
  { label: string; Icon: React.ElementType; className: string }
> = {
  "on-track": {
    label: "On Track",
    Icon: CheckCircle2,
    className: "bg-success-subtle text-success border-success/20",
  },
  caution: {
    label: "Caution",
    Icon: AlertTriangle,
    className: "bg-warning-subtle text-warning border-warning/20",
  },
  "over-budget": {
    label: "Over Budget",
    Icon: AlertCircle,
    className: "bg-critical-subtle text-critical border-critical/20",
  },
};

function BudgetStatusBadge({ budget }: { budget: BudgetRead }) {
  const status = getBudgetStatus(budget);
  const { label, Icon, className } = STATUS_CONFIG[status];
  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium",
        className
      )}
    >
      <Icon className="h-3 w-3" />
      {label}
    </span>
  );
}

// ── Spend progress bar ────────────────────────────────────────────────────────

function SpendBar({ pct, alertPct }: { pct: number; alertPct: number }) {
  const capped = Math.min(pct, 100);
  const trackColor =
    pct >= 100
      ? "bg-critical"
      : pct >= alertPct
      ? "bg-warning"
      : "bg-success";

  return (
    <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
      <div
        className={cn("h-full rounded-full transition-all duration-500", trackColor)}
        style={{ width: `${capped}%` }}
      />
    </div>
  );
}

// ── Shared form ───────────────────────────────────────────────────────────────

interface BudgetFormState {
  scope_type: BudgetScopeType;
  scope_value: string;
  monthly_limit: string;
  alert_at_pct: string;
}

const FORM_DEFAULTS: BudgetFormState = {
  scope_type: "global",
  scope_value: "",
  monthly_limit: "",
  alert_at_pct: "80",
};

function validateForm(form: BudgetFormState): string | null {
  const limit = parseFloat(form.monthly_limit);
  if (isNaN(limit) || limit <= 0) return "Monthly limit must be a positive number.";
  const pct = parseInt(form.alert_at_pct, 10);
  if (isNaN(pct) || pct < 1 || pct > 99) return "Alert threshold must be between 1 and 99.";
  if (form.scope_type !== "global" && !form.scope_value.trim()) {
    return "Scope value is required for this scope type.";
  }
  return null;
}

function BudgetFormFields({
  form,
  onChange,
  scopeLocked = false,
}: {
  form: BudgetFormState;
  onChange: (updates: Partial<BudgetFormState>) => void;
  scopeLocked?: boolean;
}) {
  const needsValue = form.scope_type !== "global";

  return (
    <>
      <div className="space-y-1.5">
        <Label htmlFor="budget-scope-type">Scope</Label>
        <Select
          value={form.scope_type}
          onValueChange={(v) =>
            onChange({ scope_type: v as BudgetScopeType, scope_value: "" })
          }
          disabled={scopeLocked}
        >
          <SelectTrigger id="budget-scope-type">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {(Object.keys(SCOPE_LABELS) as BudgetScopeType[]).map((s) => (
              <SelectItem key={s} value={s}>
                {SCOPE_LABELS[s]}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {scopeLocked && (
          <p className="text-xs text-muted-foreground">
            Scope cannot be changed after creation.
          </p>
        )}
      </div>

      {needsValue && (
        <div className="space-y-1.5">
          <Label htmlFor="budget-scope-value">Scope value</Label>
          <Input
            id="budget-scope-value"
            value={form.scope_value}
            onChange={(e) => onChange({ scope_value: e.target.value })}
            placeholder={SCOPE_VALUE_PLACEHOLDER[form.scope_type] ?? ""}
            autoComplete="off"
            disabled={scopeLocked}
          />
        </div>
      )}

      <div className="space-y-1.5">
        <Label htmlFor="budget-monthly-limit">Monthly limit (USD)</Label>
        <Input
          id="budget-monthly-limit"
          type="number"
          min="0.01"
          step="0.01"
          value={form.monthly_limit}
          onChange={(e) => onChange({ monthly_limit: e.target.value })}
          placeholder="1000.00"
        />
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="budget-alert-pct">Alert threshold (%)</Label>
        <Input
          id="budget-alert-pct"
          type="number"
          min="1"
          max="99"
          value={form.alert_at_pct}
          onChange={(e) => onChange({ alert_at_pct: e.target.value })}
        />
        <p className="text-xs text-muted-foreground">
          You&apos;ll receive an email at this threshold and again at 100%.
        </p>
      </div>
    </>
  );
}

// ── Budget card ───────────────────────────────────────────────────────────────

function BudgetCard({
  budget,
  onUpdated,
  onDeleted,
}: {
  budget: BudgetRead;
  onUpdated: (budget: BudgetRead) => void;
  onDeleted: (id: string) => void;
}) {
  const { getToken } = useAuth();
  const { toast } = useToast();
  const [editOpen, setEditOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [isPendingDelete, startDelete] = useTransition();
  const [isPendingEdit, startEdit] = useTransition();
  const [editForm, setEditForm] = useState<BudgetFormState>({
    scope_type: budget.scope_type,
    scope_value: budget.scope_value ?? "",
    monthly_limit: budget.monthly_limit,
    alert_at_pct: String(budget.alert_at_pct),
  });
  const [editError, setEditError] = useState<string | null>(null);

  const remaining =
    parseFloat(budget.monthly_limit) - parseFloat(budget.current_spend_mtd);
  const daysLeft = daysLeftInMonth();
  const isOver = budget.spent_pct >= 100;

  function handleDelete() {
    startDelete(async () => {
      try {
        const token = await getToken();
        const api = createApiClient(token!);
        await api.delete(`/budgets/${budget.id}`);
        onDeleted(budget.id);
      } catch {
        setDeleteOpen(false);
      }
    });
  }

  function handleEditSubmit(e: React.FormEvent) {
    e.preventDefault();
    setEditError(null);
    const err = validateForm(editForm);
    if (err) {
      setEditError(err);
      return;
    }
    startEdit(async () => {
      try {
        const token = await getToken();
        const api = createApiClient(token!);
        const updated = await api.patch<BudgetRead>(`/budgets/${budget.id}`, {
          monthly_limit: parseFloat(editForm.monthly_limit),
          alert_at_pct: parseInt(editForm.alert_at_pct, 10),
        });
        onUpdated(updated);
        setEditOpen(false);
        toast({ title: "Budget updated", description: "Changes have been saved." });
      } catch (err) {
        setEditError(
          err instanceof Error ? err.message : "Failed to update budget."
        );
      }
    });
  }

  return (
    <>
      <div
        className={cn(
          "flex flex-col rounded-xl border bg-card shadow-card transition-shadow duration-200 hover:shadow-card-hover",
          isOver && "border-critical/30"
        )}
      >
        {/* Card body */}
        <div className="flex flex-col gap-4 p-6">
          {/* Header: name + status badge */}
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <p className="truncate text-base font-semibold text-foreground">
                {scopeLabel(budget)}
              </p>
              <p className="mt-0.5 text-xs text-muted-foreground">
                Alert at {budget.alert_at_pct}%
                {budget.hard_cap ? " · Hard cap on" : ""}
              </p>
            </div>
            <BudgetStatusBadge budget={budget} />
          </div>

          {/* Spend numbers */}
          <div>
            <p
              className={cn(
                "text-2xl font-bold text-mono",
                isOver ? "text-critical" : "text-foreground"
              )}
            >
              {fmtUSD(budget.current_spend_mtd)}
            </p>
            <p className="mt-0.5 text-sm text-muted-foreground">
              of {fmtUSD(budget.monthly_limit)} monthly limit
            </p>
          </div>

          {/* Progress bar + percentage */}
          <div className="space-y-1.5">
            <SpendBar pct={budget.spent_pct} alertPct={budget.alert_at_pct} />
            <div className="flex items-center justify-between">
              <p className="text-xs text-muted-foreground">
                {remaining >= 0
                  ? `${fmtUSD(remaining)} remaining`
                  : `${fmtUSD(Math.abs(remaining))} over limit`}
              </p>
              <p
                className={cn(
                  "text-xs font-semibold tabular-nums",
                  isOver
                    ? "text-critical"
                    : budget.spent_pct >= budget.alert_at_pct
                    ? "text-warning"
                    : "text-muted-foreground"
                )}
              >
                {budget.spent_pct}%
              </p>
            </div>
          </div>

          {/* Days left — urgent when ≤5 days remain and budget is not on track */}
          <p
            className={cn(
              "text-xs",
              daysLeft <= 5 && getBudgetStatus(budget) !== "on-track"
                ? "font-medium text-warning"
                : "text-muted-foreground"
            )}
          >
            {daysLeft === 0
              ? "Last day of the month"
              : `${daysLeft} day${daysLeft !== 1 ? "s" : ""} left this month`}
          </p>
        </div>

        {/* Card footer */}
        <Separator />
        <div className="flex items-center justify-between px-4 py-3">
          <Button
            size="sm"
            variant="ghost"
            className="h-8 gap-1.5 text-muted-foreground hover:text-foreground"
            onClick={() => setEditOpen(true)}
          >
            <Pencil className="h-3.5 w-3.5" />
            Edit
          </Button>
          <Button
            size="sm"
            variant="ghost"
            className="h-8 gap-1.5 text-muted-foreground hover:text-destructive"
            onClick={() => setDeleteOpen(true)}
          >
            <Trash2 className="h-3.5 w-3.5" />
            Delete
          </Button>
        </div>
      </div>

      {/* Edit dialog */}
      <Dialog
        open={editOpen}
        onOpenChange={(v) => {
          setEditOpen(v);
          if (!v) setEditError(null);
        }}
      >
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Edit budget</DialogTitle>
          </DialogHeader>
          <form onSubmit={handleEditSubmit} className="space-y-4 pt-2">
            <BudgetFormFields
              form={editForm}
              onChange={(updates) =>
                setEditForm((f) => ({ ...f, ...updates }))
              }
              scopeLocked
            />
            {editError && (
              <p className="flex items-center gap-1.5 text-sm text-destructive">
                <AlertTriangle className="h-4 w-4 shrink-0" />
                {editError}
              </p>
            )}
            <div className="flex justify-end gap-2 pt-1">
              <Button
                type="button"
                variant="ghost"
                onClick={() => setEditOpen(false)}
              >
                Cancel
              </Button>
              <Button type="submit" disabled={isPendingEdit}>
                {isPendingEdit ? "Saving…" : "Save changes"}
              </Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>

      {/* Delete confirmation */}
      <ConfirmDialog
        open={deleteOpen}
        onClose={() => setDeleteOpen(false)}
        onConfirm={handleDelete}
        title="Delete budget"
        description={`This will permanently delete the "${scopeLabel(budget)}" budget. Email alerts for this scope will stop immediately.`}
        confirmLabel="Delete budget"
        variant="destructive"
        isLoading={isPendingDelete}
      />
    </>
  );
}

// ── Create budget dialog ──────────────────────────────────────────────────────

function CreateBudgetDialog({
  open,
  onOpenChange,
  onCreated,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreated: (budget: BudgetRead) => void;
}) {
  const { getToken } = useAuth();
  const { toast } = useToast();
  const [form, setForm] = useState<BudgetFormState>(FORM_DEFAULTS);
  const [error, setError] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  function reset() {
    setForm(FORM_DEFAULTS);
    setError(null);
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    const err = validateForm(form);
    if (err) {
      setError(err);
      return;
    }
    startTransition(async () => {
      try {
        const token = await getToken();
        const api = createApiClient(token!);
        const created = await api.post<BudgetRead>("/budgets", {
          scope_type: form.scope_type,
          scope_value:
            form.scope_type !== "global" ? form.scope_value.trim() : null,
          monthly_limit: parseFloat(form.monthly_limit),
          alert_at_pct: parseInt(form.alert_at_pct, 10),
          hard_cap: false,
        });
        onCreated(created);
        onOpenChange(false);
        reset();
        toast({ title: "Budget created", description: "Your new budget is now active." });
      } catch (err) {
        setError(
          err instanceof Error ? err.message : "Failed to create budget."
        );
      }
    });
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(v) => {
        onOpenChange(v);
        if (!v) reset();
      }}
    >
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>New budget</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4 pt-2">
          <BudgetFormFields
            form={form}
            onChange={(updates) => setForm((f) => ({ ...f, ...updates }))}
          />
          {error && (
            <p className="flex items-center gap-1.5 text-sm text-destructive">
              <AlertTriangle className="h-4 w-4 shrink-0" />
              {error}
            </p>
          )}
          <div className="flex justify-end gap-2 pt-1">
            <Button
              type="button"
              variant="ghost"
              onClick={() => onOpenChange(false)}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={isPending}>
              {isPending ? "Creating…" : "Create budget"}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}

// ── Root client component ─────────────────────────────────────────────────────

export function BudgetsClient({
  initialBudgets,
}: {
  initialBudgets: BudgetRead[];
}) {
  const [budgets, setBudgets] = useState<BudgetRead[]>(initialBudgets);
  const [createOpen, setCreateOpen] = useState(false);

  function handleCreated(budget: BudgetRead) {
    setBudgets((prev) => [budget, ...prev]);
  }

  function handleUpdated(updated: BudgetRead) {
    setBudgets((prev) => prev.map((b) => (b.id === updated.id ? updated : b)));
  }

  function handleDeleted(id: string) {
    setBudgets((prev) => prev.filter((b) => b.id !== id));
  }

  const overBudgetCount = budgets.filter((b) => b.spent_pct >= 100).length;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Budgets"
        description="Monthly spend limits with email alerts at your threshold and at 100%."
        actions={
          <Button
            size="sm"
            className="gap-1.5"
            onClick={() => setCreateOpen(true)}
          >
            <Plus className="h-4 w-4" />
            New budget
          </Button>
        }
      />

      {/* Over-budget critical banner */}
      {overBudgetCount > 0 && (
        <div className="flex items-center gap-3 rounded-lg border border-critical/30 bg-critical-subtle px-4 py-3 text-sm text-critical">
          <AlertCircle className="h-4 w-4 shrink-0" />
          <p>
            <span className="font-semibold">
              {overBudgetCount} budget{overBudgetCount > 1 ? "s" : ""}
            </span>{" "}
            exceeded this month — review your spend or raise the limit.
          </p>
        </div>
      )}

      {budgets.length === 0 ? (
        <EmptyState
          icon={Wallet}
          title="No budgets configured"
          description="Set monthly spend limits per provider, model, or team. Get alerted before you overspend."
          action={{ label: "Create first budget", onClick: () => setCreateOpen(true) }}
        />
      ) : (
        <StaggerGrid className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          {budgets.map((budget) => (
            <StaggerItem key={budget.id}>
              <BudgetCard
                budget={budget}
                onUpdated={handleUpdated}
                onDeleted={handleDeleted}
              />
            </StaggerItem>
          ))}
        </StaggerGrid>
      )}

      <CreateBudgetDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        onCreated={handleCreated}
      />
    </div>
  );
}
