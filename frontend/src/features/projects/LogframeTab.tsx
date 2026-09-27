import { useMutation, useQuery } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";
import { useTranslation } from "react-i18next";

import { Button, Card, ErrorText } from "@/components/ui";
import { useCurrentOrg } from "@/features/orgs/useCurrentOrg";
import { CHILD_LEVEL, type LogframeNode, type NodeLevel, projectsApi } from "@/lib/api";
import { permissions } from "@/lib/permissions";
import { checkQuery, indicatorsQuery, logframeQuery } from "@/lib/queries";

import { useInvalidateProject } from "./useInvalidateProject";

const levelStyles: Record<NodeLevel, string> = {
  goal: "bg-brand-700 text-white",
  outcome: "bg-brand-100 text-brand-800",
  output: "bg-sky-100 text-sky-800",
  activity: "bg-amber-100 text-amber-800",
  sub_activity: "bg-slate-100 text-slate-700",
};

interface Props {
  orgId: string;
  projectId: string;
}

function AddNodeForm({
  orgId,
  projectId,
  level,
  parentId,
  onDone,
}: Props & { level: NodeLevel; parentId: string | null; onDone: () => void }) {
  const { t } = useTranslation();
  const invalidate = useInvalidateProject(orgId, projectId);
  const [code, setCode] = useState("");
  const [title, setTitle] = useState("");
  const add = useMutation({
    mutationFn: () =>
      projectsApi.addNode(orgId, projectId, { level, code, title, parent_id: parentId }),
    onSuccess: async () => {
      await invalidate();
      onDone();
    },
  });
  const submit = (event: FormEvent) => {
    event.preventDefault();
    add.mutate();
  };
  return (
    <form onSubmit={submit} className="mt-2 flex flex-wrap items-center gap-2">
      <input
        aria-label={t("logframe.code")}
        placeholder={t("logframe.code")}
        className="w-24 rounded-md border border-slate-300 px-2 py-1.5 text-sm"
        value={code}
        onChange={(e) => setCode(e.target.value)}
      />
      <input
        aria-label={t("logframe.title")}
        placeholder={t(`levels.${level}`)}
        required
        autoFocus
        className="min-w-48 flex-1 rounded-md border border-slate-300 px-2 py-1.5 text-sm"
        value={title}
        onChange={(e) => setTitle(e.target.value)}
      />
      <Button type="submit" disabled={add.isPending}>
        {t("logframe.add")}
      </Button>
      <Button type="button" variant="ghost" onClick={onDone}>
        {t("common.cancel")}
      </Button>
      <ErrorText error={add.error} />
    </form>
  );
}

function NodeItem({
  node,
  indicatorCounts,
  canPlan,
  ...props
}: Props & { node: LogframeNode; indicatorCounts: Map<string, number>; canPlan: boolean }) {
  const { t } = useTranslation();
  const invalidate = useInvalidateProject(props.orgId, props.projectId);
  const [adding, setAdding] = useState(false);
  const childLevel = CHILD_LEVEL[node.level];
  const count = indicatorCounts.get(node.id) ?? 0;
  const remove = useMutation({
    mutationFn: () => projectsApi.deleteNode(props.orgId, props.projectId, node.id),
    onSuccess: invalidate,
  });

  return (
    <li className="py-1.5">
      <div className="group flex flex-wrap items-start gap-2">
        <span
          className={`mt-0.5 shrink-0 rounded px-1.5 py-0.5 text-[11px] font-semibold uppercase tracking-wide ${levelStyles[node.level]}`}
        >
          {t(`levels.${node.level}`)}
        </span>
        {node.code && <span className="mt-0.5 font-mono text-xs text-slate-500">{node.code}</span>}
        <span className="min-w-0 flex-1 text-sm">{node.title}</span>
        {count > 0 && (
          <span className="text-xs text-slate-500">{t("logframe.indicatorsCount", { count })}</span>
        )}
        {canPlan && (
          <span className="flex gap-1 opacity-70 group-hover:opacity-100">
            {childLevel && (
              <button
                className="rounded px-1.5 text-xs text-brand-700 hover:bg-brand-50"
                onClick={() => setAdding(true)}
              >
                + {t(`levels.${childLevel}`)}
              </button>
            )}
            <button
              className="rounded px-1.5 text-xs text-red-700 hover:bg-red-50"
              onClick={() => {
                if (window.confirm(t("logframe.confirmDelete"))) remove.mutate();
              }}
            >
              {t("logframe.delete")}
            </button>
          </span>
        )}
      </div>
      {adding && childLevel && (
        <AddNodeForm
          {...props}
          level={childLevel}
          parentId={node.id}
          onDone={() => setAdding(false)}
        />
      )}
      {node.children.length > 0 && (
        <ul className="ml-4 border-l border-slate-200 pl-4">
          {node.children.map((child) => (
            <NodeItem
              key={child.id}
              node={child}
              indicatorCounts={indicatorCounts}
              canPlan={canPlan}
              {...props}
            />
          ))}
        </ul>
      )}
    </li>
  );
}

