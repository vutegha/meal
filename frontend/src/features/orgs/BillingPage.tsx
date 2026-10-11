import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";
import { useTranslation } from "react-i18next";

import { Badge, Button, Card, ErrorText, Select } from "@/components/ui";
import {
  billingApi,
  type Cycle,
  formatPrice,
  type Payment,
  type Subscription,
} from "@/lib/billing";
import { permissions } from "@/lib/permissions";
import { catalogQuery, paymentsQuery, subscriptionQuery } from "@/lib/queries";

import { CycleToggle, PlanCard } from "../site/plans";
import { AiUsagePanel } from "./AiUsagePanel";
import { useCurrentOrg } from "./useCurrentOrg";

const STATUS_TONE = {
  trialing: "info",
  active: "success",
  canceled: "warning",
  expired: "danger",
} as const;

function Meter({ label, used, limit }: { label: string; used: number; limit: number | null }) {
  const share = limit ? Math.min(1, used / limit) : 0;
  return (
    <div>
      <div className="flex justify-between text-sm">
        <span className="text-slate-600">{label}</span>
        <span className="font-medium text-slate-900">
          {used}
          {limit !== null && ` / ${limit}`}
        </span>
      </div>
      {limit !== null && (
        <div className="mt-1 h-2 rounded-full bg-slate-100">
          <div
            className={`h-2 rounded-full ${limit !== null && used > limit ? "bg-amber-500" : "bg-brand-600"}`}
            style={{ width: `${share * 100}%` }}
          />
        </div>
      )}
    </div>
  );
}

function CurrentPlan({ sub, currency }: { sub: Subscription; currency: string }) {
  const { t, i18n } = useTranslation();
  const date = (value: string | null) =>
    value
      ? new Intl.DateTimeFormat(i18n.language, { dateStyle: "long" }).format(new Date(value))
      : "";
  const period = {
    trialing: t("billing.trialEnds", { date: date(sub.trial_ends_at) }),
    active:
      sub.cycle === "usage" ? "" : t("billing.renews", { date: date(sub.current_period_end) }),
    canceled: t("billing.endsOn", {
      date: date(sub.current_period_end ?? sub.trial_ends_at),
    }),
    expired: t("billing.expiredOn"),
  }[sub.status];

  return (
    <Card>
      <p className="text-sm text-slate-500">{t("billing.current")}</p>
      <div className="mt-1 flex flex-wrap items-center gap-2">
        <h1 className="text-xl font-semibold">{t(`billing.plans.${sub.plan}`)}</h1>
        <Badge tone={STATUS_TONE[sub.status]}>{t(`billing.status.${sub.status}`)}</Badge>
        <Badge tone={sub.account_type === "individual" ? "info" : "brand"}>
          {t(`billing.accountType.${sub.account_type}`)}
        </Badge>
      </div>
      <p className="mt-1 text-sm text-slate-600">
        {t("billing.cycle")} : {t(`site.pricing.cycles.${sub.cycle}`)}
        {period && ` · ${period}`}
      </p>
      <div className="mt-5 grid gap-4 sm:grid-cols-3">
        <Meter
          label={t("billing.usageProjects")}
          used={sub.usage.projects}
          limit={sub.limits.projects}
        />
        <Meter
          label={t("billing.usageMembers")}
          used={sub.usage.members}
          limit={sub.limits.members}
        />
        <div>
          <div className="flex justify-between text-sm">
            <span className="text-slate-600">{t("billing.usageAi")}</span>
            <span className="font-medium text-slate-900">
              {formatPrice(sub.usage.ai_month_cost_usd, currency, i18n.language)} /{" "}
              {formatPrice(sub.limits.ai_monthly_budget_usd, currency, i18n.language)}
            </span>
          </div>
        </div>
      </div>
      {sub.cycle === "usage" && (
        <p className="mt-4 text-sm">
          <span className="text-slate-600">{t("billing.credits")} : </span>
          <span className="text-lg font-semibold text-slate-900">{sub.credits}</span>
        </p>
      )}
    </Card>
  );
}

