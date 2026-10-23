import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "@tanstack/react-router";
import { type FormEvent, useState } from "react";
import { useTranslation } from "react-i18next";

import { Button, ErrorText, Field } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { startSession } from "@/lib/session";

import { AuthLayout } from "./AuthLayout";

export function LoginPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [otp, setOtp] = useState("");
  const [needsOtp, setNeedsOtp] = useState(false);
  const login = useMutation({
    mutationFn: () => api.login(email, password, needsOtp ? otp : undefined),
    onSuccess: async (tokens) => {
      await startSession(queryClient, tokens);
      await navigate({ to: "/" });
    },
    onError: (error) => {
      if (error instanceof ApiError && error.otpRequired) setNeedsOtp(true);
    },
  });
  // La première demande de code n'est pas une erreur : la personne n'a encore rien saisi.
  const firstOtpPrompt = login.error instanceof ApiError && login.error.otpRequired && !otp;

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
        {needsOtp && (
          <Field
            label={t("auth.otpCode")}
            hint={t("auth.otpHint")}
            inputMode="numeric"
            autoComplete="one-time-code"
            required
            autoFocus
            value={otp}
            onChange={(e) => setOtp(e.target.value)}
          />
        )}
        <ErrorText error={firstOtpPrompt ? null : login.error} />
        <Button type="submit" className="w-full" disabled={login.isPending}>
          {t("auth.loginSubmit")}
        </Button>
      </form>
      <p className="mt-4 text-center text-sm">
        <Link to="/forgot-password" className="text-brand-700 hover:underline">
          {t("auth.forgotLink")}
        </Link>
      </p>
      <p className="mt-3 text-center text-sm text-slate-600">
        {t("auth.noAccount")}{" "}
        <Link to="/register" className="font-medium text-brand-700 hover:underline">
          {t("auth.createAccount")}
        </Link>
      </p>
    </AuthLayout>
  );
}
