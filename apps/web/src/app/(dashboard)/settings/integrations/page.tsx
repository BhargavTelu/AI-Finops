import { auth } from "@clerk/nextjs/server";
import { createApiClient } from "@/lib/api-client";
import { IntegrationsPage } from "@/components/integrations-page";
import type { IntegrationRead } from "@/lib/types";

export default async function SettingsIntegrationsPage() {
  const { getToken } = await auth();
  const token = await getToken();
  const integrations = await createApiClient(token!)
    .get<IntegrationRead[]>("/integrations")
    .catch(() => [] as IntegrationRead[]);

  return <IntegrationsPage integrations={integrations} />;
}
