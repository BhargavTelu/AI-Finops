"use client";

import { ErrorState } from "@/components/error-state";

export default function TagsError({
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <ErrorState
      title="Failed to load tag rules"
      description="There was a problem fetching your tags and rules. Check your connection or try again."
      onRetry={reset}
    />
  );
}
