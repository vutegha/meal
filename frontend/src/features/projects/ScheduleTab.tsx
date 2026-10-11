import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { type KeyboardEvent, type PointerEvent, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { Button, Card, ErrorText } from "@/components/ui";
import { useCurrentOrg } from "@/features/orgs/useCurrentOrg";
import { type Execution, type LogframeNode, type Project, projectsApi, torApi } from "@/lib/api";
import { flattenTree, formatNumber, formatRate } from "@/lib/format";
import { permissions } from "@/lib/permissions";
import { executionsQuery, indicatorsQuery, logframeQuery, torsQuery } from "@/lib/queries";
import {
  type ActivityState,
  activityState,
  type DragMode,
  dragPeriod,
  monthEndIso,
  monthIndex,
  monthStartIso,
  relatedIndicators,
  timelineRange,
  todayIndex,
} from "@/lib/schedule";

import { TorBadge } from "./TorTab";
import { useJob } from "./useJob";

/** Largeur d'un mois dans le diagramme, en pixels. */
const COL = 44;

type Period = [number, number];

interface Drag {
  id: string;
  mode: DragMode;
  x: number;
  origin: Period;
  period: Period;
  moved: boolean;
}

const barStyles: Record<ActivityState, string> = {
  unscheduled: "bg-slate-300 text-slate-700",
  planned: "bg-sky-600 text-white",
  in_progress: "bg-amber-500 text-white",
  executed: "bg-emerald-600 text-white",
};

const dotStyles: Record<ActivityState, string> = {
  unscheduled: "bg-slate-300",
  planned: "bg-sky-600",
  in_progress: "bg-amber-500",
  executed: "bg-emerald-600",
};

function StateBadge({ state }: { state: ActivityState }) {
  const { t } = useTranslation();
  return (
    <span className="inline-flex items-center gap-1.5 text-xs font-medium text-slate-700">
      <span className={`h-2.5 w-2.5 rounded-full ${dotStyles[state]}`} />
      {t(`schedule.state.${state}`)}
    </span>
  );
}

function useMonthFormat() {
  const { i18n } = useTranslation();
  return useMemo(() => {
    const short = new Intl.DateTimeFormat(i18n.language, { month: "short" });
    const long = new Intl.DateTimeFormat(i18n.language, { month: "short", year: "numeric" });
    const date = (index: number) => new Date(Math.floor(index / 12), index % 12, 1);
    return {
      month: (index: number) => short.format(date(index)).replace(".", ""),
      period: ([start, end]: Period) =>
        start === end
          ? long.format(date(start))
          : `${long.format(date(start))} – ${long.format(date(end))}`,
    };
  }, [i18n.language]);
}

const periodOf = (node: LogframeNode): Period | null =>
  node.planned_start && node.planned_end
    ? [monthIndex(node.planned_start), monthIndex(node.planned_end)]
    : null;

export function ScheduleTab({ orgId, project }: { orgId: string; project: Project }) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const { role } = useCurrentOrg();
  const canPlan = permissions.plan(role);
  const logframe = useQuery(logframeQuery(orgId, project.id));
  const executions = useQuery(executionsQuery(orgId, project.id));
  const formatMonth = useMonthFormat();

  const [selected, setSelected] = useState<string | null>(null);
  const [drag, setDrag] = useState<Drag | null>(null);
  // Périodes enregistrées mais pas encore relues depuis l'API : la barre ne revient pas en arrière.
  const [pending, setPending] = useState<Record<string, Period | null>>({});

  const nodes = useMemo(() => flattenTree(logframe.data ?? []), [logframe.data]);
  const byId = useMemo(() => new Map(nodes.map((n) => [n.id, n])), [nodes]);
  const rows = nodes.filter(
    (n) => n.level === "output" || n.level === "activity" || n.level === "sub_activity",
  );
  const activities = rows.filter((n) => n.level !== "output");
  const bounds = timelineRange(project, activities);
  const months = Array.from({ length: bounds.last - bounds.first + 1 }, (_, i) => bounds.first + i);

  const save = useMutation({
    mutationFn: ({ id, period }: { id: string; period: Period | null }) =>
      projectsApi.updateNode(
        orgId,
        project.id,
        id,
        period
          ? { planned_start: monthStartIso(period[0]), planned_end: monthEndIso(period[1]) }
          : { planned_start: null, planned_end: null },
      ),
    onMutate: ({ id, period }) => setPending((p) => ({ ...p, [id]: period })),
    onSettled: async (_data, _error, { id }) => {
      await queryClient.invalidateQueries({ queryKey: logframeQuery(orgId, project.id).queryKey });
      setPending((p) => {
        const next = { ...p };
        delete next[id];
        return next;
      });
    },
  });

  const periodFor = (node: LogframeNode): Period | null => {
    if (drag?.id === node.id) return drag.period;
    if (node.id in pending) return pending[node.id];
    return periodOf(node);
  };
  const stateFor = (node: LogframeNode) =>
    activityState(
      { id: node.id, planned_start: periodFor(node) ? "x" : null },
      executions.data ?? [],
    );

  const onPointerDown = (event: PointerEvent<HTMLDivElement>, node: LogframeNode) => {
    if (event.button !== 0) return;
    const handle = (event.target as HTMLElement).closest<HTMLElement>("[data-drag]");
    const current = periodFor(node);
    if (!canPlan) {
      if (handle) setSelected(node.id);
      return;
    }
    let mode: DragMode;
    let origin: Period;
    if (handle && current) {
      mode = handle.dataset.drag as DragMode;
      origin = current;
    } else {
      const left = event.currentTarget.getBoundingClientRect().left;
      const month = bounds.first + Math.floor((event.clientX - left) / COL);
      mode = "create";
      origin = [month, month];
    }
    event.preventDefault();
    event.currentTarget.setPointerCapture(event.pointerId);
    setDrag({
      id: node.id,
      mode,
      x: event.clientX,
      origin,
      period: origin,
      moved: mode === "create",
    });
  };

  const onPointerMove = (event: PointerEvent<HTMLDivElement>) => {
    if (!drag) return;
    const delta = Math.round((event.clientX - drag.x) / COL);
    const period = dragPeriod(drag.mode, drag.origin[0], drag.origin[1], delta, bounds);
    if (period[0] !== drag.period[0] || period[1] !== drag.period[1] || (delta && !drag.moved))
      setDrag({ ...drag, period, moved: drag.moved || delta !== 0 });
  };

  const onPointerUp = () => {
    if (!drag) return;
    const node = byId.get(drag.id);
    setDrag(null);
    if (!drag.moved) {
      setSelected(drag.id);
      return;
    }
    const before = node ? periodOf(node) : null;
    if (before && before[0] === drag.period[0] && before[1] === drag.period[1]) return;
    save.mutate({ id: drag.id, period: drag.period });
  };

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>, node: LogframeNode) => {
    const current = periodFor(node);
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      setSelected(node.id);
      return;
    }
    if (!canPlan || !current || (event.key !== "ArrowLeft" && event.key !== "ArrowRight")) return;
    event.preventDefault();
    const delta = event.key === "ArrowLeft" ? -1 : 1;
    const period = dragPeriod(
      event.shiftKey ? "end" : "move",
      current[0],
      current[1],
      delta,
      bounds,
    );
    if (period[0] !== current[0] || period[1] !== current[1]) save.mutate({ id: node.id, period });
  };

  if (logframe.isPending) return <p className="text-sm text-slate-500">{t("common.loading")}</p>;

  const width = months.length * COL;
  const today = todayIndex();
  const now = new Date();
  const todayOffset =
    today >= bounds.first && today <= bounds.last
      ? (today - bounds.first + (now.getDate() - 1) / 31) * COL
      : null;
  const years = months.reduce<{ year: number; count: number }[]>((acc, month) => {
    const year = Math.floor(month / 12);
    if (acc.at(-1)?.year === year) acc.at(-1)!.count += 1;
    else acc.push({ year, count: 1 });
    return acc;
  }, []);
  const grid = {
    backgroundImage: "linear-gradient(to right, rgb(226 232 240) 1px, transparent 1px)",
    backgroundSize: `${COL}px 100%`,
  };
  const selectedNode = selected ? byId.get(selected) : undefined;

  return (
    <>
      <Card title={t("schedule.title")}>
        <p className="mb-3 text-sm text-slate-600">{t("schedule.intro")}</p>
        {!project.start_date && (
          <p className="mb-3 rounded-md bg-amber-50 px-3 py-2 text-sm text-amber-800">
            {t("schedule.noDates")}
          </p>
        )}
        <ErrorText error={logframe.error ?? save.error} />
        {activities.length === 0 ? (
          <p className="text-sm text-slate-500">{t("schedule.noActivity")}</p>
        ) : (
          <div className="overflow-x-auto rounded-lg border border-slate-200" data-testid="gantt">
            <div className="min-w-max text-sm select-none">
              <div className="flex border-b border-slate-200 bg-slate-50 text-xs text-slate-500">
                <div className="sticky left-0 z-20 flex w-40 shrink-0 items-end border-r border-slate-200 bg-slate-50 px-3 py-1.5 font-medium sm:w-72">
                  {t("schedule.activity")}
                </div>
                <div style={{ width }}>
                  <div className="flex border-b border-slate-200">
                    {years.map(({ year, count }) => (
                      <div
                        key={year}
                        style={{ width: count * COL }}
                        className="truncate border-r border-slate-200 px-2 py-1 font-semibold text-slate-700"
                      >
                        {year}
                      </div>
                    ))}
                  </div>
                  <div className="flex">
                    {months.map((month) => (
                      <div
                        key={month}
                        style={{ width: COL }}
                        className={`border-r border-slate-200 py-1 text-center capitalize ${
                          month === today ? "font-semibold text-brand-800" : ""
                        }`}
                      >
                        {formatMonth.month(month)}
                      </div>
                    ))}
                  </div>
                </div>
              </div>

              {rows.map((node) => {
                if (node.level === "output")
                  return (
                    <div key={node.id} className="flex border-b border-slate-200 bg-slate-50/70">
                      <div className="sticky left-0 z-10 w-40 shrink-0 truncate border-r border-slate-200 bg-slate-50 px-3 py-1.5 text-xs font-semibold text-slate-700 sm:w-72">
                        <span className="mr-1.5 font-mono text-slate-500">{node.code}</span>
                        {node.title}
                      </div>
                      <div style={{ width, ...grid }} />
                    </div>
                  );
                const period = periodFor(node);
                const state = stateFor(node);
                const sub = node.level === "sub_activity";
                const dragging = drag?.id === node.id;
                const own = (executions.data ?? []).filter((e) => e.activity_id === node.id);
                return (
                  <div
                    key={node.id}
                    className={`flex border-b border-slate-100 ${selected === node.id ? "bg-brand-50/60" : "bg-white"}`}
                  >
                    <button
                      type="button"
                      onClick={() => setSelected(node.id)}
                      className={`sticky left-0 z-10 flex w-40 shrink-0 items-center gap-2 border-r border-slate-200 bg-inherit px-3 py-2 text-left hover:bg-slate-50 sm:w-72 ${
                        sub ? "pl-7" : ""
                      }`}
                    >
                      <span className={`h-2 w-2 shrink-0 rounded-full ${dotStyles[state]}`} />
                      <span className="min-w-0 flex-1 truncate" title={node.title}>
                        <span className="mr-1.5 font-mono text-xs text-slate-500">{node.code}</span>{" "}
                        {node.title}
                      </span>
                    </button>
                    <div
                      className={`relative h-10 ${canPlan ? "cursor-crosshair" : ""}`}
                      style={{ width, ...grid, touchAction: "pan-y" }}
                      onPointerDown={(e) => onPointerDown(e, node)}
                      onPointerMove={onPointerMove}
                      onPointerUp={onPointerUp}
                      onPointerCancel={() => setDrag(null)}
                    >
                      {todayOffset !== null && (
                        <div
                          className="pointer-events-none absolute inset-y-0 w-px bg-red-400"
                          style={{ left: todayOffset }}
                        />
                      )}
                      {period ? (
                        <div
                          data-drag="move"
                          role="button"
                          tabIndex={0}
                          aria-label={t("schedule.barLabel", {
                            code: node.code,
                            title: node.title,
                            period: formatMonth.period(period),
                          })}
                          title={`${node.code} ${node.title} · ${formatMonth.period(period)}`}
                          onKeyDown={(e) => onKeyDown(e, node)}
                          className={`group absolute top-1/2 flex -translate-y-1/2 items-center overflow-hidden rounded-md px-2 text-xs font-medium shadow-sm ring-brand-800 focus:outline-none focus-visible:ring-2 ${
                            barStyles[state]
                          } ${sub ? "h-5 opacity-90" : "h-7"} ${
                            canPlan
                              ? dragging
                                ? "cursor-grabbing"
                                : "cursor-grab"
                              : "cursor-pointer"
                          } ${dragging ? "ring-2 ring-offset-1" : ""}`}
                          style={{
                            left: (period[0] - bounds.first) * COL + 2,
                            width: (period[1] - period[0] + 1) * COL - 4,
                          }}
                        >
                          {canPlan && (
                            <span
                              data-drag="start"
                              className="absolute inset-y-0 left-0 w-2 cursor-ew-resize rounded-l-md bg-black/10 opacity-0 group-hover:opacity-100"
                            />
                          )}
                          <span className="truncate">{node.code || node.title}</span>
                          {canPlan && (
                            <span
                              data-drag="end"
                              className="absolute inset-y-0 right-0 w-2 cursor-ew-resize rounded-r-md bg-black/10 opacity-0 group-hover:opacity-100"
                            />
                          )}
                        </div>
                      ) : (
                        canPlan && (
                          <span className="pointer-events-none absolute inset-y-0 left-2 flex items-center text-xs text-slate-400 italic">
                            {t("schedule.dragToPlan")}
                          </span>
                        )
                      )}
                      {own.map((execution) => {
                        const month = monthIndex(execution.start_date);
                        if (month < bounds.first || month > bounds.last) return null;
                        return (
                          <span
                            key={execution.id}
                            title={execution.title || execution.start_date}
                            className="pointer-events-none absolute bottom-0.5 h-1.5 w-1.5 rotate-45 bg-slate-800"
                            style={{ left: (month - bounds.first) * COL + COL / 2 - 3 }}
                          />
                        );
                      })}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}
        <div className="mt-3 flex flex-wrap items-center gap-4">
          {(["planned", "in_progress", "executed"] as const).map((state) => (
            <StateBadge key={state} state={state} />
          ))}
          <span className="inline-flex items-center gap-1.5 text-xs text-slate-600">
            <span className="h-3 w-px bg-red-400" />
            {t("schedule.today")}
          </span>
          {save.isPending && (
            <span role="status" className="text-xs text-slate-500">
              {t("schedule.saving")}
            </span>
          )}
        </div>
      </Card>

      {selectedNode && (
        <ActivityPanel
          key={selectedNode.id}
          orgId={orgId}
          project={project}
          activity={selectedNode}
          parent={selectedNode.parent_id ? byId.get(selectedNode.parent_id) : undefined}
          nodes={byId}
          period={periodFor(selectedNode)}
          state={stateFor(selectedNode)}
          executions={(executions.data ?? []).filter((e) => e.activity_id === selectedNode.id)}
          canPlan={canPlan}
          onUnplan={() => save.mutate({ id: selectedNode.id, period: null })}
          onClose={() => setSelected(null)}
        />
      )}
    </>
  );
}

// --- Fiche d'une activité : TdR si elle est planifiée, indicateurs si elle est exécutée -----

function ActivityPanel({
  orgId,
  project,
  activity,
  parent,
  nodes,
  period,
  state,
  executions,
  canPlan,
  onUnplan,
  onClose,
}: {
  orgId: string;
  project: Project;
  activity: LogframeNode;
  parent: LogframeNode | undefined;
  nodes: Map<string, LogframeNode>;
  period: Period | null;
  state: ActivityState;
  executions: Execution[];
  canPlan: boolean;
  onUnplan: () => void;
  onClose: () => void;
}) {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const formatMonth = useMonthFormat();
  const close = useRef<HTMLButtonElement>(null);
  const executed = state === "executed" || state === "in_progress";

  useEffect(() => {
    close.current?.focus();
    const onKey = (event: globalThis.KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-40 flex justify-end"
      role="dialog"
      aria-modal="true"
      aria-labelledby="activity-title"
    >
      <button
        type="button"
        aria-label={t("schedule.close")}
        className="absolute inset-0 bg-slate-900/20"
        onClick={onClose}
        tabIndex={-1}
      />
      <aside className="relative flex h-full w-full max-w-md flex-col overflow-y-auto bg-white shadow-xl">
        <div className="flex items-start gap-3 border-b border-slate-200 p-4">
          <div className="min-w-0 flex-1">
            <p className="font-mono text-xs text-slate-500">{activity.code}</p>
            <h2 id="activity-title" className="text-base font-semibold">
              {activity.title}
            </h2>
            {parent && (
              <p className="mt-0.5 text-xs text-slate-500">
                {parent.code} {parent.title}
              </p>
            )}
          </div>
          <button
            ref={close}
            type="button"
            onClick={onClose}
            aria-label={t("schedule.close")}
            className="rounded-md px-2 py-1 text-slate-500 hover:bg-slate-100 hover:text-slate-900"
          >
            ✕
          </button>
        </div>

        <div className="space-y-5 p-4">
          <div className="flex flex-wrap items-center gap-3">
            <StateBadge state={state} />
            <span className="text-sm text-slate-700">
              {period ? formatMonth.period(period) : t("schedule.noPeriod")}
            </span>
            {canPlan && period && !executed && (
              <button className="text-xs text-slate-500 underline" onClick={onUnplan}>
                {t("schedule.unplan")}
              </button>
            )}
          </div>

          {executed ? (
            <>
              <IndicatorsSection
                orgId={orgId}
                projectId={project.id}
                activity={activity}
                nodes={nodes}
              />
              <section>
                <h3 className="mb-2 text-sm font-semibold">{t("schedule.executionsTitle")}</h3>
                <ul className="divide-y divide-slate-100 text-sm">
                  {executions.map((execution) => (
                    <li
                      key={execution.id}
                      className="flex flex-wrap items-center gap-x-3 gap-y-1 py-2"
                    >
                      <span className="min-w-0 flex-1">
                        {execution.title || activity.title}
                        <span className="block text-xs text-slate-500">
                          {new Intl.DateTimeFormat(i18n.language, { dateStyle: "medium" }).format(
                            new Date(execution.start_date),
                          )}{" "}
                          · {t("schedule.participants", { count: execution.participants_total })}
                        </span>
                      </span>
                      <Button
                        variant="ghost"
                        onClick={() =>
                          navigate({
                            to: ".",
                            search: { tab: "execution", execution: execution.id },
                          })
                        }
                      >
                        {t("schedule.open")}
                      </Button>
                    </li>
                  ))}
                </ul>
              </section>
              <TorSection
                orgId={orgId}
                projectId={project.id}
                activity={activity}
                canPlan={false}
              />
            </>
          ) : (
            <>
              <TorSection
                orgId={orgId}
                projectId={project.id}
                activity={activity}
                canPlan={canPlan}
              />
              <Button
                variant="ghost"
                onClick={() => navigate({ to: ".", search: { tab: "execution" } })}
              >
                {t("schedule.recordExecution")}
              </Button>
            </>
          )}
        </div>
      </aside>
    </div>
  );
}

function TorSection({
  orgId,
  projectId,
  activity,
  canPlan,
}: {
  orgId: string;
  projectId: string;
  activity: LogframeNode;
  canPlan: boolean;
}) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const tors = useQuery(torsQuery(orgId, projectId));
  const [instructions, setInstructions] = useState("");
  const open = (torId: string) => navigate({ to: ".", search: { tab: "tor", tor: torId } });

  const job = useJob(orgId, async (result) => {
    await queryClient.invalidateQueries({ queryKey: torsQuery(orgId, projectId).queryKey });
    await open(String(result.result.tor_id));
  });
  const generate = useMutation({
    mutationFn: () => torApi.generate(orgId, projectId, activity.id, instructions),
    onSuccess: job.start,
  });
  const create = useMutation({
    mutationFn: () => torApi.create(orgId, projectId, activity.id),
    onSuccess: (tor) => open(tor.id),
  });
  const tor = tors.data?.find((item) => item.activity_id === activity.id);
  const busy = generate.isPending || job.running;

  if (!tor && !canPlan) return null;
  return (
    <section>
      <h3 className="mb-2 text-sm font-semibold">{t("schedule.torTitle")}</h3>
      {tors.isPending ? (
        <p className="text-sm text-slate-500">{t("common.loading")}</p>
      ) : tor ? (
        <div className="flex flex-wrap items-center gap-3">
          <TorBadge status={tor.status} />
          <span className="text-xs text-slate-500">v{tor.version}</span>
          <Button onClick={() => open(tor.id)}>{t("schedule.torOpen")}</Button>
        </div>
      ) : (
        <div className="space-y-2">
          <p className="text-sm text-slate-600">{t("schedule.torNone")}</p>
          <label className="block text-xs font-medium text-slate-700">
            {t("tor.instructions")}
            <textarea
              className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm font-normal"
              rows={2}
              placeholder={t("tor.instructionsPlaceholder")}
              value={instructions}
              onChange={(e) => setInstructions(e.target.value)}
            />
          </label>
          <div className="flex flex-wrap gap-2">
            <Button onClick={() => generate.mutate()} disabled={busy}>
              ✨ {t("schedule.torGenerate")}
            </Button>
            <Button
              variant="ghost"
              onClick={() => create.mutate()}
              disabled={busy || create.isPending}
            >
              {t("schedule.torBlank")}
            </Button>
          </div>
          {busy && (
            <p role="status" className="text-sm text-slate-600">
              {t("schedule.torRunning")}
            </p>
          )}
        </div>
      )}
      <ErrorText error={generate.error ?? job.error ?? create.error} />
    </section>
  );
}

function IndicatorsSection({
  orgId,
  projectId,
  activity,
  nodes,
}: {
  orgId: string;
  projectId: string;
  activity: LogframeNode;
  nodes: Map<string, LogframeNode>;
}) {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const indicators = useQuery(indicatorsQuery(orgId, projectId));
  const related = relatedIndicators(activity, nodes, indicators.data ?? []);
  return (
    <section>
      <h3 className="text-sm font-semibold">{t("schedule.indicatorsTitle")}</h3>
      <p className="mb-2 text-xs text-slate-500">{t("schedule.indicatorsHint")}</p>
      {indicators.isPending ? (
        <p className="text-sm text-slate-500">{t("common.loading")}</p>
      ) : related.length ? (
        <ul className="space-y-3">
          {related.map((indicator) => {
            const rate = indicator.achievement_rate;
            const node = nodes.get(indicator.node_id);
            return (
              <li key={indicator.id} className="text-sm">
                <p>
                  <span className="mr-1.5 font-mono text-xs text-slate-500">{indicator.code}</span>
                  {indicator.name}
                </p>
                <p className="text-xs text-slate-500">
                  {node && node.id !== activity.id ? `${node.code} · ` : ""}
                  {t("schedule.achieved", {
                    achieved: formatNumber(indicator.achieved, i18n.language),
                    target:
                      `${formatNumber(indicator.target, i18n.language)} ${indicator.unit}`.trim(),
                  })}
                  {rate !== null && ` · ${formatRate(rate, i18n.language)}`}
                </p>
                {rate !== null && (
                  <div className="mt-1 h-1.5 rounded-full bg-slate-100">
                    <div
                      className={`h-1.5 rounded-full ${rate >= 1 ? "bg-emerald-600" : "bg-brand-600"}`}
                      style={{ width: `${Math.min(100, Math.round(rate * 100))}%` }}
                    />
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      ) : (
        <p className="text-sm text-slate-500">{t("schedule.noIndicator")}</p>
      )}
      <Button
        variant="ghost"
        className="mt-2"
        onClick={() => navigate({ to: ".", search: { tab: "indicators" } })}
      >
        {t("schedule.seeIndicators")}
      </Button>
    </section>
  );
}
