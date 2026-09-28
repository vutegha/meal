import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";
import { useTranslation } from "react-i18next";

import { Button, Card, ErrorText, Field, Select } from "@/components/ui";
import { useCurrentOrg } from "@/features/orgs/useCurrentOrg";
import {
  accountabilityApi,
  FEEDBACK_CATEGORIES,
  FEEDBACK_CHANNELS,
  FEEDBACK_STATUSES,
  type FeedbackCategory,
  type FeedbackEntry,
  type FeedbackIn,
  type FeedbackStatus,
  type FeedbackSuggestion,
  SENSITIVE_CATEGORIES,
} from "@/lib/api";
import { flattenTree, formatRate } from "@/lib/format";
import { discard, newId, queueFeedback, syncOutbox, usePending } from "@/lib/outbox";
import { permissions } from "@/lib/permissions";
import { useOnline } from "@/lib/useOnline";
import { feedbackQuery, feedbackStatsQuery, logframeQuery, membersQuery } from "@/lib/queries";

import { useInvalidateProject } from "./useInvalidateProject";

const today = () => new Date().toISOString().slice(0, 10);

const statusStyles: Record<FeedbackStatus, string> = {
  received: "bg-slate-100 text-slate-700",
  in_progress: "bg-amber-100 text-amber-800",
  responded: "bg-sky-100 text-sky-800",
  closed: "bg-emerald-100 text-emerald-800",
};

function FeedbackForm({
  orgId,
  projectId,
  onDone,
}: {
  orgId: string;
  projectId: string;
  onDone: (result: "sent" | "queued" | null) => void;
}) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const online = useOnline();
  const logframe = useQuery(logframeQuery(orgId, projectId));
  const activities = flattenTree(logframe.data ?? []).filter(
    (n) => n.level === "activity" || n.level === "sub_activity",
  );
  const [entry, setEntry] = useState<FeedbackIn>(() => ({
    received_on: today(),
    channel: "community_meeting",
    category: "complaint",
    description: "",
    location: "",
    activity_id: null,
    anonymous: false,
    contact: "",
    client_uuid: newId(),
  }));
  const [suggestion, setSuggestion] = useState<FeedbackSuggestion | null>(null);
  const set = (patch: Partial<FeedbackIn>) => setEntry({ ...entry, ...patch });
  // Toujours par la file d'envoi : sans réseau, le retour part dès que la connexion revient.
  const save = useMutation({
    // La saisie va d'abord dans la file locale : elle doit fonctionner sans réseau.
    networkMode: "always",
    mutationFn: async () => {
      await queueFeedback(orgId, projectId, entry);
      return navigator.onLine ? syncOutbox() : { offline: true };
    },
    onSuccess: (result) => {
      // Sans attendre : hors ligne, React Query met les rechargements en pause.
      void queryClient.invalidateQueries({ queryKey: ["orgs", orgId, "projects", projectId] });
      onDone(result.offline ? "queued" : "sent");
    },
  });
  const classify = useMutation({
    mutationFn: () =>
      accountabilityApi.classifyFeedback(orgId, projectId, {
        description: entry.description,
        channel: entry.channel,
      }),
    onSuccess: (result) => {
      setSuggestion(result);
      set({ category: result.category, sensitive: result.sensitive });
    },
  });
  const submit = (event: FormEvent) => {
    event.preventDefault();
    save.mutate();
  };

  return (
    <form onSubmit={submit} className="space-y-3">
      <div className="grid gap-3 sm:grid-cols-3">
        <Field
          label={t("feedback.receivedOn")}
          type="date"
          required
          max={today()}
          value={entry.received_on}
          onChange={(e) => set({ received_on: e.target.value })}
        />
        <Select
          label={t("feedback.channel")}
          value={entry.channel}
          onChange={(e) => set({ channel: e.target.value as FeedbackIn["channel"] })}
        >
          {FEEDBACK_CHANNELS.map((channel) => (
            <option key={channel} value={channel}>
              {t(`feedback.channels.${channel}`)}
            </option>
          ))}
        </Select>
        <Select
          label={t("feedback.category")}
          value={entry.category}
          onChange={(e) => set({ category: e.target.value as FeedbackCategory, sensitive: null })}
        >
          {FEEDBACK_CATEGORIES.map((category) => (
            <option key={category} value={category}>
              {t(`feedback.categories.${category}`)}
            </option>
          ))}
        </Select>
      </div>
      {SENSITIVE_CATEGORIES.includes(entry.category) && (
        <p className="rounded-md border border-red-200 bg-red-50 p-2 text-sm text-red-800">
          🔒 {t("feedback.sensitiveHint")}
        </p>
      )}
      <label className="block text-sm font-medium text-slate-700">
        {t("feedback.description")}
        <textarea
          className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm font-normal"
          rows={3}
          required
          minLength={3}
          value={entry.description}
          onChange={(e) => set({ description: e.target.value })}
        />
      </label>
      {online && (
        <div className="space-y-2">
          <Button
            type="button"
            variant="ghost"
            onClick={() => classify.mutate()}
            disabled={classify.isPending || entry.description.trim().length < 3}
          >
            ✨ {classify.isPending ? t("feedback.classifying") : t("feedback.classify")}
          </Button>
          <ErrorText error={classify.error} />
          {suggestion && (
            <div
              role="status"
              className="rounded-md border border-brand-100 bg-brand-50/50 p-3 text-sm"
            >
              <p className="font-medium text-brand-900">
                {t(`feedback.categories.${suggestion.category}`)}
                {suggestion.sensitive && ` · 🔒 ${t("feedback.sensitive")}`}
                {" · "}
                <span className={suggestion.urgency === "high" ? "text-red-700" : ""}>
                  {t(`feedback.urgency.${suggestion.urgency}`)}
                </span>
              </p>
              <p className="text-slate-700">{suggestion.summary}</p>
              <p className="text-xs text-slate-500">
                {suggestion.justification} {t("feedback.suggestionHint")}
              </p>
            </div>
          )}
        </div>
      )}
      <div className="grid gap-3 sm:grid-cols-2">
        <Field
          label={t("execution.location")}
          value={entry.location}
          onChange={(e) => set({ location: e.target.value })}
        />
        <Select
          label={t("feedback.activity")}
          value={entry.activity_id ?? ""}
          onChange={(e) => set({ activity_id: e.target.value || null })}
        >
          <option value="">–</option>
          {activities.map((activity) => (
            <option key={activity.id} value={activity.id}>
              {activity.code} {activity.title}
            </option>
          ))}
        </Select>
      </div>
      <div className="flex flex-wrap items-end gap-3">
        <label className="flex items-center gap-2 pb-2 text-sm">
          <input
            type="checkbox"
            checked={entry.anonymous}
            onChange={(e) => set({ anonymous: e.target.checked, contact: "" })}
          />
          {t("feedback.anonymous")}
        </label>
        {!entry.anonymous && (
          <div className="min-w-0 flex-1">
            <Field
              label={t("feedback.contact")}
              hint={t("feedback.contactHint")}
              value={entry.contact}
              onChange={(e) => set({ contact: e.target.value })}
            />
          </div>
        )}
      </div>
      <ErrorText error={save.error} />
      <div className="flex gap-2">
        <Button type="submit" disabled={save.isPending}>
          {t("feedback.record")}
        </Button>
        <Button type="button" variant="ghost" onClick={() => onDone(null)}>
          {t("common.cancel")}
        </Button>
      </div>
    </form>
  );
}

