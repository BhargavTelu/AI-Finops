import { auth } from "@clerk/nextjs/server";
import { createApiClient } from "@/lib/api-client";
import type { Tag, UsageEventRead } from "@/lib/types";
import { UsageEventsClient } from "./usage-events-client";

export default async function UsageEventsPage() {
  const { getToken } = await auth();
  const token = await getToken();
  const api = createApiClient(token!);

  const [events, tags] = await Promise.all([
    api.get<UsageEventRead[]>("/usage/events").catch(() => [] as UsageEventRead[]),
    api.get<Tag[]>("/tags").catch(() => [] as Tag[]),
  ]);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Usage Events</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Admin view of raw ingestion events. Use tag overrides to manually correct
          attribution that the tag-rule engine missed.
        </p>
      </div>
      <UsageEventsClient events={events} tags={tags} />
    </div>
  );
}
