import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { Card } from "@/components/ui";
import type { Participants, Project } from "@/lib/api";
import { flattenTree, formatMoney, formatNumber, formatRate } from "@/lib/format";
import {
  budgetSummaryQuery,
  executionsQuery,
  indicatorsQuery,
  logframeQuery,
  reportsQuery,
  torsQuery,
} from "@/lib/queries";

import { TorBadge } from "./TorTab";

function Bar({ rate, tone = "brand" }: { rate: number | null; tone?: "brand" | "red" }) {
  const width = Math.min(100, Math.max(0, (rate ?? 0) * 100));
  return (
    <div className="h-2 w-full overflow-hidden rounded-full bg-slate-100">
      <div
        className={`h-full rounded-full ${tone === "red" ? "bg-red-500" : "bg-brand-600"}`}
        style={{ width: `${width}%` }}
      />
    </div>
  );
}

function Kpi({ label, value, children }: { label: string; value: string; children?: ReactNode }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
      <p className="text-xs font-medium tracking-wide text-slate-500 uppercase">{label}</p>
      <p className="mt-1 text-2xl font-semibold text-brand-800 tabular-nums">{value}</p>
      <div className="mt-2 space-y-1 text-xs text-slate-600">{children}</div>
    </div>
  );
}

const PEOPLE: (keyof Omit<Participants, "with_disability">)[] = ["women", "men", "girls", "boys"];
const PEOPLE_COLORS = ["bg-brand-700", "bg-sky-500", "bg-amber-500", "bg-violet-400"];

