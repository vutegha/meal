import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useSearch } from "@tanstack/react-router";
import { type FormEvent, useState } from "react";
import { useTranslation } from "react-i18next";

import { Button, Card, ErrorText, Field, Select } from "@/components/ui";
import { useCurrentOrg } from "@/features/orgs/useCurrentOrg";
import { lastPeriod } from "@/lib/accountability";
import { PERIODIC_KINDS, type PeriodicKind, periodicApi, type Project } from "@/lib/api";
import { permissions } from "@/lib/permissions";
import { periodicListQuery, periodicQuery } from "@/lib/queries";

import { DocumentEditor } from "./DocumentEditor";
import { TorBadge } from "./TorTab";
import { useInvalidateProject } from "./useInvalidateProject";
import { useJob } from "./useJob";

const COMPUTED = new Set(["activites", "indicateurs", "budget"]);

type Tracker = ReturnType<typeof useJob>;

function NewPeriodic({
  project,
  tracker,
  onDone,
}: {
  project: Project;
  tracker: Tracker;
  onDone: () => void;
}) {
  const { t } = useTranslation();
  const { orgId } = useCurrentOrg();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [kind, setKind] = useState<PeriodicKind>("quarterly");
  const [[start, end], setPeriod] = useState(() => lastPeriod("quarterly", project));
  const [instructions, setInstructions] = useState("");
  const [withAi, setWithAi] = useState(true);
  const create = useMutation({
    mutationFn: async () => {
      const report = await periodicApi.create(orgId, project.id, {
        kind,
        period_start: start,
        period_end: end,
        instructions,
      });
      if (withAi) tracker.start(await periodicApi.generate(orgId, project.id, report.id));
      return report;
    },
    onSuccess: async (report) => {
      await queryClient.invalidateQueries({
        queryKey: periodicListQuery(orgId, project.id).queryKey,
      });
      await navigate({ to: ".", search: { tab: "reports", periodic: report.id } });
      onDone();
    },
  });
  const submit = (event: FormEvent) => {
    event.preventDefault();
    create.mutate();
  };
  return (
    <form onSubmit={submit} className="mb-4 space-y-3 rounded-md border border-slate-200 p-4">
      <div className="grid gap-3 sm:grid-cols-3">
        <Select
          label={t("periodic.kind")}
          value={kind}
          onChange={(e) => {
            const next = e.target.value as PeriodicKind;
            setKind(next);
            setPeriod(lastPeriod(next, project));
          }}
        >
          {PERIODIC_KINDS.map((value) => (
            <option key={value} value={value}>
              {t(`periodic.kinds.${value}`)}
            </option>
          ))}
        </Select>
        <Field
          label={t("periodic.start")}
          type="date"
          required
          value={start}
          onChange={(e) => setPeriod([e.target.value, end])}
        />
        <Field
          label={t("periodic.end")}
          type="date"
          required
          min={start}
          value={end}
          onChange={(e) => setPeriod([start, e.target.value])}
        />
      </div>
      <label className="block text-sm font-medium text-slate-700">
        {t("tor.instructions")}
        <textarea
          className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm font-normal"
          rows={2}
          placeholder={t("periodic.instructionsPlaceholder")}
          value={instructions}
          onChange={(e) => setInstructions(e.target.value)}
        />
      </label>
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={withAi} onChange={(e) => setWithAi(e.target.checked)} />
        {t("periodic.withAi")}
      </label>
      <ErrorText error={create.error} />
      <div className="flex gap-2">
        <Button type="submit" disabled={create.isPending}>
          {t("periodic.create")}
        </Button>
        <Button type="button" variant="ghost" onClick={onDone}>
          {t("common.cancel")}
        </Button>
      </div>
    </form>
  );
}

