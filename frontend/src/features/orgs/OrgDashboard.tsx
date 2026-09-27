import { useSuspenseQuery } from "@tanstack/react-query";
import { useParams } from "@tanstack/react-router";
import { useTranslation } from "react-i18next";

import { Card } from "@/components/ui";
import { meQuery } from "@/lib/queries";

import { AuditPanel } from "./AuditPanel";
import { MembersPanel } from "./MembersPanel";

export function OrgDashboard() {
  const { t } = useTranslation();
  const { orgId } = useParams({ from: "/orgs/$orgId" });
  const { data: me } = useSuspenseQuery(meQuery);
  const org = me.organizations.find((o) => o.id === orgId);
  if (!org) return <Card>404</Card>;
  const isAdmin = org.role === "admin";

  return (
    <>
      <Card>
        <h1 className="text-xl font-semibold">{t("orgs.welcome", { name: org.name })}</h1>
        <p className="mt-1 text-sm text-slate-600">
          {t("orgs.yourRole", { role: t(`roles.${org.role}`) })}
        </p>
        <p className="mt-3 text-sm text-slate-500">{t("orgs.nextSteps")}</p>
      </Card>
      <MembersPanel orgId={orgId} isAdmin={isAdmin} currentUserId={me.id} />
      {isAdmin && <AuditPanel orgId={orgId} />}
    </>
  );
}
