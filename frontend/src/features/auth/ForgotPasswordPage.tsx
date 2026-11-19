import { useMutation } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { type FormEvent, useState } from "react";
import { useTranslation } from "react-i18next";

import { Button, ErrorText, Field } from "@/components/ui";
import { api } from "@/lib/api";

import { AuthLayout } from "./AuthLayout";

export function ForgotPasswordPage() {
  const { t } = useTranslation();
  const [email, setEmail] = useState("");
  const forgot = useMutation({ mutationFn: () => api.forgotPassword(email) });

  const submit = (event: FormEvent) => {
    event.preventDefault();
    forgot.mutate();
  };

  return (
    <AuthLayout title={t("auth.forgotTitle")}>
      {forgot.isSuccess ? (
        <p className="text-sm text-slate-700">{t("auth.forgotSent")}</p>
      ) : (
        <form onSubmit={submit} className="space-y-4">
          <p className="text-sm text-slate-600">{t("auth.forgotIntro")}</p>
          <Field
            label={t("common.email")}
            type="email"
            autoComplete="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
          <ErrorText error={forgot.error} />
          <Button type="submit" className="w-full" disabled={forgot.isPending}>
            {t("auth.forgotSubmit")}
          </Button>
        </form>
      )}
      <p className="mt-5 text-center text-sm">
        <Link to="/login" className="text-brand-700 hover:underline">
          {t("auth.backToLogin")}
        </Link>
      </p>
    </AuthLayout>
  );
}