function HandleForm({
  orgId,
  projectId,
  entry,
  onDone,
}: {
  orgId: string;
  projectId: string;
  entry: FeedbackEntry;
  onDone: () => void;
}) {
  const { t } = useTranslation();
  const invalidate = useInvalidateProject(orgId, projectId);
  const members = useQuery(membersQuery(orgId));
  const [state, setState] = useState({
    status: entry.status,
    assigned_to: entry.assigned_to,
    response: entry.response,
    responded_on: entry.responded_on ?? "",
  });
  const save = useMutation({
    mutationFn: () =>
      accountabilityApi.updateFeedback(orgId, projectId, entry.id, {
        ...state,
        responded_on: state.responded_on || null,
      }),
    onSuccess: async () => {
      await invalidate();
      onDone();
    },
  });
  const answering = state.status === "responded" || state.status === "closed";
  return (
    <form
      className="mt-3 space-y-3 rounded-md bg-slate-50 p-3"
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate();
      }}
    >
      <div className="grid gap-3 sm:grid-cols-3">
        <Select
          label={t("feedback.statusLabel")}
          value={state.status}
          onChange={(e) => setState({ ...state, status: e.target.value as FeedbackStatus })}
        >
          {FEEDBACK_STATUSES.map((status) => (
            <option key={status} value={status}>
              {t(`feedback.status.${status}`)}
            </option>
          ))}
        </Select>
        <Select
          label={t("feedback.assignedTo")}
          value={state.assigned_to ?? ""}
          onChange={(e) => setState({ ...state, assigned_to: e.target.value || null })}
        >
          <option value="">–</option>
          {(members.data ?? []).map((m) => (
            <option key={m.user.id} value={m.user.id}>
              {m.user.full_name || m.user.email}
            </option>
          ))}
        </Select>
        {answering && (
          <Field
            label={t("feedback.respondedOn")}
            type="date"
            min={entry.received_on}
            max={today()}
            value={state.responded_on}
            onChange={(e) => setState({ ...state, responded_on: e.target.value })}
          />
        )}
      </div>
      <label className="block text-sm font-medium text-slate-700">
        {t("feedback.response")}
        <textarea
          className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm font-normal"
          rows={2}
          required={answering}
          value={state.response}
          onChange={(e) => setState({ ...state, response: e.target.value })}
        />
      </label>
      <ErrorText error={save.error} />
      <div className="flex gap-2">
        <Button type="submit" disabled={save.isPending}>
          {t("tor.save")}
        </Button>
        <Button type="button" variant="ghost" onClick={onDone}>
          {t("common.cancel")}
        </Button>
      </div>
    </form>
  );
}

