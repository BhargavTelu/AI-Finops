"use client";

import { ErrorState } from "@/components/error-state";

export default function BudgetsError({
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <ErrorState
      title="Failed to load budgets"
      description="There was a problem fetching your budget data. Check your connection or try again."
      onRetry={reset}
    />
  );
}
