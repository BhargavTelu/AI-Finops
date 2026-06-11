"use client";

import { useState } from "react";
import { useAuth } from "@clerk/nextjs";
import { useRouter } from "next/navigation";
import { Download, FileText, Loader2, Sparkles } from "lucide-react";

import { createApiClient } from "@/lib/api-client";
import type { ReportDownloadResponse, ReportGenerateAccepted, ReportRead } from "@/lib/types";
import { useToast } from "@/hooks/use-toast";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/empty-state";

function periodLabel(report: ReportRead): string {
  const start = new Date(report.period_start + "T00:00:00Z");
  return start.toLocaleDateString("en-US", {
    month: "long",
    year: "numeric",
    timeZone: "UTC",
  });
}

function isPartialPeriod(report: ReportRead): boolean {
  const end = new Date(report.period_end + "T00:00:00Z");
  const lastDay = new Date(
    Date.UTC(end.getUTCFullYear(), end.getUTCMonth() + 1, 0)
  );
  return end.getUTCDate() !== lastDay.getUTCDate();
}

interface Props {
  initialReports: ReportRead[];
}

export function ReportsClient({ initialReports }: Props) {
  const { getToken } = useAuth();
  const { toast } = useToast();
  const router = useRouter();

  const [generating, setGenerating] = useState(false);
  const [downloadingId, setDownloadingId] = useState<string | null>(null);

  async function handleGenerate() {
    setGenerating(true);
    try {
      const token = await getToken();
      const api = createApiClient(token!);
      await api.post<ReportGenerateAccepted>("/reports/generate", null);
      toast({
        title: "Report queued",
        description:
          "Generating your month-to-date report. It appears in the list within a minute - refresh to see it.",
      });
      // Refresh after a grace period so a fast worker shows up without a manual reload.
      setTimeout(() => router.refresh(), 20_000);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Could not queue the report.";
      toast({
        title: msg.includes("Limit") ? "Daily limit reached" : "Generation failed",
        description: msg,
        variant: "destructive",
      });
    } finally {
      setGenerating(false);
    }
  }

  async function handleDownload(report: ReportRead) {
    setDownloadingId(report.id);
    try {
      const token = await getToken();
      const api = createApiClient(token!);
      const { url } = await api.get<ReportDownloadResponse>(
        `/reports/${report.id}/download`
      );
      window.open(url, "_blank", "noopener");
    } catch (err: unknown) {
      toast({
        title: "Download failed",
        description:
          err instanceof Error ? err.message : "Could not fetch the download link.",
        variant: "destructive",
      });
    } finally {
      setDownloadingId(null);
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        <Button onClick={handleGenerate} disabled={generating} size="sm" className="gap-1.5">
          {generating ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Sparkles className="h-4 w-4" />
          )}
          Generate current month
        </Button>
      </div>

      {initialReports.length === 0 ? (
        <EmptyState
          icon={FileText}
          title="No reports yet"
          description="Your first report arrives automatically on the 1st of the month - or generate a month-to-date report right now."
          action={{ label: "Generate current month", onClick: handleGenerate }}
        />
      ) : (
        <div className="space-y-3">
          {initialReports.map((report) => (
            <div
              key={report.id}
              className="flex items-center justify-between gap-4 rounded-xl border border-transparent bg-card p-5 shadow-card transition-shadow hover:shadow-card-hover"
            >
              <div className="flex items-center gap-3 min-w-0">
                <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-muted">
                  <FileText className="h-4 w-4 text-muted-foreground" />
                </div>
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-sm font-semibold text-foreground">
                      {periodLabel(report)}
                    </span>
                    {isPartialPeriod(report) && (
                      <span className="rounded-md bg-muted px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
                        Month to date
                      </span>
                    )}
                  </div>
                  <p className="mt-0.5 text-xs text-muted-foreground">
                    Generated{" "}
                    {new Date(report.generated_at).toLocaleDateString("en-US", {
                      month: "short",
                      day: "numeric",
                      year: "numeric",
                    })}
                  </p>
                </div>
              </div>

              {report.has_file ? (
                <Button
                  variant="outline"
                  size="sm"
                  className="gap-1.5 shrink-0"
                  onClick={() => handleDownload(report)}
                  disabled={downloadingId === report.id}
                >
                  {downloadingId === report.id ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Download className="h-4 w-4" />
                  )}
                  Download PDF
                </Button>
              ) : (
                <span className="shrink-0 text-xs text-muted-foreground">
                  File unavailable - regenerate
                </span>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
