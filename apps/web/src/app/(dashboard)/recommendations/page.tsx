import Link from "next/link";
import { Lightbulb, ArrowRight } from "lucide-react";

import { PageMotion } from "@/components/motion-wrapper";

// M3 milestone: Rule-based recommendations with projected savings.
export default function RecommendationsPage() {
  return (
    <PageMotion>
      <div className="space-y-6">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Recommendations</h1>
          <p className="mt-0.5 text-sm text-muted-foreground">Rule-based savings opportunities for your LLM spend</p>
        </div>

        <div className="flex min-h-[360px] flex-col items-center justify-center rounded-xl border border-dashed border-border bg-card/50 text-center">
          <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-emerald-50 dark:bg-emerald-950/40">
            <Lightbulb className="h-7 w-7 text-emerald-500" strokeWidth={1.5} />
          </div>
          <h2 className="text-base font-medium">No recommendations yet</h2>
          <p className="mt-2 max-w-xs text-sm text-muted-foreground">
            Savings opportunities appear after your first nightly analysis. We analyze model usage patterns and suggest cheaper alternatives.
          </p>
          <div className="mt-4 flex items-center gap-1.5 rounded-full bg-muted/60 px-3 py-1.5">
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
            <span className="text-xs text-muted-foreground">Available in M3</span>
          </div>
        </div>

        <p className="text-center text-xs text-muted-foreground">
          Want a head start?{" "}
          <Link href="/cost-explorer" className="text-primary hover:underline inline-flex items-center gap-0.5">
            Explore cost breakdown <ArrowRight className="h-3 w-3" />
          </Link>
        </p>
      </div>
    </PageMotion>
  );
}
