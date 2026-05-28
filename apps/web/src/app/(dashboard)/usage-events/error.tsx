"use client";

import { ErrorState } from "@/components/error-state";

export default function UsageEventsError({
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <ErrorState
      title="Failed to load usage events"
      description="There was a problem fetching usage event data. Check your connection or try again."
      onRetry={reset}
    />
  );
}
