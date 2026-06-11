import type { Metadata, Route } from "next";
import Link from "next/link";
import { SignedIn, SignedOut } from "@clerk/nextjs";
import {
  ArrowRight,
  BellRing,
  FileText,
  KeyRound,
  PieChart,
  ShieldCheck,
} from "lucide-react";

export const metadata: Metadata = {
  title: "SpendOps AI — Know which feature, team, and customer burns your LLM budget",
  description:
    "Per-feature and per-team LLM cost attribution, anomaly alerts in Slack, and a CFO-ready monthly PDF. For AI startups spending $5K–$80K/mo on OpenAI and Anthropic.",
};

const ROUTES = {
  signUp: "/sign-up" as Route,
  signIn: "/sign-in" as Route,
  dashboard: "/dashboard" as Route,
  security: "/security" as Route,
};

/* ── Ledger hero vignette: the product's soul, typeset as a statement ── */

const LEDGER_ROWS: { label: string; value: string; flag?: "anomaly" }[] = [
  { label: "chat-assistant · gpt-4o", value: "$11,284.10" },
  { label: "doc-extraction · claude-sonnet-4-6", value: "$6,032.55" },
  { label: "search-rerank · gpt-4o-mini", value: "$2,418.07", flag: "anomaly" },
  { label: "eval-suite · claude-haiku-4-5", value: "$904.22" },
  { label: "(untagged)", value: "$310.66" },
];

function LedgerCard() {
  return (
    <div className="rounded-xl border bg-card p-6 shadow-card sm:p-8">
      <div className="flex items-baseline justify-between border-b pb-3">
        <p className="text-xs font-medium uppercase tracking-widest text-muted-foreground">
          Spend by feature · May
        </p>
        <p className="text-xs tabular-nums text-muted-foreground">acme-ai · 2 providers</p>
      </div>
      <ul className="divide-y">
        {LEDGER_ROWS.map((row) => (
          <li key={row.label} className="flex items-baseline gap-2 py-3 text-sm">
            <span className={row.flag ? "font-medium text-warning" : "text-foreground"}>
              {row.label}
            </span>
            {row.flag && (
              <span className="rounded-md bg-warning-subtle px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-warning">
                +212% spike
              </span>
            )}
            {/* dot leader */}
            <span className="mx-1 flex-1 border-b border-dotted border-border" aria-hidden />
            <span className="tabular-nums font-medium text-foreground">{row.value}</span>
          </li>
        ))}
      </ul>
      <div className="flex items-baseline justify-between border-t-2 border-foreground/80 pt-3">
        <p className="text-sm font-semibold text-foreground">Month to date</p>
        <p className="tabular-nums text-sm font-semibold text-foreground">$20,949.60</p>
      </div>
      <p className="mt-3 text-right text-xs text-muted-foreground">
        Projected month-end <span className="tabular-nums font-medium text-foreground">$23,841</span>
      </p>
    </div>
  );
}

/* ── Section scaffolding: editorial numbered rules ── */

function SectionRule({ index, title }: { index: string; title: string }) {
  return (
    <div className="flex items-center gap-4">
      <span className="tabular-nums text-xs font-semibold tracking-widest text-primary">
        {index}
      </span>
      <h2 className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">
        {title}
      </h2>
      <span className="h-px flex-1 bg-border" aria-hidden />
    </div>
  );
}

const FEATURES = [
  {
    icon: PieChart,
    title: "Attribution, not averages",
    body: "Tag rules map every API key to a feature, team, and environment - so \"the OpenAI bill\" becomes \"chat costs 4x what search does.\" No SDK, no code changes.",
  },
  {
    icon: BellRing,
    title: "Anomalies land in Slack",
    body: "Nightly statistical detection (rolling mean + 2 sigma - explainable, no ML black box) posts spikes to your channel before they become a line item you have to explain.",
  },
  {
    icon: FileText,
    title: "A PDF your CFO forwards",
    body: "On the 1st of every month: spend by provider, model, feature, and team, month-over-month, anomalies, and realized savings. Finance-ready without editing.",
  },
];

