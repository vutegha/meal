import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useSearch } from "@tanstack/react-router";
import { type FormEvent, useState } from "react";
import { useTranslation } from "react-i18next";

import { Button, ErrorText, Field, Select } from "@/components/ui";
import { type AccountType, api } from "@/lib/api";
import { type Cycle, CYCLES } from "@/lib/billing";
import { catalogQuery } from "@/lib/queries";
import { startSession } from "@/lib/session";
import { cn } from "@/lib/utils";

import { AuthLayout } from "./AuthLayout";

const DEFAULT_PLAN: Record<AccountType, string> = { individual: "solo", organization: "team" };

export function RegisterPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  // Formule choisie sur la page Tarifs, le cas échéant.
  const search = useSearch({ from: "/register" });
  const { data: catalog } = useQuery(catalogQuery);
  const [accountType, setAccountType] = useState<AccountType>(search.type ?? "organization");
  const [plan, setPlan] = useState(search.plan ?? DEFAULT_PLAN[accountType]);
  const [cycle, setCycle] = useState<Cycle>(search.cycle ?? "monthly");
  const queryClient = useQueryClient();
  const [form, setForm] = useState({
    full_name: "",
    email: "",
    password: "",
    organization_name: "",
  });
  const update = (key: keyof typeof form) => (e: { target: { value: string } }) =>
    setForm((f) => ({ ...f, [key]: e.target.value }));
  const plans = catalog?.plans.filter((p) => p.account_type === accountType) ?? [];

  const chooseType = (type: AccountType) => {
    setAccountType(type);
    setPlan(DEFAULT_PLAN[type]);
  };

  const register = useMutation({
    mutationFn: () =>
      api.register({
        full_name: form.full_name,
        email: form.email,
        password: form.password,
        organization_name: accountType === "organization" ? form.organization_name : undefined,
        account_type: accountType,
        plan,
        cycle,
      }),
    onSuccess: async (tokens) => {
      await startSession(queryClient, tokens);
      await navigate({ to: "/" });
    },
  });

  const submit = (event: FormEvent) => {
    event.preventDefault();
    register.mutate();
  };

  return (
    <AuthLayout title={t("auth.registerTitle")} wide>
      <form onSubmit={submit} className="space-y-4">
        <fieldset>
          <legend className="mb-2 text-sm font-medium text-slate-700">
            {t("auth.accountType")}
          </legend>
          <div className="grid gap-2 sm:grid-cols-2">
            {(["individual", "organization"] as const).map((type) => (
              <label
                key={type}
                className={cn(
                  "cursor-pointer rounded-lg border p-3 text-sm transition",
                  accountType === type
                    ? "border-brand-700 bg-brand-50 ring-1 ring-brand-700"
                    : "border-slate-200 hover:border-slate-300",
                )}
              >
                <input
                  type="radio"
                  name="account_type"
                  value={type}
                  checked={accountType === type}
                  onChange={() => chooseType(type)}
                  className="sr-only"
                />
                <span className="block font-semibold text-slate-900">{t(`auth.${type}`)}</span>
                <span className="mt-1 block text-xs text-slate-600">{t(`auth.${type}Hint`)}</span>
              </label>
            ))}
          </div>
        </fieldset>
        <Field
          label={t("common.fullName")}
          autoComplete="name"
          required
          value={form.full_name}
          onChange={update("full_name")}
        />
        {accountType === "organization" && (
          <Field
            label={t("auth.organizationName")}
            required
            minLength={2}
            value={form.organization_name}
            onChange={update("organization_name")}
          />
        )}
        <Field
          label={t("common.email")}
          type="email"
          autoComplete="email"
          required
          value={form.email}
          onChange={update("email")}
        />
        <Field
          label={t("common.password")}
          type="password"
          autoComplete="new-password"
          required
          minLength={8}
          hint={t("auth.passwordHint")}
          value={form.password}
          onChange={update("password")}
        />
        <div className="grid gap-3 sm:grid-cols-2">
          <Select label={t("auth.plan")} value={plan} onChange={(e) => setPlan(e.target.value)}>
            {(plans.length ? plans.map((p) => p.id) : [plan]).map((id) => (
              <option key={id} value={id}>
                {t(`billing.plans.${id}`)}
              </option>
            ))}
          </Select>
          <Select
            label={t("auth.cycle")}
            value={cycle}
            onChange={(e) => setCycle(e.target.value as Cycle)}
          >
            {CYCLES.map((c) => (
              <option key={c} value={c}>
                {t(`site.pricing.cycles.${c}`)}
              </option>
            ))}
          </Select>
        </div>
        <p className="rounded-md bg-slate-50 p-3 text-xs text-slate-600">
          {cycle === "usage"
            ? t("auth.usageNote", { count: catalog?.welcome_credits ?? 5 })
            : t("auth.trialNote", { days: catalog?.trial_days ?? 14 })}{" "}
          <Link to="/tarifs" className="font-medium text-brand-700 hover:underline">
            {t("site.nav.pricing")}
          </Link>
        </p>
        <ErrorText error={register.error} />
        <Button type="submit" className="w-full" disabled={register.isPending}>
          {t("auth.registerSubmit")}
        </Button>
      </form>
      <p className="mt-5 text-center text-sm text-slate-600">
        {t("auth.hasAccount")}{" "}
        <Link to="/login" className="font-medium text-brand-700 hover:underline">
          {t("auth.loginSubmit")}
        </Link>
      </p>
    </AuthLayout>
  );
}
