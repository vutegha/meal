import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useSearch } from "@tanstack/react-router";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { Markdown } from "@/components/Markdown";
import { LazyRichEditor as RichEditor } from "@/components/LazyRichEditor";
import { Button, Card, ErrorText } from "@/components/ui";
import { useCurrentOrg } from "@/features/orgs/useCurrentOrg";
import {
  download,
  type LogframeNode,
  type Project,
  type Tor,
  type TorSection,
  type TorStatus,
  torApi,
} from "@/lib/api";
import { flattenTree } from "@/lib/format";
import { permissions } from "@/lib/permissions";
import { logframeQuery, torQuery, torsQuery, torVersionsQuery } from "@/lib/queries";

import { useInvalidateProject } from "./useInvalidateProject";
import { useJob } from "./useJob";

const statusStyles: Record<TorStatus, string> = {
  draft: "bg-slate-100 text-slate-700",
  submitted: "bg-amber-100 text-amber-800",
  approved: "bg-emerald-100 text-emerald-800",
};

export function TorBadge({ status }: { status: TorStatus }) {
  const { t } = useTranslation();
  return (
    <span className={`rounded px-1.5 py-0.5 text-xs font-medium ${statusStyles[status]}`}>
      {t(`tor.status.${status}`)}
    </span>
  );
}

// --- Liste des activités et de leurs TdR --------------------------------------------

function GenerateForm({
  onStart,
  disabled,
  onCancel,
}: {
  onStart: (instructions: string) => void;
  disabled: boolean;
  onCancel: () => void;
}) {
  const { t } = useTranslation();
  const [instructions, setInstructions] = useState("");
  return (
    <div className="mt-2 w-full space-y-2 rounded-md bg-slate-50 p-3">
      <label className="block text-xs font-medium text-slate-700">
        {t("tor.instructions")}
        <textarea
          className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm font-normal"
          rows={2}
          placeholder={t("tor.instructionsPlaceholder")}
          value={instructions}
          onChange={(e) => setInstructions(e.target.value)}
        />
      </label>
      <div className="flex gap-2">
        <Button onClick={() => onStart(instructions)} disabled={disabled}>
          ✨ {t("tor.generate")}
        </Button>
        <Button variant="ghost" onClick={onCancel}>
          {t("common.cancel")}
        </Button>
      </div>
    </div>
  );
}

function TorList({ orgId, projectId }: { orgId: string; projectId: string }) {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { role } = useCurrentOrg();
  const canPlan = permissions.plan(role);
  const logframe = useQuery(logframeQuery(orgId, projectId));
  const tors = useQuery(torsQuery(orgId, projectId));
  const [asking, setAsking] = useState<string | null>(null);
  const open = (torId: string) => navigate({ to: ".", search: { tab: "tor", tor: torId } });

  const job = useJob(orgId, async (result) => {
    await queryClient.invalidateQueries({ queryKey: torsQuery(orgId, projectId).queryKey });
    await open(String(result.result.tor_id));
  });
  const generate = useMutation({
    mutationFn: ({ activityId, instructions }: { activityId: string; instructions: string }) =>
      torApi.generate(orgId, projectId, activityId, instructions),
    onSuccess: (started) => {
      setAsking(null);
      job.start(started);
    },
  });
  const create = useMutation({
    mutationFn: (activityId: string) => torApi.create(orgId, projectId, activityId),
    onSuccess: (tor) => open(tor.id),
  });

  const nodes = flattenTree(logframe.data ?? []);
  const parents = new Map(nodes.map((n) => [n.id, n]));
  const activities = nodes.filter((n) => n.level === "activity" || n.level === "sub_activity");
  const byActivity = new Map((tors.data ?? []).map((tor) => [tor.activity_id, tor]));
  const busy = generate.isPending || job.running;
  const dates = new Intl.DateTimeFormat(i18n.language, { dateStyle: "medium" });

  if (logframe.isPending || tors.isPending)
    return <p className="text-sm text-slate-500">{t("common.loading")}</p>;

  const row = (activity: LogframeNode) => {
    const tor = byActivity.get(activity.id);
    const parent = activity.parent_id ? parents.get(activity.parent_id) : undefined;
    return (
      <li key={activity.id} className="flex flex-wrap items-center gap-x-3 gap-y-1 py-2.5">
        <div className="min-w-0 flex-1">
          <p className="text-sm">
            <span className="mr-2 font-mono text-xs text-slate-500">{activity.code}</span>
            {activity.title}
          </p>
          {parent && (
            <p className="text-xs text-slate-500">
              {parent.code} {parent.title}
            </p>
          )}
        </div>
        {tor ? (
          <>
            <TorBadge status={tor.status} />
            <span className="text-xs text-slate-500">
              v{tor.version} · {dates.format(new Date(tor.updated_at))}
            </span>
            <Button variant="ghost" onClick={() => open(tor.id)}>
              {t("tor.open")}
            </Button>
          </>
        ) : (
          <>
            <span className="text-xs text-slate-500">{t("tor.none")}</span>
            {canPlan && (
              <>
                <Button variant="ghost" onClick={() => setAsking(activity.id)} disabled={busy}>
                  ✨ {t("tor.generateShort")}
                </Button>
                <Button
                  variant="ghost"
                  onClick={() => create.mutate(activity.id)}
                  disabled={create.isPending}
                >
                  {t("tor.createBlank")}
                </Button>
              </>
            )}
          </>
        )}
        {asking === activity.id && (
          <GenerateForm
            disabled={busy}
            onCancel={() => setAsking(null)}
            onStart={(instructions) => generate.mutate({ activityId: activity.id, instructions })}
          />
        )}
      </li>
    );
  };

  return (
    <Card title={t("tor.title")}>
      <p className="mb-2 text-sm text-slate-600">{t("tor.intro")}</p>
      {busy && (
        <p role="status" className="mb-2 text-sm text-slate-600">
          {t("tor.running")}
        </p>
      )}
      <ErrorText error={generate.error ?? job.error ?? create.error} />
      {activities.length ? (
        <ul className="divide-y divide-slate-100">{activities.map(row)}</ul>
      ) : (
        <p className="text-sm text-slate-500">{t("tor.noActivity")}</p>
      )}
    </Card>
  );
}

