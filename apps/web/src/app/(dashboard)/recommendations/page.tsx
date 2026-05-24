import { auth } from "@clerk/nextjs/server";

import { createApiClient } from "@/lib/api-client";
import type { RecommendationRead, RecommendationStatus } from "@/lib/types";
import { PageMotion } from "@/components/motion-wrapper";
import { RecommendationsClient } from "./recommendations-client";

const VALID_STATUS = new Set<RecommendationStatus>(["new", "applied", "dismissed"]);

export default async function RecommendationsPage({
  searchParams,
}: {
  searchParams: Promise<{ status?: string }>;
}) {
  const params = await searchParams;
  const status: RecommendationStatus = VALID_STATUS.has(params.status as RecommendationStatus)
    ? (params.status as RecommendationStatus)
    : "new";

  const { getToken } = await auth();
  const token = await getToken();
  const api = createApiClient(token!);

  const recommendations = await api
    .get<RecommendationRead[]>(`/recommendations?status=${status}`)
    .catch(() => [] as RecommendationRead[]);

  return (
    <PageMotion>
      <div className="space-y-6">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Recommendations</h1>
          <p className="mt-0.5 text-sm text-muted-foreground">
            Rule-based savings opportunities — analyzed nightly from your LLM usage patterns
          </p>
        </div>

        <RecommendationsClient initialRecs={recommendations} status={status} />
      </div>
    </PageMotion>
  );
}
