"use client";

import { ErrorState } from "@/components/error-state";

export default function CostExplorerError({
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <ErrorState
      title="Failed to load cost data"
      description="There was a problem fetching your cost explorer data. Check your connection or try again."
      onRetry={reset}
    />
  );
}
