import { useMutation, useQuery } from "@tanstack/react-query";
import { Link, useNavigate, useParams, useSearch } from "@tanstack/react-router";
import { useTranslation } from "react-i18next";

import { Button, Card, ErrorText } from "@/components/ui";
import { download, projectsApi } from "@/lib/api";
import { FeatureGate } from "@/features/orgs/FeatureGate";
import { useCurrentOrg } from "@/features/orgs/useCurrentOrg";
import { hasFeature } from "@/lib/billing";
import { projectQuery } from "@/lib/queries";

import { BudgetTab } from "./BudgetTab";
import { DashboardTab } from "./DashboardTab";
import { DocumentsTab } from "./DocumentsTab";
import { ExecutionTab } from "./ExecutionTab";
import { FeedbackTab } from "./FeedbackTab";
import { FormsTab } from "./FormsTab";
import { IndicatorsTab } from "./IndicatorsTab";
import { LessonsTab } from "./LessonsTab";
import { LogframeTab } from "./LogframeTab";
import { PeriodicTab } from "./PeriodicTab";
import { ScheduleTab } from "./ScheduleTab";
import { StatusBadge } from "./StatusBadge";
import { TorTab } from "./TorTab";
import { TAB_FEATURES, TAB_GROUPS } from "./tabs";

export function ProjectPage() {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const { orgId, projectId } = useParams({ from: "/orgs/$orgId/projects/$projectId" });
  const { tab } = useSearch({ from: "/orgs/$orgId/projects/$projectId" });
  const project = useQuery(projectQuery(orgId, projectId));
  const { org } = useCurrentOrg();
  const locked = (key: keyof typeof TAB_FEATURES) => {
    const feature = TAB_FEATURES[key];
    return !!feature && !!org && !hasFeature(org, feature);
  };
  const exportFile = useMutation({
    mutationFn: (format: "xlsx" | "pdf" | "docx") =>
      download(
        format === "xlsx"
          ? projectsApi.exportPath(orgId, projectId)
          : projectsApi.documentPath(orgId, projectId, format),
        `cadre-logique-${project.data?.code ?? "projet"}.${format}`,
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
          <div className="flex flex-wrap gap-1">
            <Button
              variant="ghost"
              onClick={() => exportFile.mutate("xlsx")}
              disabled={exportFile.isPending}
            >
              ⬇ {t("projects.export")}
            </Button>
            <Button
              variant="ghost"
              onClick={() => exportFile.mutate("pdf")}
              disabled={exportFile.isPending}
            >
              ⬇ PDF
            </Button>
            <Button
              variant="ghost"
              onClick={() => exportFile.mutate("docx")}
              disabled={exportFile.isPending}
            >
              ⬇ Word
            </Button>
          </div>
        </div>
        <ErrorText error={exportFile.error} />
      </Card>

      <div className="flex flex-col gap-6 md:flex-row md:items-start">
        <nav
          className="-mx-4 overflow-x-auto px-4 md:sticky md:top-4 md:mx-0 md:w-56 md:shrink-0 md:overflow-visible md:px-0"
          aria-label={p.title}
        >
          <div className="flex gap-1 whitespace-nowrap md:flex-col md:gap-4 md:whitespace-normal md:rounded-xl md:border md:border-slate-200 md:bg-white md:p-2">
            {TAB_GROUPS.map((group) => (
              <div key={group.key} className="flex gap-1 md:flex-col md:gap-0.5">
                <p className="hidden px-3 pt-1 pb-1 text-[11px] font-semibold tracking-wide text-slate-400 uppercase md:block">
                  {t(`projects.tabGroups.${group.key}`)}
                </p>
                {group.tabs.map((key) => (
                  <button
                    key={key}
                    onClick={() => navigate({ to: ".", search: { tab: key } })}
                    aria-current={tab === key ? "page" : undefined}
                    className={`rounded-md px-3 py-2 text-left text-sm font-medium md:border-l-2 ${
                      tab === key
                        ? "bg-brand-50 text-brand-800 md:border-brand-700"
                        : "text-slate-600 hover:bg-slate-100 hover:text-slate-900 md:border-transparent"
                    }`}
                  >
                    {t(`projects.tabs.${key}`)}
                    {locked(key) && (
                      <span className="ml-1.5 text-xs" title={t("billing.locked.tab")}>
                        🔒
                      </span>
                    )}
                  </button>
                ))}
              </div>
            ))}
          </div>
        </nav>

        <div className="min-w-0 flex-1 space-y-6">
          {tab === "dashboard" && <DashboardTab orgId={orgId} project={p} />}
          {tab === "logframe" && <LogframeTab orgId={orgId} projectId={projectId} />}
          {tab === "schedule" && <ScheduleTab orgId={orgId} project={p} />}
          {tab === "budget" && <BudgetTab orgId={orgId} project={p} />}
          {tab === "indicators" && <IndicatorsTab orgId={orgId} projectId={projectId} />}
          {tab === "tor" && <TorTab orgId={orgId} project={p} />}
          {tab === "execution" && <ExecutionTab orgId={orgId} project={p} />}
          {tab === "forms" && (
            <FeatureGate feature="forms">
              <FormsTab orgId={orgId} projectId={projectId} />
            </FeatureGate>
          )}
          {tab === "reports" && (
            <FeatureGate feature="periodic_reports">
              <PeriodicTab project={p} />
            </FeatureGate>
          )}
          {tab === "feedback" && <FeedbackTab orgId={orgId} projectId={projectId} />}
          {tab === "lessons" && <LessonsTab orgId={orgId} projectId={projectId} />}
          {tab === "documents" && <DocumentsTab orgId={orgId} project={p} />}
        </div>
      </div>
    </>
  );
}