function Checks({ orgId, projectId }: Props) {
  const { t } = useTranslation();
  const check = useQuery(checkQuery(orgId, projectId));
  if (!check.data) return null;
  const { nodes_without_indicator, indicators_without_source, activities_without_budget } =
    check.data;
  const groups = [
    {
      label: t("logframe.noIndicator"),
      items: nodes_without_indicator.map((n) => `${n.code} ${n.title}`),
    },
    {
      label: t("logframe.noSource"),
      items: indicators_without_source.map((i) => `${i.code} ${i.name}`),
    },
    {
      label: t("logframe.noBudget"),
      items: activities_without_budget.map((n) => `${n.code} ${n.title}`),
    },
  ].filter((g) => g.items.length);

  return (
    <Card title={t("logframe.checks")}>
      {groups.length === 0 ? (
        <p className="text-sm text-brand-800">✓ {t("logframe.allGood")}</p>
      ) : (
        <div className="space-y-3 text-sm">
          {groups.map((group) => (
            <div key={group.label}>
              <p className="font-medium text-amber-800">⚠ {group.label}</p>
              <ul className="ml-5 list-disc text-slate-600">
                {group.items.map((item) => (
                  <li key={item}>{item.trim()}</li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}

export function LogframeTab({ orgId, projectId }: Props) {
  const { t } = useTranslation();
  const { role } = useCurrentOrg();
  const canPlan = permissions.plan(role);
  const logframe = useQuery(logframeQuery(orgId, projectId));
  const indicators = useQuery(indicatorsQuery(orgId, projectId));
  const [addingGoal, setAddingGoal] = useState(false);

  const indicatorCounts = new Map<string, number>();
  for (const indicator of indicators.data ?? []) {
    indicatorCounts.set(indicator.node_id, (indicatorCounts.get(indicator.node_id) ?? 0) + 1);
  }

  return (
    <>
      <Card>
        {logframe.isPending ? (
          <p className="text-sm text-slate-500">{t("common.loading")}</p>
        ) : logframe.data?.length ? (
          <ul>
            {logframe.data.map((node) => (
              <NodeItem
                key={node.id}
                node={node}
                orgId={orgId}
                projectId={projectId}
                indicatorCounts={indicatorCounts}
                canPlan={canPlan}
              />
            ))}
          </ul>
        ) : (
          <p className="text-sm text-slate-500">{t("logframe.empty")}</p>
        )}
        {canPlan &&
          (addingGoal ? (
            <AddNodeForm
              orgId={orgId}
              projectId={projectId}
              level="goal"
              parentId={null}
              onDone={() => setAddingGoal(false)}
            />
          ) : (
            <Button variant="ghost" className="mt-3" onClick={() => setAddingGoal(true)}>
              + {t("logframe.addGoal")}
            </Button>
          ))}
      </Card>
      <Checks orgId={orgId} projectId={projectId} />
    </>
  );
}
