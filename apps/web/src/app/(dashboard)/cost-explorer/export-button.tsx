"use client";

import { Download } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { ExploreRow } from "@/lib/types";

function rowsToCsv(rows: ExploreRow[], groupBy: string): string {
  const headers = [
    `${groupBy.replace("_", " ")}`,
    "Total Cost (USD)",
    "Requests",
    "Tokens",
    "% of Total",
  ];
  const lines = rows.map((r) => [
    r.group_key || "(untagged)",
    parseFloat(r.total_cost_usd).toFixed(4),
    r.total_requests,
    r.total_tokens,
    r.pct_of_total.toFixed(2),
  ]);
  return [headers, ...lines]
    .map((row) =>
      row.map((cell) => `"${String(cell).replace(/"/g, '""')}"`).join(","),
    )
    .join("\n");
}

interface Props {
  rows: ExploreRow[];
  groupBy: string;
}

export function ExportButton({ rows, groupBy }: Props) {
  function handleExport() {
    const csv = rowsToCsv(rows, groupBy);
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `spendops-cost-explorer-${new Date().toISOString().slice(0, 10)}.csv`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  return (
    <Button variant="outline" size="sm" onClick={handleExport} disabled={rows.length === 0}>
      <Download className="h-4 w-4" />
      Export CSV
    </Button>
  );
}
