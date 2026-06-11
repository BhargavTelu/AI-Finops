// Browser-only. Only import from "use client" components.
// posthog.capture() is a no-op until init() runs, so call order is safe.
import posthog from "posthog-js";

export function initPostHog(): void {
  if (typeof window === "undefined" || !process.env.NEXT_PUBLIC_POSTHOG_KEY) {
    return;
  }
  posthog.init(process.env.NEXT_PUBLIC_POSTHOG_KEY, {
    api_host: process.env.NEXT_PUBLIC_POSTHOG_HOST ?? "https://app.posthog.com",
    // App Router: disable auto-capture - client-side nav doesn't trigger
    // full page loads. Manual tracking via usePathname() wired in M4.
    capture_pageview: false,
    capture_pageleave: true,
  });
}

// ── Typed event stubs (all 9 required by architecture.md § Engineering Reqs) ─

export function captureSignup(): void {
  posthog.capture("signup");
}

export function captureOrgCreated(orgId: string): void {
  posthog.capture("org_created", { org_id: orgId });
}

export function captureProviderConnected(provider: "openai" | "anthropic" | "gemini"): void {
  posthog.capture("provider_connected", { provider });
}

export function captureTagCreated(tagType: "feature" | "team" | "customer" | "env"): void {
  posthog.capture("tag_created", { tag_type: tagType });
}

// scope_type widened from the M0 stub's 3-value union: budgets now support 7
// scope types (global/provider/model/feature_tag/team_tag/customer_tag/env_tag).
export function captureBudgetCreated(scopeType: string): void {
  posthog.capture("budget_created", { scope_type: scopeType });
}

export function captureAnomalyViewed(anomalyId: string, severity: string): void {
  posthog.capture("anomaly_viewed", { anomaly_id: anomalyId, severity });
}

export function captureRecommendationApplied(
  recommendationId: string,
  type: string
): void {
  posthog.capture("recommendation_applied", {
    recommendation_id: recommendationId,
    type,
  });
}

export function capturePdfDownloaded(reportId: string): void {
  posthog.capture("pdf_downloaded", { report_id: reportId });
}

export function captureCheckoutCompleted(plan: "starter" | "growth" | "enterprise"): void {
  posthog.capture("checkout_completed", { plan });
}
