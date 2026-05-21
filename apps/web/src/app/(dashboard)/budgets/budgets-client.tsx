"use client";

import { useState, useTransition } from "react";
import { Wallet, Plus, Trash2, AlertTriangle } from "lucide-react";
import { useAuth } from "@clerk/nextjs";
import { motion, AnimatePresence } from "framer-motion";

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
  DialogTrigger,
} from "@/components/ui/dialog";

// ── Scope helpers ───────────────────────────────────────────────────────────────

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

// ── Spend progress bar ─────────────────────────────────────────────────────────

function SpendBar({ pct }: { pct: number }) {
  const capped = Math.min(pct, 100);
  const color =
    pct >= 100
      ? "bg-red-500"
      : pct >= 80
      ? "bg-amber-400"
      : "bg-emerald-500";

  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-muted">
        <div
          className={cn("h-full rounded-full transition-all", color)}
          style={{ width: `${capped}%` }}
        />
      </div>
      <span
        className={cn(
          "w-10 text-right text-xs font-medium tabular-nums",
          pct >= 100 ? "text-red-500" : pct >= 80 ? "text-amber-500" : "text-muted-foreground"
        )}
      >
        {pct}%
      </span>
    </div>
  );
}

// ── Formatters ─────────────────────────────────────────────────────────────────

