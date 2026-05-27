"use client";

import { ErrorState } from "@/components/error-state";

export default function SlackError({
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <ErrorState
      title="Failed to load Slack settings"
      description="There was a problem fetching your Slack integration status. Check your connection or try again."
      onRetry={reset}
    />
  );
}