const STEPS = [
  {
    n: "1",
    title: "Connect a read-only Admin key",
    body: "OpenAI or Anthropic. Encrypted before it touches the database; never returned, never logged.",
  },
  {
    n: "2",
    title: "See your first chart in minutes",
    body: "We backfill 30 days of cost history. Numbers match your provider dashboard.",
  },
  {
    n: "3",
    title: "Tag, budget, relax",
    body: "Attribution rules, monthly budgets, Slack alerts, and the monthly CFO report - on autopilot.",
  },
];

const PLANS = [
  {
    name: "Starter",
    price: "$299",
    spend: "Up to $10K/mo tracked spend",
    featured: false,
  },
  {
    name: "Growth",
    price: "$599",
    spend: "Up to $40K/mo tracked spend",
    featured: true,
  },
  {
    name: "Enterprise",
    price: "$1,500",
    spend: "Unlimited spend · priority support",
    featured: false,
  },
];

const FAQS = [
  {
    q: "Does my traffic flow through your servers?",
    a: "No. SpendOps pulls aggregate cost and usage data from your providers' Admin APIs on a schedule. We are never in your request path - zero added latency, and an outage on our side can't touch your product.",
  },
  {
    q: "Can you see our prompts or our users' data?",
    a: "No. The Admin APIs return token counts and dollar amounts, not content. We never see prompts, completions, or end-user data.",
  },
  {
    q: "Do the numbers match our invoice?",
    a: "OpenAI figures come from OpenAI's own Cost API, so they reconcile by construction. Anthropic figures are computed from list pricing and typically land within a few percent - every report says exactly which is which.",
  },
  {
    q: "Which providers are supported?",
    a: "OpenAI and Anthropic today, with Gemini cost ingestion on the roadmap. Multi-provider spend is normalized to USD in one view.",
  },
  {
    q: "How long does setup take?",
    a: "Under 10 minutes: sign up, paste a read-only Admin key, and your last 30 days of spend appear. Tag rules and budgets take a few minutes more.",
  },
  {
    q: "What does the trial require?",
    a: "Nothing but a sign-up - 14 days, full product, no credit card. If it doesn't pay for itself in found savings, walk away.",
  },
];

