"use client";

import { ErrorState } from "@/components/error-state";

export default function DashboardError({
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <ErrorState
      title="Failed to load dashboard"
      description="There was a problem fetching your spend data. Check your connection or try again."
      onRetry={reset}
    />
  );
}
