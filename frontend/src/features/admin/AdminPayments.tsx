import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";
import { useTranslation } from "react-i18next";

import { Badge, Button, Card, ErrorText, Field, Select } from "@/components/ui";
import { download } from "@/lib/api";
import {
  type AdminPayment,
  type AdminPaymentRecord,
  type AdminRow,
  adminApi,
  type Catalog,
  CYCLES,
  type Cycle,
  formatPrice,
  PAYMENT_STATUS_TONE,
} from "@/lib/billing";
import { adminPaymentsQuery } from "@/lib/queries";

const STATUSES = ["pending", "paid", "refunded", "canceled", "failed"] as const;
const OFFLINE_METHODS = ["mobile_money", "bank_transfer", "cash", "other"] as const;

const invalidate = (queryClient: ReturnType<typeof useQueryClient>) =>
  queryClient.invalidateQueries({ queryKey: ["admin"] });

/** Tous les paiements : confirmer un virement reçu, rembourser, télécharger un reçu. */
export function PaymentsView() {
  const { t, i18n } = useTranslation();
  const queryClient = useQueryClient();
  const [status, setStatus] = useState("");
  const [search, setSearch] = useState("");
  const [q, setQ] = useState("");
  const filters = { ...(status ? { status } : {}), ...(q ? { q } : {}) };
  const list = useQuery({ ...adminPaymentsQuery(filters), placeholderData: keepPreviousData });
  const data = list.data;
  const money = (value: string) =>
    formatPrice(value, data?.summary.currency ?? "USD", i18n.language);
  const date = (value: string | null | undefined) =>
    value ? new Date(value).toLocaleDateString(i18n.language) : "—";

  const confirm = useMutation({
    mutationFn: (p: AdminPayment) => {
      const note = window.prompt(t("admin.payments.confirmPrompt", { reference: p.reference }));
      if (note === null) return Promise.resolve(null);
      return adminApi.confirm(p.id, note);
    },
    onSuccess: () => invalidate(queryClient),
  });
  const refund = useMutation({
    mutationFn: (p: AdminPayment) => {
      const note = window.prompt(t("admin.payments.refundPrompt", { number: p.receipt_number }));
      if (!note?.trim()) return Promise.resolve(null);
      return adminApi.refund(p.id, note.trim());
    },
    onSuccess: () => invalidate(queryClient),
  });
  const receipt = useMutation({
    mutationFn: (p: AdminPayment) =>
      download(adminApi.receiptPath(p.id), `recu-${p.receipt_number}.pdf`),
  });

  const tiles = data
    ? [
        [t("admin.payments.pending"), String(data.summary.pending)],
        [t("admin.payments.pendingAmount"), money(data.summary.pending_amount)],
        [t("admin.summary.revenue"), money(data.summary.paid_last_30_days)],
        [t("admin.payments.refunded"), money(data.summary.refunded_last_30_days)],
      ]
    : [];

  return (
    <>
      <ul className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {tiles.map(([label, value]) => (
          <li key={label} className="rounded-xl border border-slate-200 bg-white p-3">
            <p className="text-xs text-slate-500">{label}</p>
            <p className="mt-1 text-xl font-semibold text-slate-900">{value}</p>
          </li>
        ))}
      </ul>

      <div className="flex flex-wrap items-end gap-3">
        <form
          className="flex items-end gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            setQ(search.trim());
          }}
        >
          <Field
            label={t("admin.search")}
            placeholder={t("admin.payments.searchPlaceholder")}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <Button type="submit" variant="ghost">
            {t("admin.searchAction")}
          </Button>
        </form>
        <Select
          label={t("admin.status")}
          value={status}
          onChange={(e) => setStatus(e.target.value)}
        >
          <option value="">{t("admin.all")}</option>
          {STATUSES.map((s) => (
            <option key={s} value={s}>
              {t(`billing.paymentStatus.${s}`)}
            </option>
          ))}
        </Select>
      </div>

      <ErrorText error={list.error ?? confirm.error ?? refund.error ?? receipt.error} />
      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white">
        <table className="w-full min-w-[60rem] text-sm">
          <thead>
            <tr className="border-b border-slate-200 text-left text-slate-500">
              <th className="p-3 font-medium">{t("billing.date")}</th>
              <th className="p-3 font-medium">{t("admin.columns.organization")}</th>
              <th className="p-3 font-medium">{t("billing.description")}</th>
              <th className="p-3 font-medium">{t("admin.status")}</th>
              <th className="p-3 text-right font-medium">{t("billing.amount")}</th>
              <th className="p-3 font-medium">{t("billing.reference")}</th>
              <th className="p-3" />
            </tr>
          </thead>
          <tbody>
            {data?.items.map((p) => (
              <tr key={p.id} className="border-b border-slate-100 align-top last:border-0">
                <td className="p-3 whitespace-nowrap">{date(p.paid_at ?? p.created_at)}</td>
                <td className="p-3">
                  <p className="font-medium text-slate-900">{p.organization_name}</p>
                  <p className="text-xs text-slate-500">{p.paid_by_email ?? "—"}</p>
                </td>
                <td className="p-3">
                  {t(`billing.plans.${p.plan}`)} · {t(`site.pricing.cycles.${p.cycle}`)}
                  {p.credits > 0 && ` · ${t("billing.creditsCount", { count: p.credits })}`}
                  <span className="block text-xs text-slate-500">
                    {t(`billing.methods.${p.method}`)}
                    {p.note && ` · ${p.note}`}
                  </span>
                </td>
                <td className="p-3">
                  <Badge tone={PAYMENT_STATUS_TONE[p.status]}>
                    {t(`billing.paymentStatus.${p.status}`)}
                  </Badge>
                </td>
                <td className="p-3 text-right whitespace-nowrap">
                  {formatPrice(p.amount, p.currency, i18n.language)}
                </td>
                <td className="p-3 font-mono text-xs text-slate-600">
                  {p.reference}
                  {p.receipt_number && <span className="block">{p.receipt_number}</span>}
                </td>
                <td className="p-3 text-right whitespace-nowrap">
                  {p.status === "pending" && (
                    <Button
                      disabled={confirm.isPending}
                      aria-label={t("admin.payments.confirmOf", { reference: p.reference })}
                      onClick={() => confirm.mutate(p)}
                    >
                      {t("admin.payments.confirm")}
                    </Button>
                  )}
                  {p.receipt_number && (
                    <Button
                      variant="ghost"
                      disabled={receipt.isPending}
                      onClick={() => receipt.mutate(p)}
                    >
                      {t("billing.receipt")}
                    </Button>
                  )}
                  {p.status === "paid" && (
                    <Button
                      variant="ghost"
                      disabled={refund.isPending}
                      onClick={() => refund.mutate(p)}
                    >
                      {t("admin.payments.refund")}
                    </Button>
                  )}
                </td>
              </tr>
            ))}
            {data && data.items.length === 0 && (
              <tr>
                <td colSpan={7} className="p-6 text-center text-slate-500">
                  {t("admin.payments.empty")}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </>
  );
}

