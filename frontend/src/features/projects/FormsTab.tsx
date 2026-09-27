import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useSearch } from "@tanstack/react-router";
import { type FormEvent, useState } from "react";
import { useTranslation } from "react-i18next";

import { Button, Card, ErrorText, Field, Select } from "@/components/ui";
import { useCurrentOrg } from "@/features/orgs/useCurrentOrg";
import {
  type CollectionForm,
  download,
  FIELD_TYPES,
  type FieldSummary,
  type FieldType,
  type FormField,
  type FormInput,
  type FormStatus,
  formsApi,
} from "@/lib/api";
import { flattenTree } from "@/lib/format";
import {
  blankField,
  type Draft,
  emptyDraft,
  formatAnswer,
  toAnswers,
  withKeys,
  withOptions,
} from "@/lib/forms";
import { discard, newId, queueSubmission, syncOutbox, usePending } from "@/lib/outbox";
import { permissions } from "@/lib/permissions";
import {
  formQuery,
  formsQuery,
  formSummaryQuery,
  logframeQuery,
  submissionsQuery,
} from "@/lib/queries";
import { move } from "@/lib/templates";
import { useOnline } from "@/lib/useOnline";

import { useInvalidateProject } from "./useInvalidateProject";

const statusStyles: Record<FormStatus, string> = {
  draft: "bg-slate-100 text-slate-700",
  published: "bg-emerald-100 text-emerald-800",
  closed: "bg-amber-100 text-amber-800",
};

