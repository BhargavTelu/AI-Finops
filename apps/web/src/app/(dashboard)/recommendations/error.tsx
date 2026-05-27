"use client";

import { ErrorState } from "@/components/error-state";

export default function RecommendationsError({
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <ErrorState
      title="Failed to load recommendations"
      description="There was a problem fetching your recommendations. Check your connection or try again."
      onRetry={reset}
    />
  );
}
