"use client";

import { useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import {
  createColumnHelper,
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
  type SortingState,
} from "@tanstack/react-table";
import { ArrowUp, ArrowDown, ArrowUpDown } from "lucide-react";

import type { ExploreRow } from "@/lib/types";

const DIMENSION_LABELS: Record<string, string> = {
  provider: "Provider",
  model: "Model",
  feature_tag: "Feature Tag",
  team_tag: "Team Tag",
  customer_tag: "Customer Tag",
  env_tag: "Env Tag",
};

function fmtCost(raw: string | number): string {
  const n = typeof raw === "string" ? parseFloat(raw) : raw;
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
  if (!direction)
    return <ArrowUpDown className="ml-1.5 h-3.5 w-3.5 opacity-40" />;
  return direction === "asc" ? (
    <ArrowUp className="ml-1.5 h-3.5 w-3.5 text-primary" />
  ) : (
    <ArrowDown className="ml-1.5 h-3.5 w-3.5 text-primary" />
  );
}

export function ExploreTable({ rows, groupBy }: Props) {
  const router = useRouter();
  const searchParams = useSearchParams();
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
          <span className="font-medium">{val}</span>
        );
      },
      sortingFn: "alphanumeric",
    }),
    columnHelper.accessor("total_cost_usd", {
      header: "Cost",
      cell: (info) => (
        <span className="text-mono">{fmtCost(info.getValue())}</span>
      ),
      sortingFn: (a, b) =>
        parseFloat(a.original.total_cost_usd) - parseFloat(b.original.total_cost_usd),
    }),
    columnHelper.accessor("total_requests", {
      header: "Requests",
      cell: (info) => (
        <span className="text-mono">{fmtNumber(info.getValue())}</span>
      ),
    }),
    columnHelper.accessor("total_tokens", {
      header: "Tokens",
      cell: (info) => (
        <span className="text-mono">{fmtNumber(info.getValue())}</span>
      ),
    }),
    columnHelper.accessor(
      (row) =>
        row.total_tokens > 0
          ? (parseFloat(row.total_cost_usd) / row.total_tokens) * 1000
          : 0,
      {
        id: "avg_per_1k",
        header: "Avg/1K tkns",
        cell: (info) => {
          const avg = info.getValue();
          if (avg === 0)
            return <span className="text-mono text-muted-foreground">—</span>;
          return <span className="text-mono">${avg.toFixed(4)}</span>;
        },
      },
    ),
    columnHelper.accessor("pct_of_total", {
      header: "% of Total",
      cell: (info) => {
        const pct = info.getValue();
        return (
          <div className="flex items-center gap-2.5">
            <div className="h-1.5 w-20 overflow-hidden rounded-full bg-muted">
              <div
                className="h-full rounded-full bg-primary/70"
                style={{ width: `${Math.min(pct, 100)}%` }}
              />
            </div>
            <span className="text-mono text-sm">{pct.toFixed(1)}%</span>
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

  return (
    <div className="overflow-x-auto rounded-xl border border-border/60 scrollbar-thin">
      <table className="w-full text-sm">
        <thead className="border-b border-border/60 bg-muted/30">
          {table.getHeaderGroups().map((hg) => (
            <tr key={hg.id}>
              {hg.headers.map((header, idx) => {
                const isNumeric = idx > 0;
                const sortDir = header.column.getIsSorted();
                return (
                  <th
                    key={header.id}
                    scope="col"
                    aria-sort={
                      sortDir === "asc"
                        ? "ascending"
                        : sortDir === "desc"
                        ? "descending"
                        : "none"
                    }
                    className={`px-4 py-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground ${
                      isNumeric ? "text-right" : "text-left"
                    }`}
                  >
                    {header.isPlaceholder ? null : (
                      <button
                        className={`flex items-center gap-0 transition-colors duration-150 hover:text-foreground ${
                          isNumeric ? "ml-auto" : ""
                        }`}
                        onClick={header.column.getToggleSortingHandler()}
                        aria-label={`Sort by ${typeof header.column.columnDef.header === "string" ? header.column.columnDef.header : header.id}${sortDir === "asc" ? ", currently ascending" : sortDir === "desc" ? ", currently descending" : ""}`}
                      >
                        {flexRender(header.column.columnDef.header, header.getContext())}
                        <SortIcon direction={header.column.getIsSorted()} />
                      </button>
                    )}
                  </th>
                );
              })}
            </tr>
          ))}
        </thead>

        <tbody className="divide-y divide-border/40">
          {table.getRowModel().rows.map((row) => {
            const groupKey = row.original.group_key;
            const drillable = groupKey !== "";
            return (
              <tr
                key={row.id}
                className={`transition-colors duration-150 ${
                  drillable
                    ? "cursor-pointer hover:bg-muted/40"
                    : "hover:bg-muted/20"
                }`}
                onClick={
                  drillable
                    ? () => {
                        const params = new URLSearchParams(searchParams.toString());
                        params.set(groupBy, groupKey);
                        router.push(`/cost-explorer?${params.toString()}`);
                      }
                    : undefined
                }
              >
                {row.getVisibleCells().map((cell, idx) => {
                  const isNumeric = idx > 0 && idx < 5; // Cost, Requests, Tokens, Avg/1K
                  const isPct = idx === 5;
                  return (
                    <td
                      key={cell.id}
                      className={`px-4 py-3 ${isNumeric ? "whitespace-nowrap text-right" : isPct ? "" : "text-left"}`}
                    >
                      {flexRender(cell.column.columnDef.cell, cell.getContext())}
                    </td>
                  );
                })}
              </tr>
            );
          })}
        </tbody>

        {/* Grand total footer */}
        <tfoot className="border-t border-border/60 bg-muted/30">
          <tr>
            <td className="px-4 py-3 text-sm font-semibold text-foreground">
              Grand Total
            </td>
            <td className="whitespace-nowrap px-4 py-3 text-right">
              <span className="text-mono font-semibold">{fmtCost(grandTotalCost.toString())}</span>
            </td>
            <td className="whitespace-nowrap px-4 py-3 text-right">
              <span className="text-mono font-semibold">{fmtNumber(grandTotalRequests)}</span>
            </td>
            <td className="whitespace-nowrap px-4 py-3 text-right">
              <span className="text-mono font-semibold">{fmtNumber(grandTotalTokens)}</span>
            </td>
            <td className="whitespace-nowrap px-4 py-3 text-right">
              {grandTotalTokens > 0 ? (
                <span className="text-mono font-semibold">
                  ${((grandTotalCost / grandTotalTokens) * 1000).toFixed(4)}
                </span>
              ) : (
                <span className="text-mono text-muted-foreground">—</span>
              )}
            </td>
            <td className="px-4 py-3" />
          </tr>
        </tfoot>
      </table>
    </div>
  );
}