function FormStatusBadge({ status }: { status: FormStatus }) {
  const { t } = useTranslation();
  return (
    <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${statusStyles[status]}`}>
      {t(`forms.status.${status}`)}
    </span>
  );
}

function useActivities(orgId: string, projectId: string) {
  const logframe = useQuery(logframeQuery(orgId, projectId));
  return flattenTree(logframe.data ?? []).filter(
    (n) => n.level === "activity" || n.level === "sub_activity",
  );
}

// --- Conception ---------------------------------------------------------------------------

function FieldEditor({
  field,
  index,
  count,
  locked,
  onChange,
  onMove,
  onRemove,
}: {
  field: FormField;
  index: number;
  count: number;
  locked: boolean;
  onChange: (patch: Partial<FormField>) => void;
  onMove: (delta: -1 | 1) => void;
  onRemove: () => void;
}) {
  const { t } = useTranslation();
  const [options, setOptions] = useState(field.options.join("\n"));
  return (
    <fieldset className="space-y-3 rounded-md border border-slate-200 p-3">
      <legend className="px-1 text-xs font-medium text-slate-500">
        {t("forms.question", { n: index + 1 })}
      </legend>
      <div className="grid gap-3 sm:grid-cols-[1fr_12rem]">
        <Field
          label={t("forms.label")}
          required
          value={field.label}
          onChange={(e) => onChange({ label: e.target.value })}
        />
        <Select
          label={t("forms.type")}
          value={field.type}
          disabled={locked}
          onChange={(e) => onChange({ type: e.target.value as FieldType })}
        >
          {FIELD_TYPES.map((type) => (
            <option key={type} value={type}>
              {t(`forms.types.${type}`)}
            </option>
          ))}
        </Select>
      </div>
      {withOptions(field.type) && (
        <label className="block text-sm font-medium text-slate-700">
          {t("forms.options")}
          <textarea
            className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm font-normal"
            rows={3}
            required
            disabled={locked}
            value={options}
            onChange={(e) => {
              setOptions(e.target.value);
              onChange({ options: e.target.value.split("\n").map((o) => o.trim()) });
            }}
          />
        </label>
      )}
      <Field
        label={t("forms.hint")}
        value={field.hint}
        onChange={(e) => onChange({ hint: e.target.value })}
      />
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <label className="flex items-center gap-2">
          <input
            type="checkbox"
            checked={field.required}
            onChange={(e) => onChange({ required: e.target.checked })}
          />
          {t("forms.required")}
        </label>
        <span className="flex-1" />
        {!locked && (
          <>
            <Button
              type="button"
              variant="ghost"
              aria-label={t("templates.up")}
              disabled={index === 0}
              onClick={() => onMove(-1)}
            >
              ↑
            </Button>
            <Button
              type="button"
              variant="ghost"
              aria-label={t("templates.down")}
              disabled={index === count - 1}
              onClick={() => onMove(1)}
            >
              ↓
            </Button>
            <Button type="button" variant="danger" disabled={count === 1} onClick={onRemove}>
              {t("common.remove")}
            </Button>
          </>
        )}
      </div>
    </fieldset>
  );
}

function FormBuilder({
  orgId,
  projectId,
  form,
  onDone,
}: {
  orgId: string;
  projectId: string;
  form?: CollectionForm;
  onDone: (id: string | null) => void;
}) {
  const { t } = useTranslation();
  const invalidate = useInvalidateProject(orgId, projectId);
  const activities = useActivities(orgId, projectId);
  // Une fois des réponses reçues, les questions gardent leur clé, leur type et leurs choix.
  const locked = !!form?.submissions;
  const [draft, setDraft] = useState<FormInput>(() =>
    form
      ? {
          title: form.title,
          description: form.description,
          activity_id: form.activity_id,
          fields: form.fields,
        }
      : { title: "", description: "", activity_id: null, fields: [blankField([])] },
  );
  // Identifiants d'affichage stables pendant la conception (les clés changent avec les libellés).
  const [ids, setIds] = useState<string[]>(() => draft.fields.map(() => newId()));
  const save = useMutation({
    mutationFn: () => {
      const body = { ...draft, fields: withKeys(draft.fields, locked) };
      return form
        ? formsApi.update(orgId, projectId, form.id, body)
        : formsApi.create(orgId, projectId, body);
    },
    onSuccess: async (saved) => {
      await invalidate();
      onDone(saved.id);
    },
  });
  const setFields = (fields: FormField[], nextIds: string[]) => {
    setDraft({ ...draft, fields });
    setIds(nextIds);
  };
  const submit = (event: FormEvent) => {
    event.preventDefault();
    save.mutate();
  };

  return (
    <form onSubmit={submit} className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-2">
        <Field
          label={t("forms.title")}
          required
          minLength={3}
          value={draft.title}
          onChange={(e) => setDraft({ ...draft, title: e.target.value })}
        />
        <Select
          label={t("execution.activity")}
          value={draft.activity_id ?? ""}
          onChange={(e) => setDraft({ ...draft, activity_id: e.target.value || null })}
        >
          <option value="">–</option>
          {activities.map((activity) => (
            <option key={activity.id} value={activity.id}>
              {activity.code} {activity.title}
            </option>
          ))}
        </Select>
      </div>
      <label className="block text-sm font-medium text-slate-700">
        {t("forms.description")}
        <textarea
          className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm font-normal"
          rows={2}
          value={draft.description}
          onChange={(e) => setDraft({ ...draft, description: e.target.value })}
        />
      </label>
      {locked && (
        <p className="rounded-md bg-amber-50 p-2 text-sm text-amber-800">{t("forms.locked")}</p>
      )}
      {draft.fields.map((field, index) => (
        <FieldEditor
          key={ids[index]}
          field={field}
          index={index}
          count={draft.fields.length}
          locked={locked}
          onChange={(patch) =>
            setFields(
              draft.fields.map((f, i) => (i === index ? { ...f, ...patch } : f)),
              ids,
            )
          }
          onMove={(delta) => setFields(move(draft.fields, index, delta), move(ids, index, delta))}
          onRemove={() =>
            setFields(
              draft.fields.filter((_, i) => i !== index),
              ids.filter((_, i) => i !== index),
            )
          }
        />
      ))}
      {!locked && (
        <Button
          type="button"
          variant="ghost"
          onClick={() =>
            setFields(
              [...draft.fields, blankField(draft.fields.map((f) => f.key))],
              [...ids, newId()],
            )
          }
        >
          + {t("forms.addQuestion")}
        </Button>
      )}
      <ErrorText error={save.error} />
      <div className="flex gap-2">
        <Button type="submit" disabled={save.isPending}>
          {t("common.save")}
        </Button>
        <Button type="button" variant="ghost" onClick={() => onDone(null)}>
          {t("common.cancel")}
        </Button>
      </div>
    </form>
  );
}

// --- Saisie -------------------------------------------------------------------------------

function AnswerInput({
  field,
  value,
  onChange,
}: {
  field: FormField;
  value: Draft;
  onChange: (value: Draft) => void;
}) {
  const { t } = useTranslation();
  const legend = (
    <>
      {field.label}
      {field.required && <span className="text-red-700"> *</span>}
    </>
  );
  const hint = field.hint && <p className="text-xs font-normal text-slate-500">{field.hint}</p>;
  if (field.type === "yesno" || field.type === "select" || field.type === "multiselect") {
    const choices: [string, Draft][] =
      field.type === "yesno"
        ? [
            [t("forms.yes"), true],
            [t("forms.no"), false],
          ]
        : field.options.map((o) => [o, o]);
    const multiple = field.type === "multiselect";
    const selected = (choice: Draft) =>
      multiple ? (value as string[]).includes(choice as string) : value === choice;
    return (
      <fieldset className="space-y-1">
        <legend className="text-sm font-medium text-slate-700">{legend}</legend>
        {hint}
        <div className="flex flex-wrap gap-x-4 gap-y-1">
          {choices.map(([label, choice]) => (
            <label key={label} className="flex items-center gap-2 text-sm">
              <input
                type={multiple ? "checkbox" : "radio"}
                name={field.key}
                required={field.required && !multiple}
                checked={selected(choice)}
                onChange={(e) => {
                  if (!multiple) return onChange(choice);
                  const current = value as string[];
                  onChange(
                    e.target.checked
                      ? [...current, choice as string]
                      : current.filter((v) => v !== choice),
                  );
                }}
              />
              {label}
            </label>
          ))}
        </div>
      </fieldset>
    );
  }
  const input = {
    text: { type: "text" },
    number: { type: "number", step: "any" },
    integer: { type: "number", step: 1 },
    date: { type: "date" },
  }[field.type];
  return (
    <label className="block space-y-1 text-sm font-medium text-slate-700">
      <span>{legend}</span>
      {hint}
      <input
        {...input}
        className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm font-normal"
        required={field.required}
        value={value as string}
        onChange={(e) => onChange(e.target.value)}
      />
    </label>
  );
}

function FillForm({
  orgId,
  projectId,
  form,
  onDone,
}: {
  orgId: string;
  projectId: string;
  form: CollectionForm;
  onDone: (result: "sent" | "queued" | null) => void;
}) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const initial = () => Object.fromEntries(form.fields.map((f) => [f.key, emptyDraft(f)]));
  const [drafts, setDrafts] = useState<Record<string, Draft>>(initial);
  const [location, setLocation] = useState("");
  const [position, setPosition] = useState<{ latitude: number; longitude: number } | null>(null);
  const [locating, setLocating] = useState(false);
  const [error, setError] = useState("");
  const locate = () => {
    setLocating(true);
    navigator.geolocation.getCurrentPosition(
      ({ coords }) => {
        setPosition({
          latitude: Number(coords.latitude.toFixed(6)),
          longitude: Number(coords.longitude.toFixed(6)),
        });
        setLocating(false);
      },
      () => {
        setError(t("execution.noPosition"));
        setLocating(false);
      },
      { enableHighAccuracy: true, timeout: 15_000 },
    );
  };
  const save = useMutation({
    // La réponse va d'abord dans la file locale : elle doit fonctionner sans réseau.
    networkMode: "always",
    mutationFn: async () => {
      await queueSubmission(orgId, projectId, form.id, {
        answers: toAnswers(form.fields, drafts),
        location,
        latitude: position?.latitude ?? null,
        longitude: position?.longitude ?? null,
        collected_at: new Date().toISOString(),
        client_uuid: newId(),
      });
      return navigator.onLine ? syncOutbox() : { offline: true, sent: 0, rejected: 0 };
    },
    onSuccess: (result) => {
      void queryClient.invalidateQueries({ queryKey: ["orgs", orgId, "projects", projectId] });
      onDone(result.offline ? "queued" : "sent");
    },
  });
  const submit = (event: FormEvent) => {
    event.preventDefault();
    const missing = form.fields.find(
      (f) => f.type === "multiselect" && f.required && !(drafts[f.key] as string[]).length,
    );
    if (missing) return setError(t("forms.requiredMissing", { label: missing.label }));
    setError("");
    save.mutate();
  };

  return (
    <form onSubmit={submit} className="space-y-4" aria-label={form.title}>
      {form.description && (
        <p className="text-sm whitespace-pre-line text-slate-600">{form.description}</p>
      )}
      {form.fields.map((field) => (
        <AnswerInput
          key={field.key}
          field={field}
          value={drafts[field.key]}
          onChange={(value) => setDrafts({ ...drafts, [field.key]: value })}
        />
      ))}
      <div className="flex flex-wrap items-end gap-3">
        <div className="min-w-0 flex-1">
          <Field
            label={t("execution.location")}
            value={location}
            onChange={(e) => setLocation(e.target.value)}
          />
        </div>
        <Button type="button" variant="ghost" onClick={locate} disabled={locating}>
          📍{" "}
          {locating
            ? t("execution.locating")
            : position
              ? `${position.latitude}, ${position.longitude}`
              : t("execution.usePosition")}
        </Button>
      </div>
      <ErrorText error={error || save.error} />
      <div className="flex gap-2">
        <Button type="submit" disabled={save.isPending}>
          {t("forms.send")}
        </Button>
        <Button type="button" variant="ghost" onClick={() => onDone(null)}>
          {t("common.cancel")}
        </Button>
      </div>
    </form>
  );
}

// --- Consultation -------------------------------------------------------------------------

function SummaryItem({ field, total }: { field: FieldSummary; total: number }) {
  const { t, i18n } = useTranslation();
  const number = new Intl.NumberFormat(i18n.language, { maximumFractionDigits: 2 });
  const counts = Object.entries(field.counts).map(([label, count]) => [
    field.type === "yesno" ? t(`forms.${label}`) : label,
    count,
  ]) as [string, number][];
  return (
    <li className="py-3">
      <p className="text-sm font-medium">
        {field.label}{" "}
        <span className="font-normal text-slate-500">
          · {t("forms.answered", { count: field.answered, total })}
        </span>
      </p>
      {counts.length > 0 && (
        <ul className="mt-1 space-y-1">
          {counts.map(([label, count]) => (
            <li key={label} className="grid grid-cols-[8rem_1fr_3rem] items-center gap-2 text-xs">
              <span className="truncate">{label}</span>
              <span className="h-2 rounded-full bg-slate-100">
                <span
                  className="block h-2 rounded-full bg-brand-600"
                  style={{ width: `${field.answered ? (count / field.answered) * 100 : 0}%` }}
                />
              </span>
              <span className="text-right tabular-nums">{count}</span>
            </li>
          ))}
        </ul>
      )}
      {field.mean !== null && (
        <p className="mt-1 text-xs text-slate-600">
          {t("forms.stats", {
            total: number.format(field.total ?? 0),
            mean: number.format(field.mean),
            min: number.format(field.min ?? 0),
            max: number.format(field.max ?? 0),
          })}
        </p>
      )}
      {field.samples.length > 0 && (
        <ul className="mt-1 list-disc pl-5 text-xs text-slate-600">
          {field.samples.map((sample, index) => (
            <li key={index}>{sample}</li>
          ))}
        </ul>
      )}
    </li>
  );
}

function Submissions({
  orgId,
  projectId,
  form,
}: {
  orgId: string;
  projectId: string;
  form: CollectionForm;
}) {
  const { t, i18n } = useTranslation();
  const { role } = useCurrentOrg();
  const invalidate = useInvalidateProject(orgId, projectId);
  const submissions = useQuery(submissionsQuery(orgId, projectId, form.id));
  const remove = useMutation({
    mutationFn: (id: string) => formsApi.removeSubmission(orgId, projectId, form.id, id),
    onSuccess: invalidate,
  });
  const dates = new Intl.DateTimeFormat(i18n.language, {
    dateStyle: "short",
    timeStyle: "short",
  });
  const yesNo = { yes: t("forms.yes"), no: t("forms.no") };
  if (!submissions.data?.length) return <ErrorText error={submissions.error} />;
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-xs">
        <thead className="text-slate-500">
          <tr>
            <th className="py-1 pr-3">{t("forms.collectedAt")}</th>
            <th className="py-1 pr-3">{t("forms.collectedBy")}</th>
            <th className="py-1 pr-3">{t("execution.location")}</th>
            {form.fields.map((field) => (
              <th key={field.key} className="py-1 pr-3">
                {field.label}
              </th>
            ))}
            <th />
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {submissions.data.map((submission) => (
            <tr key={submission.id}>
              <td className="py-1 pr-3 whitespace-nowrap">
                {dates.format(new Date(submission.collected_at))}
              </td>
              <td className="py-1 pr-3">{submission.submitter_name}</td>
              <td className="py-1 pr-3">{submission.location}</td>
              {form.fields.map((field) => (
                <td key={field.key} className="py-1 pr-3">
                  {formatAnswer(submission.answers[field.key], yesNo, i18n.language)}
                </td>
              ))}
              <td className="py-1">
                {permissions.manageProjects(role) && (
                  <button
                    className="text-red-700 hover:underline"
                    onClick={() => {
                      if (window.confirm(t("forms.confirmDeleteSubmission")))
                        remove.mutate(submission.id);
                    }}
                  >
                    {t("logframe.delete")}
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function FormView({
  orgId,
  projectId,
  formId,
  onBack,
}: {
  orgId: string;
  projectId: string;
  formId: string;
  onBack: () => void;
}) {
  const { t } = useTranslation();
  const { role } = useCurrentOrg();
  const canPlan = permissions.plan(role);
  const canCollect = permissions.recordValues(role);
  const invalidate = useInvalidateProject(orgId, projectId);
  const form = useQuery(formQuery(orgId, projectId, formId));
  const summary = useQuery({ ...formSummaryQuery(orgId, projectId, formId), enabled: canPlan });
  const [mode, setMode] = useState<"view" | "edit" | "fill">("view");
  const [saved, setSaved] = useState<"sent" | "queued" | null>(null);
  const setStatus = useMutation({
    mutationFn: (status: FormStatus) => formsApi.update(orgId, projectId, formId, { status }),
    onSuccess: invalidate,
  });
  const remove = useMutation({
    mutationFn: () => formsApi.remove(orgId, projectId, formId),
    onSuccess: async () => {
      await invalidate();
      onBack();
    },
  });
  const exportFile = useMutation({
    mutationFn: () =>
      download(formsApi.exportPath(orgId, projectId, formId), `formulaire-${formId}.xlsx`),
  });

  if (form.isPending) return <p className="text-sm text-slate-500">{t("common.loading")}</p>;
  if (!form.data) return <ErrorText error={form.error} />;
  const f = form.data;
  const canDelete = f.submissions ? permissions.manageProjects(role) : canPlan;

  return (
    <>
      <button className="text-sm text-brand-700 hover:underline" onClick={onBack}>
        ← {t("forms.back")}
      </button>
      <Card>
        <div className="flex flex-wrap items-start gap-2">
          <h2 className="min-w-0 flex-1 text-base font-semibold">{f.title}</h2>
          <FormStatusBadge status={f.status} />
        </div>
        <p className="mt-1 text-sm text-slate-600">
          {t("forms.questions", { count: f.fields.length })} ·{" "}
          {t("forms.submissions", { count: f.submissions })}
        </p>
        {saved && (
          <p role="status" className="mt-2 text-sm text-emerald-700">
            {saved === "sent" ? t("forms.sent") : t("execution.queued")}
          </p>
        )}
        {mode === "view" && (
          <div className="mt-3 flex flex-wrap gap-2">
            {canCollect && f.status === "published" && (
              <Button
                onClick={() => {
                  setSaved(null);
                  setMode("fill");
                }}
              >
                {t("forms.fill")}
              </Button>
            )}
            {canPlan && f.status === "draft" && (
              <Button onClick={() => setStatus.mutate("published")}>{t("forms.publish")}</Button>
            )}
            {canPlan && f.status === "published" && (
              <Button variant="ghost" onClick={() => setStatus.mutate("closed")}>
                {t("forms.close")}
              </Button>
            )}
            {canPlan && f.status === "closed" && (
              <Button variant="ghost" onClick={() => setStatus.mutate("published")}>
                {t("forms.reopen")}
              </Button>
            )}
            {canPlan && (
              <Button variant="ghost" onClick={() => setMode("edit")}>
                {t("report.edit")}
              </Button>
            )}
            {canPlan && f.submissions > 0 && (
              <Button
                variant="ghost"
                onClick={() => exportFile.mutate()}
                disabled={exportFile.isPending}
              >
                ⬇ {t("projects.export")}
              </Button>
            )}
            {canDelete && (
              <Button
                variant="danger"
                onClick={() => {
                  if (window.confirm(t("forms.confirmDelete"))) remove.mutate();
                }}
              >
                {t("logframe.delete")}
              </Button>
            )}
          </div>
        )}
        <ErrorText error={setStatus.error || remove.error || exportFile.error} />
      </Card>

      {mode === "edit" && (
        <Card title={t("forms.editTitle")}>
          <FormBuilder
            orgId={orgId}
            projectId={projectId}
            form={f}
            onDone={() => setMode("view")}
          />
        </Card>
      )}
      {mode === "fill" && (
        <Card title={t("forms.fill")}>
          <FillForm
            orgId={orgId}
            projectId={projectId}
            form={f}
            onDone={(result) => {
              setSaved(result);
              setMode("view");
            }}
          />
        </Card>
      )}
      {mode === "view" && canPlan && summary.data && summary.data.submissions > 0 && (
        <>
          <Card title={t("forms.summary")}>
            <ul className="divide-y divide-slate-100">
              {summary.data.fields.map((field) => (
                <SummaryItem key={field.key} field={field} total={summary.data.submissions} />
              ))}
            </ul>
          </Card>
          <Card title={t("forms.responses")}>
            <Submissions orgId={orgId} projectId={projectId} form={f} />
          </Card>
        </>
      )}
      {mode === "view" && f.status === "draft" && (
        <Card title={t("forms.preview")}>
          <ol className="list-decimal space-y-1 pl-5 text-sm">
            {f.fields.map((field) => (
              <li key={field.key}>
                {field.label}{" "}
                <span className="text-xs text-slate-500">
                  ({t(`forms.types.${field.type}`)}
                  {field.required && `, ${t("forms.required").toLowerCase()}`})
                </span>
              </li>
            ))}
          </ol>
        </Card>
      )}
    </>
  );
}

// --- Liste --------------------------------------------------------------------------------

export function FormsTab({ orgId, projectId }: { orgId: string; projectId: string }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { form: formId } = useSearch({ from: "/orgs/$orgId/projects/$projectId" });
  const { role } = useCurrentOrg();
  const canPlan = permissions.plan(role);
  const forms = useQuery(formsQuery(orgId, projectId));
  const pending = usePending(projectId).submissions;
  const online = useOnline();
  const queryClient = useQueryClient();
  const [creating, setCreating] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const open = (id?: string) =>
    navigate({ to: ".", search: (prev) => ({ ...prev, tab: "forms" as const, form: id }) });
  const syncNow = async () => {
    setSyncing(true);
    try {
      await syncOutbox();
      await queryClient.invalidateQueries({ queryKey: ["orgs", orgId, "projects", projectId] });
    } finally {
      setSyncing(false);
    }
  };
  const titles = new Map((forms.data ?? []).map((f) => [f.id, f.title]));

  const pendingList = pending.length > 0 && (
    <Card>
      <div className="flex flex-wrap items-center gap-2">
        <p className="flex-1 text-sm">
          {t("forms.waiting", { count: pending.length })}{" "}
          {!online && <span className="text-slate-500">{t("execution.waitingOffline")}</span>}
        </p>
        {online && (
          <Button variant="ghost" onClick={syncNow} disabled={syncing}>
            {t("execution.syncNow")}
          </Button>
        )}
      </div>
      <ul className="mt-2 divide-y divide-slate-100 text-sm">
        {pending.map((item) => (
          <li key={item.client_uuid} className="flex flex-wrap items-center gap-2 py-1.5">
            <span className="min-w-0 flex-1">
              {titles.get(item.formId) ?? "–"}{" "}
              <span className="text-xs text-slate-500">· {t("execution.pending")}</span>
            </span>
            {item.error && <span className="text-xs text-red-700">{item.error}</span>}
            <button
              className="text-xs text-red-700 hover:underline"
              onClick={() => void discard("submissions", item.client_uuid)}
            >
              {t("execution.discard")}
            </button>
          </li>
        ))}
      </ul>
    </Card>
  );

  if (formId)
    return (
      <>
        {pendingList}
        <FormView orgId={orgId} projectId={projectId} formId={formId} onBack={() => open()} />
      </>
    );

  const visible = (forms.data ?? []).filter((f) => canPlan || f.status === "published");
  return (
    <>
      {pendingList}
      <Card title={t("forms.title_plural")}>
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <p className="flex-1 text-sm text-slate-600">{t("forms.intro")}</p>
          {canPlan && !creating && (
            <Button onClick={() => setCreating(true)}>+ {t("forms.new")}</Button>
          )}
        </div>
        {creating && (
          <div className="mb-4 rounded-md border border-slate-200 p-4">
            <FormBuilder
              orgId={orgId}
              projectId={projectId}
              onDone={(id) => {
                setCreating(false);
                if (id) void open(id);
              }}
            />
          </div>
        )}
        <ErrorText error={forms.error} />
        {visible.length ? (
          <ul className="divide-y divide-slate-100">
            {visible.map((form) => (
              <li key={form.id}>
                <button
                  className="flex w-full flex-wrap items-center gap-2 py-3 text-left hover:bg-slate-50"
                  onClick={() => void open(form.id)}
                >
                  <span className="min-w-0 flex-1 text-sm font-medium">{form.title}</span>
                  <span className="text-xs text-slate-500">
                    {t("forms.submissions", { count: form.submissions })}
                  </span>
                  <FormStatusBadge status={form.status} />
                </button>
              </li>
            ))}
          </ul>
        ) : (
          !forms.isPending && <p className="text-sm text-slate-500">{t("forms.empty")}</p>
        )}
      </Card>
    </>
  );
}
