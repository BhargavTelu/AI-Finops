"use client";

import { useEffect, useState } from "react";
import type { Route } from "next";
import Link from "next/link";
import { ArrowRight, CheckCircle2, Circle, X } from "lucide-react";

import type { OnboardingStatus } from "@/lib/types";
import { cn } from "@/lib/utils";

const DISMISS_KEY = "spendops-activation-dismissed";

const STEPS: {
  key: keyof OnboardingStatus;
  label: string;
  description: string;
  href: Route;
}[] = [
  {
    key: "provider_connected",
    label: "Connect a provider",
    description: "Add an OpenAI or Anthropic Admin key",
    href: "/settings/integrations" as Route,
  },
  {
    key: "tag_rule_created",
    label: "Create a tag rule",
    description: "Attribute spend to features and teams",
    href: "/settings/tags" as Route,
  },
  {
    key: "slack_connected",
    label: "Connect Slack",
    description: "Daily digests and real-time alerts",
    href: "/settings/slack" as Route,
  },
  {
    key: "budget_created",
    label: "Set a budget",
    description: "Get warned before spend runs away",
    href: "/budgets" as Route,
  },
];

interface Props {
  status: OnboardingStatus;
}

export function ActivationChecklist({ status }: Props) {
  // Hydration-safe: render nothing until localStorage has been consulted.
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    setVisible(localStorage.getItem(DISMISS_KEY) !== "1");
  }, []);

  const doneCount = STEPS.filter((s) => status[s.key]).length;
  // All four complete: the card has served its purpose - never show it again.
  if (doneCount === STEPS.length || !visible) return null;

  function dismiss() {
    localStorage.setItem(DISMISS_KEY, "1");
    setVisible(false);
  }

  return (
    <div className="rounded-xl border bg-card p-5 shadow-card">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-sm font-semibold text-foreground">
            Get set up ({doneCount}/{STEPS.length})
          </h2>
          <p className="mt-0.5 text-xs text-muted-foreground">
            Four steps to full cost visibility - most teams finish in under 10 minutes.
          </p>
        </div>
        <button
          onClick={dismiss}
          aria-label="Dismiss setup checklist"
          className="rounded p-1 text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      <div className="mt-4 grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
        {STEPS.map((step) => {
          const done = status[step.key];
          return (
            <Link
              key={step.key}
              href={step.href}
              className={cn(
                "group flex items-start gap-2.5 rounded-lg border p-3 transition-colors",
                done
                  ? "border-transparent bg-muted/50 opacity-70"
                  : "hover:border-foreground/20 hover:bg-accent"
              )}
            >
              {done ? (
                <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-success" />
              ) : (
                <Circle className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
              )}
              <span className="min-w-0">
                <span
                  className={cn(
                    "flex items-center gap-1 text-xs font-medium",
                    done ? "text-muted-foreground line-through" : "text-foreground"
                  )}
                >
                  {step.label}
                  {!done && (
                    <ArrowRight className="h-3 w-3 opacity-0 transition-opacity group-hover:opacity-100" />
                  )}
                </span>
                <span className="mt-0.5 block text-[11px] leading-snug text-muted-foreground">
                  {step.description}
                </span>
              </span>
            </Link>
          );
        })}
      </div>
    </div>
  );
}
