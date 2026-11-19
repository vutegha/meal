import { useQuery } from "@tanstack/react-query";
import { useNavigate, useSearch } from "@tanstack/react-router";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { Button, Card, ErrorText, Pager } from "@/components/ui";
import { useCurrentOrg } from "@/features/orgs/useCurrentOrg";
import type { Project } from "@/lib/api";
import { flattenTree, formatMoney } from "@/lib/format";
import { discard, syncOutbox, usePending } from "@/lib/outbox";
import { permissions } from "@/lib/permissions";
import { executionsQuery, logframeQuery } from "@/lib/queries";
import { useOnline } from "@/lib/useOnline";

import { ExecutionBadge } from "./ExecutionBadge";
import { ExecutionDetailView } from "./ExecutionDetail";
import { ExecutionForm } from "./ExecutionForm";

function ExecutionList({ orgId, project }: { orgId: string; project: Project }) {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const online = useOnline();
  const { role } = useCurrentOrg();
  const canCollect = permissions.recordValues(role);
  const [offset, setOffset] = useState(0);
  const [search, setSearch] = useState("");
  const executions = useQuery(executionsQuery(orgId, project.id, { offset, q: search }));
  const page = executions.data;
  const logframe = useQuery(logframeQuery(orgId, project.id));
  const pending = usePending(project.id);
  const [adding, setAdding] = useState(false);
  const [notice, setNotice] = useState<"sent" | "queued" | null>(null);
  const [syncing, setSyncing] = useState(false);
  const nodes = new Map(flattenTree(logframe.data ?? []).map((n) => [n.id, n]));
  const dates = new Intl.DateTimeFormat(i18n.language, { dateStyle: "medium" });
  const waiting = pending.executions.length + pending.evidence.length;

  const syncNow = async () => {
    setSyncing(true);
    await syncOutbox();
    setSyncing(false);
  };

  return (
    <>
      {waiting > 0 && (
        <Card>
          <div className="flex flex-wrap items-center gap-3">
            <p className="flex-1 text-sm text-amber-800">
              ⏳ {t("execution.waiting", { count: waiting })}
              {!online && ` ${t("execution.waitingOffline")}`}
            </p>
            {online && (
              <Button variant="ghost" onClick={syncNow} disabled={syncing}>
                {t("execution.syncNow")}
              </Button>
            )}
          </div>
          <ul className="mt-2 space-y-1 text-sm">
            {pending.executions.map((p) => (
              <li key={p.client_uuid} className="flex flex-wrap gap-2">
                <span className="font-medium">
                  {nodes.get(p.body.activity_id)?.code}{" "}
                  {p.body.title || nodes.get(p.body.activity_id)?.title}
                </span>
                <span className="text-slate-500">{dates.format(new Date(p.body.start_date))}</span>
                {p.error && (
                  <>
                    <span className="text-red-700">{p.error}</span>
                    <button
                      className="text-red-700 underline"
                      onClick={() => discard("executions", p.client_uuid)}
                    >
                      {t("execution.discard")}
                    </button>
                  </>
                )}
              </li>
            ))}
          </ul>
        </Card>
      )}

      <Card title={t("execution.title_list")}>
        {canCollect && !adding && (
          <Button className="mb-3" onClick={() => setAdding(true)}>
            + {t("execution.new")}
          </Button>
        )}
        {notice && !adding && (
          <p role="status" className="mb-3 text-sm text-brand-800">
            {t(notice === "sent" ? "execution.sent" : "execution.queued")}
          </p>
        )}
        {adding && (
          <div className="mb-4 rounded-md border border-slate-200 p-4">
            <ExecutionForm
              orgId={orgId}
              projectId={project.id}
              onDone={(outcome) => {
                setAdding(false);
                setNotice(outcome);
              }}
            />
          </div>
        )}
        <input
          type="search"
          className="mb-3 w-full rounded-md border border-slate-300 px-3 py-1.5 text-sm"
          placeholder={t("common.search")}
          aria-label={t("common.search")}
          value={search}
          onChange={(event) => {
            setSearch(event.target.value);
            setOffset(0);
          }}
        />
        <ErrorText error={executions.error} />
        {page?.items.length ? (
          <ul className="divide-y divide-slate-100">
            {page.items.map((e) => {
              const activity = nodes.get(e.activity_id);
              return (
                <li key={e.id}>
                  <button
                    className="flex w-full flex-wrap items-center gap-x-3 gap-y-1 py-2.5 text-left hover:bg-slate-50"
                    onClick={() =>
                      navigate({ to: ".", search: { tab: "execution", execution: e.id } })
                    }
                  >
                    <span className="text-xs text-slate-500 sm:w-28">
                      {dates.format(new Date(e.start_date))}
                    </span>
                    <span className="min-w-0 basis-full text-sm sm:order-none sm:basis-auto sm:flex-1">
                      <span className="mr-2 font-mono text-xs text-slate-500">
                        {activity?.code}
                      </span>
                      {e.title || activity?.title}
                      {e.location && <span className="text-slate-500"> · {e.location}</span>}
                    </span>
                    <span className="text-xs text-slate-600">
                      👥 {e.participants_total} · 📎 {e.evidence_count} ·{" "}
                      {formatMoney(e.spent, project.currency, i18n.language)}
                    </span>
                    <ExecutionBadge status={e.status} />
                  </button>
                </li>
              );
            })}
          </ul>
        ) : (
          !executions.isPending && <p className="text-sm text-slate-500">{t("execution.empty")}</p>
        )}
        {page && (
          <Pager
            total={page.total}
            offset={page.offset}
            limit={page.limit}
            onChange={setOffset}
            labels={{
              range: t("common.pageRange", {
                from: page.offset + 1,
                to: page.offset + page.items.length,
                total: page.total,
              }),
              previous: t("common.previous"),
              next: t("common.next"),
            }}
          />
        )}
      </Card>
    </>
  );
}

export function ExecutionTab({ orgId, project }: { orgId: string; project: Project }) {
  const { execution } = useSearch({ from: "/orgs/$orgId/projects/$projectId" });
  return execution ? (
    <ExecutionDetailView orgId={orgId} project={project} executionId={execution} />
  ) : (
    <ExecutionList orgId={orgId} project={project} />
  );
}
