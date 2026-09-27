import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { Button, Card, ErrorText } from "@/components/ui";
import { useCurrentOrg } from "@/features/orgs/useCurrentOrg";
import { lessonFromReport } from "@/lib/accountability";
import { type Report, reportsApi } from "@/lib/api";
import { permissions } from "@/lib/permissions";
import { executionReportsQuery, reportQuery } from "@/lib/queries";

import { DocumentEditor } from "./DocumentEditor";
import { LessonForm } from "./LessonsTab";
import { useInvalidateProject } from "./useInvalidateProject";
import { useJob } from "./useJob";

// Sections calculées depuis les données saisies (voir backend/app/services/report.py).
const COMPUTED = new Set(["participants", "budget"]);

function Suggestions({
  orgId,
  projectId,
  report,
}: {
  orgId: string;
  projectId: string;
  report: Report;
}) {
  const { t } = useTranslation();
  const { role } = useCurrentOrg();
  const invalidate = useInvalidateProject(orgId, projectId);
  const canRecord = permissions.recordValues(role);
  const [values, setValues] = useState(report.indicator_suggestions.map((s) => s.value));
  const apply = useMutation({
    mutationFn: (index: number) =>
      reportsApi.applySuggestion(orgId, projectId, report.id, index, values[index]),
    onSuccess: invalidate,
  });
  if (!report.indicator_suggestions.length) return null;
  return (
    <div className="mt-3 rounded-md border border-brand-100 bg-brand-50/50 p-3 text-sm">
      <p className="font-medium text-brand-900">{t("report.suggestions")}</p>
      <p className="text-xs text-slate-600">{t("report.suggestionsHint")}</p>
      <ul className="mt-2 space-y-2">
        {report.indicator_suggestions.map((s, index) => (
          <li key={`${s.indicator_id}-${index}`} className="flex flex-wrap items-center gap-2">
            <span className="min-w-0 flex-1">
              <span className="mr-1 font-mono text-xs text-slate-500">{s.code}</span>
              {s.name}
              <span className="block text-xs text-slate-500">
                {s.justification}
                {s.source_ref && ` [${s.source_ref}]`}
              </span>
            </span>
            {s.applied_value_id ? (
              <span className="text-xs font-medium text-emerald-700">
                ✓ {s.value} {s.unit} · {t("report.applied")}
              </span>
            ) : (
              <>
                <input
                  aria-label={s.name}
                  type="number"
                  min={0}
                  step="any"
                  className="w-24 rounded border border-slate-300 px-2 py-1 text-sm"
                  value={values[index]}
                  disabled={!canRecord}
                  onChange={(e) =>
                    setValues(values.map((v, i) => (i === index ? e.target.value : v)))
                  }
                />
                <span className="text-xs text-slate-500">{s.unit}</span>
                {canRecord && (
                  <Button
                    variant="ghost"
                    onClick={() => apply.mutate(index)}
                    disabled={apply.isPending || values[index] === ""}
                  >
                    {t("report.apply")}
                  </Button>
                )}
              </>
            )}
          </li>
        ))}
      </ul>
      <ErrorText error={apply.error} />
    </div>
  );
}

/** Rapport narratif d'une exécution : rédaction IA, relecture, validation et export. */
export function ReportPanel({
  orgId,
  projectId,
  executionId,
}: {
  orgId: string;
  projectId: string;
  executionId: string;
}) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const { role } = useCurrentOrg();
  const canPlan = permissions.plan(role);
  const reports = useQuery(executionReportsQuery(orgId, projectId, executionId));
  const reportId = reports.data?.[0]?.id;
  const report = useQuery({
    ...reportQuery(orgId, projectId, reportId ?? ""),
    enabled: !!reportId,
  });
  const job = useJob(orgId, () =>
    queryClient.invalidateQueries({ queryKey: ["orgs", orgId, "projects", projectId, "reports"] }),
  );
  const generate = useMutation({
    mutationFn: () => reportsApi.generate(orgId, projectId, executionId),
    onSuccess: job.start,
  });
  const busy = generate.isPending || job.running;
  const invalidate = useInvalidateProject(orgId, projectId);
  const [addingLesson, setAddingLesson] = useState(false);

  const status = (
    <>
      {busy && (
        <p role="status" className="mb-2 text-sm text-slate-600">
          {t("report.running")}
        </p>
      )}
      <ErrorText error={generate.error ?? job.error} />
    </>
  );

  if (reports.isPending || (reportId && report.isPending))
    return <p className="text-sm text-slate-500">{t("common.loading")}</p>;
  if (!report.data)
    return (
      <Card title={t("report.title")}>
        <p className="mb-3 text-sm text-slate-600">{t("report.intro")}</p>
        {status}
        {canPlan ? (
          <Button onClick={() => generate.mutate()} disabled={busy}>
            ✨ {t("report.generate")}
          </Button>
        ) : (
          <p className="text-sm text-slate-500">{t("report.none")}</p>
        )}
      </Card>
    );
  return (
    <>
      {status}
      <DocumentEditor
        key={`${report.data.id}-${report.data.version}-${report.data.status}`}
        doc={report.data}
        label={t("report.title")}
        computedKeys={COMPUTED}
        filename="Rapport"
        save={(body) => reportsApi.update(orgId, projectId, report.data.id, body)}
        transition={(action, comment) =>
          reportsApi.transition(orgId, projectId, report.data.id, action, comment)
        }
        remove={() => reportsApi.remove(orgId, projectId, report.data.id)}
        exportPath={(format) => reportsApi.exportPath(orgId, projectId, report.data.id, format)}
        loadVersions={() => reportsApi.versions(orgId, projectId, report.data.id)}
        onRegenerate={() => generate.mutate()}
        busy={busy}
        onChanged={invalidate}
        toolbar={
          canPlan && (
            <Button variant="ghost" onClick={() => setAddingLesson(!addingLesson)}>
              💡 {t("lessons.fromReport")}
            </Button>
          )
        }
      >
        {addingLesson && (
          <div className="mt-3 rounded-md border border-slate-200 p-3">
            <LessonForm
              orgId={orgId}
              projectId={projectId}
              initial={lessonFromReport(report.data)}
              onDone={() => setAddingLesson(false)}
            />
          </div>
        )}
        <Suggestions orgId={orgId} projectId={projectId} report={report.data} />
      </DocumentEditor>
    </>
  );
}
