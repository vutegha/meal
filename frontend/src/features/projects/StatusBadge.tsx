import { useTranslation } from "react-i18next";

import type { ProjectStatus } from "@/lib/api";

const styles: Record<ProjectStatus, string> = {
  draft: "bg-slate-100 text-slate-700",
  active: "bg-brand-100 text-brand-800",
  closed: "bg-slate-200 text-slate-600",
};

export function StatusBadge({ status }: { status: ProjectStatus }) {
  const { t } = useTranslation();
  return (
    <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${styles[status]}`}>
      {t(`projects.status.${status}`)}
    </span>
  );
}
