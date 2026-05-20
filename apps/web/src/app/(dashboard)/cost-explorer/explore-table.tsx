"use client";

import { useState } from "react";
import {
  createColumnHelper,
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
  type SortingState,
} from "@tanstack/react-table";

import type { ExploreRow } from "@/lib/types";

const DIMENSION_LABELS: Record<string, string> = {
  provider: "Provider",
  model: "Model",
  feature_tag: "Feature Tag",
  team_tag: "Team Tag",
  customer_tag: "Customer Tag",
  env_tag: "Env Tag",
};

function fmtCost(raw: string): string {
  const n = parseFloat(raw);
  if (n === 0) return "$0.00";
  if (n < 0.01) return `$${n.toFixed(6)}`;
  return `$${n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function fmtNumber(n: number): string {
  return n.toLocaleString("en-US");
}

const columnHelper = createColumnHelper<ExploreRow>();

interface Props {
  rows: ExploreRow[];
  groupBy: string;
}

function SortIcon({ direction }: { direction: "asc" | "desc" | false }) {
  if (!direction) return <span className="ml-1 opacity-30">↕</span>;
  return <span className="ml-1">{direction === "asc" ? "↑" : "↓"}</span>;
}

export function ExploreTable({ rows, groupBy }: Props) {
  const [sorting, setSorting] = useState<SortingState>([
    { id: "total_cost_usd", desc: true },
  ]);

  const dimensionLabel = DIMENSION_LABELS[groupBy] ?? groupBy;

  const grandTotalCost = rows.reduce((s, r) => s + parseFloat(r.total_cost_usd), 0);
  const grandTotalRequests = rows.reduce((s, r) => s + r.total_requests, 0);
  const grandTotalTokens = rows.reduce((s, r) => s + r.total_tokens, 0);

  const columns = [
    columnHelper.accessor("group_key", {
      header: dimensionLabel,
      cell: (info) => {
        const val = info.getValue();
        return val === "" ? (
          <span className="italic text-muted-foreground">(untagged)</span>
        ) : (
          val
        );
      },
      sortingFn: "alphanumeric",
    }),
    columnHelper.accessor("total_cost_usd", {
      header: "Cost",
      cell: (info) => (
        <span className="tabular-nums">{fmtCost(info.getValue())}</span>
      ),
      // Sort numerically despite string storage
      sortingFn: (a, b) =>
        parseFloat(a.original.total_cost_usd) - parseFloat(b.original.total_cost_usd),
    }),
    columnHelper.accessor("total_requests", {
      header: "Requests",
      cell: (info) => (
        <span className="tabular-nums">{fmtNumber(info.getValue())}</span>
      ),
    }),
    columnHelper.accessor("total_tokens", {
      header: "Tokens",
      cell: (info) => (
        <span className="tabular-nums">{fmtNumber(info.getValue())}</span>
      ),
    }),
    columnHelper.accessor("pct_of_total", {
      header: "% of Total",
      cell: (info) => {
        const pct = info.getValue();
        return (
          <div className="flex items-center gap-2">
            <div className="h-1.5 w-24 overflow-hidden rounded-full bg-muted">
              <div
                className="h-full rounded-full bg-primary"
                style={{ width: `${Math.min(pct, 100)}%` }}
              />
            </div>
            <span className="tabular-nums text-sm">{pct.toFixed(1)}%</span>
          </div>
        );
      },
    }),
  ];

  const table = useReactTable({
    data: rows,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  });

  if (rows.length === 0) {
    return (
      <div className="rounded-lg border bg-card p-12 text-center text-sm text-muted-foreground">
        No spend data for this period. Connect an integration or wait for the next sync.
      </div>
    );
  }

  return (
    <div className="overflow-x-auto rounded-lg border">
      <table className="w-full text-sm">
        <thead className="border-b bg-muted/40">
          {table.getHeaderGroups().map((hg) => (
            <tr key={hg.id}>
              {hg.headers.map((header) => (
                <th
                  key={header.id}
                  className="px-4 py-3 text-left font-medium text-muted-foreground"
                >
                  {header.isPlaceholder ? null : (
                    <button
                      className="flex items-center hover:text-foreground"
                      onClick={header.column.getToggleSortingHandler()}
                    >
                      {flexRender(header.column.columnDef.header, header.getContext())}
                      <SortIcon direction={header.column.getIsSorted()} />
                    </button>
                  )}
                </th>
              ))}
            </tr>
          ))}
        </thead>
        <tbody className="divide-y">
          {table.getRowModel().rows.map((row) => (
            <tr key={row.id} className="hover:bg-muted/20">
              {row.getVisibleCells().map((cell) => (
                <td key={cell.id} className="px-4 py-3">
                  {flexRender(cell.column.columnDef.cell, cell.getContext())}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
        <tfoot className="border-t bg-muted/40 font-medium">
          <tr>
            <td className="px-4 py-3 text-muted-foreground">Total</td>
            <td className="px-4 py-3 tabular-nums">{fmtCost(grandTotalCost.toString())}</td>
            <td className="px-4 py-3 tabular-nums">{fmtNumber(grandTotalRequests)}</td>
            <td className="px-4 py-3 tabular-nums">{fmtNumber(grandTotalTokens)}</td>
            <td className="px-4 py-3" />
          </tr>
        </tfoot>
      </table>
    </div>
  );
}
