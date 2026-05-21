import { auth } from "@clerk/nextjs/server";

import { createApiClient } from "@/lib/api-client";
import type { BudgetRead } from "@/lib/types";
import { PageMotion } from "@/components/motion-wrapper";
import { BudgetsClient } from "./budgets-client";

export default async function BudgetsPage() {
  const { getToken } = await auth();
  const token = await getToken();
  const api = createApiClient(token!);

  const budgets = await api
    .get<BudgetRead[]>("/budgets")
    .catch(() => [] as BudgetRead[]);

  return (
    <PageMotion>
      <div className="space-y-6">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Budgets</h1>
          <p className="mt-0.5 text-sm text-muted-foreground">
            Monthly spend limits with email alerts at your threshold and at 100%
          </p>
        </div>

        <BudgetsClient initialBudgets={budgets} />
      </div>
    </PageMotion>
  );
}
