import type { Metadata, Route } from "next";
import Link from "next/link";
import {
  KeyRound,
  Eye,
  Layers,
  FileX2,
  Trash2,
  Building2,
  type LucideIcon,
} from "lucide-react";

export const metadata: Metadata = {
  title: "Security | SpendOps AI",
  description:
    "How SpendOps AI protects your provider Admin API keys and spend data: AES-256-GCM encryption, read-only architecture, and per-tenant isolation.",
};

const SECTIONS: {
  icon: LucideIcon;
  title: string;
  points: string[];
}[] = [
  {
    icon: KeyRound,
    title: "Your Admin API keys",
    points: [
      "Keys are encrypted with AES-256-GCM before they touch the database and are only ever decrypted inside our ingestion workers.",
      "A key is validated and encrypted server-side the moment you submit it. It is never returned to the browser, never included in any API response, and never written to logs.",
      "We recommend least-privilege keys: OpenAI Admin keys support a read-only Usage API scope, and the connect form shows exact setup steps per provider.",
      "Revoking an integration stops syncing immediately. You can also revoke the key at the provider at any time - we degrade gracefully.",
    ],
  },
  {
    icon: Eye,
    title: "Read-only by design",
    points: [
      "SpendOps pulls cost and usage data from your providers' Admin APIs on a schedule. We only call read endpoints.",
      "None of your application traffic flows through our servers - no proxy, no gateway, no latency added, and an outage on our side can never affect your product.",
      "We never see your prompts, completions, or end-user data. We ingest aggregate cost and token counts only.",
    ],
  },
  {
    icon: Layers,
    title: "Tenant isolation",
    points: [
      "Every customer-data table is protected by Postgres Row-Level Security scoped to your organization. Isolation is enforced by the database, not just application code.",
      "A two-tenant isolation probe runs before every deploy to verify that one organization can never read another's rows.",
    ],
  },
  {
    icon: FileX2,
    title: "No PII in logs",
    points: [
      "Structured logs carry organization, request, and actor identifiers - never emails, names, or key material.",
    ],
  },
  {
    icon: Trash2,
    title: "Your data, your call",
    points: [
      "You can export your cost data as CSV at any time from the Cost Explorer.",
      "On request we delete all data for your organization - usage events, aggregates, reports, and encrypted keys.",
    ],
  },
  {
    icon: Building2,
    title: "Infrastructure & subprocessors",
    points: [
      "Hosting and data: Vercel (web), Railway (API and workers), Supabase (Postgres), Upstash (Redis), Cloudflare R2 (report storage).",
      "Services: Clerk (authentication), Stripe (billing - we never see card numbers), Resend (email), Slack (alerts you configure), Sentry (errors), PostHog (product analytics).",
    ],
  },
];

export default function SecurityPage() {
  return (
    <div className="min-h-screen bg-background">
      {/* Minimal public top bar - this page renders outside the dashboard shell */}
      <header className="border-b">
        <div className="mx-auto flex h-14 max-w-3xl items-center justify-between px-6">
          <Link href="/" className="text-sm font-semibold text-foreground">
            SpendOps AI
          </Link>
          <Link
            href={"/sign-in" as Route}
            className="text-sm text-muted-foreground transition-colors hover:text-foreground"
          >
            Sign in
          </Link>
        </div>
      </header>

      <main className="mx-auto max-w-3xl px-6 py-12">
        <h1 className="text-2xl font-semibold tracking-tight text-foreground">
          Security
        </h1>
        <p className="mt-2 text-sm text-muted-foreground">
          SpendOps AI exists because you trusted us with an Admin API key. Here
          is exactly what we do - and deliberately don&apos;t do - with it.
        </p>

        <div className="mt-10 space-y-8">
          {SECTIONS.map(({ icon: Icon, title, points }) => (
            <section key={title} className="rounded-xl border bg-card p-6 shadow-card">
              <div className="flex items-center gap-2.5">
                <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-muted">
                  <Icon className="h-4 w-4 text-muted-foreground" aria-hidden />
                </div>
                <h2 className="text-base font-semibold text-foreground">{title}</h2>
              </div>
              <ul className="mt-4 space-y-2.5">
                {points.map((point) => (
                  <li
                    key={point}
                    className="flex gap-2 text-sm leading-relaxed text-muted-foreground"
                  >
                    <span className="mt-2 h-1 w-1 shrink-0 rounded-full bg-foreground/40" aria-hidden />
                    {point}
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </div>

        <p className="mt-10 text-sm text-muted-foreground">
          Questions, security reviews, or vulnerability reports: email{" "}
          <a
            href="mailto:security@spendopsai.com"
            className="font-medium text-foreground underline underline-offset-2 hover:no-underline"
          >
            security@spendopsai.com
          </a>
          . Reports go straight to the founders.
        </p>
      </main>
    </div>
  );
}
