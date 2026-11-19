import { useTranslation } from "react-i18next";

import { Card } from "@/components/ui";
import { ROLES } from "@/lib/api";
import { OPERATIONS } from "@/lib/permissions";

/** Ce que chaque rôle peut faire dans l'organisation : les mêmes règles que le serveur. */
export function RolesMatrix() {
  const { t } = useTranslation();
  return (
    <Card title={t("rolesMatrix.title")}>
      <p className="mb-3 text-sm text-slate-600">{t("rolesMatrix.intro")}</p>
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead className="text-xs text-slate-500">
            <tr>
              <th className="py-1 pr-3 font-medium">{t("rolesMatrix.operation")}</th>
              {ROLES.map((role) => (
                <th key={role} className="px-2 py-1 text-center font-medium">
                  {t(`roles.${role}`)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {OPERATIONS.map(({ key, allowed }) => (
              <tr key={key}>
                <td className="py-1.5 pr-3">{t(`rolesMatrix.operations.${key}`)}</td>
                {ROLES.map((role) => (
                  <td key={role} className="px-2 py-1.5 text-center">
                    {allowed(role) ? (
                      <span className="text-brand-700" aria-label={t("rolesMatrix.yes")}>
                        ✓
                      </span>
                    ) : (
                      <span className="text-slate-300" aria-label={t("rolesMatrix.no")}>
                        –
                      </span>
                    )}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}
