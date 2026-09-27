import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { Markdown } from "@/components/Markdown";
import { Button, Card, ErrorText } from "@/components/ui";
import { useCurrentOrg } from "@/features/orgs/useCurrentOrg";
import { download, type Report, reportsApi, type TorSection } from "@/lib/api";
import { permissions } from "@/lib/permissions";
import { executionReportsQuery, reportQuery, reportVersionsQuery } from "@/lib/queries";

import { ReviewBox, TorBadge } from "./TorTab";
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

function ReportEditor({
  orgId,
  projectId,
  report,
  onRegenerate,
  busy,
}: {
  orgId: string;
  projectId: string;
  report: Report;
  onRegenerate: () => void;
  busy: boolean;
}) {
  const { t, i18n } = useTranslation();
  const { role } = useCurrentOrg();
  const invalidate = useInvalidateProject(orgId, projectId);
  const canPlan = permissions.plan(role);
  const canApprove = permissions.manageProjects(role);
  const editable = canPlan && report.status === "draft";
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState(report.title);
  const [sections, setSections] = useState<TorSection[]>(report.sections);
  const [review, setReview] = useState<"approve" | "return" | null>(null);
  const [showVersions, setShowVersions] = useState(false);
  const versions = useQuery({
    ...reportVersionsQuery(orgId, projectId, report.id),
    enabled: showVersions,
  });
  const dirty =
    title !== report.title || sections.some((s, i) => s.content !== report.sections[i]?.content);
  const dates = new Intl.DateTimeFormat(i18n.language, { dateStyle: "short", timeStyle: "short" });
  const unknownRefs = sections.some((s) => s.content.includes("[source introuvable]"));

  const save = useMutation({
    mutationFn: () => reportsApi.update(orgId, projectId, report.id, { title, sections }),
    onSuccess: invalidate,
  });
  const transition = useMutation({
    mutationFn: ({
      action,
      comment,
    }: {
      action: Parameters<typeof reportsApi.transition>[3];
      comment?: string;
    }) => reportsApi.transition(orgId, projectId, report.id, action, comment),
    onSuccess: async () => {
      setReview(null);
      await invalidate();
    },
  });
  const remove = useMutation({
    mutationFn: () => reportsApi.remove(orgId, projectId, report.id),
    onSuccess: invalidate,
  });
  const exportFile = useMutation({
    mutationFn: (format: "docx" | "pdf") =>
      download(
        reportsApi.exportPath(orgId, projectId, report.id, format),
        `Rapport-v${report.version}.${format}`,
      ),
  });
  const pending = save.isPending || transition.isPending || busy;

  return (
    <Card>
      <div className="flex flex-wrap items-center gap-3">
        <p className="w-full text-xs font-medium tracking-wide text-slate-500 uppercase">
          {t("report.title")}
        </p>
        {editing ? (
          <input
            aria-label={t("report.docTitle")}
            className="min-w-0 flex-1 rounded-md border border-slate-300 px-3 py-1.5 text-lg font-semibold"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
          />
        ) : (
          <h2 className="min-w-0 flex-1 text-lg font-semibold">{report.title}</h2>
        )}
        <TorBadge status={report.status} />
        <span className="text-xs text-slate-500">v{report.version}</span>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        {editable && !editing && (
          <>
            <Button variant="ghost" onClick={() => setEditing(true)}>
              ✎ {t("report.edit")}
            </Button>
            <Button
              variant="ghost"
              onClick={() => transition.mutate({ action: "submit" })}
              disabled={pending}
            >
              {t("tor.submit")}
            </Button>
            <Button
              variant="ghost"
              onClick={() => {
                if (window.confirm(t("report.confirmRegenerate"))) onRegenerate();
              }}
              disabled={pending}
            >
              ✨ {t("report.regenerate")}
            </Button>
          </>
        )}
        {editing && (
          <>
            <Button onClick={() => save.mutate()} disabled={!dirty || pending}>
              {t("tor.save")}
            </Button>
            <Button
              variant="ghost"
              onClick={() => {
                setTitle(report.title);
                setSections(report.sections);
                setEditing(false);
              }}
            >
              {t("common.cancel")}
            </Button>
          </>
        )}
        {canApprove && report.status === "submitted" && (
          <>
            <Button onClick={() => setReview("approve")} disabled={pending}>
              {t("tor.approve")}
            </Button>
            <Button variant="danger" onClick={() => setReview("return")} disabled={pending}>
              {t("tor.return")}
            </Button>
          </>
        )}
        {canApprove && report.status === "approved" && (
          <Button
            variant="ghost"
            onClick={() => {
              if (window.confirm(t("report.confirmReopen")))
                transition.mutate({ action: "reopen" });
            }}
            disabled={pending}
          >
            {t("tor.reopen")}
          </Button>
        )}
        <span className="flex-1" />
        <Button variant="ghost" onClick={() => exportFile.mutate("docx")} disabled={dirty}>
          ⬇ Word
        </Button>
        <Button variant="ghost" onClick={() => exportFile.mutate("pdf")} disabled={dirty}>
          ⬇ PDF
        </Button>
        {canApprove && (
          <Button
            variant="danger"
            onClick={() => {
              if (window.confirm(t("report.confirmDelete"))) remove.mutate();
            }}
          >
            {t("logframe.delete")}
          </Button>
        )}
        {review && (
          <ReviewBox
            action={review}
            onDone={(comment) => transition.mutate({ action: review, comment })}
          />
        )}
      </div>
      <ErrorText error={save.error ?? transition.error ?? exportFile.error ?? remove.error} />

      {report.status === "submitted" && !canApprove && (
        <p className="mt-2 text-sm text-slate-600">{t("tor.awaitingApproval")}</p>
      )}
      {report.review_comment && (
        <p className="mt-3 rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
          <span className="font-medium">{t("tor.reviewComment")} : </span>
          {report.review_comment}
        </p>
      )}
      {report.missing_information.length > 0 && (
        <div className="mt-3 rounded-md border border-amber-200 bg-amber-50 p-3 text-sm">
          <p className="font-medium text-amber-900">{t("tor.missing")}</p>
          <ul className="mt-1 list-disc pl-5 text-amber-900">
            {report.missing_information.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
      )}
      {unknownRefs && (
        <p role="alert" className="mt-3 text-sm text-red-700">
          {t("report.unknownSource")}
        </p>
      )}
      <Suggestions orgId={orgId} projectId={projectId} report={report} />

      <ol className="mt-6 space-y-6">
        {sections.map((section, index) => (
          <li key={section.key}>
            <h3 className="mb-1.5 text-sm font-semibold text-brand-800">
              {index + 1}. {section.title}
            </h3>
            {editing ? (
              <>
                <textarea
                  aria-label={section.title}
                  className="w-full rounded-md border border-slate-300 px-3 py-2 font-mono text-[13px] leading-relaxed"
                  rows={Math.min(18, Math.max(3, section.content.split("\n").length + 1))}
                  value={section.content}
                  onChange={(e) =>
                    setSections(
                      sections.map((s, i) => (i === index ? { ...s, content: e.target.value } : s)),
                    )
                  }
                />
                {COMPUTED.has(section.key) && (
                  <p className="text-xs text-slate-500">{t("report.computedHint")}</p>
                )}
              </>
            ) : section.content.trim() ? (
              <Markdown source={section.content} />
            ) : (
              <p className="text-sm text-slate-400">–</p>
            )}
          </li>
        ))}
      </ol>
      {editing && <p className="mt-4 text-xs text-slate-500">{t("tor.formatHint")}</p>}

      {report.sources.length > 0 && (
        <div className="mt-6 border-t border-slate-100 pt-4">
          <p className="text-sm font-semibold text-slate-700">{t("report.sources")}</p>
          <ul className="mt-1 space-y-0.5 text-xs text-slate-600">
            {report.sources.map((source) => (
              <li key={source.ref}>
                <span className="mr-1.5 font-mono font-semibold text-brand-700">
                  [{source.ref}]
                </span>
                {source.label}
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="mt-4 border-t border-slate-100 pt-3">
        <button
          className="text-sm font-medium text-brand-700 hover:underline"
          onClick={() => setShowVersions(!showVersions)}
        >
          {showVersions ? "▾" : "▸"} {t("tor.versions")}
        </button>
        {showVersions && versions.data && (
          <ul className="mt-2 space-y-1 text-xs text-slate-600">
            {versions.data.map((version) => (
              <li key={version.id}>
                v{version.version} · {dates.format(new Date(version.created_at))} · {version.note}
              </li>
            ))}
          </ul>
        )}
      </div>
    </Card>
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
      <ReportEditor
        key={`${report.data.id}-${report.data.version}-${report.data.status}`}
        orgId={orgId}
        projectId={projectId}
        report={report.data}
        onRegenerate={() => generate.mutate()}
        busy={busy}
      />
    </>
  );
}
