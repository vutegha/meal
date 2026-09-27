import { useMutation, useQuery } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";
import { useTranslation } from "react-i18next";

import { Button, Card, ErrorText, Field, Select } from "@/components/ui";
import { useCurrentOrg } from "@/features/orgs/useCurrentOrg";
import { type BudgetLine, type Project, projectsApi } from "@/lib/api";
import { flattenTree, formatMoney, formatNumber, formatRate } from "@/lib/format";
import { permissions } from "@/lib/permissions";
import { budgetLinesQuery, budgetSummaryQuery, logframeQuery } from "@/lib/queries";

import { useInvalidateProject } from "./useInvalidateProject";

function RateBar({ rate }: { rate: number | null }) {
  const pct = Math.min(100, Math.round((rate ?? 0) * 100));
  const over = (rate ?? 0) > 1;
  return (
    <div className="h-1.5 w-full rounded-full bg-slate-100" aria-hidden>
      <div
        className={`h-1.5 rounded-full ${over ? "bg-red-600" : "bg-brand-600"}`}
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}

function Stat({ label, value, tone }: { label: string; value: string; tone?: "warn" }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4">
      <p className="text-xs text-slate-500">{label}</p>
      <p className={`mt-1 text-xl font-semibold ${tone === "warn" ? "text-red-700" : ""}`}>
        {value}
      </p>
    </div>
  );
}