// --- Édition et validation d'un TdR -------------------------------------------------

export function ReviewBox({
  onDone,
  action,
}: {
  onDone: (comment: string) => void;
  action: "approve" | "return";
}) {
  const { t } = useTranslation();
  const [comment, setComment] = useState("");
  return (
    <div className="w-full space-y-2 rounded-md bg-slate-50 p-3">
      <label className="block text-xs font-medium text-slate-700">
        {t(action === "return" ? "tor.returnComment" : "tor.approveComment")}
        <textarea
          className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm font-normal"
          rows={2}
          value={comment}
          required={action === "return"}
          onChange={(e) => setComment(e.target.value)}
        />
      </label>
      <Button
        onClick={() => onDone(comment)}
        disabled={action === "return" && !comment.trim()}
        variant={action === "return" ? "danger" : "primary"}
      >
        {t(action === "return" ? "tor.return" : "tor.approve")}
      </Button>
    </div>
  );
}

function TorEditor({ orgId, projectId, tor }: { orgId: string; projectId: string; tor: Tor }) {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const { role } = useCurrentOrg();
  const invalidate = useInvalidateProject(orgId, projectId);
  const canPlan = permissions.plan(role);
  const canApprove = permissions.manageProjects(role);
  const editable = canPlan && tor.status === "draft";
  const [title, setTitle] = useState(tor.title);
  const [sections, setSections] = useState<TorSection[]>(tor.sections);
  const [review, setReview] = useState<"approve" | "return" | null>(null);
  const [showVersions, setShowVersions] = useState(false);
  const versions = useQuery({
    ...torVersionsQuery(orgId, projectId, tor.id),
    enabled: showVersions,
  });
  const dirty =
    title !== tor.title || sections.some((s, i) => s.content !== tor.sections[i]?.content);
  const dates = new Intl.DateTimeFormat(i18n.language, { dateStyle: "short", timeStyle: "short" });

  const save = useMutation({
    mutationFn: () => torApi.update(orgId, projectId, tor.id, { title, sections }),
    onSuccess: invalidate,
  });
  const transition = useMutation({
    mutationFn: ({
      action,
      comment,
    }: {
      action: Parameters<typeof torApi.transition>[3];
      comment?: string;
    }) => torApi.transition(orgId, projectId, tor.id, action, comment),
    onSuccess: async () => {
      setReview(null);
      await invalidate();
    },
  });
  const remove = useMutation({
    mutationFn: () => torApi.remove(orgId, projectId, tor.id),
    onSuccess: async () => {
      await navigate({ to: ".", search: { tab: "tor" } });
      await invalidate();
    },
  });
  const exportFile = useMutation({
    mutationFn: (format: "docx" | "pdf") =>
      download(
        torApi.exportPath(orgId, projectId, tor.id, format),
        `TdR-v${tor.version}.${format}`,
      ),
  });
  const pending = save.isPending || transition.isPending;

  return (
    <>
      <Link to="." search={{ tab: "tor" }} className="text-sm text-brand-700 hover:underline">
        ← {t("tor.back")}
      </Link>
      <Card>
        <div className="flex flex-wrap items-center gap-3">
          {editable ? (
            <input
              aria-label={t("tor.docTitle")}
              className="min-w-0 flex-1 rounded-md border border-slate-300 px-3 py-1.5 text-lg font-semibold"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
            />
          ) : (
            <h2 className="min-w-0 flex-1 text-lg font-semibold">{tor.title}</h2>
          )}
          <TorBadge status={tor.status} />
          <span className="text-xs text-slate-500">v{tor.version}</span>
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          {editable && (
            <>
              <Button onClick={() => save.mutate()} disabled={!dirty || pending}>
                {t("tor.save")}
              </Button>
              <Button
                variant="ghost"
                onClick={() => transition.mutate({ action: "submit" })}
                disabled={dirty || pending}
                title={dirty ? t("tor.saveFirst") : undefined}
              >
                {t("tor.submit")}
              </Button>
            </>
          )}
          {canApprove && tor.status === "submitted" && (
            <>
              <Button onClick={() => setReview("approve")} disabled={pending}>
                {t("tor.approve")}
              </Button>
              <Button variant="danger" onClick={() => setReview("return")} disabled={pending}>
                {t("tor.return")}
              </Button>
            </>
          )}
          {canApprove && tor.status === "approved" && (
            <Button
              variant="ghost"
              onClick={() => {
                if (window.confirm(t("tor.confirmReopen"))) transition.mutate({ action: "reopen" });
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
                if (window.confirm(t("tor.confirmDelete"))) remove.mutate();
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
        {tor.status === "submitted" && !canApprove && (
          <p className="mt-2 text-sm text-slate-600">{t("tor.awaitingApproval")}</p>
        )}
        {tor.review_comment && (
          <p className="mt-3 rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
            <span className="font-medium">{t("tor.reviewComment")} : </span>
            {tor.review_comment}
          </p>
        )}
        {tor.missing_information.length > 0 && (
          <div className="mt-3 rounded-md border border-amber-200 bg-amber-50 p-3 text-sm">
            <p className="font-medium text-amber-900">{t("tor.missing")}</p>
            <ul className="mt-1 list-disc pl-5 text-amber-900">
              {tor.missing_information.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </div>
        )}
      </Card>

      <Card>
        <ol className="space-y-6">
          {sections.map((section, index) => (
            <li key={section.key}>
              <h3 className="mb-1.5 text-sm font-semibold text-brand-800">
                {index + 1}. {section.title}
              </h3>
              {editable ? (
                <>
                  <RichEditor
                    label={section.title}
                    value={section.content}
                    onChange={(content) =>
                      setSections((current) =>
                        current.map((s, i) => (i === index ? { ...s, content } : s)),
                      )
                    }
                  />
                  {section.key === "budget" && (
                    <p className="text-xs text-slate-500">{t("tor.budgetHint")}</p>
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
        {editable && <p className="mt-4 text-xs text-slate-500">{t("tor.formatHint")}</p>}
      </Card>

      <Card>
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
      </Card>
    </>
  );
}

export function TorTab({ orgId, project }: { orgId: string; project: Project }) {
  const { t } = useTranslation();
  const { tor: torId } = useSearch({ from: "/orgs/$orgId/projects/$projectId" });
  const tor = useQuery({
    ...torQuery(orgId, project.id, torId ?? ""),
    enabled: !!torId,
  });
  if (!torId) return <TorList orgId={orgId} projectId={project.id} />;
  if (tor.isPending) return <p className="text-sm text-slate-500">{t("common.loading")}</p>;
  if (!tor.data) return <ErrorText error={tor.error} />;
  return (
    <TorEditor
      key={`${tor.data.id}-${tor.data.version}-${tor.data.status}`}
      orgId={orgId}
      projectId={project.id}
      tor={tor.data}
    />
  );
}