/** Saisie d'un paiement reçu hors de l'application pour l'espace choisi. */
export function RecordPayment({ row, catalog }: { row: AdminRow; catalog: Catalog }) {
  const { t, i18n } = useTranslation();
  const queryClient = useQueryClient();
  const [plan, setPlan] = useState(row.plan);
  const [cycle, setCycle] = useState<Cycle>(row.cycle);
  const [pack, setPack] = useState(catalog.credit_packs[0]);
  const [method, setMethod] = useState<AdminPaymentRecord["method"]>("mobile_money");
  const [amount, setAmount] = useState("");
  const [reference, setReference] = useState("");
  const [note, setNote] = useState("");
  const [saved, setSaved] = useState<string | null>(null);
  const chosen = catalog.plans.find((p) => p.id === plan) ?? catalog.plans[0];
  const listPrice =
    cycle === "usage" ? Number(chosen.prices.credit) * pack : Number(chosen.prices[cycle]);

  const record = useMutation({
    mutationFn: () =>
      adminApi.record(row.organization_id, {
        plan,
        cycle,
        method,
        reference,
        note,
        ...(cycle === "usage" ? { pack } : {}),
        ...(amount ? { amount } : {}),
      }),
    onSuccess: async (payment) => {
      setSaved(payment.receipt_number);
      setAmount("");
      setReference("");
      setNote("");
      await invalidate(queryClient);
    },
  });
  const submit = (event: FormEvent) => {
    event.preventDefault();
    setSaved(null);
    record.mutate();
  };

  return (
    <Card title={t("admin.record.title", { name: row.organization_name })}>
      <form onSubmit={submit} className="space-y-4">
        <p className="text-sm text-slate-600">{t("admin.record.intro")}</p>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Select label={t("admin.plan")} value={plan} onChange={(e) => setPlan(e.target.value)}>
            {catalog.plans.map((p) => (
              <option key={p.id} value={p.id}>
                {t(`billing.plans.${p.id}`)}
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
          {cycle === "usage" && (
            <Select
              label={t("billing.pack")}
              value={pack}
              onChange={(e) => setPack(Number(e.target.value))}
            >
              {catalog.credit_packs.map((count) => (
                <option key={count} value={count}>
                  {t("billing.creditsCount", { count })}
                </option>
              ))}
            </Select>
          )}
          <Select
            label={t("billing.method")}
            value={method}
            onChange={(e) => setMethod(e.target.value as AdminPaymentRecord["method"])}
          >
            {OFFLINE_METHODS.map((m) => (
              <option key={m} value={m}>
                {t(`billing.methods.${m}`)}
              </option>
            ))}
          </Select>
          <Field
            label={t("admin.record.amount")}
            type="number"
            min={0}
            step="0.01"
            placeholder={formatPrice(listPrice, catalog.currency, i18n.language)}
            hint={t("admin.record.amountHint")}
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
          />
          <Field
            label={t("admin.record.reference")}
            maxLength={80}
            value={reference}
            onChange={(e) => setReference(e.target.value)}
          />
          <Field
            label={t("admin.edit.note")}
            maxLength={500}
            value={note}
            onChange={(e) => setNote(e.target.value)}
          />
        </div>
        <ErrorText error={record.error} />
        {saved && (
          <p role="status" className="text-sm text-emerald-700">
            {t("admin.record.saved", { number: saved })}
          </p>
        )}
        <Button type="submit" disabled={record.isPending}>
          {t("admin.record.submit")}
        </Button>
      </form>
    </Card>
  );
}
