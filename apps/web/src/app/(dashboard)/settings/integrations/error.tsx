"use client";

import { ErrorState } from "@/components/error-state";

export default function IntegrationsError({
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <ErrorState
      title="Failed to load integrations"
      description="There was a problem fetching your API integrations. Check your connection or try again."
      onRetry={reset}
    />
  );
}
