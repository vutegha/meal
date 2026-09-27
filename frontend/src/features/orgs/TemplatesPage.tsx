import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";
import { useTranslation } from "react-i18next";

import { Button, Card, ErrorText, Field } from "@/components/ui";
import {
  type DocumentTemplate,
  TEMPLATE_KINDS,
  type TemplateIn,
  type TemplateKind,
  templatesApi,
} from "@/lib/api";
import { permissions } from "@/lib/permissions";
import { builtinTemplatesQuery, projectsQuery, templatesQuery } from "@/lib/queries";
import { move, sectionKey, startTemplate } from "@/lib/templates";

import { useCurrentOrg } from "./useCurrentOrg";

function TemplateForm({
  orgId,
  initial,
  templateId,
  onDone,
}: {
  orgId: string;
  initial: TemplateIn;
  templateId?: string;
  onDone: () => void;
}) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const builtin = useQuery(builtinTemplatesQuery(orgId));
  const projects = useQuery(projectsQuery(orgId));
  const [template, setTemplate] = useState<TemplateIn>(initial);
  const computed = new Map(
    (builtin.data?.[template.kind] ?? []).filter((s) => s.computed).map((s) => [s.key, s.title]),
  );
  const missingComputed = [...computed].filter(
    ([key]) => !template.sections.some((s) => s.key === key),
  );
  const donors = [...new Set((projects.data ?? []).map((p) => p.donor).filter(Boolean))];
  const set = (patch: Partial<TemplateIn>) => setTemplate({ ...template, ...patch });
  const setSection = (index: number, patch: Partial<TemplateIn["sections"][number]>) =>
    set({ sections: template.sections.map((s, i) => (i === index ? { ...s, ...patch } : s)) });
  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: ["orgs", orgId, "templates"] });
  const save = useMutation({
    mutationFn: () =>
      templateId
        ? templatesApi.update(orgId, templateId, template)
        : templatesApi.create(orgId, template),
    onSuccess: async () => {
      await invalidate();
      onDone();
    },
  });
  const remove = useMutation({
    mutationFn: () => templatesApi.remove(orgId, templateId ?? ""),
    onSuccess: async () => {
      await invalidate();
      onDone();
    },
  });
  const submit = (event: FormEvent) => {
    event.preventDefault();
    save.mutate();
  };

  return (
    <form onSubmit={submit} className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-3">
        <Field
          label={t("templates.name")}
          required
          minLength={2}
          value={template.name}
          onChange={(e) => set({ name: e.target.value })}
        />
        <div>
          <Field
            label={t("templates.donor")}
            hint={t("templates.donorHint")}
            list="template-donors"
            value={template.donor}
            onChange={(e) => set({ donor: e.target.value })}
          />
          <datalist id="template-donors">
            {donors.map((donor) => (
              <option key={donor} value={donor} />
            ))}
          </datalist>
        </div>
        <label className="flex items-center gap-2 pt-6 text-sm">
          <input
            type="checkbox"
            checked={template.is_default}
            onChange={(e) => set({ is_default: e.target.checked })}
          />
          {t("templates.isDefault")}
        </label>
      </div>

      <div>
        <p className="mb-1 text-sm font-medium text-slate-700">{t("templates.sections")}</p>
        <p className="mb-2 text-xs text-slate-500">{t("templates.sectionsHint")}</p>
        <ol className="space-y-2">
          {template.sections.map((section, index) => (
            <li key={section.key} className="rounded-md border border-slate-200 p-3">
              <div className="flex flex-wrap items-center gap-2">
                <span className="w-6 text-sm text-slate-500 tabular-nums">{index + 1}.</span>
                <input
                  aria-label={t("templates.sectionTitle")}
                  required
                  className="min-w-0 flex-1 rounded-md border border-slate-300 px-2 py-1.5 text-sm"
                  value={section.title}
                  onChange={(e) => setSection(index, { title: e.target.value })}
                />
                {computed.has(section.key) && (
                  <span className="rounded bg-sky-100 px-1.5 py-0.5 text-xs text-sky-800">
                    {t("templates.computed")}
                  </span>
                )}
                <button
                  type="button"
                  aria-label={t("templates.up")}
                  className="px-1 text-slate-500 hover:text-slate-800 disabled:opacity-30"
                  disabled={index === 0}
                  onClick={() => set({ sections: move(template.sections, index, -1) })}
                >
                  ↑
                </button>
                <button
                  type="button"
                  aria-label={t("templates.down")}
                  className="px-1 text-slate-500 hover:text-slate-800 disabled:opacity-30"
                  disabled={index === template.sections.length - 1}
                  onClick={() => set({ sections: move(template.sections, index, 1) })}
                >
                  ↓
                </button>
                <button
                  type="button"
                  aria-label={t("templates.removeSection")}
                  className="px-1 text-red-700 disabled:opacity-30"
                  disabled={template.sections.length === 1}
                  onClick={() => set({ sections: template.sections.filter((_, i) => i !== index) })}
                >
                  ✕
                </button>
              </div>
              {!computed.has(section.key) && (
                <textarea
                  aria-label={t("templates.guidance")}
                  placeholder={t("templates.guidancePlaceholder")}
                  className="mt-2 w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm"
                  rows={1}
                  maxLength={1000}
                  value={section.guidance}
                  onChange={(e) => setSection(index, { guidance: e.target.value })}
                />
              )}
            </li>
          ))}
        </ol>
        <div className="mt-2 flex flex-wrap gap-2">
          <Button
            type="button"
            variant="ghost"
            onClick={() =>
              set({
                sections: [
                  ...template.sections,
                  {
                    key: sectionKey(
                      t("templates.newSection"),
                      template.sections.map((s) => s.key),
                    ),
                    title: t("templates.newSection"),
                    guidance: "",
                  },
                ],
              })
            }
          >
            + {t("templates.addSection")}
          </Button>
          {missingComputed.map(([key, title]) => (
            <Button
              key={key}
              type="button"
              variant="ghost"
              onClick={() =>
                set({ sections: [...template.sections, { key, title, guidance: "" }] })
              }
            >
              + {title}
            </Button>
          ))}
        </div>
      </div>

      <div>
        <p className="mb-2 text-sm font-medium text-slate-700">{t("templates.layout")}</p>
        <div className="grid gap-3 sm:grid-cols-[1fr_1fr_8rem]">
          <Field
            label={t("templates.header")}
            maxLength={200}
            value={template.layout.header}
            onChange={(e) => set({ layout: { ...template.layout, header: e.target.value } })}
          />
          <Field
            label={t("templates.footer")}
            maxLength={200}
            value={template.layout.footer}
            onChange={(e) => set({ layout: { ...template.layout, footer: e.target.value } })}
          />
          <Field
            label={t("templates.color")}
            type="color"
            value={template.layout.color}
            onChange={(e) => set({ layout: { ...template.layout, color: e.target.value } })}
          />
        </div>
      </div>

      <ErrorText error={save.error ?? remove.error} />
      <div className="flex flex-wrap gap-2">
        <Button type="submit" disabled={save.isPending}>
          {t("common.save")}
        </Button>
        <Button type="button" variant="ghost" onClick={onDone}>
          {t("common.cancel")}
        </Button>
        {templateId && (
          <Button
            type="button"
            variant="danger"
            className="ml-auto"
            onClick={() => {
              if (window.confirm(t("templates.confirmDelete"))) remove.mutate();
            }}
          >
            {t("logframe.delete")}
          </Button>
        )}
      </div>
    </form>
  );
}

