import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { Card } from "@/components/ui";
import { auditQuery } from "@/lib/queries";

function detail(data: Record<string, unknown>): string | undefined {
  const value = ["email", "code", "title", "label", "name", "indicator"]
    .map((key) => data[key])
    .find((v) => typeof v === "string" && v);
  return value as string | undefined;
}

export function AuditPanel({ orgId }: { orgId: string }) {
  const { t, i18n } = useTranslation();
  const audit = useQuery(auditQuery(orgId));
  const format = new Intl.DateTimeFormat(i18n.language, {
    dateStyle: "short",
    timeStyle: "short",
  });

  return (
    <Card title={t("orgs.audit")}>
      {audit.isPending ? (
        <p className="text-sm text-slate-500">{t("common.loading")}</p>
      ) : audit.data?.length ? (
        <ul className="space-y-1.5 text-sm">
          {audit.data.map((entry) => (
            <li key={entry.id} className="flex flex-wrap gap-x-3">
              <time className="text-slate-500" dateTime={entry.created_at}>
                {format.format(new Date(entry.created_at))}
              </time>
              <span>{t(`audit.${entry.action}`, { defaultValue: entry.action })}</span>
              {detail(entry.data) && <span className="text-slate-500">{detail(entry.data)}</span>}
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-sm text-slate-500">{t("orgs.noAudit")}</p>
      )}
    </Card>
  );
}
