import { useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";
import { useTranslation } from "react-i18next";

import { Button, Field, Select } from "@/components/ui";
import {
  EVIDENCE_KINDS,
  type EvidenceKind,
  type ExecutionStatus,
  type LogframeNode,
  type Participants,
} from "@/lib/api";
import { flattenTree } from "@/lib/format";
import { type FileToSend, newId, queueExecution, syncOutbox } from "@/lib/outbox";
import { logframeQuery } from "@/lib/queries";

const PARTICIPANT_KEYS: (keyof Participants)[] = [
  "women",
  "men",
  "girls",
  "boys",
  "with_disability",
];
const ACCEPT = "image/*,.pdf,.docx,.xlsx,.txt,.md";

const activitiesOf = (nodes: LogframeNode[]) =>
  flattenTree(nodes).filter((n) => n.level === "activity" || n.level === "sub_activity");

/** Fichiers choisis avant envoi, avec leur type, légende et consentement. */
export function FilePicker({
  files,
  onChange,
}: {
  files: FileToSend[];
  onChange: (files: FileToSend[]) => void;
}) {
  const { t } = useTranslation();
  const add = (list: FileList | null) => {
    const added = Array.from(list ?? []).map((file) => ({
      file,
      filename: file.name,
      meta: {
        kind: (file.type.startsWith("image/") ? "photo" : "report") as EvidenceKind,
        caption: "",
        consent_given: false,
        client_uuid: newId(),
      },
    }));
    onChange([...files, ...added]);
  };
  const update = (index: number, meta: Partial<FileToSend["meta"]>) =>
    onChange(files.map((f, i) => (i === index ? { ...f, meta: { ...f.meta, ...meta } } : f)));

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-2">
        <label className="cursor-pointer rounded-md px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100">
          📷 {t("execution.takePhoto")}
          <input
            type="file"
            accept="image/*"
            capture="environment"
            className="sr-only"
            onChange={(e) => {
              add(e.target.files);
              e.target.value = "";
            }}
          />
        </label>
        <label className="cursor-pointer rounded-md px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100">
          📎 {t("execution.addFiles")}
          <input
            type="file"
            multiple
            accept={ACCEPT}
            className="sr-only"
            onChange={(e) => {
              add(e.target.files);
              e.target.value = "";
            }}
          />
        </label>
      </div>
      {files.length > 0 && (
        <ul className="divide-y divide-slate-100 rounded-md border border-slate-200">
          {files.map((item, index) => (
            <li
              key={item.meta.client_uuid}
              className="flex flex-wrap items-center gap-2 p-2 text-sm"
            >
              <span className="min-w-0 flex-1 truncate">{item.filename}</span>
              <select
                aria-label={t("execution.kind")}
                className="rounded border border-slate-300 px-1.5 py-1 text-xs"
                value={item.meta.kind}
                onChange={(e) => update(index, { kind: e.target.value as EvidenceKind })}
              >
                {EVIDENCE_KINDS.map((kind) => (
                  <option key={kind} value={kind}>
                    {t(`execution.kinds.${kind}`)}
                  </option>
                ))}
              </select>
              <input
                aria-label={t("execution.caption")}
                placeholder={t("execution.caption")}
                className="w-40 rounded border border-slate-300 px-1.5 py-1 text-xs"
                value={item.meta.caption}
                onChange={(e) => update(index, { caption: e.target.value })}
              />
              {item.meta.kind === "photo" && (
                <label className="flex items-center gap-1 text-xs">
                  <input
                    type="checkbox"
                    checked={item.meta.consent_given}
                    onChange={(e) => update(index, { consent_given: e.target.checked })}
                  />
                  {t("execution.consent")}
                </label>
              )}
              <button
                type="button"
                className="text-xs text-red-700"
                onClick={() => onChange(files.filter((_, i) => i !== index))}
              >
                ✕
              </button>
            </li>
          ))}
        </ul>
      )}
      {files.some((f) => f.meta.kind === "photo") && (
        <p className="text-xs text-slate-500">{t("execution.consentHint")}</p>
      )}
    </div>
  );
}

export function ParticipantsFields({
  value,
  onChange,
}: {
  value: Participants;
  onChange: (value: Participants) => void;
}) {
  const { t } = useTranslation();
  return (
    <fieldset>
      <legend className="mb-1 text-sm font-medium text-slate-700">
        {t("execution.participants")}
      </legend>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-5">
        {PARTICIPANT_KEYS.map((key) => (
          <Field
            key={key}
            label={t(`execution.people.${key}`)}
            type="number"
            min={0}
            inputMode="numeric"
            value={String(value[key])}
            onChange={(e) =>
              onChange({ ...value, [key]: Math.max(0, Number(e.target.value) || 0) })
            }
          />
        ))}
      </div>
    </fieldset>
  );
}

