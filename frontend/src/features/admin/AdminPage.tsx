import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "@tanstack/react-router";
import { type FormEvent, useState } from "react";
import { useTranslation } from "react-i18next";

import { Badge, Button, Card, ErrorText, Field, Select } from "@/components/ui";
import {
  type AdminFilters,
  type AdminRow,
  type AdminUpdate,
  adminApi,
  CYCLES,
  type Cycle,
  formatPrice,
} from "@/lib/billing";
import { adminSubscriptionsQuery, catalogQuery, meQuery } from "@/lib/queries";
import { tokenStore } from "@/lib/tokens";

const STATUSES = ["trialing", "active", "canceled", "expired"] as const;
const STATUS_TONE = {
  trialing: "info",
  active: "success",
  canceled: "warning",
  expired: "danger",
} as const;

/** Administration de la plateforme : formule, échéance et crédits de chaque espace. */
export function AdminPage() {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { data: me } = useQuery(meQuery);
  const { data: catalog } = useQuery(catalogQuery);
  const [filters, setFilters] = useState<AdminFilters>({});
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<string | null>(null);
  const list = useQuery({ ...adminSubscriptionsQuery(filters), placeholderData: keepPreviousData });
  const data = list.data;
  const row = data?.items.find((r) => r.organization_id === selected);
  const currency = data?.summary.currency ?? "USD";
  const money = (value: string) => formatPrice(value, currency, i18n.language);
  const date = (value: string | null | undefined) =>
    value ? new Date(value).toLocaleDateString(i18n.language) : "—";
  const home = me?.organizations[0];

  const setFilter = (key: keyof AdminFilters, value: string) =>
    setFilters((f) => ({ ...f, [key]: value || undefined }));
  const submitSearch = (event: FormEvent) => {
    event.preventDefault();
    setFilter("q", search.trim());
  };
  const logout = async () => {
    tokenStore.set(null);
    queryClient.clear();
    await navigate({ to: "/login" });
  };

  const tiles = data
    ? [
        [t("admin.summary.organizations"), String(data.summary.organizations)],
        ...STATUSES.map((s) => [t(`billing.status.${s}`), String(data.summary.by_status[s] ?? 0)]),
        [t("admin.summary.recurring"), money(data.summary.monthly_recurring)],
        [t("admin.summary.revenue"), money(data.summary.revenue_last_30_days)],
      ]
    : [];

  return (
    <div className="min-h-screen">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-3 px-4 py-3">
          <span className="text-lg font-bold text-brand-700">{t("app.name")}</span>
          <Badge tone="brand">{t("admin.badge")}</Badge>
          {home && (
            <Link
              to="/orgs/$orgId"
              params={{ orgId: home.id }}
              className="ml-auto rounded-md px-2 py-1.5 text-sm text-slate-700 hover:bg-slate-100"
            >
              {t("admin.backToApp")}
            </Link>
          )}
          <Button variant="ghost" className={home ? "" : "ml-auto"} onClick={logout}>
            {t("common.logout")}
          </Button>
        </div>
      </header>

      <main className="mx-auto max-w-7xl space-y-6 px-4 py-6">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">{t("admin.title")}</h1>
          <p className="mt-1 text-sm text-slate-600">{t("admin.subtitle")}</p>
        </div>

        <ul className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-7">
          {tiles.map(([label, value]) => (
            <li key={label} className="rounded-xl border border-slate-200 bg-white p-3">
              <p className="text-xs text-slate-500">{label}</p>
              <p className="mt-1 text-xl font-semibold text-slate-900">{value}</p>
            </li>
          ))}
        </ul>

        <div className="flex flex-wrap items-end gap-3">
          <form onSubmit={submitSearch} className="flex items-end gap-2">
            <Field
              label={t("admin.search")}
              placeholder={t("admin.searchPlaceholder")}
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
            <Button type="submit" variant="ghost">
              {t("admin.searchAction")}
            </Button>
          </form>
          <Select
            label={t("admin.status")}
            value={filters.status ?? ""}
            onChange={(e) => setFilter("status", e.target.value)}
          >
            <option value="">{t("admin.all")}</option>
            {STATUSES.map((s) => (
              <option key={s} value={s}>
                {t(`billing.status.${s}`)}
              </option>
            ))}
          </Select>
          <Select
            label={t("admin.plan")}
            value={filters.plan ?? ""}
            onChange={(e) => setFilter("plan", e.target.value)}
          >
            <option value="">{t("admin.all")}</option>
            {catalog?.plans.map((p) => (
              <option key={p.id} value={p.id}>
                {t(`billing.plans.${p.id}`)}
              </option>
            ))}
          </Select>
        </div>

        <ErrorText error={list.error} />
        <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white">
          <table className="w-full min-w-[60rem] text-sm">
            <thead>
              <tr className="border-b border-slate-200 text-left text-slate-500">
                <th className="p-3 font-medium">{t("admin.columns.organization")}</th>
                <th className="p-3 font-medium">{t("admin.columns.plan")}</th>
                <th className="p-3 font-medium">{t("admin.columns.status")}</th>
                <th className="p-3 font-medium">{t("admin.columns.ends")}</th>
                <th className="p-3 font-medium">{t("admin.columns.usage")}</th>
                <th className="p-3 text-right font-medium">{t("admin.columns.paid")}</th>
                <th className="p-3" />
              </tr>
            </thead>
            <tbody>
              {data?.items.map((r) => (
                <tr
                  key={r.organization_id}
                  className={`border-b border-slate-100 last:border-0 ${
                    r.organization_id === selected ? "bg-brand-50/60" : ""
                  }`}
                >
                  <td className="p-3">
                    <p className="font-medium text-slate-900">{r.organization_name}</p>
                    <p className="text-xs text-slate-500">
                      {r.contact_email ?? "—"} ·{" "}
                      {t("admin.since", { date: date(r.organization_created_at) })}
                    </p>
                  </td>
                  <td className="p-3">
                    <p className="font-medium text-slate-900">{t(`billing.plans.${r.plan}`)}</p>
                    <p className="text-xs text-slate-500">
                      {t(`site.pricing.cycles.${r.cycle}`)} ·{" "}
                      {t(`billing.accountType.${r.account_type}`)}
                    </p>
                  </td>
                  <td className="p-3">
                    <Badge tone={STATUS_TONE[r.status]}>{t(`billing.status.${r.status}`)}</Badge>
                  </td>
                  <td className="p-3 text-slate-700">
                    {r.cycle === "usage" && r.status !== "trialing"
                      ? t("billing.creditsCount", { count: r.credits })
                      : date(r.status === "trialing" ? r.trial_ends_at : r.current_period_end)}
                  </td>
                  <td className="p-3 text-xs text-slate-600">
                    {t("admin.usageLine", {
                      projects: r.projects,
                      members: r.members,
                      credits: r.credits_used_this_month,
                    })}
                  </td>
                  <td className="p-3 text-right text-slate-900">{money(r.total_paid)}</td>
                  <td className="p-3 text-right">
                    <Button
                      variant="ghost"
                      aria-label={t("admin.manageOf", { name: r.organization_name })}
                      onClick={() => setSelected(r.organization_id)}
                    >
                      {t("admin.manage")}
                    </Button>
                  </td>
                </tr>
              ))}
              {data && data.items.length === 0 && (
                <tr>
                  <td colSpan={7} className="p-6 text-center text-slate-500">
                    {t("admin.empty")}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        {row && (
          <EditSubscription
            key={row.organization_id}
            row={row}
            plans={catalog?.plans.map((p) => p.id) ?? []}
            onClose={() => setSelected(null)}
          />
        )}
      </main>
    </div>
  );
}

const toDateInput = (value: string | null | undefined) => (value ? value.slice(0, 10) : "");
const fromDateInput = (value: string) =>
  value ? new Date(`${value}T23:59:59Z`).toISOString() : null;

function EditSubscription({
  row,
  plans,
  onClose,
}: {
  row: AdminRow;
  plans: string[];
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [plan, setPlan] = useState(row.plan);
  const [cycle, setCycle] = useState<Cycle>(row.cycle);
  const [status, setStatus] = useState<"trialing" | "active">(
    row.status === "trialing" ? "trialing" : "active",
  );
  const field = status === "trialing" ? "trial_ends_at" : "current_period_end";
  const [ends, setEnds] = useState(toDateInput(row[field]));
  const [credits, setCredits] = useState("");
  const [cancel, setCancel] = useState(row.cancel_at_period_end);
  const [note, setNote] = useState("");
  const [saved, setSaved] = useState(false);

  const save = useMutation({
    mutationFn: (body: AdminUpdate) => adminApi.update(row.organization_id, body),
    onSuccess: async (updated) => {
      setSaved(true);
      setCredits("");
      setEnds(toDateInput(updated[field]));
      await queryClient.invalidateQueries({ queryKey: ["admin", "subscriptions"] });
    },
  });

  const changes = (): AdminUpdate => {
    const body: AdminUpdate = { note };
    if (plan !== row.plan) body.plan = plan;
    if (cycle !== row.cycle) body.cycle = cycle;
    // Toujours envoyé : un espace expiré peut l'être en essai comme en période payée.
    body.status = status;
    if (cycle !== "usage" && ends !== toDateInput(row[field])) body[field] = fromDateInput(ends);
    if (credits && Number(credits)) body.add_credits = Number(credits);
    if (cancel !== row.cancel_at_period_end) body.cancel_at_period_end = cancel;
    return body;
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    setSaved(false);
    save.mutate(changes());
  };
  const extend = (days: number) => {
    setSaved(false);
    save.mutate({ extend_days: days, note });
  };

  return (
    <Card title={t("admin.edit.title", { name: row.organization_name })}>
      <form onSubmit={submit} className="space-y-4">
        <p className="text-sm text-slate-600">
          {row.contact_name ? `${row.contact_name} · ` : ""}
          {row.contact_email ?? t("admin.edit.noContact")}
        </p>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Select label={t("admin.plan")} value={plan} onChange={(e) => setPlan(e.target.value)}>
            {plans.map((id) => (
              <option key={id} value={id}>
                {t(`billing.plans.${id}`)}
              </option>
            ))}
          </Select>
          <Select
            label={t("billing.cycle")}
            value={cycle}
            onChange={(e) => setCycle(e.target.value as Cycle)}
          >
            {CYCLES.map((c) => (
              <option key={c} value={c}>
                {t(`site.pricing.cycles.${c}`)}
              </option>
            ))}
          </Select>
          <Select
            label={t("admin.status")}
            value={status}
            onChange={(e) => setStatus(e.target.value as "trialing" | "active")}
          >
            <option value="trialing">{t("billing.status.trialing")}</option>
            <option value="active">{t("billing.status.active")}</option>
          </Select>
          {cycle === "usage" ? (
            <Field
              label={t("admin.edit.addCredits", { count: row.credits })}
              type="number"
              step={1}
              value={credits}
              onChange={(e) => setCredits(e.target.value)}
            />
          ) : (
            <Field
              label={t(status === "trialing" ? "admin.edit.trialEnds" : "admin.edit.periodEnds")}
              type="date"
              value={ends}
              onChange={(e) => setEnds(e.target.value)}
            />
          )}
        </div>
        {cycle !== "usage" && (
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <span className="text-slate-600">{t("admin.edit.extend")}</span>
            {[30, 365].map((days) => (
              <Button
                key={days}
                type="button"
                variant="ghost"
                disabled={save.isPending}
                onClick={() => extend(days)}
              >
                {t("admin.edit.days", { count: days })}
              </Button>
            ))}
            <label className="ml-auto flex items-center gap-2 text-slate-700">
              <input
                type="checkbox"
                checked={cancel}
                onChange={(e) => setCancel(e.target.checked)}
              />
              {t("admin.edit.cancel")}
            </label>
          </div>
        )}
        <Field
          label={t("admin.edit.note")}
          hint={t("admin.edit.noteHint")}
          maxLength={500}
          value={note}
          onChange={(e) => setNote(e.target.value)}
        />
        <ErrorText error={save.error} />
        {saved && !save.error && (
          <p role="status" className="text-sm text-emerald-700">
            {t("admin.edit.saved")}
          </p>
        )}
        <div className="flex gap-2">
          <Button type="submit" disabled={save.isPending}>
            {t("common.save")}
          </Button>
          <Button type="button" variant="ghost" onClick={onClose}>
            {t("admin.close")}
          </Button>
        </div>
      </form>
    </Card>
  );
}
