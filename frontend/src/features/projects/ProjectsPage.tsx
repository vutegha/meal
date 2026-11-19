import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "@tanstack/react-router";
import { type DragEvent, type FormEvent, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { Button, Card, ErrorText, Field } from "@/components/ui";
import { aiApi, projectsApi } from "@/lib/api";
import { permissions } from "@/lib/permissions";
import { projectsQuery } from "@/lib/queries";
import { useCurrentOrg } from "@/features/orgs/useCurrentOrg";

import { ACCEPT } from "./DocumentsTab";
import { StatusBadge } from "./StatusBadge";

const emptyForm = { code: "", title: "", donor: "", currency: "USD", start_date: "", end_date: "" };

export function ProjectsPage() {
  const { t } = useTranslation();
  const { orgId, role } = useCurrentOrg();
  const queryClient = useQueryClient();
  const projects = useQuery(projectsQuery(orgId));
  const [form, setForm] = useState(emptyForm);
  const [open, setOpen] = useState(false);
  const navigate = useNavigate();
  const input = useRef<HTMLInputElement>(null);
  const [files, setFiles] = useState<File[]>([]);
  const [dragOver, setDragOver] = useState(false);
  const [step, setStep] = useState<string | null>(null);

  // Création en une fois : le projet, puis ses documents ; l'onglet Documents lance ensuite
  // l'extraction qui pré-remplit le cadre logique, les indicateurs, le budget et le chronogramme.
  const create = useMutation({
    mutationFn: async () => {
      setStep(t("projects.setup.creating"));
      const project = await projectsApi.create(orgId, {
        ...form,
        currency: form.currency.toUpperCase(),
        start_date: form.start_date || null,
        end_date: form.end_date || null,
      });
      // Le projet existe déjà : un import refusé (format, taille) se reprend dans son onglet
      // Documents plutôt que de recréer le projet.
      let uploaded = true;
      for (const file of files) {
        setStep(t("projects.setup.uploading", { name: file.name }));
        try {
          await aiApi.upload(orgId, project.id, file);
        } catch {
          uploaded = false;
        }
      }
      return { project, uploaded };
    },
    onSettled: () => setStep(null),
    onSuccess: async ({ project, uploaded }) => {
      const withDocuments = files.length > 0;
      setForm(emptyForm);
      setFiles([]);
      setOpen(false);
      await queryClient.invalidateQueries({ queryKey: ["orgs", orgId, "projects"] });
      await navigate({
        to: "/orgs/$orgId/projects/$projectId",
        params: { orgId, projectId: project.id },
        search: withDocuments
          ? { tab: "documents", setup: uploaded || undefined }
          : { tab: "dashboard" },
      });
    },
  });

  const addFiles = (list: FileList | null) => {
    const added = Array.from(list ?? []);
    if (added.length) setFiles((current) => [...current, ...added]);
  };
  const onDrop = (event: DragEvent) => {
    event.preventDefault();
    setDragOver(false);
    addFiles(event.dataTransfer.files);
  };

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
            <p className="text-xs text-slate-500">{t("projects.setup.optional")}</p>

            <div
              onDragOver={(e) => {
                e.preventDefault();
                setDragOver(true);
              }}
              onDragLeave={() => setDragOver(false)}
              onDrop={onDrop}
              className={`rounded-lg border-2 border-dashed p-4 ${
                dragOver ? "border-brand-600 bg-brand-50" : "border-slate-300"
              }`}
            >
              <p className="text-sm font-medium">{t("projects.setup.documents")}</p>
              <p className="mt-0.5 text-xs text-slate-600">{t("projects.setup.documentsHint")}</p>
              <div className="mt-3 flex flex-wrap items-center gap-2">
                <input
                  ref={input}
                  type="file"
                  multiple
                  accept={ACCEPT}
                  className="hidden"
                  aria-label={t("projects.setup.choose")}
                  onChange={(e) => {
                    addFiles(e.target.files);
                    e.target.value = "";
                  }}
                />
                <Button type="button" variant="ghost" onClick={() => input.current?.click()}>
                  ⬆ {t("projects.setup.choose")}
                </Button>
                <span className="text-xs text-slate-500">
                  {t("projects.setup.drop")} · {t("documents.formats")}
                </span>
              </div>
              {files.length > 0 && (
                <ul className="mt-3 divide-y divide-slate-100 rounded-md bg-white text-sm">
                  {files.map((file, index) => (
                    <li
                      key={`${file.name}-${index}`}
                      className="flex items-center gap-2 px-2 py-1.5"
                    >
                      <span className="min-w-0 flex-1 truncate">{file.name}</span>
                      <button
                        type="button"
                        className="rounded px-1.5 text-xs text-red-700 hover:bg-red-50"
                        onClick={() => setFiles(files.filter((_, i) => i !== index))}
                      >
                        {t("common.remove")}
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>

            <ErrorText error={create.error} />
            <div className="flex flex-wrap items-center gap-3">
              <Button type="submit" disabled={create.isPending}>
                {files.length
                  ? t("projects.setup.createWithDocuments", { count: files.length })
                  : t("projects.create")}
              </Button>
              {step && (
                <span role="status" className="text-sm text-slate-600">
                  {step}
                </span>
              )}
            </div>
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