/** Modèles de TdR et de rapports de l'organisation, avec leurs variantes par bailleur. */
export function TemplatesPage() {
  const { t } = useTranslation();
  const { orgId, role } = useCurrentOrg();
  const canEdit = permissions.manageProjects(role);
  const templates = useQuery(templatesQuery(orgId));
  const builtin = useQuery(builtinTemplatesQuery(orgId));
  const [editing, setEditing] = useState<DocumentTemplate | TemplateKind | null>(null);

  if (editing)
    return (
      <Card
        title={
          typeof editing === "string"
            ? t("templates.newOf", { kind: t(`templates.kinds.${editing}`) })
            : editing.name
        }
      >
        {builtin.data && (
          <TemplateForm
            orgId={orgId}
            initial={typeof editing === "string" ? startTemplate(editing, builtin.data) : editing}
            templateId={typeof editing === "string" ? undefined : editing.id}
            onDone={() => setEditing(null)}
          />
        )}
      </Card>
    );

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">{t("templates.title")}</h1>
      <p className="text-sm text-slate-600">{t("templates.intro")}</p>
      <ErrorText error={templates.error} />
      {TEMPLATE_KINDS.map((kind) => {
        const rows = (templates.data ?? []).filter((tpl) => tpl.kind === kind);
        return (
          <Card key={kind} title={t(`templates.kinds.${kind}`)}>
            {rows.length ? (
              <ul className="mb-3 divide-y divide-slate-100">
                {rows.map((tpl) => (
                  <li key={tpl.id} className="flex flex-wrap items-center gap-2 py-2 text-sm">
                    <span className="min-w-0 flex-1 font-medium">{tpl.name}</span>
                    <span className="text-xs text-slate-500">
                      {tpl.donor
                        ? t("templates.forDonor", { donor: tpl.donor })
                        : t("templates.forOrg")}
                    </span>
                    {tpl.is_default && (
                      <span className="rounded bg-brand-50 px-1.5 py-0.5 text-xs text-brand-800">
                        {t("templates.default")}
                      </span>
                    )}
                    <span className="text-xs text-slate-500">
                      {t("templates.sectionCount", { count: tpl.sections.length })}
                    </span>
                    {canEdit && (
                      <button
                        className="text-brand-700 hover:underline"
                        onClick={() => setEditing(tpl)}
                      >
                        {t("report.edit")}
                      </button>
                    )}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="mb-3 text-sm text-slate-500">{t("templates.builtinUsed")}</p>
            )}
            {canEdit && (
              <Button variant="ghost" onClick={() => setEditing(kind)} disabled={!builtin.data}>
                + {t("templates.new")}
              </Button>
            )}
          </Card>
        );
      })}
    </div>
  );
}
