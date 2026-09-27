import { useTranslation } from "react-i18next";

import type { ExecutionStatus } from "@/lib/api";

export function ExecutionBadge({ status }: { status: ExecutionStatus }) {
  const { t } = useTranslation();
  const style =
    status === "completed" ? "bg-emerald-100 text-emerald-800" : "bg-sky-100 text-sky-800";
  return (
    <span className={`rounded px-1.5 py-0.5 text-xs font-medium ${style}`}>
      {t(`execution.status.${status}`)}
    </span>
  );
}
