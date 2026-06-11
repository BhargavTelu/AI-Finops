import { Zap } from "lucide-react";

// Branded frame for the Clerk auth screens - the first surface a buyer sees.
export default function AuthLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="relative flex min-h-screen flex-col items-center justify-center bg-background px-4 py-12">
      {/* Soft primary glow behind the card - depth without decoration */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 bg-[radial-gradient(56%_38%_at_50%_0%,hsl(var(--primary)/0.08),transparent)]"
      />

      {/* Brand lockup */}
      <div className="relative mb-8 flex items-center gap-2.5">
        <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-gradient-to-br from-primary to-chart-2 shadow-card">
          <Zap className="h-5 w-5 text-primary-foreground" strokeWidth={2.5} aria-hidden />
        </div>
        <span className="text-lg font-semibold tracking-tight text-foreground">
          SpendOps
          <span className="ml-1 text-muted-foreground/80">AI</span>
        </span>
      </div>

      <div className="relative">{children}</div>

      <p className="relative mt-8 max-w-xs text-center text-xs text-muted-foreground">
        LLM cost attribution, anomaly alerts, and savings recommendations for AI teams.
      </p>
    </div>
  );
}
