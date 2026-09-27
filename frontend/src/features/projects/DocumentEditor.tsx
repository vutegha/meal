import { useMutation, useQuery } from "@tanstack/react-query";
import { type ReactNode, useState } from "react";
import { useTranslation } from "react-i18next";

import { Markdown } from "@/components/Markdown";
import { Button, Card, ErrorText } from "@/components/ui";
import { useCurrentOrg } from "@/features/orgs/useCurrentOrg";
import {
  download,
  type ReportSource,
  type TorSection,
  type TorStatus,
  type TorVersion,
} from "@/lib/api";
import { permissions } from "@/lib/permissions";

import { ReviewBox, TorBadge } from "./TorTab";

export interface EditableDocument {
  id: string;
  title: string;
  status: TorStatus;
  version: number;
  sections: TorSection[];
  sources: ReportSource[];
  missing_information: string[];
  review_comment: string;
}

type Action = "submit" | "approve" | "return" | "reopen";

/** Rapport rédigé (narratif ou périodique) : lecture, édition, validation, export. */
export function DocumentEditor({
  doc,
  label,
  computedKeys,
  filename,
  save,
  transition,
  remove,
  exportPath,
  loadVersions,
  onRegenerate,
  busy,
  toolbar,
  children,
  onChanged,
}: {
  doc: EditableDocument;
  label: string;
  computedKeys: Set<string>;
  filename: string;
  save: (body: { title: string; sections: TorSection[] }) => Promise<unknown>;
  transition: (action: Action, comment?: string) => Promise<unknown>;
  remove: () => Promise<unknown>;
  exportPath: (format: "docx" | "pdf") => string;
  loadVersions: () => Promise<TorVersion[]>;
  onRegenerate?: () => void;
  busy: boolean;
  toolbar?: ReactNode;
  children?: ReactNode;
  onChanged: () => Promise<unknown>;
}) {
  const { t, i18n } = useTranslation();
  const { role } = useCurrentOrg();
  const canPlan = permissions.plan(role);
  const canApprove = permissions.manageProjects(role);
  const editable = canPlan && doc.status === "draft";
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState(doc.title);
  const [sections, setSections] = useState<TorSection[]>(doc.sections);
  const [review, setReview] = useState<"approve" | "return" | null>(null);
  const [showVersions, setShowVersions] = useState(false);
  const versions = useQuery({
    queryKey: ["versions", doc.id, doc.version],
    queryFn: loadVersions,
    enabled: showVersions,
  });
  const dirty =
    title !== doc.title || sections.some((s, i) => s.content !== doc.sections[i]?.content);
  const dates = new Intl.DateTimeFormat(i18n.language, { dateStyle: "short", timeStyle: "short" });
  const unknownRefs = sections.some((s) => s.content.includes("[source introuvable]"));

  const saveMutation = useMutation({
    mutationFn: () => save({ title, sections }),
    onSuccess: onChanged,
  });
  const transitionMutation = useMutation({
    mutationFn: ({ action, comment }: { action: Action; comment?: string }) =>
      transition(action, comment),
    onSuccess: async () => {
      setReview(null);
      await onChanged();
    },
  });
  const removeMutation = useMutation({ mutationFn: remove, onSuccess: onChanged });
  const exportFile = useMutation({
    mutationFn: (format: "docx" | "pdf") =>
      download(exportPath(format), `${filename}-v${doc.version}.${format}`),
  });
  const pending = saveMutation.isPending || transitionMutation.isPending || busy;

  return (
    <Card>
      <div className="flex flex-wrap items-center gap-3">
        <p className="w-full text-xs font-medium tracking-wide text-slate-500 uppercase">{label}</p>
        {editing ? (
          <input
            aria-label={t("report.docTitle")}
            className="min-w-0 flex-1 rounded-md border border-slate-300 px-3 py-1.5 text-lg font-semibold"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
          />
        ) : (
          <h2 className="min-w-0 flex-1 text-lg font-semibold">{doc.title}</h2>
        )}
        <TorBadge status={doc.status} />
        <span className="text-xs text-slate-500">v{doc.version}</span>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        {editable && !editing && (
          <>
            <Button variant="ghost" onClick={() => setEditing(true)}>
              ✎ {t("report.edit")}
            </Button>
            <Button
              variant="ghost"
              onClick={() => transitionMutation.mutate({ action: "submit" })}
              disabled={pending}
            >
              {t("tor.submit")}
            </Button>
            {onRegenerate && (
              <Button
                variant="ghost"
                onClick={() => {
                  if (window.confirm(t("report.confirmRegenerate"))) onRegenerate();
                }}
                disabled={pending}
              >
                ✨ {t("report.regenerate")}
              </Button>
            )}
            {toolbar}
          </>
        )}
        {editing && (
          <>
            <Button onClick={() => saveMutation.mutate()} disabled={!dirty || pending}>
              {t("tor.save")}
            </Button>
            <Button
              variant="ghost"
              onClick={() => {
                setTitle(doc.title);
                setSections(doc.sections);
                setEditing(false);
              }}
            >
              {t("common.cancel")}
            </Button>
          </>
        )}
        {canApprove && doc.status === "submitted" && (
          <>
            <Button onClick={() => setReview("approve")} disabled={pending}>
              {t("tor.approve")}
            </Button>
            <Button variant="danger" onClick={() => setReview("return")} disabled={pending}>
              {t("tor.return")}
            </Button>
          </>
        )}
        {canApprove && doc.status === "approved" && (
          <Button
            variant="ghost"
            onClick={() => {
              if (window.confirm(t("report.confirmReopen")))
                transitionMutation.mutate({ action: "reopen" });
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
              if (window.confirm(t("report.confirmDelete"))) removeMutation.mutate();
            }}
          >
            {t("logframe.delete")}
          </Button>
        )}
        {review && (
          <ReviewBox
            action={review}
            onDone={(comment) => transitionMutation.mutate({ action: review, comment })}
          />
        )}
      </div>
      <ErrorText
        error={
          saveMutation.error ?? transitionMutation.error ?? exportFile.error ?? removeMutation.error
        }
      />

      {doc.status === "submitted" && !canApprove && (
        <p className="mt-2 text-sm text-slate-600">{t("tor.awaitingApproval")}</p>
      )}
      {doc.review_comment && (
        <p className="mt-3 rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
          <span className="font-medium">{t("tor.reviewComment")} : </span>
          {doc.review_comment}
        </p>
      )}
      {doc.missing_information.length > 0 && (
        <div className="mt-3 rounded-md border border-amber-200 bg-amber-50 p-3 text-sm">
          <p className="font-medium text-amber-900">{t("tor.missing")}</p>
          <ul className="mt-1 list-disc pl-5 text-amber-900">
            {doc.missing_information.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
      )}
      {unknownRefs && (
        <p role="alert" className="mt-3 text-sm text-red-700">
          {t("report.unknownSource")}
        </p>
      )}
      {children}

      <ol className="mt-6 space-y-6">
        {sections.map((section, index) => (
          <li key={section.key}>
            <h3 className="mb-1.5 text-sm font-semibold text-brand-800">
              {index + 1}. {section.title}
            </h3>
            {editing ? (
              <>
                <textarea
                  aria-label={section.title}
                  className="w-full rounded-md border border-slate-300 px-3 py-2 font-mono text-[13px] leading-relaxed"
                  rows={Math.min(18, Math.max(3, section.content.split("\n").length + 1))}
                  value={section.content}
                  onChange={(e) =>
                    setSections(
                      sections.map((s, i) => (i === index ? { ...s, content: e.target.value } : s)),
                    )
                  }
                />
                {computedKeys.has(section.key) && (
                  <p className="text-xs text-slate-500">{t("report.computedHint")}</p>
                )}
              </>
            ) : section.content.trim() ? (
              <div className="overflow-x-auto">
                <Markdown source={section.content} />
              </div>
            ) : (
              <p className="text-sm text-slate-400">–</p>
            )}
          </li>
        ))}
      </ol>
      {editing && <p className="mt-4 text-xs text-slate-500">{t("tor.formatHint")}</p>}

      {doc.sources.length > 0 && (
        <div className="mt-6 border-t border-slate-100 pt-4">
          <p className="text-sm font-semibold text-slate-700">{t("report.sources")}</p>
          <ul className="mt-1 space-y-0.5 text-xs text-slate-600">
            {doc.sources.map((source) => (
              <li key={source.ref}>
                <span className="mr-1.5 font-mono font-semibold text-brand-700">
                  [{source.ref}]
                </span>
                {source.label}
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="mt-4 border-t border-slate-100 pt-3">
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
      </div>
    </Card>
  );
}
