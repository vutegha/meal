import { useMutation, useQuery } from "@tanstack/react-query";
import { Link, useNavigate, useParams, useSearch } from "@tanstack/react-router";
import { useTranslation } from "react-i18next";

import { Button, Card, ErrorText } from "@/components/ui";
import { download, projectsApi } from "@/lib/api";
import { projectQuery } from "@/lib/queries";

import { BudgetTab } from "./BudgetTab";
import { DashboardTab } from "./DashboardTab";
import { DocumentsTab } from "./DocumentsTab";
import { ExecutionTab } from "./ExecutionTab";
import { IndicatorsTab } from "./IndicatorsTab";
import { LogframeTab } from "./LogframeTab";
import { StatusBadge } from "./StatusBadge";
import { TorTab } from "./TorTab";
import { PROJECT_TABS } from "./tabs";

export function ProjectPage() {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const { orgId, projectId } = useParams({ from: "/orgs/$orgId/projects/$projectId" });
  const { tab } = useSearch({ from: "/orgs/$orgId/projects/$projectId" });
  const project = useQuery(projectQuery(orgId, projectId));
  const exportFile = useMutation({
    mutationFn: () =>
      download(
        projectsApi.exportPath(orgId, projectId),
        `cadre-logique-${project.data?.code ?? "projet"}.xlsx`,
      ),
  });

  if (project.isPending) return <p className="text-sm text-slate-500">{t("common.loading")}</p>;
  if (!project.data) return <ErrorText error={project.error} />;
  const p = project.data;
  const dates = new Intl.DateTimeFormat(i18n.language, { dateStyle: "medium" });

  return (
    <>
      <Link to="/orgs/$orgId" params={{ orgId }} className="text-sm text-brand-700 hover:underline">
        ← {t("projects.back")}
      </Link>
      <Card>
        <div className="flex flex-wrap items-start gap-3">
          <div className="min-w-0 basis-full sm:basis-auto sm:flex-1">
            <p className="font-mono text-xs text-slate-500">{p.code}</p>
            <h1 className="text-xl font-semibold">{p.title}</h1>
            <p className="mt-1 text-sm text-slate-600">
              {[
                p.donor,
                p.currency,
                p.start_date && p.end_date
                  ? `${dates.format(new Date(p.start_date))} – ${dates.format(new Date(p.end_date))}`
                  : null,
                p.zones.join(", "),
              ]
                .filter(Boolean)
                .join(" · ")}
            </p>
          </div>
          <StatusBadge status={p.status} />
          <Button
            variant="ghost"
            onClick={() => exportFile.mutate()}
            disabled={exportFile.isPending}
          >
            ⬇ {t("projects.export")}
          </Button>
        </div>
        <ErrorText error={exportFile.error} />
      </Card>

      <nav
        className="flex gap-1 overflow-x-auto whitespace-nowrap border-b border-slate-200"
        aria-label={p.title}
      >
        {PROJECT_TABS.map((key) => (
          <button
            key={key}
            onClick={() => navigate({ to: ".", search: { tab: key } })}
            aria-current={tab === key ? "page" : undefined}
            className={`-mb-px border-b-2 px-4 py-2 text-sm font-medium ${
              tab === key
                ? "border-brand-700 text-brand-800"
                : "border-transparent text-slate-600 hover:text-slate-900"
            }`}
          >
            {t(`projects.tabs.${key}`)}
          </button>
        ))}
      </nav>

      {tab === "dashboard" && <DashboardTab orgId={orgId} project={p} />}
      {tab === "logframe" && <LogframeTab orgId={orgId} projectId={projectId} />}
      {tab === "budget" && <BudgetTab orgId={orgId} project={p} />}
      {tab === "indicators" && <IndicatorsTab orgId={orgId} projectId={projectId} />}
      {tab === "tor" && <TorTab orgId={orgId} project={p} />}
      {tab === "execution" && <ExecutionTab orgId={orgId} project={p} />}
      {tab === "documents" && <DocumentsTab orgId={orgId} project={p} />}
    </>
  );
}