function fmtUSD(raw: string | number): string {
  const n = typeof raw === "string" ? parseFloat(raw) : raw;
  return `$${n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

// ── Add budget dialog ──────────────────────────────────────────────────────────

interface AddBudgetFormState {
  scope_type: BudgetScopeType;
  scope_value: string;
  monthly_limit: string;
  alert_at_pct: string;
}

const FORM_DEFAULTS: AddBudgetFormState = {
  scope_type: "global",
  scope_value: "",
  monthly_limit: "",
  alert_at_pct: "80",
};

function AddBudgetDialog({ onCreated }: { onCreated: (budget: BudgetRead) => void }) {
  const { getToken } = useAuth();
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState<AddBudgetFormState>(FORM_DEFAULTS);
  const [error, setError] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  const needsValue = form.scope_type !== "global";

  function reset() {
    setForm(FORM_DEFAULTS);
    setError(null);
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);

    const limit = parseFloat(form.monthly_limit);
    if (isNaN(limit) || limit <= 0) {
      setError("Monthly limit must be a positive number.");
      return;
    }
    const pct = parseInt(form.alert_at_pct, 10);
    if (isNaN(pct) || pct < 1 || pct > 100) {
      setError("Alert threshold must be between 1 and 100.");
      return;
    }
    if (needsValue && !form.scope_value.trim()) {
      setError("Scope value is required for this scope type.");
      return;
    }

    startTransition(async () => {
      try {
        const token = await getToken();
        const api = createApiClient(token!);
        const created = await api.post<BudgetRead>("/budgets", {
          scope_type: form.scope_type,
          scope_value: needsValue ? form.scope_value.trim() : null,
          monthly_limit: limit,
          alert_at_pct: pct,
          hard_cap: false,
        });
        onCreated(created);
        setOpen(false);
        reset();
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to create budget.");
      }
    });
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(v) => {
        setOpen(v);
        if (!v) reset();
      }}
    >
      <DialogTrigger asChild>
        <Button size="sm" className="gap-1.5">
          <Plus className="h-4 w-4" />
          Add budget
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>New budget</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4 pt-2">
          <div className="space-y-1.5">
            <Label htmlFor="scope_type">Scope</Label>
            <Select
              value={form.scope_type}
              onValueChange={(v) =>
                setForm((f) => ({ ...f, scope_type: v as BudgetScopeType, scope_value: "" }))
              }
            >
              <SelectTrigger id="scope_type">
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
          </div>

          {needsValue && (
            <div className="space-y-1.5">
              <Label htmlFor="scope_value">Scope value</Label>
              <Input
                id="scope_value"
                value={form.scope_value}
                onChange={(e) => setForm((f) => ({ ...f, scope_value: e.target.value }))}
                placeholder={SCOPE_VALUE_PLACEHOLDER[form.scope_type] ?? ""}
                autoComplete="off"
              />
            </div>
          )}

          <div className="space-y-1.5">
            <Label htmlFor="monthly_limit">Monthly limit (USD)</Label>
            <Input
              id="monthly_limit"
              type="number"
              min="0.01"
              step="0.01"
              value={form.monthly_limit}
              onChange={(e) => setForm((f) => ({ ...f, monthly_limit: e.target.value }))}
              placeholder="1000.00"
            />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="alert_at_pct">Alert threshold (%)</Label>
            <Input
              id="alert_at_pct"
              type="number"
              min="1"
              max="100"
              value={form.alert_at_pct}
              onChange={(e) => setForm((f) => ({ ...f, alert_at_pct: e.target.value }))}
            />
            <p className="text-xs text-muted-foreground">
              You'll receive an email when spend reaches this % and again at 100%.
            </p>
          </div>

          {error && (
            <p className="flex items-center gap-1.5 text-sm text-red-500">
              <AlertTriangle className="h-4 w-4 shrink-0" />
              {error}
            </p>
          )}

          <div className="flex justify-end gap-2 pt-1">
            <Button type="button" variant="ghost" onClick={() => setOpen(false)}>
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

// ── Delete confirmation ────────────────────────────────────────────────────────

function DeleteButton({
  budget,
  onDeleted,
}: {
  budget: BudgetRead;
  onDeleted: (id: string) => void;
}) {
  const { getToken } = useAuth();
  const [isPending, startTransition] = useTransition();
  const [confirming, setConfirming] = useState(false);

  function handleDelete() {
    startTransition(async () => {
      try {
        const token = await getToken();
        const api = createApiClient(token!);
        await api.delete(`/budgets/${budget.id}`);
        onDeleted(budget.id);
      } catch {
        // keep confirming state — user can retry
      }
    });
  }

  if (confirming) {
    return (
      <div className="flex items-center gap-1.5">
        <span className="text-xs text-muted-foreground">Delete?</span>
        <Button
          size="sm"
          variant="destructive"
          className="h-7 px-2 text-xs"
          onClick={handleDelete}
          disabled={isPending}
        >
          {isPending ? "…" : "Yes"}
        </Button>
        <Button
          size="sm"
          variant="ghost"
          className="h-7 px-2 text-xs"
          onClick={() => setConfirming(false)}
        >
          No
        </Button>
      </div>
    );
  }

  return (
    <Button
      size="sm"
      variant="ghost"
      className="h-7 w-7 p-0 text-muted-foreground hover:text-red-500"
      onClick={() => setConfirming(true)}
      aria-label="Delete budget"
    >
      <Trash2 className="h-4 w-4" />
    </Button>
  );
}

// ── Budget row ─────────────────────────────────────────────────────────────────

function BudgetRow({
  budget,
  onDeleted,
}: {
  budget: BudgetRead;
  onDeleted: (id: string) => void;
}) {
  const isOver = budget.spent_pct >= 100;
  const isWarning = budget.spent_pct >= budget.alert_at_pct && !isOver;

  return (
    <motion.tr
      layout
      initial={{ opacity: 0, y: -8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -4 }}
      transition={{ duration: 0.2 }}
      className="border-b last:border-0"
    >
      {/* Scope */}
      <td className="px-4 py-3.5">
        <span className="text-sm font-medium">{scopeLabel(budget)}</span>
      </td>

      {/* Monthly limit */}
      <td className="px-4 py-3.5 text-sm tabular-nums">
        {fmtUSD(budget.monthly_limit)}
      </td>

      {/* MTD spend */}
      <td className="px-4 py-3.5 text-sm tabular-nums">
        <span
          className={cn(
            isOver ? "text-red-500 font-medium" : isWarning ? "text-amber-600" : ""
          )}
        >
          {fmtUSD(budget.current_spend_mtd)}
        </span>
      </td>

      {/* Progress bar */}
      <td className="px-4 py-3.5 min-w-[160px]">
        <SpendBar pct={budget.spent_pct} />
      </td>

      {/* Alert at */}
      <td className="px-4 py-3.5 text-sm text-muted-foreground">
        {budget.alert_at_pct}%
      </td>

      {/* Actions */}
      <td className="px-4 py-3.5 text-right">
        <DeleteButton budget={budget} onDeleted={onDeleted} />
      </td>
    </motion.tr>
  );
}

// ── Empty state ────────────────────────────────────────────────────────────────

function EmptyState({ onAddClicked }: { onAddClicked: () => void }) {
  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.97 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ duration: 0.25 }}
      className="flex min-h-[320px] flex-col items-center justify-center rounded-xl border border-dashed border-border bg-card/50 text-center"
    >
      <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-blue-50 dark:bg-blue-950/40">
        <Wallet className="h-7 w-7 text-blue-500" strokeWidth={1.5} />
      </div>
      <h2 className="text-base font-medium">No budgets configured</h2>
      <p className="mt-2 max-w-xs text-sm text-muted-foreground">
        Set monthly spend limits per provider, model, or team. Get emailed at your alert
        threshold and again at 100%.
      </p>
      <Button size="sm" className="mt-5 gap-1.5" onClick={onAddClicked}>
        <Plus className="h-4 w-4" />
        Set your first budget
      </Button>
    </motion.div>
  );
}

// ── Budget table ───────────────────────────────────────────────────────────────

const TABLE_HEADERS = ["Scope", "Monthly limit", "MTD spend", "Usage", "Alert at", ""];

function BudgetTable({
  budgets,
  onDeleted,
}: {
  budgets: BudgetRead[];
  onDeleted: (id: string) => void;
}) {
  return (
    <div className="overflow-hidden rounded-xl border">
      <table className="w-full text-left">
        <thead className="border-b bg-muted/40">
          <tr>
            {TABLE_HEADERS.map((h) => (
              <th
                key={h}
                className="px-4 py-3 text-xs font-medium uppercase tracking-wide text-muted-foreground"
              >
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          <AnimatePresence initial={false}>
            {budgets.map((b) => (
              <BudgetRow key={b.id} budget={b} onDeleted={onDeleted} />
            ))}
          </AnimatePresence>
        </tbody>
      </table>
    </div>
  );
}

// ── Root client component ──────────────────────────────────────────────────────

export function BudgetsClient({ initialBudgets }: { initialBudgets: BudgetRead[] }) {
  const [budgets, setBudgets] = useState<BudgetRead[]>(initialBudgets);
  const [dialogOpen, setDialogOpen] = useState(false);

  function handleCreated(budget: BudgetRead) {
    setBudgets((prev) => [budget, ...prev]);
  }

  function handleDeleted(id: string) {
    setBudgets((prev) => prev.filter((b) => b.id !== id));
  }

  const overCount = budgets.filter((b) => b.spent_pct >= 100).length;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        {overCount > 0 && (
          <p className="flex items-center gap-1.5 text-sm text-red-500">
            <AlertTriangle className="h-4 w-4 shrink-0" />
            {overCount} budget{overCount > 1 ? "s" : ""} exceeded this month
          </p>
        )}
        {overCount === 0 && <span />}

        {/* Dialog trigger wired to allow EmptyState to open it programmatically */}
        <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
          <DialogTrigger asChild>
            <Button size="sm" className="gap-1.5">
              <Plus className="h-4 w-4" />
              Add budget
            </Button>
          </DialogTrigger>
          <DialogContent className="sm:max-w-md">
            <DialogHeader>
              <DialogTitle>New budget</DialogTitle>
            </DialogHeader>
            <AddBudgetForm
              onCreated={(b) => {
                handleCreated(b);
                setDialogOpen(false);
              }}
            />
          </DialogContent>
        </Dialog>
      </div>

      {budgets.length === 0 ? (
        <EmptyState onAddClicked={() => setDialogOpen(true)} />
      ) : (
        <BudgetTable budgets={budgets} onDeleted={handleDeleted} />
      )}
    </div>
  );
}

// ── Form extracted for reuse in both dialog locations ──────────────────────────

function AddBudgetForm({ onCreated }: { onCreated: (budget: BudgetRead) => void }) {
  const { getToken } = useAuth();
  const [form, setForm] = useState<AddBudgetFormState>(FORM_DEFAULTS);
  const [error, setError] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  const needsValue = form.scope_type !== "global";

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);

    const limit = parseFloat(form.monthly_limit);
    if (isNaN(limit) || limit <= 0) {
      setError("Monthly limit must be a positive number.");
      return;
    }
    const pct = parseInt(form.alert_at_pct, 10);
    if (isNaN(pct) || pct < 1 || pct > 100) {
      setError("Alert threshold must be between 1 and 100.");
      return;
    }
    if (needsValue && !form.scope_value.trim()) {
      setError("Scope value is required for this scope type.");
      return;
    }

    startTransition(async () => {
      try {
        const token = await getToken();
        const api = createApiClient(token!);
        const created = await api.post<BudgetRead>("/budgets", {
          scope_type: form.scope_type,
          scope_value: needsValue ? form.scope_value.trim() : null,
          monthly_limit: limit,
          alert_at_pct: pct,
          hard_cap: false,
        });
        onCreated(created);
        setForm(FORM_DEFAULTS);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to create budget.");
      }
    });
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4 pt-2">
      <div className="space-y-1.5">
        <Label htmlFor="scope_type">Scope</Label>
        <Select
          value={form.scope_type}
          onValueChange={(v) =>
            setForm((f) => ({ ...f, scope_type: v as BudgetScopeType, scope_value: "" }))
          }
        >
          <SelectTrigger id="scope_type">
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
      </div>

      {needsValue && (
        <div className="space-y-1.5">
          <Label htmlFor="scope_value">Scope value</Label>
          <Input
            id="scope_value"
            value={form.scope_value}
            onChange={(e) => setForm((f) => ({ ...f, scope_value: e.target.value }))}
            placeholder={SCOPE_VALUE_PLACEHOLDER[form.scope_type] ?? ""}
            autoComplete="off"
          />
        </div>
      )}

      <div className="space-y-1.5">
        <Label htmlFor="monthly_limit">Monthly limit (USD)</Label>
        <Input
          id="monthly_limit"
          type="number"
          min="0.01"
          step="0.01"
          value={form.monthly_limit}
          onChange={(e) => setForm((f) => ({ ...f, monthly_limit: e.target.value }))}
          placeholder="1000.00"
        />
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="alert_at_pct">Alert threshold (%)</Label>
        <Input
          id="alert_at_pct"
          type="number"
          min="1"
          max="100"
          value={form.alert_at_pct}
          onChange={(e) => setForm((f) => ({ ...f, alert_at_pct: e.target.value }))}
        />
        <p className="text-xs text-muted-foreground">
          You'll receive an email at this threshold and again at 100%.
        </p>
      </div>

      {error && (
        <p className="flex items-center gap-1.5 text-sm text-red-500">
          <AlertTriangle className="h-4 w-4 shrink-0" />
          {error}
        </p>
      )}

      <div className="flex justify-end gap-2 pt-1">
        <Button type="submit" disabled={isPending}>
          {isPending ? "Creating…" : "Create budget"}
        </Button>
      </div>
    </form>
  );
}