export default function LandingPage() {
  return (
    <div className="min-h-screen bg-background">
      {/* ── Nav ─────────────────────────────────────────────────────────── */}
      <header className="sticky top-0 z-40 border-b bg-background/90 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-5xl items-center justify-between px-6">
          <Link href={"/" as Route} className="text-sm font-semibold tracking-tight text-foreground">
            SpendOps <span className="text-primary">AI</span>
          </Link>
          <nav className="flex items-center gap-5 text-sm">
            <a href="#pricing" className="hidden text-muted-foreground transition-colors hover:text-foreground sm:block">
              Pricing
            </a>
            <Link
              href={ROUTES.security}
              className="hidden text-muted-foreground transition-colors hover:text-foreground sm:block"
            >
              Security
            </Link>
            <SignedOut>
              <Link href={ROUTES.signIn} className="text-muted-foreground transition-colors hover:text-foreground">
                Sign in
              </Link>
              <Link
                href={ROUTES.signUp}
                className="rounded-lg bg-primary px-3.5 py-1.5 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90"
              >
                Start free trial
              </Link>
            </SignedOut>
            <SignedIn>
              <Link
                href={ROUTES.dashboard}
                className="rounded-lg bg-primary px-3.5 py-1.5 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90"
              >
                Open dashboard
              </Link>
            </SignedIn>
          </nav>
        </div>
      </header>

      <main className="mx-auto max-w-5xl px-6">
        {/* ── Hero ──────────────────────────────────────────────────────── */}
        <section className="grid items-center gap-12 py-16 sm:py-24 lg:grid-cols-[1.1fr_1fr]">
          <div className="animate-in fade-in slide-in-from-bottom-4 duration-700">
            <p className="text-xs font-semibold uppercase tracking-widest text-primary">
              LLM cost attribution for AI startups
            </p>
            <h1 className="mt-4 text-4xl font-semibold leading-[1.08] tracking-tight text-foreground sm:text-5xl">
              Know which feature, team, and customer burns your LLM budget.
            </h1>
            <p className="mt-5 max-w-xl text-base leading-relaxed text-muted-foreground">
              SpendOps AI turns your OpenAI and Anthropic bills into per-feature
              attribution, Slack anomaly alerts, and a monthly PDF your CFO
              actually reads. Read-only Admin keys. First chart in under
              10 minutes.
            </p>
            <div className="mt-8 flex flex-wrap items-center gap-4">
              <Link
                href={ROUTES.signUp}
                className="inline-flex items-center gap-2 rounded-lg bg-primary px-5 py-2.5 text-sm font-semibold text-primary-foreground transition-opacity hover:opacity-90"
              >
                Start 14-day free trial
                <ArrowRight className="h-4 w-4" />
              </Link>
              <p className="text-xs text-muted-foreground">No credit card. No code changes.</p>
            </div>
          </div>
          <div className="animate-in fade-in slide-in-from-bottom-8 duration-700 [animation-delay:150ms]">
            <LedgerCard />
          </div>
        </section>

        {/* ── Features ──────────────────────────────────────────────────── */}
        <section className="py-14">
          <SectionRule index="01" title="What you get" />
          <div className="mt-8 grid gap-8 md:grid-cols-3">
            {FEATURES.map(({ icon: Icon, title, body }) => (
              <div key={title}>
                <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary/10">
                  <Icon className="h-[18px] w-[18px] text-primary" />
                </div>
                <h3 className="mt-4 text-base font-semibold text-foreground">{title}</h3>
                <p className="mt-2 text-sm leading-relaxed text-muted-foreground">{body}</p>
              </div>
            ))}
          </div>
        </section>

        {/* ── How it works ──────────────────────────────────────────────── */}
        <section className="py-14">
          <SectionRule index="02" title="How it works" />
          <ol className="mt-8 grid gap-8 md:grid-cols-3">
            {STEPS.map((step) => (
              <li key={step.n} className="relative">
                <span className="tabular-nums text-3xl font-semibold tracking-tight text-primary/30">
                  {step.n}
                </span>
                <h3 className="mt-2 text-sm font-semibold text-foreground">{step.title}</h3>
                <p className="mt-1.5 text-sm leading-relaxed text-muted-foreground">{step.body}</p>
              </li>
            ))}
          </ol>
        </section>

        {/* ── Pricing ───────────────────────────────────────────────────── */}
        <section id="pricing" className="py-14">
          <SectionRule index="03" title="Pricing" />
          <p className="mt-6 max-w-lg text-sm text-muted-foreground">
            Every plan includes everything - attribution, anomaly alerts,
            budgets, Slack, and the monthly CFO report. Tiers scale with the
            spend we track for you.
          </p>
          <div className="mt-8 grid gap-4 md:grid-cols-3">
            {PLANS.map((plan) => (
              <div
                key={plan.name}
                className={
                  plan.featured
                    ? "relative rounded-xl border-2 border-primary bg-card p-6 shadow-card"
                    : "rounded-xl border bg-card p-6 shadow-card"
                }
              >
                {plan.featured && (
                  <span className="absolute -top-3 left-6 rounded-md bg-primary px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-primary-foreground">
                    Most common
                  </span>
                )}
                <h3 className="text-sm font-semibold text-foreground">{plan.name}</h3>
                <p className="mt-3 flex items-baseline gap-1">
                  <span className="tabular-nums text-3xl font-semibold tracking-tight text-foreground">
                    {plan.price}
                  </span>
                  <span className="text-sm text-muted-foreground">/mo</span>
                </p>
                <p className="mt-2 text-xs text-muted-foreground">{plan.spend}</p>
                <Link
                  href={ROUTES.signUp}
                  className={
                    plan.featured
                      ? "mt-6 block rounded-lg bg-primary px-4 py-2 text-center text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90"
                      : "mt-6 block rounded-lg border px-4 py-2 text-center text-sm font-medium text-foreground transition-colors hover:bg-accent"
                  }
                >
                  Start free trial
                </Link>
              </div>
            ))}
          </div>
        </section>

        {/* ── Security band ─────────────────────────────────────────────── */}
        <section className="py-14">
          <div className="rounded-xl bg-[hsl(214,51%,25%)] p-8 text-white sm:p-10">
            <div className="flex flex-col gap-6 sm:flex-row sm:items-center sm:justify-between">
              <div className="max-w-xl">
                <div className="flex items-center gap-2">
                  <ShieldCheck className="h-4 w-4 text-white/70" />
                  <p className="text-xs font-semibold uppercase tracking-widest text-white/70">
                    Built for the key you are trusting us with
                  </p>
                </div>
                <p className="mt-3 text-lg font-medium leading-snug">
                  AES-256 encrypted keys that never reach a browser. Read-only by
                  design - none of your traffic touches our servers. Row-level
                  tenant isolation, verified before every deploy.
                </p>
              </div>
              <Link
                href={ROUTES.security}
                className="inline-flex shrink-0 items-center gap-2 rounded-lg border border-white/30 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-white/10"
              >
                <KeyRound className="h-4 w-4" />
                Read the security overview
              </Link>
            </div>
          </div>
        </section>

        {/* ── FAQ ───────────────────────────────────────────────────────── */}
        <section className="py-14">
          <SectionRule index="04" title="Questions" />
          <div className="mt-8 divide-y rounded-xl border bg-card shadow-card">
            {FAQS.map((faq) => (
              <details key={faq.q} className="group px-6 py-4">
                <summary className="flex cursor-pointer list-none items-center justify-between gap-4 text-sm font-medium text-foreground [&::-webkit-details-marker]:hidden">
                  {faq.q}
                  <span className="text-muted-foreground transition-transform group-open:rotate-45">
                    +
                  </span>
                </summary>
                <p className="mt-3 max-w-2xl text-sm leading-relaxed text-muted-foreground">
                  {faq.a}
                </p>
              </details>
            ))}
          </div>
        </section>

        {/* ── Final CTA ─────────────────────────────────────────────────── */}
        <section className="py-20 text-center">
          <h2 className="mx-auto max-w-2xl text-3xl font-semibold tracking-tight text-foreground">
            Your next invoice is already growing.
          </h2>
          <p className="mx-auto mt-3 max-w-md text-sm text-muted-foreground">
            Connect a key now - see 30 days of attributed spend before your coffee cools.
          </p>
          <Link
            href={ROUTES.signUp}
            className="mt-8 inline-flex items-center gap-2 rounded-lg bg-primary px-6 py-3 text-sm font-semibold text-primary-foreground transition-opacity hover:opacity-90"
          >
            Start 14-day free trial
            <ArrowRight className="h-4 w-4" />
          </Link>
        </section>
      </main>

      {/* ── Footer ──────────────────────────────────────────────────────── */}
      <footer className="border-t">
        <div className="mx-auto flex max-w-5xl flex-col gap-3 px-6 py-8 text-xs text-muted-foreground sm:flex-row sm:items-center sm:justify-between">
          <p>SpendOps AI - LLM cost attribution for AI startups.</p>
          <div className="flex gap-5">
            <Link href={ROUTES.security} className="transition-colors hover:text-foreground">
              Security
            </Link>
            <a href="mailto:security@spendopsai.com" className="transition-colors hover:text-foreground">
              Contact
            </a>
          </div>
        </div>
      </footer>
    </div>
  );
}
