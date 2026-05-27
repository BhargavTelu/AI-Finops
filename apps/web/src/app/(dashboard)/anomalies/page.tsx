import { auth } from "@clerk/nextjs/server";

import { createApiClient } from "@/lib/api-client";
import type { AnomalyRead, AnomalyStatus } from "@/lib/types";
import { PageMotion } from "@/components/motion-wrapper";
import { AnomaliesClient } from "./anomalies-client";

const VALID_STATUS = new Set<AnomalyStatus>(["open", "acked", "dismissed"]);

export default async function AnomaliesPage({
  searchParams,
}: {
  searchParams: Promise<{ status?: string }>;
}) {
  const params = await searchParams;
  const status: AnomalyStatus = VALID_STATUS.has(params.status as AnomalyStatus)
    ? (params.status as AnomalyStatus)
    : "open";

  const { getToken } = await auth();
  const token = await getToken();
  const api = createApiClient(token!);

  const anomalies = await api
    .get<AnomalyRead[]>(`/anomalies?status=${status}`)
    .catch(() => [] as AnomalyRead[]);

  return (
    <PageMotion>
      <AnomaliesClient initialAnomalies={anomalies} status={status} />
    </PageMotion>
  );
}
