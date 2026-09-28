import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { Card, ErrorText } from "@/components/ui";
import type { AiUsageRow } from "@/lib/api";
import { formatNumber } from "@/lib/format";
import { aiUsageQuery } from "@/lib/queries";

/** Dépenses IA de l'organisation : mois en cours, plafond, répartition et derniers appels. */
export function AiUsagePanel({ orgId }: { orgId: string }) {
  const { t, i18n } = useTranslation();
  const lang = i18n.language;
  const usage = useQuery(aiUsageQuery(orgId));
  const usd = (value: string | number) =>
    new Intl.NumberFormat(lang, { style: "currency", currency: "USD" }).format(Number(value));
  const purpose = (key: string) => t(`aiUsage.purposes.${key}`, { defaultValue: key });
  const u = usage.data;
  if (!u) return <ErrorText error={usage.error} />;

  const cap = u.monthly_budget_usd === null ? null : Number(u.monthly_budget_usd);
  const share = cap ? Math.min(1, Number(u.month_cost_usd) / cap) : null;
  const maxMonth = Math.max(...u.by_month.map((m) => Number(m.cost_usd)), 0);
  const months = new Intl.DateTimeFormat(lang, { month: "short", year: "2-digit" });
  const dates = new Intl.DateTimeFormat(lang, { dateStyle: "short", timeStyle: "short" });

  const table = (rows: AiUsageRow[], label: (row: AiUsageRow) => string) => (
    <table className="w-full text-sm">
      <tbody className="divide-y divide-slate-100">
        {rows.map((row) => (
          <tr key={row.key || "none"}>
            <td className="py-1.5 pr-2">{label(row)}</td>
            <td className="py-1.5 text-right text-slate-500 tabular-nums">
              {t("aiUsage.calls", { count: row.calls })}
              {row.errors > 0 && (
                <span className="ml-1 text-red-700">
                  · {t("aiUsage.errors", { count: row.errors })}
                </span>
              )}
            </td>
            <td className="w-24 py-1.5 text-right font-medium tabular-nums">{usd(row.cost_usd)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );

  return (
    <Card title={t("aiUsage.title")}>
      <p className="mb-4 text-sm text-slate-600">{t("aiUsage.intro")}</p>
      <div className="grid gap-4 sm:grid-cols-3">
        <div>
          <p className="text-xs text-slate-500">{t("aiUsage.thisMonth")}</p>
          <p className="text-2xl font-semibold text-brand-800 tabular-nums">
            {usd(u.month_cost_usd)}
          </p>
          <p className="text-xs text-slate-500">
            {t("aiUsage.calls", { count: u.calls_this_month })}
          </p>
        </div>
        <div>
          <p className="text-xs text-slate-500">{t("aiUsage.budget")}</p>
          {cap === null ? (
            <p className="text-sm text-slate-600">{t("aiUsage.noBudget")}</p>
          ) : (
            <>
              <p className="text-2xl font-semibold tabular-nums">{usd(cap)}</p>
              <div className="mt-1 h-2 w-full overflow-hidden rounded-full bg-slate-100">
                <div
                  className={`h-full rounded-full ${(share ?? 0) >= 0.9 ? "bg-red-500" : "bg-brand-600"}`}
                  style={{ width: `${(share ?? 0) * 100}%` }}
                />
              </div>
              <p className="mt-1 text-xs text-slate-500">
                {t("aiUsage.used", { rate: Math.round((share ?? 0) * 100) })}
              </p>
            </>
          )}
        </div>
        <div>
          <p className="mb-1 text-xs text-slate-500">{t("aiUsage.months")}</p>
          <div className="flex h-16 items-end gap-1.5" aria-label={t("aiUsage.months")}>
            {u.by_month.map((m) => (
              <div key={m.key} className="flex flex-1 flex-col items-center gap-0.5">
                <div
                  className="w-full rounded-t bg-brand-600"
                  title={`${m.key} · ${usd(m.cost_usd)}`}
                  style={{
                    height: `${maxMonth ? Math.max(4, (Number(m.cost_usd) / maxMonth) * 48) : 4}px`,
                  }}
                />
                <span className="text-[10px] text-slate-500">
                  {months.format(new Date(`${m.key}-01T12:00:00`))}
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {u.by_purpose.length > 0 && (
        <div className="mt-5 grid gap-6 md:grid-cols-2">
          <div>
            <h3 className="mb-1 text-sm font-semibold">{t("aiUsage.byPurpose")}</h3>
            {table(u.by_purpose, (row) => purpose(row.key))}
          </div>
          <div>
            <h3 className="mb-1 text-sm font-semibold">{t("aiUsage.byProject")}</h3>
            {table(u.by_project, (row) => row.label || t("aiUsage.noProject"))}
          </div>
        </div>
      )}

      {u.recent.length > 0 && (
        <details className="mt-5">
          <summary className="cursor-pointer text-sm font-semibold">{t("aiUsage.recent")}</summary>
          <div className="-mx-5 mt-2 overflow-x-auto px-5">
            <table className="w-full min-w-[40rem] text-xs">
              <thead>
                <tr className="text-left text-slate-500">
                  <th className="py-1 font-medium">{t("aiUsage.when")}</th>
                  <th className="py-1 font-medium">{t("aiUsage.purpose")}</th>
                  <th className="py-1 font-medium">{t("aiUsage.model")}</th>
                  <th className="py-1 text-right font-medium">{t("aiUsage.tokens")}</th>
                  <th className="py-1 text-right font-medium">{t("aiUsage.duration")}</th>
                  <th className="py-1 text-right font-medium">{t("aiUsage.cost")}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {u.recent.map((call) => (
                  <tr key={call.id} className={call.status === "ok" ? "" : "text-red-700"}>
                    <td className="py-1 pr-2 whitespace-nowrap">
                      {dates.format(new Date(call.created_at))}
                    </td>
                    <td className="py-1 pr-2">
                      {call.project_code && (
                        <span className="mr-1 font-mono text-slate-500">{call.project_code}</span>
                      )}
                      {purpose(call.purpose)}
                      {call.error && <span className="block">{call.error}</span>}
                    </td>
                    <td className="py-1 pr-2 font-mono">{call.model}</td>
                    <td className="py-1 text-right tabular-nums">
                      {formatNumber(call.input_tokens, lang)} /{" "}
                      {formatNumber(call.output_tokens, lang)}
                    </td>
                    <td className="py-1 text-right tabular-nums">
                      {formatNumber(Math.round(call.duration_ms / 100) / 10, lang)} s
                    </td>
                    <td className="py-1 text-right tabular-nums">{usd(call.cost_usd)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      )}
    </Card>
  );
}
