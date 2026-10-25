import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useParams } from "@tanstack/react-router";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { Card, ErrorText, Select } from "@/components/ui";
import { Kpi } from "@/features/projects/DashboardTab";
import { BENEFICIARIES, type DashboardBreakdown, type DashboardFilters } from "@/lib/api";
import { formatMoney, formatNumber } from "@/lib/format";
import { orgDashboardQuery } from "@/lib/queries";

const PEOPLE_COLORS = ["bg-brand-700", "bg-sky-500", "bg-amber-500", "bg-violet-400"];

function BreakdownTable({
  title,
  rows,
  label,
}: {
  title: string;
  rows: DashboardBreakdown[];
  label?: (row: DashboardBreakdown) => string;
}) {
  const { t, i18n } = useTranslation();
  const max = Math.max(1, ...rows.map((r) => r.people));
  return (
    <Card title={title}>
      {rows.length ? (
        <table className="w-full text-left text-sm">
          <thead className="text-xs text-slate-500">
            <tr>
              <th className="py-1 pr-3 font-medium" />
              <th className="py-1 pr-3 text-right font-medium">{t("orgDashboard.executions")}</th>
              <th className="py-1 text-right font-medium">{t("orgDashboard.people")}</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {rows.map((row) => (
              <tr key={row.key}>
                <td className="py-1.5 pr-3">
                  {label ? label(row) : row.label}
                  <div className="mt-1 h-1.5 rounded-full bg-slate-100" aria-hidden>
                    <div
                      className="h-1.5 rounded-full bg-brand-600"
                      style={{ width: `${(row.people / max) * 100}%` }}
                    />
                  </div>
                </td>
                <td className="py-1.5 pr-3 text-right tabular-nums">{row.executions}</td>
                <td className="py-1.5 text-right tabular-nums">
                  {row.masked ? (
                    <span title={t("orgDashboard.maskedHint")}>{t("orgDashboard.masked")}</span>
                  ) : (
                    formatNumber(row.people, i18n.language)
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <p className="text-sm text-slate-500">{t("orgDashboard.noData")}</p>
      )}
    </Card>
  );
}

/** Tableau de bord de l'organisation : tous les projets, filtrés par période, lieu et public. */
export function OrgDashboardPage() {
  const { t, i18n } = useTranslation();
  const lang = i18n.language;
  const { orgId } = useParams({ from: "/orgs/$orgId" });
  const [filters, setFilters] = useState<DashboardFilters>({});
  const dashboard = useQuery({
    ...orgDashboardQuery(orgId, filters),
    placeholderData: keepPreviousData,
  });
  const data = dashboard.data;
  const set = (key: keyof DashboardFilters) => (e: { target: { value: string } }) =>
    setFilters((f) => ({ ...f, [key]: e.target.value || undefined }));
  const monthName = (month: number) =>
    new Intl.DateTimeFormat(lang, { month: "long" }).format(new Date(2000, month - 1, 1));
  const monthLabel = (key: string) => {
    const [year, month] = key.split("-").map(Number);
    return new Intl.DateTimeFormat(lang, { month: "short", year: "numeric" }).format(
      new Date(year, month - 1, 1),
    );
  };

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">{t("orgDashboard.title")}</h1>
      <Card>
        <div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-6">
          <Select label={t("orgDashboard.year")} value={filters.year ?? ""} onChange={set("year")}>
            <option value="">{t("orgDashboard.all")}</option>
            {data?.options.years.map((year) => (
              <option key={year} value={year}>
                {year}
              </option>
            ))}
          </Select>
          <Select
            label={t("orgDashboard.month")}
            value={filters.month ?? ""}
            onChange={set("month")}
          >
            <option value="">{t("orgDashboard.all")}</option>
            {Array.from({ length: 12 }, (_, i) => (
              <option key={i + 1} value={i + 1}>
                {monthName(i + 1)}
              </option>
            ))}
          </Select>
          <Select label={t("orgDashboard.zone")} value={filters.zone ?? ""} onChange={set("zone")}>
            <option value="">{t("orgDashboard.all")}</option>
            {data?.options.zones.map((zone) => (
              <option key={zone}>{zone}</option>
            ))}
          </Select>
          <Select
            label={t("orgDashboard.location")}
            value={filters.location ?? ""}
            onChange={set("location")}
          >
            <option value="">{t("orgDashboard.all")}</option>
            {data?.options.locations.map((location) => (
              <option key={location}>{location}</option>
            ))}
          </Select>
          <Select
            label={t("orgDashboard.project")}
            value={filters.project_id ?? ""}
            onChange={set("project_id")}
          >
            <option value="">{t("orgDashboard.all")}</option>
            {data?.options.projects.map((p) => (
              <option key={p.id} value={p.id}>
                {p.code} {p.title}
              </option>
            ))}
          </Select>
          <Select
            label={t("orgDashboard.beneficiary")}
            value={filters.beneficiary ?? ""}
            onChange={set("beneficiary")}
          >
            <option value="">{t("orgDashboard.all")}</option>
            {BENEFICIARIES.map((b) => (
              <option key={b} value={b}>
                {t(`execution.people.${b}`)}
              </option>
            ))}
          </Select>
        </div>
        <ErrorText error={dashboard.error} />
      </Card>

      {!data ? (
        <p className="text-sm text-slate-500">{t("common.loading")}</p>
      ) : (
        <>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Kpi label={t("orgDashboard.projects")} value={formatNumber(data.projects, lang)}>
              <p>{t("orgDashboard.activeProjects", { count: data.active_projects })}</p>
            </Kpi>
            <Kpi label={t("orgDashboard.executions")} value={formatNumber(data.executions, lang)}>
              <p>{t("orgDashboard.completed", { count: data.completed_executions })}</p>
            </Kpi>
            <Kpi
              label={t("orgDashboard.people")}
              value={
                data.people.masked.includes("total")
                  ? t("orgDashboard.masked")
                  : formatNumber(data.people.total, lang)
              }
            >
              {data.people.masked.includes("with_disability") ? (
                <p>{t("orgDashboard.disabilityMasked")}</p>
              ) : (
                <p>{t("dashboard.disability", { count: data.people.with_disability })}</p>
              )}
              {data.people.masked.length > 0 && <p>{t("orgDashboard.maskedHint")}</p>}
            </Kpi>
            <Kpi
              label={t("orgDashboard.spent")}
              value={
                data.spending.length
                  ? formatMoney(data.spending[0].amount, data.spending[0].currency, lang)
                  : "–"
              }
            >
              {data.spending.slice(1).map((s) => (
                <p key={s.currency}>{formatMoney(s.amount, s.currency, lang)}</p>
              ))}
              {(filters.location || filters.beneficiary) && <p>{t("orgDashboard.spentHint")}</p>}
            </Kpi>
          </div>

          {data.people.total > 0 && !filters.beneficiary && (
            <Card title={t("dashboard.disaggregation")}>
              <div className="flex h-3 overflow-hidden rounded-full bg-slate-100">
                {(["women", "men", "girls", "boys"] as const).map((key, i) => (
                  <div
                    key={key}
                    className={PEOPLE_COLORS[i]}
                    style={{ width: `${(data.people[key] / data.people.total) * 100}%` }}
                  />
                ))}
              </div>
              <ul className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-600">
                {(["women", "men", "girls", "boys"] as const).map((key, i) => (
                  <li key={key} className="flex items-center gap-1.5">
                    <span className={`h-2.5 w-2.5 rounded-full ${PEOPLE_COLORS[i]}`} />
                    {t(`execution.people.${key}`)}{" "}
                    {data.people.masked.includes(key)
                      ? t("orgDashboard.masked")
                      : formatNumber(data.people[key], lang)}
                  </li>
                ))}
              </ul>
            </Card>
          )}

          <BreakdownTable
            title={t("orgDashboard.byMonth")}
            rows={data.by_month}
            label={(row) => monthLabel(row.key)}
          />
          <div className="grid gap-4 lg:grid-cols-2">
            <BreakdownTable title={t("orgDashboard.byZone")} rows={data.by_zone} />
            <BreakdownTable title={t("orgDashboard.byLocation")} rows={data.by_location} />
          </div>
          <BreakdownTable title={t("orgDashboard.byProject")} rows={data.by_project} />
        </>
      )}
    </div>
  );
}
