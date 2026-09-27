import { useMutation, useQuery } from "@tanstack/react-query";
import { type FormEvent, useDeferredValue, useState } from "react";
import { useTranslation } from "react-i18next";

import { Button, Card, ErrorText, Field, Select } from "@/components/ui";
import { useCurrentOrg } from "@/features/orgs/useCurrentOrg";
import { EMPTY_LESSON } from "@/lib/accountability";
import { accountabilityApi, type Lesson, type LessonIn } from "@/lib/api";
import { flattenTree } from "@/lib/format";
import { permissions } from "@/lib/permissions";
import { lessonsQuery, logframeQuery } from "@/lib/queries";

import { useInvalidateProject } from "./useInvalidateProject";

export function LessonForm({
  orgId,
  projectId,
  initial = EMPTY_LESSON,
  lessonId,
  onDone,
}: {
  orgId: string;
  projectId: string;
  initial?: LessonIn;
  lessonId?: string;
  onDone: () => void;
}) {
  const { t } = useTranslation();
  const invalidate = useInvalidateProject(orgId, projectId);
  const logframe = useQuery(logframeQuery(orgId, projectId));
  const activities = flattenTree(logframe.data ?? []).filter(
    (n) => n.level === "activity" || n.level === "sub_activity",
  );
  const [lesson, setLesson] = useState<LessonIn>(initial);
  const [tags, setTags] = useState(initial.tags.join(", "));
  const save = useMutation({
    mutationFn: () => {
      const body = { ...lesson, tags: tags.split(",").filter((tag) => tag.trim()) };
      return lessonId
        ? accountabilityApi.updateLesson(orgId, projectId, lessonId, body)
        : accountabilityApi.addLesson(orgId, projectId, body);
    },
    onSuccess: async () => {
      await invalidate();
      onDone();
    },
  });
  const set = (patch: Partial<LessonIn>) => setLesson({ ...lesson, ...patch });
  const submit = (event: FormEvent) => {
    event.preventDefault();
    save.mutate();
  };

  return (
    <form onSubmit={submit} className="space-y-3">
      <Field
        label={t("lessons.titleLabel")}
        required
        minLength={3}
        value={lesson.title}
        onChange={(e) => set({ title: e.target.value })}
      />
      <label className="block text-sm font-medium text-slate-700">
        {t("lessons.description")}
        <textarea
          className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm font-normal"
          rows={3}
          value={lesson.description}
          onChange={(e) => set({ description: e.target.value })}
        />
      </label>
      <label className="block text-sm font-medium text-slate-700">
        {t("lessons.recommendation")}
        <textarea
          className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm font-normal"
          rows={2}
          value={lesson.recommendation}
          onChange={(e) => set({ recommendation: e.target.value })}
        />
      </label>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field
          label={t("lessons.tags")}
          placeholder={t("lessons.tagsPlaceholder")}
          value={tags}
          onChange={(e) => setTags(e.target.value)}
        />
        <Select
          label={t("execution.activity")}
          value={lesson.activity_id ?? ""}
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

function LessonItem({
  lesson,
  orgId,
  projectId,
  activity,
  onTag,
}: {
  lesson: Lesson;
  orgId: string;
  projectId: string;
  activity?: string;
  onTag: (tag: string) => void;
}) {
  const { t, i18n } = useTranslation();
  const { role } = useCurrentOrg();
  const canPlan = permissions.plan(role);
  const invalidate = useInvalidateProject(orgId, projectId);
  const [editing, setEditing] = useState(false);
  const remove = useMutation({
    mutationFn: () => accountabilityApi.deleteLesson(orgId, projectId, lesson.id),
    onSuccess: invalidate,
  });
  if (editing)
    return (
      <li className="py-3">
        <LessonForm
          orgId={orgId}
          projectId={projectId}
          lessonId={lesson.id}
          initial={lesson}
          onDone={() => setEditing(false)}
        />
      </li>
    );
  return (
    <li className="py-3">
      <div className="flex flex-wrap items-start gap-2">
        <h3 className="min-w-0 flex-1 text-sm font-semibold">💡 {lesson.title}</h3>
        <span className="text-xs text-slate-500">
          {new Intl.DateTimeFormat(i18n.language, { dateStyle: "medium" }).format(
            new Date(lesson.created_at),
          )}
        </span>
      </div>
      {lesson.description && (
        <p className="mt-1 text-sm whitespace-pre-line text-slate-700">{lesson.description}</p>
      )}
      {lesson.recommendation && (
        <p className="mt-1 text-sm text-slate-700">
          <span className="font-medium text-brand-800">{t("lessons.recommendation")} : </span>
          {lesson.recommendation}
        </p>
      )}
      <div className="mt-1.5 flex flex-wrap items-center gap-1.5 text-xs">
        {activity && <span className="text-slate-500">{activity}</span>}
        {lesson.source_report_id && (
          <span className="text-slate-500">
            {activity && "· "}
            {t("lessons.fromReportTag")}
          </span>
        )}
        {lesson.tags.map((tag) => (
          <button
            key={tag}
            className="rounded-full bg-brand-50 px-2 py-0.5 text-brand-800 hover:bg-brand-100"
            onClick={() => onTag(tag)}
          >
            #{tag}
          </button>
        ))}
        <span className="flex-1" />
        {canPlan && (
          <>
            <button className="text-brand-700 hover:underline" onClick={() => setEditing(true)}>
              {t("report.edit")}
            </button>
            <button
              className="text-red-700 hover:underline"
              onClick={() => {
                if (window.confirm(t("lessons.confirmDelete"))) remove.mutate();
              }}
            >
              {t("logframe.delete")}
            </button>
          </>
        )}
      </div>
    </li>
  );
}

export function LessonsTab({ orgId, projectId }: { orgId: string; projectId: string }) {
  const { t } = useTranslation();
  const { role } = useCurrentOrg();
  const canPlan = permissions.plan(role);
  const [search, setSearch] = useState("");
  const [tag, setTag] = useState("");
  const [adding, setAdding] = useState(false);
  const q = useDeferredValue(search);
  const lessons = useQuery(lessonsQuery(orgId, projectId, q, tag));
  const all = useQuery(lessonsQuery(orgId, projectId));
  const logframe = useQuery(logframeQuery(orgId, projectId));
  const nodes = new Map(flattenTree(logframe.data ?? []).map((n) => [n.id, n]));
  const tagCounts = new Map<string, number>();
  for (const lesson of all.data ?? [])
    for (const item of lesson.tags) tagCounts.set(item, (tagCounts.get(item) ?? 0) + 1);

  return (
    <Card title={t("lessons.title")}>
      <p className="mb-3 text-sm text-slate-600">{t("lessons.intro")}</p>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <input
          type="search"
          aria-label={t("lessons.search")}
          placeholder={t("lessons.search")}
          className="min-w-0 flex-1 rounded-md border border-slate-300 px-3 py-2 text-sm"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        {canPlan && !adding && (
          <Button onClick={() => setAdding(true)}>+ {t("lessons.new")}</Button>
        )}
      </div>
      {tagCounts.size > 0 && (
        <div className="mb-3 flex flex-wrap gap-1.5 text-xs">
          {[...tagCounts].map(([item, count]) => (
            <button
              key={item}
              aria-pressed={tag === item}
              className={`rounded-full px-2 py-0.5 ${
                tag === item ? "bg-brand-700 text-white" : "bg-slate-100 text-slate-700"
              }`}
              onClick={() => setTag(tag === item ? "" : item)}
            >
              #{item} · {count}
            </button>
          ))}
        </div>
      )}
      {adding && (
        <div className="mb-4 rounded-md border border-slate-200 p-4">
          <LessonForm orgId={orgId} projectId={projectId} onDone={() => setAdding(false)} />
        </div>
      )}
      <ErrorText error={lessons.error} />
      {lessons.data?.length ? (
        <ul className="divide-y divide-slate-100">
          {lessons.data.map((lesson) => {
            const node = lesson.activity_id ? nodes.get(lesson.activity_id) : undefined;
            return (
              <LessonItem
                key={lesson.id}
                lesson={lesson}
                orgId={orgId}
                projectId={projectId}
                activity={node && `${node.code} ${node.title}`}
                onTag={setTag}
              />
            );
          })}
        </ul>
      ) : (
        !lessons.isPending && (
          <p className="text-sm text-slate-500">
            {search || tag ? t("lessons.noMatch") : t("lessons.empty")}
          </p>
        )
      )}
    </Card>
  );
}
