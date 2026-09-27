import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import { Button, ErrorText } from "@/components/ui";
import {
  aiApi,
  type NodeLevel,
  type Proposal,
  type ProposedBudgetLine,
  type ProposedNode,
} from "@/lib/api";
import { formatMoney, formatNumber } from "@/lib/format";

const levelStyles: Record<NodeLevel, string> = {
  goal: "bg-brand-700 text-white",
  outcome: "bg-brand-100 text-brand-800",
  output: "bg-sky-100 text-sky-800",
  activity: "bg-amber-100 text-amber-800",
  sub_activity: "bg-slate-100 text-slate-700",
};

interface Sourced {
  source_document: number | null;
  source_page: number | null;
  source_quote: string;
  verified: boolean;
}

function Source({ item, documents }: { item: Sourced; documents: string[] }) {
  const { t } = useTranslation();
  if (!item.source_quote) return null;
  const document = item.source_document ? documents[item.source_document - 1] : undefined;
  return (
    <p className="mt-0.5 text-xs text-slate-500">
      <span
        className={`mr-1.5 rounded px-1 py-0.5 font-medium ${
          item.verified ? "bg-emerald-50 text-emerald-700" : "bg-amber-100 text-amber-800"
        }`}
      >
        {item.verified ? t("proposal.verified") : t("proposal.unverified")}
      </span>
      {[document, item.source_page ? t("documents.page", { page: item.source_page }) : null]
        .filter(Boolean)
        .join(", ")}
      {" : "}
      <q className="italic">{item.source_quote}</q>
    </p>
  );
}

const planned = (line: ProposedBudgetLine) => line.quantity * line.unit_cost * line.frequency;

