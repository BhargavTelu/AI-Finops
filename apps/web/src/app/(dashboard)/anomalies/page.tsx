import { AlertTriangle } from "lucide-react";

import { PageMotion } from "@/components/motion-wrapper";

// M3 milestone: Anomaly log with severity badges.
export default function AnomaliesPage() {
  return (
    <PageMotion>
      <div className="space-y-6">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Anomalies</h1>
          <p className="mt-0.5 text-sm text-muted-foreground">Unusual spend spikes and cost deviations</p>
        </div>

        <div className="flex min-h-[360px] flex-col items-center justify-center rounded-xl border border-dashed border-border bg-card/50 text-center">
          <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-amber-50 dark:bg-amber-950/40">
            <AlertTriangle className="h-7 w-7 text-amber-500" strokeWidth={1.5} />
          </div>
          <h2 className="text-base font-medium">No anomalies detected</h2>
          <p className="mt-2 max-w-xs text-sm text-muted-foreground">
            Anomaly detection requires 14 days of spend data. Stats run nightly once your integrations are active.
          </p>
          <div className="mt-4 flex items-center gap-1.5 rounded-full bg-muted/60 px-3 py-1.5">
            <span className="h-1.5 w-1.5 rounded-full bg-amber-400" />
            <span className="text-xs text-muted-foreground">Available in M3</span>
          </div>
        </div>
      </div>
    </PageMotion>
  );
}
