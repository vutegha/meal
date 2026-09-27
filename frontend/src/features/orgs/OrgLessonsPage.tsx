import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "@tanstack/react-router";
import { useDeferredValue, useState } from "react";
import { useTranslation } from "react-i18next";

import { Card, ErrorText } from "@/components/ui";
import { lessonsQuery, projectsQuery } from "@/lib/queries";

/** Leçons apprises de tous les projets de l'organisation : recherche, étiquettes, projet. */
export function OrgLessonsPage() {
  const { t, i18n } = useTranslation();
  const { orgId } = useParams({ from: "/orgs/$orgId" });
  const [search, setSearch] = useState("");
  const [tag, setTag] = useState("");
  const [projectId, setProjectId] = useState("");
  const q = useDeferredValue(search);
  const lessons = useQuery(lessonsQuery(orgId, null, q, tag));
  const all = useQuery(lessonsQuery(orgId, null));
  const projects = useQuery(projectsQuery(orgId));
  const titles = new Map((projects.data ?? []).map((p) => [p.id, p.title]));
  const shown = (lessons.data ?? []).filter((l) => !projectId || l.project_id === projectId);
  const tagCounts = new Map<string, number>();
  for (const lesson of all.data ?? [])
    for (const item of lesson.tags) tagCounts.set(item, (tagCounts.get(item) ?? 0) + 1);
  const dates = new Intl.DateTimeFormat(i18n.language, { dateStyle: "medium" });

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">{t("lessons.title")}</h1>
      <Card>
        <p className="mb-3 text-sm text-slate-600">{t("lessons.orgIntro")}</p>
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <input
            type="search"
            aria-label={t("lessons.search")}
            placeholder={t("lessons.search")}
            className="min-w-0 flex-1 rounded-md border border-slate-300 px-3 py-2 text-sm"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <select
            aria-label={t("lessons.project")}
            className="rounded-md border border-slate-300 px-3 py-2 text-sm"
            value={projectId}
            onChange={(e) => setProjectId(e.target.value)}
          >
            <option value="">{t("lessons.allProjects")}</option>
            {(projects.data ?? []).map((project) => (
              <option key={project.id} value={project.id}>
                {project.code} · {project.title}
              </option>
            ))}
          </select>
        </div>
        {tagCounts.size > 0 && (
          <div className="mb-3 flex flex-wrap gap-1.5 text-xs">
            {[...tagCounts]
              .sort((a, b) => b[1] - a[1])
              .map(([item, count]) => (
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
        <ErrorText error={lessons.error} />
        {!lessons.isPending && (
          <p className="mb-1 text-xs text-slate-500">
            {t("lessons.count", { count: shown.length })}
          </p>
        )}
        {shown.length ? (
          <ul className="divide-y divide-slate-100">
            {shown.map((lesson) => (
              <li key={lesson.id} className="py-3">
                <div className="flex flex-wrap items-start gap-2">
                  <h2 className="min-w-0 flex-1 text-sm font-semibold">💡 {lesson.title}</h2>
                  <span className="text-xs text-slate-500">
                    {dates.format(new Date(lesson.created_at))}
                  </span>
                </div>
                {lesson.description && (
                  <p className="mt-1 text-sm whitespace-pre-line text-slate-700">
                    {lesson.description}
                  </p>
                )}
                {lesson.recommendation && (
                  <p className="mt-1 text-sm text-slate-700">
                    <span className="font-medium text-brand-800">
                      {t("lessons.recommendation")} :{" "}
                    </span>
                    {lesson.recommendation}
                  </p>
                )}
                <div className="mt-1.5 flex flex-wrap items-center gap-1.5 text-xs">
                  <Link
                    to="/orgs/$orgId/projects/$projectId"
                    params={{ orgId, projectId: lesson.project_id }}
                    search={{ tab: "lessons" }}
                    title={t("lessons.openProject")}
                    className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-slate-700 hover:bg-slate-200"
                  >
                    {lesson.project_code}
                  </Link>
                  <span className="text-slate-500">{titles.get(lesson.project_id)}</span>
                  {lesson.tags.map((item) => (
                    <button
                      key={item}
                      className="rounded-full bg-brand-50 px-2 py-0.5 text-brand-800 hover:bg-brand-100"
                      onClick={() => setTag(item)}
                    >
                      #{item}
                    </button>
                  ))}
                </div>
              </li>
            ))}
          </ul>
        ) : (
          !lessons.isPending && (
            <p className="text-sm text-slate-500">
              {search || tag || projectId ? t("lessons.noMatch") : t("lessons.empty")}
            </p>
          )
        )}
      </Card>
    </div>
  );
}
