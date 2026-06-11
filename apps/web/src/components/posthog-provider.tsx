"use client";

import posthog from "posthog-js";
import { PostHogProvider as PHProvider } from "posthog-js/react";
import { useEffect } from "react";
import { useOrganization, useUser } from "@clerk/nextjs";

import { initPostHog } from "@/lib/posthog";

function PostHogIdentity() {
  const { user } = useUser();
  const { organization } = useOrganization();

  // Identify by Clerk ids only - no email or name in analytics properties.
  useEffect(() => {
    if (user?.id) posthog.identify(user.id);
  }, [user?.id]);

  useEffect(() => {
    if (organization?.id) posthog.group("organization", organization.id);
  }, [organization?.id]);

  return null;
}

export function PostHogProvider({ children }: { children: React.ReactNode }) {
  useEffect(() => {
    initPostHog();
  }, []);

  return (
    <PHProvider client={posthog}>
      <PostHogIdentity />
      {children}
    </PHProvider>
  );
}
