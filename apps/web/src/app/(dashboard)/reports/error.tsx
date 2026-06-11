"use client";

import { ErrorState } from "@/components/error-state";

export default function ReportsError({
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <ErrorState
      title="Failed to load reports"
      description="There was a problem fetching your reports. Check your connection or try again."
      onRetry={reset}
    />
  );
}