function PeriodicList({ project, tracker }: { project: Project; tracker: Tracker }) {
  const { t, i18n } = useTranslation();
  const { orgId, role } = useCurrentOrg();
  const navigate = useNavigate();
  const reports = useQuery(periodicListQuery(orgId, project.id));
  const [adding, setAdding] = useState(false);
  const dates = new Intl.DateTimeFormat(i18n.language, { dateStyle: "medium" });
  return (
    <Card title={t("periodic.title")}>
      <p className="mb-3 text-sm text-slate-600">{t("periodic.intro")}</p>
      {permissions.plan(role) && !adding && (
        <Button className="mb-3" onClick={() => setAdding(true)}>
          + {t("periodic.new")}
        </Button>
      )}
      {adding && (
        <NewPeriodic project={project} tracker={tracker} onDone={() => setAdding(false)} />
      )}
      <ErrorText error={reports.error} />
      {reports.data?.length ? (
        <ul className="divide-y divide-slate-100">
          {reports.data.map((report) => (
            <li key={report.id}>
              <button
                className="flex w-full flex-wrap items-center gap-x-3 gap-y-1 py-2.5 text-left hover:bg-slate-50"
                onClick={() =>
                  navigate({ to: ".", search: { tab: "reports", periodic: report.id } })
                }
              >
                <span className="text-xs text-slate-500 sm:w-24">
                  {t(`periodic.kinds.${report.kind}`)}
                </span>
                <span className="min-w-0 flex-1 text-sm">{report.title}</span>
                <span className="text-xs text-slate-500">
                  {dates.format(new Date(report.period_start))} –{" "}
                  {dates.format(new Date(report.period_end))}
                </span>
                <TorBadge status={report.status} />
              </button>
            </li>
          ))}
        </ul>
      ) : (
        !reports.isPending && <p className="text-sm text-slate-500">{t("periodic.empty")}</p>
      )}
    </Card>
  );
}

function PeriodicView({
  project,
  reportId,
  tracker: job,
}: {
  project: Project;
  reportId: string;
  tracker: Tracker;
}) {
  const { t } = useTranslation();
  const { orgId, role } = useCurrentOrg();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const invalidate = useInvalidateProject(orgId, project.id);
  const report = useQuery(periodicQuery(orgId, project.id, reportId));
  const generate = useMutation({
    mutationFn: () => periodicApi.generate(orgId, project.id, reportId),
    onSuccess: job.start,
  });
  const refresh = useMutation({
    mutationFn: () => periodicApi.refresh(orgId, project.id, reportId),
    onSuccess: invalidate,
  });
  const busy = generate.isPending || job.running || refresh.isPending;
  const doc = report.data;

  return (
    <>
      <Link to="." search={{ tab: "reports" }} className="text-sm text-brand-700 hover:underline">
        ← {t("periodic.back")}
      </Link>
      {busy && (
        <p role="status" className="text-sm text-slate-600">
          {t("periodic.running")}
        </p>
      )}
      <ErrorText error={report.error ?? generate.error ?? job.error ?? refresh.error} />
      {doc && (
        <DocumentEditor
          key={`${doc.id}-${doc.version}-${doc.status}`}
          doc={doc}
          label={t(`periodic.kinds.${doc.kind}`)}
          computedKeys={COMPUTED}
          filename="Rapport-periodique"
          save={(body) => periodicApi.update(orgId, project.id, doc.id, body)}
          transition={(action, comment) =>
            periodicApi.transition(orgId, project.id, doc.id, action, comment)
          }
          remove={async () => {
            await periodicApi.remove(orgId, project.id, doc.id);
            await navigate({ to: ".", search: { tab: "reports" } });
            queryClient.removeQueries({
              queryKey: periodicQuery(orgId, project.id, doc.id).queryKey,
            });
          }}
          exportPath={(format) => periodicApi.exportPath(orgId, project.id, doc.id, format)}
          loadVersions={() => periodicApi.versions(orgId, project.id, doc.id)}
          onRegenerate={() => generate.mutate()}
          busy={busy}
          onChanged={invalidate}
          toolbar={
            permissions.plan(role) && (
              <Button variant="ghost" onClick={() => refresh.mutate()} disabled={busy}>
                ↻ {t("periodic.refresh")}
              </Button>
            )
          }
        />
      )}
    </>
  );
}

export function PeriodicTab({ project }: { project: Project }) {
  const { periodic } = useSearch({ from: "/orgs/$orgId/projects/$projectId" });
  const { orgId } = useCurrentOrg();
  // Suivi de la rédaction IA, partagé entre la liste (création) et le rapport ouvert.
  const tracker = useJob(orgId, useInvalidateProject(orgId, project.id));
  return periodic ? (
    <PeriodicView project={project} reportId={periodic} tracker={tracker} />
  ) : (
    <PeriodicList project={project} tracker={tracker} />
  );
}
