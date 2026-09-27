import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { type FormEvent, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { Button, Card, ErrorText, Field, Select } from "@/components/ui";
import { useCurrentOrg } from "@/features/orgs/useCurrentOrg";
import {
  download,
  type Evidence,
  type ExecutionDetail as Detail,
  executionsApi,
  fetchBlob,
  type Project,
} from "@/lib/api";
import { flattenTree, formatMoney, formatRate } from "@/lib/format";
import { discard, type FileToSend, queueEvidence, syncOutbox, usePending } from "@/lib/outbox";
import { permissions } from "@/lib/permissions";
import { budgetLinesQuery, executionQuery, logframeQuery } from "@/lib/queries";

import { FilePicker } from "./ExecutionForm";
import { ExecutionBadge } from "./ExecutionBadge";
import { ReportPanel } from "./ReportPanel";

/** Image protégée : chargée avec le jeton de l'utilisateur, puis affichée depuis la mémoire. */
function AuthImage({ path, alt, version = "" }: { path: string; alt: string; version?: string }) {
  const blob = useQuery({
    queryKey: ["blob", path, version],
    queryFn: () => fetchBlob(path),
    staleTime: Infinity,
  });
  const [url, setUrl] = useState<string>();
  useEffect(() => {
    if (!blob.data) return;
    const objectUrl = URL.createObjectURL(blob.data);
    // eslint-disable-next-line react-hooks/set-state-in-effect -- l'URL dépend d'une ressource externe à libérer
    setUrl(objectUrl);
    return () => URL.revokeObjectURL(objectUrl);
  }, [blob.data]);
  if (!url) return <div className="aspect-[4/3] w-full animate-pulse rounded bg-slate-100" />;
  return <img src={url} alt={alt} className="aspect-[4/3] w-full rounded object-cover" />;
}

function EvidenceItem({
  evidence,
  orgId,
  projectId,
  canCollect,
  onChanged,
}: {
  evidence: Evidence;
  orgId: string;
  projectId: string;
  canCollect: boolean;
  onChanged: () => Promise<unknown>;
}) {
  const { t, i18n } = useTranslation();
  const path = (variant: "file" | "thumbnail") =>
    executionsApi.evidencePath(orgId, projectId, evidence.id, variant);
  const toggleConsent = useMutation({
    mutationFn: () =>
      executionsApi.updateEvidence(orgId, projectId, evidence.id, {
        consent_given: !evidence.consent_given,
      }),
    onSuccess: onChanged,
  });
  const toggleBlur = useMutation({
    mutationFn: () =>
      executionsApi.updateEvidence(orgId, projectId, evidence.id, {
        blur_faces: !evidence.blur_faces,
      }),
    onSuccess: onChanged,
  });
  const { role } = useCurrentOrg();
  const remove = useMutation({
    mutationFn: () => executionsApi.removeEvidence(orgId, projectId, evidence.id),
    onSuccess: onChanged,
  });
  const open = useMutation({ mutationFn: () => download(path("file"), evidence.filename) });
  const dates = new Intl.DateTimeFormat(i18n.language, { dateStyle: "medium", timeStyle: "short" });

  return (
    <li className="space-y-1 text-sm">
      {evidence.has_thumbnail ? (
        <button className="block w-full" onClick={() => open.mutate()} title={evidence.filename}>
          <AuthImage
            path={path("thumbnail")}
            alt={evidence.caption || evidence.filename}
            version={`${evidence.blur_faces}-${evidence.consent_given}`}
          />
        </button>
      ) : (
        <button
          className="flex aspect-[4/3] w-full flex-col items-center justify-center rounded bg-slate-50 p-2 text-center text-xs text-slate-600 hover:bg-slate-100"
          onClick={() => open.mutate()}
        >
          <span className="text-2xl">📄</span>
          <span className="line-clamp-2 break-all">{evidence.filename}</span>
        </button>
      )}
      <p className="text-xs font-medium text-slate-700">
        {t(`execution.kinds.${evidence.kind}`)}
        {evidence.caption && ` · ${evidence.caption}`}
      </p>
      <p className="text-xs text-slate-500">
        {evidence.taken_at && dates.format(new Date(evidence.taken_at))}
        {evidence.latitude &&
          ` · 📍 ${Number(evidence.latitude).toFixed(4)}, ${Number(evidence.longitude).toFixed(4)}`}
        {evidence.page_count > 0 && t("documents.pages", { count: evidence.page_count })}
      </p>
      {evidence.kind === "photo" && (
        <p className={`text-xs ${evidence.consent_given ? "text-emerald-700" : "text-amber-700"}`}>
          {evidence.consent_given
            ? `✓ ${t("execution.consentOk")}`
            : `⚠ ${t("execution.consentMissing")}`}
          {canCollect && (
            <button
              className="ml-2 text-brand-700 underline"
              onClick={() => toggleConsent.mutate()}
              disabled={toggleConsent.isPending}
            >
              {t("execution.change")}
            </button>
          )}
        </p>
      )}
      {evidence.faces > 0 && (
        <p className="text-xs text-slate-600">
          {evidence.blur_faces
            ? t("execution.facesBlurred", { count: evidence.faces })
            : t("execution.facesVisible", { count: evidence.faces })}
          {permissions.plan(role) && (evidence.blur_faces ? evidence.consent_given : true) && (
            <button
              className="ml-2 text-brand-700 underline"
              onClick={() => toggleBlur.mutate()}
              disabled={toggleBlur.isPending}
            >
              {evidence.blur_faces ? t("execution.showFaces") : t("execution.blurFaces")}
            </button>
          )}
        </p>
      )}
      {canCollect && (
        <button
          className="text-xs text-red-700"
          onClick={() => {
            if (window.confirm(t("execution.confirmDeleteEvidence"))) remove.mutate();
          }}
        >
          {t("logframe.delete")}
        </button>
      )}
      <ErrorText error={toggleConsent.error ?? toggleBlur.error ?? remove.error ?? open.error} />
    </li>
  );
}

function ExpenseForm({
  orgId,
  project,
  detail,
  onDone,
}: {
  orgId: string;
  project: Project;
  detail: Detail;
  onDone: () => Promise<unknown>;
}) {
  const { t } = useTranslation();
  const lines = useQuery(budgetLinesQuery(orgId, project.id));
  const children = new Set(
    flattenTree(useQuery(logframeQuery(orgId, project.id)).data ?? [])
      .filter((n) => n.parent_id === detail.activity_id)
      .map((n) => n.id),
  );
  const own = (lines.data ?? []).filter(
    (l) => l.activity_id === detail.activity_id || children.has(l.activity_id ?? ""),
  );
  const others = (lines.data ?? []).filter((l) => !own.includes(l));
  const [lineId, setLineId] = useState("");
  const [amount, setAmount] = useState("");
  const [spentOn, setSpentOn] = useState(detail.end_date ?? detail.start_date);
  const [reference, setReference] = useState("");
  const add = useMutation({
    mutationFn: () =>
      executionsApi.addExpense(orgId, project.id, detail.id, {
        budget_line_id: lineId,
        amount,
        spent_on: spentOn,
        reference,
      }),
    onSuccess: async () => {
      setAmount("");
      setReference("");
      await onDone();
    },
  });
  const submit = (event: FormEvent) => {
    event.preventDefault();
    add.mutate();
  };
  return (
    <form onSubmit={submit} className="mt-3 grid gap-2 sm:grid-cols-5 sm:items-end">
      <div className="sm:col-span-2">
        <Select
          label={t("budget.lines")}
          required
          value={lineId}
          onChange={(e) => setLineId(e.target.value)}
        >
          <option value="">–</option>
          {own.map((l) => (
            <option key={l.id} value={l.id}>
              {l.donor_line_code} {l.label}
            </option>
          ))}
          {others.length > 0 && (
            <optgroup label={t("execution.otherLines")}>
              {others.map((l) => (
                <option key={l.id} value={l.id}>
                  {l.donor_line_code} {l.label}
                </option>
              ))}
            </optgroup>
          )}
        </Select>
      </div>
      <Field
        label={`${t("budget.amount")} (${project.currency})`}
        type="number"
        min="0.01"
        step="0.01"
        required
        value={amount}
        onChange={(e) => setAmount(e.target.value)}
      />
      <Field
        label={t("budget.date")}
        type="date"
        required
        value={spentOn}
        onChange={(e) => setSpentOn(e.target.value)}
      />
      <Field
        label={t("budget.reference")}
        value={reference}
        onChange={(e) => setReference(e.target.value)}
      />
      <div className="sm:col-span-5">
        <Button type="submit" disabled={add.isPending}>
          {t("budget.record")}
        </Button>
        <ErrorText error={add.error} />
      </div>
    </form>
  );
}

export function ExecutionDetailView({
  orgId,
  project,
  executionId,
}: {
  orgId: string;
  project: Project;
  executionId: string;
}) {
  const { t, i18n } = useTranslation();
  const queryClient = useQueryClient();
  const { role } = useCurrentOrg();
  const canCollect = permissions.recordValues(role);
  const canSpend = canCollect || permissions.editBudget(role);
  const detail = useQuery(executionQuery(orgId, project.id, executionId));
  const logframe = useQuery(logframeQuery(orgId, project.id));
  const lines = useQuery(budgetLinesQuery(orgId, project.id));
  const pending = usePending(project.id).evidence.filter((e) => e.execution_id === executionId);
  const [files, setFiles] = useState<FileToSend[]>([]);
  const [queued, setQueued] = useState(false);
  const refresh = () =>
    queryClient.invalidateQueries({ queryKey: ["orgs", orgId, "projects", project.id] });

  const complete = useMutation({
    mutationFn: () => executionsApi.update(orgId, project.id, executionId, { status: "completed" }),
    onSuccess: refresh,
  });
  const sendFiles = useMutation({
    // Les fichiers vont d'abord dans la file locale : l'envoi doit démarrer sans réseau.
    networkMode: "always",
    mutationFn: async () => {
      await queueEvidence(orgId, project.id, executionId, files);
      setFiles([]);
      const result = navigator.onLine ? await syncOutbox() : { offline: true };
      setQueued(result.offline);
      if (!result.offline) await refresh();
    },
  });

  if (detail.isPending) return <p className="text-sm text-slate-500">{t("common.loading")}</p>;
  if (!detail.data) return <ErrorText error={detail.error} />;
  const d = detail.data;
  const activity = flattenTree(logframe.data ?? []).find((n) => n.id === d.activity_id);
  const lineLabels = new Map(
    (lines.data ?? []).map((l) => [l.id, `${l.donor_line_code} ${l.label}`]),
  );
  const dates = new Intl.DateTimeFormat(i18n.language, { dateStyle: "medium" });
  const money = (value: string | number) => formatMoney(value, project.currency, i18n.language);
  const photos = d.evidence.filter((e) => e.has_thumbnail);
  const documents = d.evidence.filter((e) => !e.has_thumbnail);
  const rate = Number(d.planned) > 0 ? Number(d.spent) / Number(d.planned) : null;

  return (
    <>
      <Link to="." search={{ tab: "execution" }} className="text-sm text-brand-700 hover:underline">
        ← {t("execution.back")}
      </Link>
      <Card>
        <div className="flex flex-wrap items-start gap-3">
          <div className="min-w-0 flex-1">
            <p className="font-mono text-xs text-slate-500">
              {activity?.code} {activity?.title}
            </p>
            <h2 className="text-lg font-semibold">{d.title || activity?.title}</h2>
            <p className="text-sm text-slate-600">
              {dates.format(new Date(d.start_date))}
              {d.end_date &&
                d.end_date !== d.start_date &&
                ` – ${dates.format(new Date(d.end_date))}`}
              {d.location && ` · ${d.location}`}
              {d.latitude && (
                <>
                  {" · "}
                  <a
                    className="text-brand-700 underline"
                    href={`https://www.openstreetmap.org/?mlat=${d.latitude}&mlon=${d.longitude}#map=14/${d.latitude}/${d.longitude}`}
                    target="_blank"
                    rel="noreferrer"
                  >
                    {t("execution.map")}
                  </a>
                </>
              )}
            </p>
          </div>
          <ExecutionBadge status={d.status} />
          {canCollect && d.status === "in_progress" && (
            <Button variant="ghost" onClick={() => complete.mutate()} disabled={complete.isPending}>
              {t("execution.markCompleted")}
            </Button>
          )}
        </div>
        <ErrorText error={complete.error} />
        <dl className="mt-4 grid grid-cols-3 gap-2 text-center sm:grid-cols-6">
          {(["women", "men", "girls", "boys", "with_disability"] as const).map((key) => (
            <div key={key} className="rounded bg-slate-50 p-2">
              <dt className="text-xs text-slate-500">{t(`execution.people.${key}`)}</dt>
              <dd className="text-lg font-semibold">{d.participants[key]}</dd>
            </div>
          ))}
          <div className="rounded bg-brand-50 p-2">
            <dt className="text-xs text-slate-500">{t("execution.total")}</dt>
            <dd className="text-lg font-semibold text-brand-800">{d.participants_total}</dd>
          </div>
        </dl>
        {d.notes && (
          <div className="mt-4">
            <p className="text-sm font-medium text-slate-700">{t("execution.notes")}</p>
            <p className="whitespace-pre-line text-sm text-slate-700">{d.notes}</p>
          </div>
        )}
      </Card>

      <Card title={t("execution.evidence")}>
        {photos.length + documents.length === 0 && pending.length === 0 && (
          <p className="text-sm text-slate-500">{t("execution.noEvidence")}</p>
        )}
        {photos.length > 0 && (
          <ul className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            {photos.map((e) => (
              <EvidenceItem
                key={e.id}
                evidence={e}
                orgId={orgId}
                projectId={project.id}
                canCollect={canCollect}
                onChanged={refresh}
              />
            ))}
          </ul>
        )}
        {documents.length > 0 && (
          <ul className="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-4">
            {documents.map((e) => (
              <EvidenceItem
                key={e.id}
                evidence={e}
                orgId={orgId}
                projectId={project.id}
                canCollect={canCollect}
                onChanged={refresh}
              />
            ))}
          </ul>
        )}
        {pending.length > 0 && (
          <ul className="mt-4 space-y-1 text-sm">
            {pending.map((p) => (
              <li key={p.client_uuid} className="flex gap-2 text-amber-800">
                ⏳ {p.filename} · {p.error ?? t("execution.pending")}
                {p.error && (
                  <button
                    className="text-red-700 underline"
                    onClick={() => discard("evidence", p.client_uuid)}
                  >
                    {t("execution.discard")}
                  </button>
                )}
              </li>
            ))}
          </ul>
        )}
        {canCollect && (
          <div className="mt-4 border-t border-slate-100 pt-4">
            <FilePicker files={files} onChange={setFiles} />
            {files.length > 0 && (
              <Button
                className="mt-2"
                onClick={() => sendFiles.mutate()}
                disabled={sendFiles.isPending}
              >
                {t("execution.sendFiles", { count: files.length })}
              </Button>
            )}
            {queued && <p className="mt-2 text-sm text-amber-800">{t("execution.queued")}</p>}
            <ErrorText error={sendFiles.error} />
          </div>
        )}
      </Card>

      <Card title={t("execution.costs")}>
        <p className="text-sm text-slate-700">
          {t("execution.plannedVsSpent", {
            planned: money(d.planned),
            spent: money(d.spent),
            rate: formatRate(rate, i18n.language),
          })}
        </p>
        {d.expenses.length > 0 && (
          <ul className="mt-2 divide-y divide-slate-100 text-sm">
            {d.expenses.map((e) => (
              <li key={e.id} className="flex flex-wrap gap-x-3 py-1.5">
                <span className="text-slate-500">{dates.format(new Date(e.spent_on))}</span>
                <span className="flex-1">{lineLabels.get(e.budget_line_id)}</span>
                {e.reference && <span className="text-xs text-slate-500">{e.reference}</span>}
                <span className="font-medium tabular-nums">{money(e.amount)}</span>
              </li>
            ))}
          </ul>
        )}
        {canSpend && <ExpenseForm orgId={orgId} project={project} detail={d} onDone={refresh} />}
      </Card>

      <ReportPanel orgId={orgId} projectId={project.id} executionId={d.id} />
    </>
  );
}
