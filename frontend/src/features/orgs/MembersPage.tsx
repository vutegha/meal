import { useTranslation } from "react-i18next";

import { Card } from "@/components/ui";
import { permissions } from "@/lib/permissions";

import { AuditPanel } from "./AuditPanel";
import { MembersPanel } from "./MembersPanel";
import { useCurrentOrg } from "./useCurrentOrg";

export function MembersPage() {
  const { t } = useTranslation();
  const { orgId, org, me, role } = useCurrentOrg();
  if (!org) return <Card>404</Card>;
  const isAdmin = permissions.manageOrg(role);

  return (
    <>
      <Card>
        <h1 className="text-xl font-semibold">{t("orgs.welcome", { name: org.name })}</h1>
        <p className="mt-1 text-sm text-slate-600">
          {t("orgs.yourRole", { role: t(`roles.${org.role}`) })}
        </p>
      </Card>
      <MembersPanel orgId={orgId} isAdmin={isAdmin} currentUserId={me.id} />
      {isAdmin && <AuditPanel orgId={orgId} />}
    </>
  );
}
