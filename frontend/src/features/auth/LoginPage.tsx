import { useMutation } from "@tanstack/react-query";
import { Link, useNavigate } from "@tanstack/react-router";
import { type FormEvent, useState } from "react";
import { useTranslation } from "react-i18next";

import { Button, ErrorText, Field } from "@/components/ui";
import { api } from "@/lib/api";
import { tokenStore } from "@/lib/tokens";

import { AuthLayout } from "./AuthLayout";

export function LoginPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const login = useMutation({
    mutationFn: () => api.login(email, password),
    onSuccess: async (tokens) => {
      tokenStore.set(tokens);
      await navigate({ to: "/" });
    },
  });

  const submit = (event: FormEvent) => {
    event.preventDefault();
    login.mutate();
  };

  return (
    <AuthLayout title={t("auth.loginTitle")}>
      <form onSubmit={submit} className="space-y-4">
        <Field
          label={t("common.email")}
          type="email"
          autoComplete="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />
        <Field
          label={t("common.password")}
          type="password"
          autoComplete="current-password"
          required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        <ErrorText error={login.error} />
        <Button type="submit" className="w-full" disabled={login.isPending}>
          {t("auth.loginSubmit")}
        </Button>
      </form>
      <p className="mt-5 text-center text-sm text-slate-600">
        {t("auth.noAccount")}{" "}
        <Link to="/register" className="font-medium text-brand-700 hover:underline">
          {t("auth.createAccount")}
        </Link>
      </p>
    </AuthLayout>
  );
}
