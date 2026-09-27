import { useSuspenseQuery } from "@tanstack/react-query";
import { useParams } from "@tanstack/react-router";

import { meQuery } from "@/lib/queries";

export function useCurrentOrg() {
  const { orgId } = useParams({ strict: false }) as { orgId: string };
  const { data: me } = useSuspenseQuery(meQuery);
  const org = me.organizations.find((o) => o.id === orgId);
  return { orgId, org, me, role: org?.role };
}