const today = () => new Date().toISOString().slice(0, 10);

export function ExecutionForm({
  orgId,
  projectId,
  onDone,
}: {
  orgId: string;
  projectId: string;
  onDone: (outcome: "sent" | "queued" | null) => void;
}) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const logframe = useQuery(logframeQuery(orgId, projectId));
  const activities = activitiesOf(logframe.data ?? []);
  const [activityId, setActivityId] = useState("");
  const [title, setTitle] = useState("");
  const [startDate, setStartDate] = useState(today);
  const [endDate, setEndDate] = useState("");
  const [location, setLocation] = useState("");
  const [position, setPosition] = useState<{ latitude: number; longitude: number } | null>(null);
  const [locating, setLocating] = useState(false);
  const [participants, setParticipants] = useState<Participants>({
    women: 0,
    men: 0,
    girls: 0,
    boys: 0,
    with_disability: 0,
  });
  const [notes, setNotes] = useState("");
  const [status, setStatus] = useState<ExecutionStatus>("completed");
  const [files, setFiles] = useState<FileToSend[]>([]);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

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

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const total = participants.women + participants.men + participants.girls + participants.boys;
    if (participants.with_disability > total) return setError(t("execution.disabilityError"));
    if (endDate && endDate < startDate) return setError(t("execution.datesError"));
    setError("");
    setSaving(true);
    try {
      await queueExecution(
        orgId,
        projectId,
        {
          activity_id: activityId,
          title,
          start_date: startDate,
          end_date: endDate || null,
          location,
          latitude: position?.latitude ?? null,
          longitude: position?.longitude ?? null,
          participants,
          notes,
          status,
          client_uuid: newId(),
        },
        files,
      );
      const result = navigator.onLine ? await syncOutbox() : { offline: true };
      await queryClient.invalidateQueries({ queryKey: ["orgs", orgId, "projects", projectId] });
      onDone(result.offline ? "queued" : "sent");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  };

  return (
    <form onSubmit={submit} className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-2">
        <Select
          label={t("execution.activity")}
          required
          value={activityId}
          onChange={(e) => setActivityId(e.target.value)}
        >
          <option value="">–</option>
          {activities.map((activity) => (
            <option key={activity.id} value={activity.id}>
              {activity.code} {activity.title}
            </option>
          ))}
        </Select>
        <Field
          label={t("execution.title")}
          placeholder={t("execution.titlePlaceholder")}
          value={title}
          onChange={(e) => setTitle(e.target.value)}
        />
        <Field
          label={t("execution.start")}
          type="date"
          required
          value={startDate}
          onChange={(e) => setStartDate(e.target.value)}
        />
        <Field
          label={t("execution.end")}
          type="date"
          value={endDate}
          onChange={(e) => setEndDate(e.target.value)}
        />
        <Field
          label={t("execution.location")}
          value={location}
          onChange={(e) => setLocation(e.target.value)}
        />
        <div className="flex items-end gap-2">
          <Button type="button" variant="ghost" onClick={locate} disabled={locating}>
            📍 {locating ? t("execution.locating") : t("execution.usePosition")}
          </Button>
          {position && (
            <span className="pb-2 text-xs text-slate-600">
              {position.latitude}, {position.longitude}
            </span>
          )}
        </div>
      </div>
      <ParticipantsFields value={participants} onChange={setParticipants} />
      <label className="block text-sm font-medium text-slate-700">
        {t("execution.notes")}
        <textarea
          className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm font-normal"
          rows={4}
          placeholder={t("execution.notesPlaceholder")}
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
        />
      </label>
      <Select
        label={t("execution.statusLabel")}
        value={status}
        onChange={(e) => setStatus(e.target.value as ExecutionStatus)}
      >
        <option value="completed">{t("execution.status.completed")}</option>
        <option value="in_progress">{t("execution.status.in_progress")}</option>
      </Select>
      <div>
        <p className="mb-1 text-sm font-medium text-slate-700">{t("execution.evidence")}</p>
        <FilePicker files={files} onChange={setFiles} />
      </div>
      {error && (
        <p role="alert" className="text-sm text-red-700">
          {error}
        </p>
      )}
      <div className="flex gap-2">
        <Button type="submit" disabled={saving || !activityId}>
          {t("execution.save")}
        </Button>
        <Button type="button" variant="ghost" onClick={() => onDone(null)}>
          {t("common.cancel")}
        </Button>
      </div>
    </form>
  );
}
