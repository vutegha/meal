import { useMutation, useQuery } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";
import { useTranslation } from "react-i18next";

import { Button, Card, ErrorText, Field, Select } from "@/components/ui";
import { useCurrentOrg } from "@/features/orgs/useCurrentOrg";
import { type Indicator, type PeriodTarget, projectsApi } from "@/lib/api";
import { flattenTree, formatNumber, formatRate } from "@/lib/format";
import { filterIndicators, parseList } from "@/lib/indicators";
import { permissions } from "@/lib/permissions";
import { indicatorsQuery, logframeQuery } from "@/lib/queries";

import { useInvalidateProject } from "./useInvalidateProject";

interface Props {
  orgId: string;
  projectId: string;
}

function ValueForm({
  orgId,
  projectId,
  indicator,
  onDone,
}: Props & {
  indicator: Indicator;
  onDone: () => void;
}) {
  const { t } = useTranslation();
  const invalidate = useInvalidateProject(orgId, projectId);
  const [form, setForm] = useState({
    period_start: "",
    period_end: "",
    value: "",
    source: indicator.source_of_verification,
  });
  const add = useMutation({
    mutationFn: () => projectsApi.addValue(orgId, projectId, indicator.id, form),
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
        label={t("indicators.periodStart")}
        type="date"
        required
        value={form.period_start}
        onChange={(e) => setForm({ ...form, period_start: e.target.value })}
      />
      <Field
        label={t("indicators.periodEnd")}
        type="date"
        required
        value={form.period_end}
        onChange={(e) => setForm({ ...form, period_end: e.target.value })}
      />
      <Field
        label={`${t("indicators.value")}${indicator.unit ? ` (${indicator.unit})` : ""}`}
        type="number"
        step="any"
        required
        value={form.value}
        onChange={(e) => setForm({ ...form, value: e.target.value })}
      />
      <Button type="submit" disabled={add.isPending}>
        {t("indicators.record")}
      </Button>
      <Button type="button" variant="ghost" onClick={onDone}>
        {t("common.cancel")}
      </Button>
      <ErrorText error={add.error} />
    </form>
  );
}

function TargetsForm({
  orgId,
  projectId,
  indicator,
  onDone,
}: Props & {
  indicator: Indicator;
  onDone: () => void;
}) {
  const { t } = useTranslation();
  const invalidate = useInvalidateProject(orgId, projectId);
  const [rows, setRows] = useState<PeriodTarget[]>(() =>
    indicator.period_targets.map(({ period_start, period_end, target }) => ({
      period_start,
      period_end,
      target,
    })),
  );
  const save = useMutation({
    mutationFn: () =>
      projectsApi.updateIndicator(orgId, projectId, indicator.id, { period_targets: rows }),
    onSuccess: async () => {
      await invalidate();
      onDone();
    },
  });
  const update = (index: number, patch: Partial<PeriodTarget>) =>
    setRows(rows.map((row, i) => (i === index ? { ...row, ...patch } : row)));
  const submit = (event: FormEvent) => {
    event.preventDefault();
    save.mutate();
  };
  return (
    <form
      onSubmit={submit}
      className="space-y-2 bg-slate-50 p-3"
      aria-label={t("indicators.periodTargets")}
    >
      <p className="text-xs text-slate-600">
        {indicator.aggregation === "sum"
          ? t("indicators.periodTargetsSumHint")
          : t("indicators.periodTargetsLatestHint")}
      </p>
      {rows.map((row, index) => (
        <div key={index} className="flex flex-wrap items-end gap-2">
          <Field
            label={t("indicators.periodStart")}
            type="date"
            required
            value={row.period_start}
            onChange={(e) => update(index, { period_start: e.target.value })}
          />
          <Field
            label={t("indicators.periodEnd")}
            type="date"
            required
            min={row.period_start}
            value={row.period_end}
            onChange={(e) => update(index, { period_end: e.target.value })}
          />
          <Field
            label={`${t("indicators.target")}${indicator.unit ? ` (${indicator.unit})` : ""}`}
            type="number"
            step="any"
            required
            value={row.target}
            onChange={(e) => update(index, { target: e.target.value })}
          />
          <Button
            type="button"
            variant="danger"
            onClick={() => setRows(rows.filter((_, i) => i !== index))}
          >
            {t("common.remove")}
          </Button>
        </div>
      ))}
      <div className="flex flex-wrap gap-2">
        <Button
          type="button"
          variant="ghost"
          onClick={() => {
            const last = rows.at(-1);
            // La période suivante commence le lendemain de la précédente.
            const next = last?.period_end
              ? new Date(new Date(last.period_end).getTime() + 86_400_000)
                  .toISOString()
                  .slice(0, 10)
              : "";
            setRows([...rows, { period_start: next, period_end: "", target: "" }]);
          }}
        >
          + {t("indicators.addPeriod")}
        </Button>
        <span className="flex-1" />
        <Button type="submit" disabled={save.isPending}>
          {t("common.save")}
        </Button>
        <Button type="button" variant="ghost" onClick={onDone}>
          {t("common.cancel")}
        </Button>
      </div>
      <ErrorText error={save.error} />
    </form>
  );
}

function DetailsForm({
  orgId,
  projectId,
  indicator,
  onDone,
}: Props & {
  indicator: Indicator;
  onDone: () => void;
}) {
  const { t } = useTranslation();
  const invalidate = useInvalidateProject(orgId, projectId);
  const [source, setSource] = useState(indicator.source_of_verification);
  const [disaggregations, setDisaggregations] = useState(indicator.disaggregations.join(", "));
  const save = useMutation({
    mutationFn: () =>
      projectsApi.updateIndicator(orgId, projectId, indicator.id, {
        source_of_verification: source,
        disaggregations: parseList(disaggregations),
      }),
    onSuccess: async () => {
      await invalidate();
      onDone();
    },
  });
  const submit = (event: FormEvent) => {
    event.preventDefault();
    save.mutate();
  };
  return (
    <form onSubmit={submit} className="grid gap-3 bg-slate-50 p-3 sm:grid-cols-2">
      <Field
        label={t("indicators.source")}
        value={source}
        onChange={(e) => setSource(e.target.value)}
      />
      <Field
        label={t("indicators.disaggregations")}
        hint={t("indicators.disaggregationsHint")}
        value={disaggregations}
        onChange={(e) => setDisaggregations(e.target.value)}
      />
      <div className="flex gap-2 sm:col-span-2">
        <Button type="submit" disabled={save.isPending}>
          {t("common.save")}
        </Button>
        <Button type="button" variant="ghost" onClick={onDone}>
          {t("common.cancel")}
        </Button>
        <ErrorText error={save.error} />
      </div>
    </form>
  );
}

function PeriodTable({ indicator }: { indicator: Indicator }) {
  const { t, i18n } = useTranslation();
  const dates = new Intl.DateTimeFormat(i18n.language, { dateStyle: "medium" });
  const num = (value: string | null) => formatNumber(value, i18n.language);
  return (
    <table className="mt-2 w-full text-left text-xs">
      <thead className="text-slate-500">
        <tr>
          <th className="py-1 pr-3 font-medium">{t("indicators.period")}</th>
          <th className="py-1 pr-3 text-right font-medium">{t("indicators.target")}</th>
          <th className="py-1 pr-3 text-right font-medium">{t("indicators.achieved")}</th>
          <th className="py-1 text-right font-medium">{t("indicators.rate")}</th>
        </tr>
      </thead>
      <tbody className="divide-y divide-slate-100">
        {indicator.period_targets.map((row) => (
          <tr key={row.period_start}>
            <td className="py-1 pr-3">
              {dates.format(new Date(row.period_start))} – {dates.format(new Date(row.period_end))}
            </td>
            <td className="py-1 pr-3 text-right tabular-nums">{num(row.target)}</td>
            <td className="py-1 pr-3 text-right tabular-nums">{num(row.achieved)}</td>
            <td className="py-1 text-right tabular-nums">
              {formatRate(row.achievement_rate, i18n.language)}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

const emptyForm = {
  node_id: "",
  code: "",
  name: "",
  unit: "",
  baseline: "",
  target: "",
  aggregation: "sum" as "sum" | "latest",
  source_of_verification: "",
  disaggregations: "",
};

export function IndicatorsTab({ orgId, projectId }: Props) {
  const { t, i18n } = useTranslation();
  const { role } = useCurrentOrg();
  const canPlan = permissions.plan(role);
  const canRecord = permissions.recordValues(role);
  const invalidate = useInvalidateProject(orgId, projectId);
  const indicators = useQuery(indicatorsQuery(orgId, projectId));
  const logframe = useQuery(logframeQuery(orgId, projectId));
  const [form, setForm] = useState(emptyForm);
  const [valueFor, setValueFor] = useState<string | null>(null);
  const [targetsFor, setTargetsFor] = useState<string | null>(null);
  const [detailsFor, setDetailsFor] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [nodeFilter, setNodeFilter] = useState("");

  const nodes = flattenTree(logframe.data ?? []);
  const nodeName = new Map(nodes.map((n) => [n.id, `${n.code} ${n.title}`.trim()]));
  const num = (value: string | null) => formatNumber(value, i18n.language);
  const filterNodes = nodes.filter((n) => n.level === "outcome" || n.level === "output");
  const shown = filterIndicators(indicators.data ?? [], nodes, { query, nodeId: nodeFilter });

  const add = useMutation({
    mutationFn: () =>
      projectsApi.addIndicator(orgId, projectId, {
        ...form,
        baseline: form.baseline || null,
        target: form.target || null,
        disaggregations: parseList(form.disaggregations),
      }),
    onSuccess: async () => {
      setForm(emptyForm);
      await invalidate();
    },
  });
  const remove = useMutation({
    mutationFn: (id: string) => projectsApi.deleteIndicator(orgId, projectId, id),
    onSuccess: invalidate,
  });
  const submit = (event: FormEvent) => {
    event.preventDefault();
    add.mutate();
  };
  const set = (key: keyof typeof emptyForm) => (e: { target: { value: string } }) =>
    setForm((f) => ({ ...f, [key]: e.target.value }));

  return (
    <Card>
      {!!indicators.data?.length && (
        <div className="mb-3 grid gap-3 sm:grid-cols-2">
          <Field
            label={t("indicators.search")}
            type="search"
            placeholder={t("indicators.searchPlaceholder")}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <Select
            label={t("indicators.filterNode")}
            value={nodeFilter}
            onChange={(e) => setNodeFilter(e.target.value)}
          >
            <option value="">{t("indicators.allNodes")}</option>
            {filterNodes.map((n) => (
              <option key={n.id} value={n.id}>
                {t(`levels.${n.level}`)} · {nodeName.get(n.id)}
              </option>
            ))}
          </Select>
        </div>
      )}
      {shown.length ? (
        <ul className="divide-y divide-slate-100">
          {shown.map((indicator) => {
            const pct = Math.min(100, Math.round((indicator.achievement_rate ?? 0) * 100));
            return (
              <li key={indicator.id} className="py-3">
                <div className="flex flex-wrap items-start gap-3">
                  <span className="font-mono text-xs text-slate-500">{indicator.code}</span>
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium">{indicator.name}</p>
                    <p className="text-xs text-slate-500">{nodeName.get(indicator.node_id)}</p>
                    <dl className="mt-1 space-y-0.5 text-xs text-slate-600">
                      <div>
                        <dt className="inline font-medium">{t("indicators.source")} : </dt>
                        <dd className="inline">{indicator.source_of_verification || "–"}</dd>
                      </div>
                      <div>
                        <dt className="inline font-medium">{t("indicators.disaggregations")} : </dt>
                        <dd className="inline">
                          {indicator.disaggregations.length
                            ? indicator.disaggregations.map((d) => (
                                <span
                                  key={d}
                                  className="mr-1 rounded bg-slate-100 px-1.5 py-0.5 text-slate-700"
                                >
                                  {d}
                                </span>
                              ))
                            : "–"}
                        </dd>
                      </div>
                    </dl>
                  </div>
                  <div className="w-56 text-right text-xs text-slate-600">
                    <p>
                      {t("indicators.baseline")} {num(indicator.baseline)} ·{" "}
                      {t("indicators.target")} {num(indicator.target)} {indicator.unit}
                    </p>
                    <p className="text-sm font-medium text-slate-900">
                      {t("indicators.achieved")} {num(indicator.achieved)} ·{" "}
                      {formatRate(indicator.achievement_rate, i18n.language)}
                    </p>
                    <div className="mt-1 h-1.5 rounded-full bg-slate-100" aria-hidden>
                      <div
                        className="h-1.5 rounded-full bg-brand-600"
                        style={{ width: `${pct}%` }}
                      />
                    </div>
                  </div>
                  <div className="flex gap-1">
                    {canRecord && (
                      <Button
                        variant="ghost"
                        className="!px-2 !py-1 text-xs"
                        onClick={() => setValueFor(indicator.id)}
                      >
                        + {t("indicators.addValue")}
                      </Button>
                    )}
                    {canPlan && (
                      <Button
                        variant="ghost"
                        className="!px-2 !py-1 text-xs"
                        onClick={() => setDetailsFor(indicator.id)}
                      >
                        {t("indicators.editDetails")}
                      </Button>
                    )}
                    {canPlan && (
                      <Button
                        variant="ghost"
                        className="!px-2 !py-1 text-xs"
                        onClick={() => setTargetsFor(indicator.id)}
                      >
                        {t("indicators.periodTargets")}
                      </Button>
                    )}
                    {canPlan && (
                      <Button
                        variant="danger"
                        className="!px-2 !py-1 text-xs"
                        onClick={() => remove.mutate(indicator.id)}
                      >
                        {t("common.remove")}
                      </Button>
                    )}
                  </div>
                </div>
                {indicator.period_targets.length > 0 && targetsFor !== indicator.id && (
                  <PeriodTable indicator={indicator} />
                )}
                {targetsFor === indicator.id && (
                  <div className="mt-2">
                    <TargetsForm
                      orgId={orgId}
                      projectId={projectId}
                      indicator={indicator}
                      onDone={() => setTargetsFor(null)}
                    />
                  </div>
                )}
                {detailsFor === indicator.id && (
                  <div className="mt-2">
                    <DetailsForm
                      orgId={orgId}
                      projectId={projectId}
                      indicator={indicator}
                      onDone={() => setDetailsFor(null)}
                    />
                  </div>
                )}
                {valueFor === indicator.id && (
                  <div className="mt-2">
                    <ValueForm
                      orgId={orgId}
                      projectId={projectId}
                      indicator={indicator}
                      onDone={() => setValueFor(null)}
                    />
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      ) : (
        <p className="text-sm text-slate-500">
          {indicators.data?.length ? t("indicators.noMatch") : t("indicators.empty")}
        </p>
      )}

      {canPlan && nodes.length > 0 && (
        <form onSubmit={submit} className="mt-5 space-y-3 border-t border-slate-100 pt-5">
          <h3 className="text-sm font-semibold">{t("indicators.add")}</h3>
          <div className="grid gap-3 sm:grid-cols-[8rem_1fr]">
            <Field label={t("indicators.code")} value={form.code} onChange={set("code")} />
            <Field
              label={t("indicators.name")}
              required
              minLength={2}
              value={form.name}
              onChange={set("name")}
            />
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <Select
              label={t("indicators.attachedTo")}
              required
              value={form.node_id}
              onChange={set("node_id")}
            >
              <option value="" disabled>
                –
              </option>
              {nodes.map((n) => (
                <option key={n.id} value={n.id}>
                  {t(`levels.${n.level}`)} · {nodeName.get(n.id)}
                </option>
              ))}
            </Select>
            <Field
              label={t("indicators.source")}
              value={form.source_of_verification}
              onChange={set("source_of_verification")}
            />
          </div>
          <Field
            label={t("indicators.disaggregations")}
            hint={t("indicators.disaggregationsHint")}
            value={form.disaggregations}
            onChange={set("disaggregations")}
          />
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <Field label={t("indicators.unit")} value={form.unit} onChange={set("unit")} />
            <Field
              label={t("indicators.baseline")}
              type="number"
              step="any"
              value={form.baseline}
              onChange={set("baseline")}
            />
            <Field
              label={t("indicators.target")}
              type="number"
              step="any"
              value={form.target}
              onChange={set("target")}
            />
            <Select
              label={t("indicators.aggregation")}
              value={form.aggregation}
              onChange={set("aggregation")}
            >
              <option value="sum">{t("indicators.sum")}</option>
              <option value="latest">{t("indicators.latest")}</option>
            </Select>
          </div>
          <ErrorText error={add.error} />
          <Button type="submit" disabled={add.isPending}>
            {t("indicators.add")}
          </Button>
        </form>
      )}
    </Card>
  );
}