export function ProposalReview({
  orgId,
  projectId,
  proposal,
  currency,
  canPlan,
}: {
  orgId: string;
  projectId: string;
  proposal: Proposal;
  currency: string;
  canPlan: boolean;
}) {
  const { t, i18n } = useTranslation();
  const queryClient = useQueryClient();
  const { nodes, indicators, budget_lines: lines, documents } = proposal.payload;

  const children = useMemo(() => {
    const map = new Map<string | null, ProposedNode[]>();
    const refs = new Set(nodes.map((n) => n.ref));
    for (const node of nodes) {
      const parent = node.parent_ref && refs.has(node.parent_ref) ? node.parent_ref : null;
      map.set(parent, [...(map.get(parent) ?? []), node]);
    }
    return map;
  }, [nodes]);
  const byRef = useMemo(() => new Map(nodes.map((n) => [n.ref, n])), [nodes]);

  const [selected, setSelected] = useState(() => new Set(nodes.map((n) => n.ref)));
  const [titles, setTitles] = useState<Record<string, string>>({});
  const [keptIndicators, setKeptIndicators] = useState(() => new Set(indicators.keys()));
  const [keptLines, setKeptLines] = useState(() => new Set(lines.keys()));

  /** Retenir un élément retient ses parents ; l'écarter écarte ses descendants. */
  const toggle = (ref: string) => {
    const next = new Set(selected);
    if (next.has(ref)) {
      const drop = (r: string) => {
        next.delete(r);
        for (const child of children.get(r) ?? []) drop(child.ref);
      };
      drop(ref);
    } else {
      let current: ProposedNode | undefined = byRef.get(ref);
      while (current) {
        next.add(current.ref);
        current = current.parent_ref ? byRef.get(current.parent_ref) : undefined;
      }
    }
    setSelected(next);
  };
  const flip = (set: Set<number>, index: number) => {
    const next = new Set(set);
    if (next.has(index)) next.delete(index);
    else next.add(index);
    return next;
  };

  const indicatorActive = (index: number) =>
    keptIndicators.has(index) && selected.has(indicators[index].node_ref);
  const lineActive = (index: number) =>
    keptLines.has(index) &&
    (lines[index].activity_ref === null || selected.has(lines[index].activity_ref!));
  const total = lines.reduce(
    (sum, line, index) => sum + (lineActive(index) ? planned(line) : 0),
    0,
  );
  const unverified =
    nodes.filter((n) => !n.verified).length +
    indicators.filter((i) => !i.verified).length +
    lines.filter((l) => !l.verified).length;

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: ["orgs", orgId, "projects", projectId] });
  const apply = useMutation({
    mutationFn: () =>
      aiApi.apply(orgId, projectId, proposal.id, {
        nodes: nodes
          .filter((n) => selected.has(n.ref))
          .map((n) => ({ ...n, title: titles[n.ref]?.trim() || n.title })),
        indicators: indicators.filter((_, index) => indicatorActive(index)),
        budget_lines: lines.filter((_, index) => lineActive(index)),
      }),
    onSuccess: invalidate,
  });
  const reject = useMutation({
    mutationFn: () => aiApi.reject(orgId, projectId, proposal.id),
    onSuccess: invalidate,
  });

  const renderNode = (node: ProposedNode) => (
    <li key={node.ref} className="py-1.5">
      <div className="flex items-start gap-2">
        <input
          type="checkbox"
          className="mt-1"
          checked={selected.has(node.ref)}
          disabled={!canPlan}
          onChange={() => toggle(node.ref)}
          aria-label={`${node.code} ${node.title}`}
        />
        <div className={`min-w-0 flex-1 ${selected.has(node.ref) ? "" : "opacity-50"}`}>
          <div className="flex flex-wrap items-center gap-2">
            <span
              className={`shrink-0 rounded px-1.5 py-0.5 text-[11px] font-semibold uppercase tracking-wide ${levelStyles[node.level]}`}
            >
              {t(`levels.${node.level}`)}
            </span>
            <span className="font-mono text-xs text-slate-500">{node.code}</span>
            <input
              aria-label={t("logframe.title")}
              className="min-w-48 flex-1 rounded border border-transparent px-1 py-0.5 text-sm hover:border-slate-300 focus:border-brand-600 focus:outline-none"
              value={titles[node.ref] ?? node.title}
              disabled={!canPlan || !selected.has(node.ref)}
              onChange={(e) => setTitles({ ...titles, [node.ref]: e.target.value })}
            />
          </div>
          <Source item={node} documents={documents} />
        </div>
      </div>
      {(children.get(node.ref) ?? []).length > 0 && (
        <ul className="ml-6 border-l border-slate-200 pl-3">
          {children.get(node.ref)!.map(renderNode)}
        </ul>
      )}
    </li>
  );

  return (
    <div className="space-y-5">
      <div className="rounded-md bg-slate-50 p-3 text-sm text-slate-700">
        <p>{proposal.payload.summary}</p>
        <p className="mt-2 text-xs text-slate-500">
          {t("proposal.counts", {
            nodes: nodes.length,
            indicators: indicators.length,
            lines: lines.length,
          })}
          {unverified > 0 && ` · ${t("proposal.unverifiedCount", { count: unverified })}`}
        </p>
      </div>

      {proposal.payload.missing_information.length > 0 && (
        <div className="rounded-md border border-amber-200 bg-amber-50 p-3 text-sm">
          <p className="font-medium text-amber-900">{t("proposal.missing")}</p>
          <ul className="mt-1 list-disc pl-5 text-amber-900">
            {proposal.payload.missing_information.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
      )}

      <section>
        <h3 className="mb-1 text-sm font-semibold">{t("projects.tabs.logframe")}</h3>
        <ul>{(children.get(null) ?? []).map(renderNode)}</ul>
      </section>

      <section>
        <h3 className="mb-1 text-sm font-semibold">{t("projects.tabs.indicators")}</h3>
        <ul className="divide-y divide-slate-100">
          {indicators.map((indicator, index) => (
            <li key={index} className="flex items-start gap-2 py-1.5">
              <input
                type="checkbox"
                className="mt-1"
                checked={indicatorActive(index)}
                disabled={!canPlan || !selected.has(indicator.node_ref)}
                onChange={() => setKeptIndicators(flip(keptIndicators, index))}
                aria-label={indicator.name}
              />
              <div
                className={`min-w-0 flex-1 text-sm ${indicatorActive(index) ? "" : "opacity-50"}`}
              >
                <p>
                  <span className="mr-2 font-mono text-xs text-slate-500">
                    {byRef.get(indicator.node_ref)?.code ?? indicator.node_ref} · {indicator.code}
                  </span>
                  {indicator.name}
                </p>
                <p className="text-xs text-slate-600">
                  {t("indicators.baseline")} : {formatNumber(indicator.baseline, i18n.language)} ·{" "}
                  {t("indicators.target")} : {formatNumber(indicator.target, i18n.language)}{" "}
                  {indicator.unit}
                  {indicator.source_of_verification &&
                    ` · ${t("indicators.source")} : ${indicator.source_of_verification}`}
                </p>
                <Source item={indicator} documents={documents} />
              </div>
            </li>
          ))}
        </ul>
      </section>

      <section>
        <h3 className="mb-1 text-sm font-semibold">
          {t("projects.tabs.budget")} · {formatMoney(total, currency, i18n.language)}
        </h3>
        <ul className="divide-y divide-slate-100">
          {lines.map((line, index) => {
            const activity = line.activity_ref ? byRef.get(line.activity_ref) : undefined;
            return (
              <li key={index} className="flex items-start gap-2 py-1.5">
                <input
                  type="checkbox"
                  className="mt-1"
                  checked={lineActive(index)}
                  disabled={
                    !canPlan || (line.activity_ref !== null && !selected.has(line.activity_ref))
                  }
                  onChange={() => setKeptLines(flip(keptLines, index))}
                  aria-label={line.label}
                />
                <div className={`min-w-0 flex-1 text-sm ${lineActive(index) ? "" : "opacity-50"}`}>
                  <p className="flex flex-wrap gap-x-2">
                    <span className="font-mono text-xs text-slate-500">
                      {activity?.code ?? t("budget.support")}
                    </span>
                    <span className="flex-1">{line.label}</span>
                    <span className="font-medium tabular-nums">
                      {formatMoney(planned(line), currency, i18n.language)}
                    </span>
                  </p>
                  <p className="text-xs text-slate-600">
                    {formatNumber(line.quantity, i18n.language)} {line.unit} ×{" "}
                    {formatNumber(line.unit_cost, i18n.language)} ×{" "}
                    {formatNumber(line.frequency, i18n.language)}
                    {line.is_estimate && (
                      <span className="ml-2 rounded bg-amber-100 px-1 text-amber-800">
                        {t("proposal.estimate")}
                      </span>
                    )}
                  </p>
                  <Source item={line} documents={documents} />
                </div>
              </li>
            );
          })}
        </ul>
      </section>

      {canPlan && (
        <div className="flex flex-wrap items-center gap-2 border-t border-slate-100 pt-4">
          <Button
            onClick={() => apply.mutate()}
            disabled={apply.isPending || reject.isPending || selected.size === 0}
          >
            {t("proposal.apply", { count: selected.size })}
          </Button>
          <Button
            variant="danger"
            onClick={() => {
              if (window.confirm(t("proposal.confirmReject"))) reject.mutate();
            }}
            disabled={apply.isPending || reject.isPending}
          >
            {t("proposal.reject")}
          </Button>
          <p className="text-xs text-slate-500">{t("proposal.applyHint")}</p>
          <ErrorText error={apply.error ?? reject.error} />
        </div>
      )}
    </div>
  );
}