/** Vue d'ensemble : budget, réalisations, personnes atteintes, indicateurs et suivi par activité. */
export function DashboardTab({ orgId, project }: { orgId: string; project: Project }) {
  const { t, i18n } = useTranslation();
  const lang = i18n.language;
  const logframe = useQuery(logframeQuery(orgId, project.id));
  const budget = useQuery(budgetSummaryQuery(orgId, project.id));
  const indicators = useQuery(indicatorsQuery(orgId, project.id));
  const executions = useQuery(executionsQuery(orgId, project.id));
  const tors = useQuery(torsQuery(orgId, project.id));
  const reports = useQuery(reportsQuery(orgId, project.id));

  if ([logframe, budget, indicators, executions, tors, reports].some((q) => q.isPending))
    return <p className="text-sm text-slate-500">{t("common.loading")}</p>;

  const activities = flattenTree(logframe.data ?? []).filter(
    (n) => n.level === "activity" || n.level === "sub_activity",
  );
  const runs = executions.data ?? [];
  const done = new Set(runs.filter((e) => e.status === "completed").map((e) => e.activity_id));
  const people = runs.reduce(
    (sum, e) => {
      for (const key of [...PEOPLE, "with_disability"] as const) sum[key] += e.participants[key];
      return sum;
    },
    { women: 0, men: 0, girls: 0, boys: 0, with_disability: 0 } as Participants,
  );
  const reached = PEOPLE.reduce((sum, key) => sum + people[key], 0);
  const measured = (indicators.data ?? []).filter((i) => i.achievement_rate !== null);
  const onTrack = measured.filter((i) => (i.achievement_rate ?? 0) >= 0.5).length;
  const torByActivity = new Map((tors.data ?? []).map((tor) => [tor.activity_id, tor]));
  const executionActivity = new Map(runs.map((e) => [e.id, e.activity_id]));
  const reportsByActivity = new Map<string, number>();
  for (const report of reports.data ?? []) {
    const activity = executionActivity.get(report.execution_id);
    if (activity && report.status === "approved")
      reportsByActivity.set(activity, (reportsByActivity.get(activity) ?? 0) + 1);
  }
  const budgetByActivity = new Map(
    (budget.data?.by_activity ?? []).map((row) => [row.activity_id, row]),
  );
  const money = (value: string | number) => formatMoney(value, project.currency, lang);

  if (!activities.length && !(indicators.data ?? []).length)
    return (
      <Card>
        <p className="text-sm text-slate-600">{t("dashboard.empty")}</p>
      </Card>
    );

  return (
    <>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Kpi label={t("dashboard.budget")} value={formatRate(budget.data?.execution_rate, lang)}>
          <Bar rate={budget.data?.execution_rate ?? 0} />
          <p>
            {t("dashboard.budgetOf", {
              spent: money(budget.data?.spent ?? 0),
              planned: money(budget.data?.planned ?? 0),
            })}
          </p>
          {!!budget.data?.over_budget_lines && (
            <p className="text-red-700">
              {t("dashboard.overLines", { count: budget.data.over_budget_lines })}
            </p>
          )}
        </Kpi>
        <Kpi label={t("dashboard.activities")} value={String(done.size)}>
          <Bar rate={activities.length ? done.size / activities.length : 0} />
          <p>{t("dashboard.activitiesOf", { total: activities.length })}</p>
        </Kpi>
        <Kpi label={t("dashboard.participants")} value={formatNumber(reached, lang)}>
          {reached > 0 && (
            <div className="flex h-2 w-full overflow-hidden rounded-full bg-slate-100">
              {PEOPLE.map((key, index) => (
                <div
                  key={key}
                  className={PEOPLE_COLORS[index]}
                  style={{ width: `${(people[key] / reached) * 100}%` }}
                />
              ))}
            </div>
          )}
          <p>{t("dashboard.disability", { count: people.with_disability })}</p>
        </Kpi>
        <Kpi
          label={t("dashboard.indicators")}
          value={`${onTrack} / ${(indicators.data ?? []).length}`}
        >
          <Bar rate={indicators.data?.length ? onTrack / indicators.data.length : 0} />
          <p>{t("dashboard.indicatorsOnTrack", { count: onTrack })}</p>
        </Kpi>
      </div>

      {reached > 0 && (
        <Card title={t("dashboard.disaggregation")}>
          <ul className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-5">
            {PEOPLE.map((key, index) => (
              <li key={key} className="flex items-center gap-2">
                <span className={`size-3 rounded-sm ${PEOPLE_COLORS[index]}`} />
                <span className="text-slate-600">{t(`execution.people.${key}`)}</span>
                <span className="ml-auto font-semibold tabular-nums">
                  {formatNumber(people[key], lang)}
                </span>
              </li>
            ))}
            <li className="flex items-center gap-2">
              <span className="text-slate-600">♿ {t("execution.people.with_disability")}</span>
              <span className="ml-auto font-semibold tabular-nums">
                {formatNumber(people.with_disability, lang)}
              </span>
            </li>
          </ul>
        </Card>
      )}

      <Card title={t("dashboard.byIndicator")}>
        {indicators.data?.length ? (
          <ul className="space-y-3">
            {indicators.data.map((indicator) => (
              <li key={indicator.id} className="grid gap-1 sm:grid-cols-[1fr_12rem] sm:gap-4">
                <p className="text-sm">
                  <span className="mr-2 font-mono text-xs text-slate-500">{indicator.code}</span>
                  {indicator.name}
                </p>
                <div>
                  <p className="text-xs text-slate-600 tabular-nums">
                    {formatNumber(indicator.achieved ?? 0, lang)}
                    {indicator.target !== null
                      ? ` / ${formatNumber(indicator.target, lang)} ${indicator.unit}`
                      : ` ${indicator.unit} · ${t("dashboard.noTarget")}`}
                    {indicator.achievement_rate !== null &&
                      ` · ${formatRate(indicator.achievement_rate, lang)}`}
                  </p>
                  <Bar rate={indicator.achievement_rate} />
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-slate-500">{t("dashboard.noIndicator")}</p>
        )}
      </Card>

      <Card title={t("dashboard.byActivity")}>
        {activities.length ? (
          <div className="-mx-5 overflow-x-auto px-5">
            <table className="w-full min-w-[36rem] text-sm">
              <thead>
                <tr className="text-left text-xs text-slate-500">
                  <th className="py-2 font-medium">{t("dashboard.colActivity")}</th>
                  <th className="py-2 font-medium">{t("dashboard.colTor")}</th>
                  <th className="py-2 text-right font-medium">{t("dashboard.colExecutions")}</th>
                  <th className="py-2 text-right font-medium">{t("dashboard.colReports")}</th>
                  <th className="w-40 py-2 pl-4 font-medium">{t("dashboard.colBudget")}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {activities.map((activity) => {
                  const tor = torByActivity.get(activity.id);
                  const count = runs.filter((e) => e.activity_id === activity.id).length;
                  const line = budgetByActivity.get(activity.id);
                  return (
                    <tr key={activity.id}>
                      <td className="py-2 pr-3">
                        <span className="mr-2 font-mono text-xs text-slate-500">
                          {activity.code}
                        </span>
                        {activity.title}
                      </td>
                      <td className="py-2 pr-3">
                        {tor ? (
                          <Link to="." search={{ tab: "tor", tor: tor.id }}>
                            <TorBadge status={tor.status} />
                          </Link>
                        ) : (
                          <span className="text-xs text-slate-400">–</span>
                        )}
                      </td>
                      <td className="py-2 text-right tabular-nums">
                        {count ? (
                          <Link
                            to="."
                            search={{ tab: "execution" }}
                            className="text-brand-700 hover:underline"
                          >
                            {count}
                          </Link>
                        ) : (
                          <span className="text-slate-400">0</span>
                        )}
                      </td>
                      <td className="py-2 text-right tabular-nums">
                        {reportsByActivity.get(activity.id) ?? 0}
                      </td>
                      <td className="py-2 pl-4">
                        {line ? (
                          <>
                            <Bar
                              rate={line.execution_rate}
                              tone={(line.execution_rate ?? 0) > 1 ? "red" : "brand"}
                            />
                            <p className="mt-0.5 text-xs text-slate-500 tabular-nums">
                              {formatRate(line.execution_rate, lang)} · {money(line.planned)}
                            </p>
                          </>
                        ) : (
                          <span className="text-xs text-slate-400">–</span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="text-sm text-slate-500">{t("dashboard.noActivity")}</p>
        )}
      </Card>
    </>
  );
}
