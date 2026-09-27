import { useMutation } from "@tanstack/react-query";
import { Link, useNavigate } from "@tanstack/react-router";
import { type FormEvent, useState } from "react";
import { useTranslation } from "react-i18next";

import { Button, ErrorText, Field } from "@/components/ui";
import { api } from "@/lib/api";
import { tokenStore } from "@/lib/tokens";

import { AuthLayout } from "./AuthLayout";

export function RegisterPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [form, setForm] = useState({
    full_name: "",
    email: "",
    password: "",
    organization_name: "",
  });
  const update = (key: keyof typeof form) => (e: { target: { value: string } }) =>
    setForm((f) => ({ ...f, [key]: e.target.value }));

  const register = useMutation({
    mutationFn: () => api.register(form),
    onSuccess: async (tokens) => {
      tokenStore.set(tokens);
      await navigate({ to: "/" });
    },
  });

  const submit = (event: FormEvent) => {
    event.preventDefault();
    register.mutate();
  };

  return (
    <AuthLayout title={t("auth.registerTitle")}>
      <form onSubmit={submit} className="space-y-4">
        <Field
          label={t("common.fullName")}
          autoComplete="name"
          required
          value={form.full_name}
          onChange={update("full_name")}
        />
        <Field
          label={t("auth.organizationName")}
          required
          minLength={2}
          value={form.organization_name}
          onChange={update("organization_name")}
        />
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
