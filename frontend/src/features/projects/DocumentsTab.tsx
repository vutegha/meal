import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type ChangeEvent, type FormEvent, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { Button, Card, ErrorText } from "@/components/ui";
import { useCurrentOrg } from "@/features/orgs/useCurrentOrg";
import { aiApi, type Project, type SearchHit, type SourceDocument } from "@/lib/api";
import { permissions } from "@/lib/permissions";
import { documentsQuery, proposalsQuery } from "@/lib/queries";

import { ProposalReview } from "./ProposalReview";
import { useInvalidateProject } from "./useInvalidateProject";
import { useJob } from "./useJob";

const ACCEPT = ".pdf,.docx,.xlsx,.txt,.md,.jpg,.jpeg,.png";

function formatSize(bytes: number, language: string): string {
  const units = ["o", "Ko", "Mo"];
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${new Intl.NumberFormat(language, { maximumFractionDigits: 1 }).format(value)} ${units[unit]}`;
}

/** Surligne les passages « … » renvoyés par ts_headline, sans injecter de HTML. */
function Snippet({ text }: { text: string }) {
  return (
    <>
      {text.split(/(«[^»]*»)/).map((part, index) =>
        part.startsWith("«") ? (
          <mark key={index} className="rounded bg-amber-100 px-0.5">
            {part.slice(1, -1)}
          </mark>
        ) : (
          part
        ),
      )}
    </>
  );
}

function DocumentRow({
  document,
  orgId,
  projectId,
  canPlan,
}: {
  document: SourceDocument;
  orgId: string;
  projectId: string;
  canPlan: boolean;
}) {
  const { t, i18n } = useTranslation();
  const invalidate = useInvalidateProject(orgId, projectId);
  const remove = useMutation({
    mutationFn: () => aiApi.deleteDocument(orgId, projectId, document.id),
    onSuccess: invalidate,
  });
  const statusStyle = {
    uploaded: "bg-slate-100 text-slate-700",
    ocr: "bg-amber-100 text-amber-800",
    extracted: "bg-emerald-100 text-emerald-800",
    failed: "bg-red-100 text-red-800",
  }[document.status];
  return (
    <li className="flex flex-wrap items-center gap-x-3 gap-y-1 py-2 text-sm">
      <span className="min-w-0 flex-1 truncate font-medium">{document.filename}</span>
      <span className="text-xs text-slate-500">
        {formatSize(document.size_bytes, i18n.language)}
        {document.page_count > 0 && ` · ${t("documents.pages", { count: document.page_count })}`}
      </span>
      <span className={`rounded px-1.5 py-0.5 text-xs font-medium ${statusStyle}`}>
        {t(`documents.status.${document.status}`)}
      </span>
      {canPlan && (
        <button
          className="rounded px-1.5 text-xs text-red-700 hover:bg-red-50"
          onClick={() => {
            if (window.confirm(t("documents.confirmDelete"))) remove.mutate();
          }}
        >
          {t("logframe.delete")}
        </button>
      )}
      {document.error && (
        <p
          className={`w-full text-xs ${document.status === "failed" ? "text-red-700" : "text-amber-800"}`}
        >
          {document.error}
        </p>
      )}
      <ErrorText error={remove.error} />
    </li>
  );
}

function Search({ orgId, projectId }: { orgId: string; projectId: string }) {
  const { t } = useTranslation();
  const [query, setQuery] = useState("");
  const search = useMutation({ mutationFn: (q: string) => aiApi.search(orgId, projectId, q) });
  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (query.trim().length >= 2) search.mutate(query.trim());
  };
  return (
    <div className="mt-4 border-t border-slate-100 pt-4">
      <form onSubmit={submit} className="flex gap-2">
        <input
          type="search"
          aria-label={t("documents.search")}
          placeholder={t("documents.searchPlaceholder")}
          className="min-w-0 flex-1 rounded-md border border-slate-300 px-3 py-1.5 text-sm"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <Button type="submit" variant="ghost" disabled={search.isPending}>
          {t("documents.search")}
        </Button>
      </form>
      <ErrorText error={search.error} />
      {search.data &&
        (search.data.length ? (
          <ul className="mt-3 space-y-2">
            {search.data.map((hit: SearchHit) => (
              <li key={`${hit.document_id}-${hit.page}`} className="text-sm">
                <p className="text-xs text-slate-500">
                  {hit.filename} · {t("documents.page", { page: hit.page })}
                </p>
                <p className="text-slate-700">
                  … <Snippet text={hit.snippet} /> …
                </p>
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-3 text-sm text-slate-500">{t("documents.noResult")}</p>
        ))}
    </div>
  );
}

export function DocumentsTab({ orgId, project }: { orgId: string; project: Project }) {
  const { t, i18n } = useTranslation();
  const projectId = project.id;
  const { role } = useCurrentOrg();
  const canPlan = permissions.plan(role);
  const queryClient = useQueryClient();
  const invalidate = useInvalidateProject(orgId, projectId);
  const input = useRef<HTMLInputElement>(null);
  const documents = useQuery(documentsQuery(orgId, projectId));
  const proposals = useQuery(proposalsQuery(orgId, projectId));

  const upload = useMutation({
    mutationFn: async (files: File[]) => {
      for (const file of files) await aiApi.upload(orgId, projectId, file);
    },
    onSettled: invalidate,
  });
  const onFiles = (event: ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.target.files ?? []);
    event.target.value = "";
    if (files.length) upload.mutate(files);
  };

  const job = useJob(orgId, () =>
    queryClient.invalidateQueries({ queryKey: proposalsQuery(orgId, projectId).queryKey }),
  );
  const extract = useMutation({
    mutationFn: () => aiApi.extract(orgId, projectId),
    onSuccess: job.start,
  });
  const running = extract.isPending || job.running;

  const pending = proposals.data?.find((p) => p.status === "pending");
  const history = proposals.data?.filter((p) => p.status !== "pending") ?? [];
  const readyCount = documents.data?.filter((d) => d.status === "extracted").length ?? 0;
  const dates = new Intl.DateTimeFormat(i18n.language, { dateStyle: "short", timeStyle: "short" });

  return (
    <>
      <Card title={t("documents.title")}>
        <p className="mb-3 text-sm text-slate-600">{t("documents.intro")}</p>
        {canPlan && (
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <input
              ref={input}
              type="file"
              multiple
              accept={ACCEPT}
              className="hidden"
              onChange={onFiles}
              aria-label={t("documents.upload")}
            />
            <Button
              variant="ghost"
              onClick={() => input.current?.click()}
              disabled={upload.isPending}
            >
              ⬆ {upload.isPending ? t("documents.uploading") : t("documents.upload")}
            </Button>
            <span className="text-xs text-slate-500">{t("documents.formats")}</span>
          </div>
        )}
        <ErrorText error={upload.error} />
        {documents.isPending ? (
          <p className="text-sm text-slate-500">{t("common.loading")}</p>
        ) : documents.data?.length ? (
          <ul className="divide-y divide-slate-100">
            {documents.data.map((document) => (
              <DocumentRow
                key={document.id}
                document={document}
                orgId={orgId}
                projectId={projectId}
                canPlan={canPlan}
              />
            ))}
          </ul>
        ) : (
          <p className="text-sm text-slate-500">{t("documents.empty")}</p>
        )}
        {readyCount > 0 && <Search orgId={orgId} projectId={projectId} />}
      </Card>

      <Card title={t("proposal.title")}>
        {canPlan && !pending && (
          <div className="mb-3 flex flex-wrap items-center gap-3">
            <Button onClick={() => extract.mutate()} disabled={running || readyCount === 0}>
              ✨ {t("proposal.extract")}
            </Button>
            {running && (
              <span role="status" className="text-sm text-slate-600">
                {t("proposal.running")}
              </span>
            )}
            {readyCount === 0 && (
              <span className="text-sm text-slate-500">{t("proposal.needDocument")}</span>
            )}
          </div>
        )}
        <ErrorText error={extract.error} />
        <ErrorText error={job.error} />
        {pending ? (
          <ProposalReview
            key={pending.id}
            orgId={orgId}
            projectId={projectId}
            proposal={pending}
            currency={pending.payload.currency ?? project.currency}
            canPlan={canPlan}
          />
        ) : (
          !running && <p className="text-sm text-slate-500">{t("proposal.none")}</p>
        )}
        {history.length > 0 && (
          <ul className="mt-4 space-y-1 border-t border-slate-100 pt-3 text-xs text-slate-500">
            {history.map((p) => (
              <li key={p.id}>
                {dates.format(new Date(p.created_at))} · {t(`proposal.status.${p.status}`)}
              </li>
            ))}
          </ul>
        )}
      </Card>
    </>
  );
}
