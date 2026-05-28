"use client";

import { useRouter } from "next/navigation";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";

interface Props {
  range: string;
}

const OPTIONS = [
  { value: "7d", label: "7d" },
  { value: "30d", label: "30d" },
  { value: "90d", label: "90d" },
] as const;

/**
 * Period selector for the dashboard - navigates via URL param so the server
 * re-fetches timeseries + provider data for the chosen range.
 */
export function PeriodSelector({ range }: Props) {
  const router = useRouter();

  return (
    <Tabs value={range} onValueChange={(val) => router.push(`/dashboard?range=${val}`)}>
      <TabsList className="h-8 p-0.5">
        {OPTIONS.map((opt) => (
          <TabsTrigger key={opt.value} value={opt.value} className="h-7 px-3 text-xs">
            {opt.label}
          </TabsTrigger>
        ))}
      </TabsList>
    </Tabs>
  );
}