function FeedbackItem({
  entry,
  orgId,
  projectId,
  activity,
  assignee,
}: {
  entry: FeedbackEntry;
  orgId: string;
  projectId: string;
  activity?: string;
  assignee?: string;
}) {
  const { t, i18n } = useTranslation();
  const { role, me } = useCurrentOrg();
  const [handling, setHandling] = useState(false);
  const dates = new Intl.DateTimeFormat(i18n.language, { dateStyle: "medium" });
  const manager = permissions.manageProjects(role);
  const canHandle = entry.sensitive
    ? manager || entry.assigned_to === me.id
    : permissions.plan(role) || entry.assigned_to === me.id;

  return (
    <li className="py-3">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <span className="font-mono text-xs text-slate-500">{entry.reference}</span>
        <span className="font-medium">
          {entry.sensitive && "🔒 "}
          {t(`feedback.categories.${entry.category}`)}
        </span>
        <span className="text-xs text-slate-500">
          {dates.format(new Date(entry.received_on))} · {t(`feedback.channels.${entry.channel}`)}
          {entry.location && ` · ${entry.location}`}
        </span>
        <span className="flex-1" />
        {entry.overdue && (
          <span className="rounded bg-red-100 px-1.5 py-0.5 text-xs font-medium text-red-800">
            {t("feedback.overdue")}
          </span>
        )}
        <span className={`rounded px-1.5 py-0.5 text-xs font-medium ${statusStyles[entry.status]}`}>
          {t(`feedback.status.${entry.status}`)}
        </span>
      </div>
      <p className="mt-1 text-sm whitespace-pre-line text-slate-800">{entry.description}</p>
      <p className="mt-1 text-xs text-slate-500">
        {activity && `${activity} · `}
        {entry.anonymous
          ? t("feedback.anonymousShort")
          : entry.contact && `${t("feedback.contact")} : ${entry.contact} · `}
        {assignee && `${t("feedback.assignedTo")} : ${assignee} · `}
        {entry.response_days !== null
          ? t("feedback.answeredIn", { count: entry.response_days })
          : t("feedback.dueOn", { date: dates.format(new Date(entry.due_on)) })}
      </p>
      {entry.response && (
        <p className="mt-1 border-l-2 border-brand-600 pl-2 text-sm text-slate-700">
          {entry.response}
        </p>
      )}
      {canHandle && !handling && (
        <button
          className="mt-1 text-xs font-medium text-brand-700 hover:underline"
          onClick={() => setHandling(true)}
        >
          {t("feedback.handle")}
        </button>
      )}
      {handling && (
        <HandleForm
          orgId={orgId}
          projectId={projectId}
          entry={entry}
          onDone={() => setHandling(false)}
        />
      )}
    </li>
  );
}