function Payments({ orgId }: { orgId: string }) {
  const { t, i18n } = useTranslation();
  const { data, error } = useQuery(paymentsQuery(orgId));
  const date = new Intl.DateTimeFormat(i18n.language, { dateStyle: "medium" });
  return (
    <Card title={t("billing.payments")}>
      <ErrorText error={error} />
      {data?.length === 0 && <p className="text-sm text-slate-500">{t("billing.noPayments")}</p>}
      {!!data?.length && (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-200 text-left text-slate-500">
                <th className="py-2 pr-3 font-medium">{t("billing.date")}</th>
                <th className="py-2 pr-3 font-medium">{t("billing.description")}</th>
                <th className="py-2 pr-3 text-right font-medium">{t("billing.amount")}</th>
                <th className="py-2 font-medium">{t("billing.reference")}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {data.map((p: Payment) => (
                <tr key={p.id}>
                  <td className="py-2 pr-3 whitespace-nowrap">
                    {date.format(new Date(p.created_at))}
                  </td>
                  <td className="py-2 pr-3">
                    {t(`billing.plans.${p.plan}`)} · {t(`site.pricing.cycles.${p.cycle}`)}
                    {p.credits > 0 && ` · ${t("billing.creditsCount", { count: p.credits })}`}
                  </td>
                  <td className="py-2 pr-3 text-right whitespace-nowrap">
                    {formatPrice(p.amount, p.currency, i18n.language)}
                  </td>
                  <td className="py-2 font-mono text-xs text-slate-500">{p.reference}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}

export function BillingPage() {
  const { t, i18n } = useTranslation();
  const queryClient = useQueryClient();
  const { orgId, role } = useCurrentOrg();
  const isAdmin = permissions.manageOrg(role);
  const { data: catalog } = useQuery(catalogQuery);
  const { data: sub, error } = useQuery(subscriptionQuery(orgId));
  const [cycle, setCycle] = useState<Cycle | null>(null);
  const [plan, setPlan] = useState<string | null>(null);
  const [pack, setPack] = useState<number | null>(null);
  const [message, setMessage] = useState("");

  const refresh = async () => {
    await queryClient.invalidateQueries({ queryKey: ["orgs", orgId, "billing"] });
    await queryClient.invalidateQueries({ queryKey: ["me"] });
  };
  const checkout = useMutation({
    mutationFn: (body: { plan: string; cycle: Cycle; pack?: number }) =>
      billingApi.checkout(orgId, body),
    onSuccess: async (out) => {
      setMessage(
        t("billing.paid", {
          reference: out.payment.reference,
          plan: t(`billing.plans.${out.subscription.plan}`),
        }),
      );
      await refresh();
    },
  });
  const cancel = useMutation({ mutationFn: () => billingApi.cancel(orgId), onSuccess: refresh });

  if (!sub || !catalog) return error ? <ErrorText error={error} /> : <p>{t("common.loading")}</p>;

  const chosenCycle = cycle ?? sub.cycle;
  const chosenPlan = catalog.plans.find((p) => p.id === (plan ?? sub.plan)) ?? catalog.plans[0];
  const chosenPack = pack ?? catalog.credit_packs[0];
  const amount =
    chosenCycle === "usage"
      ? Number(chosenPlan.prices.credit) * chosenPack
      : chosenPlan.prices[chosenCycle];
  const canCancel = sub.cycle !== "usage" && (sub.status === "active" || sub.status === "trialing");

  const pay = (event: FormEvent) => {
    event.preventDefault();
    setMessage("");
    checkout.mutate({
      plan: chosenPlan.id,
      cycle: chosenCycle,
      ...(chosenCycle === "usage" ? { pack: chosenPack } : {}),
    });
  };

  return (
    <>
      <CurrentPlan sub={sub} currency={catalog.currency} />
      {message && (
        <p role="status" className="rounded-md bg-emerald-50 p-3 text-sm text-emerald-800">
          {message}
        </p>
      )}

      {isAdmin ? (
        <Card>
          <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
            <h2 className="text-base font-semibold">{t("billing.change")}</h2>
            <CycleToggle value={chosenCycle} onChange={setCycle} />
          </div>
          <form onSubmit={pay}>
            <div className="grid gap-4 lg:grid-cols-3">
              {catalog.plans.map((p, index) => (
                <PlanCard
                  key={p.id}
                  plan={p}
                  previous={index > 0 ? catalog.plans[index - 1] : undefined}
                  cycle={chosenCycle}
                  catalog={catalog}
                  selected={p.id === chosenPlan.id}
                  inApp
                  action={
                    <Button
                      type="button"
                      variant={p.id === chosenPlan.id ? "primary" : "ghost"}
                      className="w-full border border-slate-200"
                      aria-pressed={p.id === chosenPlan.id}
                      onClick={() => setPlan(p.id)}
                    >
                      {t("site.pricing.choose", { plan: t(`billing.plans.${p.id}`) })}
                    </Button>
                  }
                />
              ))}
            </div>
            <div className="mt-6 flex flex-wrap items-end gap-4 rounded-lg bg-slate-50 p-4">
              {chosenCycle === "usage" && (
                <div className="w-56">
                  <Select
                    label={t("billing.pack")}
                    value={chosenPack}
                    onChange={(e) => setPack(Number(e.target.value))}
                  >
                    {catalog.credit_packs.map((count) => (
                      <option key={count} value={count}>
                        {t("billing.packOption", {
                          count,
                          price: formatPrice(
                            Number(chosenPlan.prices.credit) * count,
                            catalog.currency,
                            i18n.language,
                          ),
                        })}
                      </option>
                    ))}
                  </Select>
                </div>
              )}
              <Button type="submit" disabled={checkout.isPending}>
                {t("billing.pay", {
                  amount: formatPrice(amount, catalog.currency, i18n.language),
                })}
              </Button>
              <p className="flex-1 text-xs text-slate-500">{t("billing.simulated")}</p>
            </div>
            <div className="mt-3">
              <ErrorText error={checkout.error} />
            </div>
          </form>
          {canCancel && !sub.cancel_at_period_end && (
            <div className="mt-4 border-t border-slate-100 pt-4">
              <Button
                variant="danger"
                disabled={cancel.isPending}
                onClick={() => window.confirm(t("billing.confirmCancel")) && cancel.mutate()}
              >
                {t("billing.cancel")}
              </Button>
              <ErrorText error={cancel.error} />
            </div>
          )}
        </Card>
      ) : (
        <Card>
          <p className="text-sm text-slate-600">{t("billing.adminOnly")}</p>
        </Card>
      )}

      {isAdmin && <Payments orgId={orgId} />}
      {isAdmin && <AiUsagePanel orgId={orgId} />}
    </>
  );
}
