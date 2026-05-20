import Link from "next/link";
import { Wallet, ArrowRight } from "lucide-react";

import { PageMotion } from "@/components/motion-wrapper";

// M3 milestone: Budget CRUD + threshold alert configuration.
export default function BudgetsPage() {
  return (
    <PageMotion>
      <div className="space-y-6">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Budgets</h1>
          <p className="mt-0.5 text-sm text-muted-foreground">Monthly spend limits with threshold alerts</p>
        </div>

        <div className="flex min-h-[360px] flex-col items-center justify-center rounded-xl border border-dashed border-border bg-card/50 text-center">
          <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-blue-50 dark:bg-blue-950/40">
            <Wallet className="h-7 w-7 text-blue-500" strokeWidth={1.5} />
          </div>
          <h2 className="text-base font-medium">No budgets configured</h2>
          <p className="mt-2 max-w-xs text-sm text-muted-foreground">
            Set monthly spend limits per provider, model, or team tag. Get alerted at 80% and 100% threshold.
          </p>
          <div className="mt-4 flex items-center gap-1.5 rounded-full bg-muted/60 px-3 py-1.5">
            <span className="h-1.5 w-1.5 rounded-full bg-blue-400" />
            <span className="text-xs text-muted-foreground">Available in M3</span>
          </div>
        </div>

        <p className="text-center text-xs text-muted-foreground">
          Need to set up a data source first?{" "}
          <Link href="/settings/integrations" className="text-primary hover:underline inline-flex items-center gap-0.5">
            Connect an integration <ArrowRight className="h-3 w-3" />
          </Link>
        </p>
      </div>
    </PageMotion>
  );
}