export function FeedbackTab({ orgId, projectId }: { orgId: string; projectId: string }) {
  const { t, i18n } = useTranslation();
  const { role } = useCurrentOrg();
  const canCollect = permissions.recordValues(role);
  const entries = useQuery(feedbackQuery(orgId, projectId));
  const stats = useQuery(feedbackStatsQuery(orgId, projectId));
  const logframe = useQuery(logframeQuery(orgId, projectId));
  const members = useQuery(membersQuery(orgId));
  const [adding, setAdding] = useState(false);
  const [saved, setSaved] = useState<"sent" | "queued" | null>(null);
  const online = useOnline();
  const pending = usePending(projectId).feedback;
  const [syncing, setSyncing] = useState(false);
  const queryClient = useQueryClient();
  const syncNow = async () => {
    setSyncing(true);
    try {
      await syncOutbox();
      await queryClient.invalidateQueries({ queryKey: ["orgs", orgId, "projects", projectId] });
    } finally {
      setSyncing(false);
    }
  };
  const [status, setStatus] = useState<FeedbackStatus | "open" | "">("open");
  const nodes = new Map(flattenTree(logframe.data ?? []).map((n) => [n.id, n]));
  const people = new Map(
    (members.data ?? []).map((m) => [m.user.id, m.user.full_name || m.user.email]),
  );
  const shown = (entries.data ?? []).filter((e) =>
    status === "open"
      ? e.status === "received" || e.status === "in_progress"
      : !status || e.status === status,
  );
  const s = stats.data;

  return (
    <>
      {s && s.total > 0 && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {[
            [t("feedback.stats.total"), String(s.total), ""],
            [t("feedback.stats.open"), String(s.open), ""],
            [t("feedback.stats.overdue"), String(s.overdue), ""],
            [
              t("feedback.stats.responseRate"),
              formatRate(s.response_rate, i18n.language),
              s.average_response_days !== null
                ? t("feedback.stats.days", { count: s.average_response_days })
                : "",
            ],
          ].map(([label, value, sub], index) => (
            <div key={label} className="rounded-lg border border-slate-200 bg-white p-3 shadow-sm">
              <p className="text-xs text-slate-500">{label}</p>
              <p
                className={`text-xl font-semibold tabular-nums ${
                  index === 2 && s.overdue ? "text-red-700" : "text-brand-800"
                }`}
              >
                {value}
              </p>
              {sub && <p className="text-xs text-slate-500">{sub}</p>}
            </div>
          ))}
        </div>
      )}

      <Card title={t("feedback.title")}>
        <p className="mb-3 text-sm text-slate-600">{t("feedback.intro")}</p>
        <div className="mb-3 flex flex-wrap items-center gap-2">
          {canCollect && !adding && (
            <Button onClick={() => setAdding(true)}>+ {t("feedback.new")}</Button>
          )}
          <span className="flex-1" />
          <select
            aria-label={t("feedback.statusLabel")}
            className="rounded-md border border-slate-300 px-2 py-1.5 text-sm"
            value={status}
            onChange={(e) => setStatus(e.target.value as typeof status)}
          >
            <option value="open">{t("feedback.filterOpen")}</option>
            <option value="">{t("feedback.filterAll")}</option>
            {FEEDBACK_STATUSES.map((value) => (
              <option key={value} value={value}>
                {t(`feedback.status.${value}`)}
              </option>
            ))}
          </select>
        </div>
        {saved && !adding && (
          <p role="status" className="mb-3 text-sm text-brand-800">
            {saved === "sent" ? t("feedback.saved") : t("feedback.queued")}
          </p>
        )}
        {pending.length > 0 && (
          <div className="mb-3 rounded-md border border-amber-200 bg-amber-50 p-3 text-sm">
            <div className="flex flex-wrap items-center gap-2">
              <p className="flex-1 text-amber-800">
                ⏳ {t("feedback.waiting", { count: pending.length })}
                {!online && ` ${t("execution.waitingOffline")}`}
              </p>
              {online && (
                <Button variant="ghost" onClick={syncNow} disabled={syncing}>
                  {t("execution.syncNow")}
                </Button>
              )}
            </div>
            <ul className="mt-1 space-y-1">
              {pending.map((p) => (
                <li key={p.client_uuid} className="flex flex-wrap gap-2">
                  <span className="min-w-0 flex-1 truncate">
                    {t(`feedback.categories.${p.body.category}`)} · {p.body.description}
                  </span>
                  {p.error && (
                    <>
                      <span className="text-red-700">{p.error}</span>
                      <button
                        className="text-red-700 underline"
                        onClick={() => discard("feedback", p.client_uuid)}
                      >
                        {t("execution.discard")}
                      </button>
                    </>
                  )}
                </li>
              ))}
            </ul>
          </div>
        )}
        {adding && (
          <div className="mb-4 rounded-md border border-slate-200 p-4">
            <FeedbackForm
              orgId={orgId}
              projectId={projectId}
              onDone={(result) => {
                setAdding(false);
                setSaved(result);
              }}
            />
          </div>
        )}
        {s && s.hidden_sensitive > 0 && (
          <p className="mb-2 text-xs text-slate-500">
            🔒 {t("feedback.hidden", { count: s.hidden_sensitive })}
          </p>
        )}
        <ErrorText error={entries.error} />
        {shown.length ? (
          <ul className="divide-y divide-slate-100">
            {shown.map((entry) => {
              const node = entry.activity_id ? nodes.get(entry.activity_id) : undefined;
              return (
                <FeedbackItem
                  key={entry.id}
                  entry={entry}
                  orgId={orgId}
                  projectId={projectId}
                  activity={node && `${node.code} ${node.title}`}
                  assignee={entry.assigned_to ? people.get(entry.assigned_to) : undefined}
                />
              );
            })}
          </ul>
        ) : (
          !entries.isPending && <p className="text-sm text-slate-500">{t("feedback.empty")}</p>
        )}
      </Card>
    </>
  );
}
