import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useSearch } from "@tanstack/react-router";
import { type FormEvent, useState } from "react";
import { useTranslation } from "react-i18next";

import { Button, ErrorText, Field } from "@/components/ui";
import { api } from "@/lib/api";
import { startSession } from "@/lib/session";

import { AuthLayout } from "./AuthLayout";

export function ResetPasswordPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { token } = useSearch({ from: "/reset-password" });
  const [password, setPassword] = useState("");
  const reset = useMutation({
    mutationFn: () => api.resetPassword(token ?? "", password),
    onSuccess: async (tokens) => {
      await startSession(queryClient, tokens);
      await navigate({ to: "/" });
    },
  });

  const submit = (event: FormEvent) => {
    event.preventDefault();
    reset.mutate();
  };

  return (
    <AuthLayout title={t("auth.resetTitle")}>
      <form onSubmit={submit} className="space-y-4">
        <Field
          label={t("account.newPassword")}
          type="password"
          autoComplete="new-password"
          minLength={8}
          required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        <ErrorText error={token ? reset.error : t("auth.resetMissingToken")} />
        <Button type="submit" className="w-full" disabled={!token || reset.isPending}>
          {t("auth.resetSubmit")}
        </Button>
      </form>
    </AuthLayout>
  );
}