function ExpenseForm({
  orgId,
  projectId,
  line,
  onDone,
}: {
  orgId: string;
  projectId: string;
  line: BudgetLine;
  onDone: () => void;
}) {
  const { t } = useTranslation();
  const invalidate = useInvalidateProject(orgId, projectId);
  const [form, setForm] = useState({
    amount: "",
    spent_on: new Date().toISOString().slice(0, 10),
    reference: "",
  });
  const add = useMutation({
    mutationFn: () => projectsApi.addExpense(orgId, projectId, line.id, form),
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
    <form onSubmit={submit} className="flex flex-wrap items-end gap-2 bg-slate-50 p-3">
      <Field
        label={t("budget.amount")}
        type="number"
        min="0.01"
        step="0.01"
        required
        value={form.amount}
        onChange={(e) => setForm({ ...form, amount: e.target.value })}
      />
      <Field
        label={t("budget.date")}
        type="date"
        required
        value={form.spent_on}
        onChange={(e) => setForm({ ...form, spent_on: e.target.value })}
      />
      <Field
        label={t("budget.reference")}
        value={form.reference}
        onChange={(e) => setForm({ ...form, reference: e.target.value })}
      />
      <Button type="submit" disabled={add.isPending}>
        {t("budget.record")}
      </Button>
      <Button type="button" variant="ghost" onClick={onDone}>
        {t("common.cancel")}
      </Button>
      <ErrorText error={add.error} />
    </form>
  );
}

const emptyLine = {
  label: "",
  activity_id: "",
  quantity: "1",
  unit: "",
  unit_cost: "",
  frequency: "1",
  donor_line_code: "",
};

export function BudgetTab({ orgId, project }: { orgId: string; project: Project }) {
  const { t, i18n } = useTranslation();
  const { role } = useCurrentOrg();
  const canEdit = permissions.editBudget(role);
  const projectId = project.id;
  const invalidate = useInvalidateProject(orgId, projectId);
  const summary = useQuery(budgetSummaryQuery(orgId, projectId));
  const lines = useQuery(budgetLinesQuery(orgId, projectId));
  const logframe = useQuery(logframeQuery(orgId, projectId));
  const [form, setForm] = useState(emptyLine);
  const [expenseLine, setExpenseLine] = useState<string | null>(null);

  const activities = flattenTree(logframe.data ?? []).filter(
    (n) => n.level === "activity" || n.level === "sub_activity",
  );
  const activityName = new Map(activities.map((a) => [a.id, `${a.code} ${a.title}`.trim()]));
  const money = (value: string) => formatMoney(value, project.currency, i18n.language);

  const addLine = useMutation({
    mutationFn: () =>
      projectsApi.addBudgetLine(orgId, projectId, {
        ...form,
        activity_id: form.activity_id || null,
      }),
    onSuccess: async () => {
      setForm(emptyLine);
      await invalidate();
    },
  });
  const removeLine = useMutation({
    mutationFn: (id: string) => projectsApi.deleteBudgetLine(orgId, projectId, id),
    onSuccess: invalidate,
  });

  const submit = (event: FormEvent) => {
    event.preventDefault();
    addLine.mutate();
  };
  const set = (key: keyof typeof emptyLine) => (e: { target: { value: string } }) =>
    setForm((f) => ({ ...f, [key]: e.target.value }));

  return (
    <>
      {summary.data && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <Stat label={t("budget.planned")} value={money(summary.data.planned)} />
          <Stat label={t("budget.spent")} value={money(summary.data.spent)} />
          <Stat
            label={t("budget.rate")}
            value={formatRate(summary.data.execution_rate, i18n.language)}
          />
          <Stat
            label={t("budget.overLines")}
            value={String(summary.data.over_budget_lines)}
            tone={summary.data.over_budget_lines ? "warn" : undefined}
          />
        </div>
      )}

      {summary.data && summary.data.by_activity.length > 0 && (
        <Card title={t("budget.byActivity")}>
          <ul className="space-y-3">
            {summary.data.by_activity.map((a) => (
              <li key={a.activity_id ?? "support"} className="space-y-1">
                <div className="flex flex-wrap justify-between gap-2 text-sm">
                  <span>
                    {a.code && (
                      <span className="mr-2 font-mono text-xs text-slate-500">{a.code}</span>
                    )}
                    {a.activity_id ? a.title : t("budget.support")}
                  </span>
                  <span className="text-slate-600">
                    {money(a.spent)} / {money(a.planned)} ·{" "}
                    {formatRate(a.execution_rate, i18n.language)}
                  </span>
                </div>
                <RateBar rate={a.execution_rate} />
              </li>
            ))}
          </ul>
        </Card>
      )}

      <Card title={t("budget.lines")}>
        {lines.data?.length ? (
          <div className="-mx-5 overflow-x-auto">
            <table className="w-full min-w-[900px] text-sm">
              <thead className="text-left text-xs text-slate-500">
                <tr>
                  <th className="px-5 py-2">{t("budget.donorCode")}</th>
                  <th className="px-3 py-2">{t("budget.label")}</th>
                  <th className="px-3 py-2">{t("budget.activity")}</th>
                  <th className="px-3 py-2 text-right whitespace-nowrap">{t("budget.quantity")}</th>
                  <th className="px-3 py-2 text-right whitespace-nowrap">{t("budget.unitCost")}</th>
                  <th className="px-3 py-2 text-right whitespace-nowrap">{t("budget.planned")}</th>
                  <th className="px-3 py-2 text-right whitespace-nowrap">{t("budget.spent")}</th>
                  <th className="px-5 py-2" />
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {lines.data.map((line) => (
                  <LineRow
                    key={line.id}
                    line={line}
                    activity={
                      line.activity_id
                        ? (activityName.get(line.activity_id) ?? "")
                        : t("budget.support")
                    }
                    money={money}
                    language={i18n.language}
                    canEdit={canEdit}
                    expenseOpen={expenseLine === line.id}
                    onExpense={() => setExpenseLine(line.id)}
                    onRemove={() => removeLine.mutate(line.id)}
                    expenseForm={
                      <ExpenseForm
                        orgId={orgId}
                        projectId={projectId}
                        line={line}
                        onDone={() => setExpenseLine(null)}
                      />
                    }
                  />
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="text-sm text-slate-500">{t("budget.empty")}</p>
        )}

        {canEdit && (
          <form onSubmit={submit} className="mt-5 space-y-3 border-t border-slate-100 pt-5">
            <h3 className="text-sm font-semibold">{t("budget.addLine")}</h3>
            <div className="grid gap-3 sm:grid-cols-[8rem_1fr_1fr]">
              <Field
                label={t("budget.donorCode")}
                value={form.donor_line_code}
                onChange={set("donor_line_code")}
              />
              <Field
                label={t("budget.label")}
                required
                value={form.label}
                onChange={set("label")}
              />
              <Select
                label={t("budget.activity")}
                value={form.activity_id}
                onChange={set("activity_id")}
              >
                <option value="">{t("budget.support")}</option>
                {activities.map((a) => (
                  <option key={a.id} value={a.id}>
                    {activityName.get(a.id)}
                  </option>
                ))}
              </Select>
            </div>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <Field
                label={t("budget.quantity")}
                type="number"
                min="0"
                step="any"
                required
                value={form.quantity}
                onChange={set("quantity")}
              />
              <Field label={t("budget.unit")} value={form.unit} onChange={set("unit")} />
              <Field
                label={`${t("budget.unitCost")} (${project.currency})`}
                type="number"
                min="0"
                step="0.01"
                required
                value={form.unit_cost}
                onChange={set("unit_cost")}
              />
              <Field
                label={t("budget.frequency")}
                type="number"
                min="0"
                step="any"
                required
                value={form.frequency}
                onChange={set("frequency")}
              />
            </div>
            <ErrorText error={addLine.error} />
            <Button type="submit" disabled={addLine.isPending}>
              {t("budget.addLine")}
            </Button>
          </form>
        )}
      </Card>
    </>
  );
}

function LineRow({
  line,
  activity,
  money,
  language,
  canEdit,
  expenseOpen,
  onExpense,
  onRemove,
  expenseForm,
}: {
  line: BudgetLine;
  activity: string;
  money: (value: string) => string;
  language: string;
  canEdit: boolean;
  expenseOpen: boolean;
  onExpense: () => void;
  onRemove: () => void;
  expenseForm: React.ReactNode;
}) {
  const { t } = useTranslation();
  const over = Number(line.spent) > Number(line.planned);
  return (
    <>
      <tr>
        <td className="px-5 py-2 font-mono text-xs text-slate-500">{line.donor_line_code}</td>
        <td className="px-3 py-2">{line.label}</td>
        <td className="px-3 py-2 text-slate-600">{activity}</td>
        <td className="px-3 py-2 text-right whitespace-nowrap">
          {formatNumber(line.quantity, language)} {line.unit}
          {Number(line.frequency) !== 1 && ` × ${formatNumber(line.frequency, language)}`}
        </td>
        <td className="px-3 py-2 text-right whitespace-nowrap">
          {formatNumber(line.unit_cost, language)}
        </td>
        <td className="px-3 py-2 text-right font-medium whitespace-nowrap">
          {money(line.planned)}
        </td>
        <td
          className={`px-3 py-2 text-right whitespace-nowrap ${over ? "font-medium text-red-700" : ""}`}
        >
          {money(line.spent)}
        </td>
        <td className="px-5 py-2 text-right whitespace-nowrap">
          {canEdit && (
            <>
              <Button variant="ghost" className="!px-2 !py-1 text-xs" onClick={onExpense}>
                + {t("budget.addExpense")}
              </Button>
              <Button variant="danger" className="!px-2 !py-1 text-xs" onClick={onRemove}>
                {t("common.remove")}
              </Button>
            </>
          )}
        </td>
      </tr>
      {expenseOpen && (
        <tr>
          <td colSpan={8}>{expenseForm}</td>
        </tr>
      )}
    </>
  );
}
