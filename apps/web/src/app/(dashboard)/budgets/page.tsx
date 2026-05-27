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
      <BudgetsClient initialBudgets={budgets} />
    </PageMotion>
  );
}
