import { auth } from "@clerk/nextjs/server";

import { createApiClient } from "@/lib/api-client";
import type { ReportRead } from "@/lib/types";
import { PageHeader } from "@/components/page-header";
import { PageMotion } from "@/components/motion-wrapper";
import { ReportsClient } from "./reports-client";

export default async function ReportsPage() {
  const { getToken } = await auth();
  const token = await getToken();
  const api = createApiClient(token!);

  const reports = await api
    .get<ReportRead[]>("/reports")
    .catch(() => [] as ReportRead[]);

  return (
    <PageMotion>
      <div className="space-y-6">
        <PageHeader
          title="Reports"
          description="Monthly CFO-ready spend reports - generated automatically on the 1st, or on demand for the current month."
        />
        <ReportsClient initialReports={reports} />
      </div>
    </PageMotion>
  );
}
