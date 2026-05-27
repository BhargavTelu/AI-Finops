"use client";

import { ErrorState } from "@/components/error-state";

export default function AnomaliesError({
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <ErrorState
      title="Failed to load alerts"
      description="There was a problem fetching your anomaly data. Check your connection or try again."
      onRetry={reset}
    />
  );
}
