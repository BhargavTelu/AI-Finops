import { auth } from "@clerk/nextjs/server";

import { createApiClient } from "@/lib/api-client";
import type { Tag, TagRule } from "@/lib/types";
import { TagsClient } from "./tags-client";

export default async function SettingsTagsPage() {
  const { getToken } = await auth();
  const token = await getToken();
  const api = createApiClient(token!);

  const [tags, rules] = await Promise.all([
    api.get<Tag[]>("/tags").catch(() => [] as Tag[]),
    api.get<TagRule[]>("/tag-rules").catch(() => [] as TagRule[]),
  ]);

  return <TagsClient tags={tags} rules={rules} token={token!} />;
}
