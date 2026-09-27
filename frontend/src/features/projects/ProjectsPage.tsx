import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { type FormEvent, useState } from "react";
import { useTranslation } from "react-i18next";

import { Button, Card, ErrorText, Field } from "@/components/ui";
import { projectsApi } from "@/lib/api";
import { permissions } from "@/lib/permissions";
import { projectsQuery } from "@/lib/queries";
import { useCurrentOrg } from "@/features/orgs/useCurrentOrg";

import { StatusBadge } from "./StatusBadge";

const emptyForm = { code: "", title: "", donor: "", currency: "USD", start_date: "", end_date: "" };

export function ProjectsPage() {
  const { t } = useTranslation();
  const { orgId, role } = useCurrentOrg();
  const queryClient = useQueryClient();
  const projects = useQuery(projectsQuery(orgId));
  const [form, setForm] = useState(emptyForm);
  const [open, setOpen] = useState(false);

  const create = useMutation({
    mutationFn: () =>
      projectsApi.create(orgId, {
        ...form,
        currency: form.currency.toUpperCase(),
        start_date: form.start_date || null,
        end_date: form.end_date || null,
      }),
    onSuccess: async () => {
      setForm(emptyForm);
      setOpen(false);
      await queryClient.invalidateQueries({ queryKey: ["orgs", orgId, "projects"] });
    },
  });

  const submit = (event: FormEvent) => {
    event.preventDefault();
    create.mutate();
  };
  const set = (key: keyof typeof emptyForm) => (e: { target: { value: string } }) =>
    setForm((f) => ({ ...f, [key]: e.target.value }));

  return (
    <>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-xl font-semibold">{t("projects.title")}</h1>
        {permissions.manageProjects(role) && (
          <Button onClick={() => setOpen((v) => !v)}>+ {t("projects.new")}</Button>
        )}
      </div>

      {open && (
        <Card title={t("projects.new")}>
          <form onSubmit={submit} className="space-y-3">
            <div className="grid gap-3 sm:grid-cols-[8rem_1fr]">
              <Field label={t("projects.code")} required value={form.code} onChange={set("code")} />
              <Field
                label={t("projects.name")}
                required
                minLength={2}
                value={form.title}
                onChange={set("title")}
              />
            </div>
            <div className="grid gap-3 sm:grid-cols-4">
              <Field label={t("projects.donor")} value={form.donor} onChange={set("donor")} />
              <Field
                label={t("projects.currency")}
                required
                pattern="[A-Za-z]{3}"
                maxLength={3}
                value={form.currency}
                onChange={set("currency")}
              />
              <Field
                label={t("projects.startDate")}
                type="date"
                value={form.start_date}
                onChange={set("start_date")}
              />
              <Field
                label={t("projects.endDate")}
                type="date"
                value={form.end_date}
                onChange={set("end_date")}
              />
            </div>
            <ErrorText error={create.error} />
            <Button type="submit" disabled={create.isPending}>
              {t("projects.create")}
            </Button>
          </form>
        </Card>
      )}

      <Card>
        {projects.isPending ? (
          <p className="text-sm text-slate-500">{t("common.loading")}</p>
        ) : projects.data?.length ? (
          <ul className="divide-y divide-slate-100">
            {projects.data.map((project) => (
              <li key={project.id}>
                <Link
                  to="/orgs/$orgId/projects/$projectId"
                  params={{ orgId, projectId: project.id }}
                  search={{ tab: "dashboard" }}
                  className="flex flex-wrap items-center gap-3 rounded-md px-2 py-3 hover:bg-slate-50"
                >
                  <span className="font-mono text-xs text-slate-500">{project.code}</span>
                  <span className="min-w-0 flex-1 font-medium">{project.title}</span>
                  {project.donor && <span className="text-sm text-slate-500">{project.donor}</span>}
                  <StatusBadge status={project.status} />
                </Link>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-slate-500">{t("projects.empty")}</p>
        )}
      </Card>
    </>
  );
}
