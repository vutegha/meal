import { useMutation, useQuery, useQueryClient, useSuspenseQuery } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { type FormEvent, useState } from "react";
import { useTranslation } from "react-i18next";

import { Button, Card, ErrorText, Field } from "@/components/ui";
import { api, type TotpSetup } from "@/lib/api";
import { meQuery } from "@/lib/queries";
import { endSession } from "@/lib/session";

/** Mon compte : mot de passe, double authentification et sessions ouvertes. */
export function AccountPage() {
  const { t } = useTranslation();
  const { data: me } = useSuspenseQuery(meQuery);
  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold">{t("account.title")}</h1>
      {me.must_change_password && (
        <p role="status" className="rounded-md bg-amber-50 px-3 py-2 text-sm text-amber-900">
          {t("account.mustChange")}
        </p>
      )}
      <PasswordCard />
      <TotpCard enabled={me.totp_enabled} />
      <SessionsCard />
      <DeleteAccountCard totp={me.totp_enabled} />
    </div>
  );
}

function PasswordCard() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [form, setForm] = useState({ current: "", next: "" });
  const change = useMutation({
    mutationFn: () => api.changePassword(form.current, form.next),
    onSuccess: async () => {
      setForm({ current: "", next: "" });
      await queryClient.invalidateQueries({ queryKey: ["me"] });
      await queryClient.invalidateQueries({ queryKey: ["sessions"] });
    },
  });
  const submit = (event: FormEvent) => {
    event.preventDefault();
    change.mutate();
  };
  return (
    <Card title={t("account.password")}>
      <form onSubmit={submit} className="grid gap-3 sm:grid-cols-2">
        <Field
          label={t("account.currentPassword")}
          type="password"
          autoComplete="current-password"
          required
          value={form.current}
          onChange={(e) => setForm({ ...form, current: e.target.value })}
        />
        <Field
          label={t("account.newPassword")}
          type="password"
          autoComplete="new-password"
          minLength={8}
          required
          value={form.next}
          onChange={(e) => setForm({ ...form, next: e.target.value })}
        />
        <div className="space-y-2 sm:col-span-2">
          <p className="text-xs text-slate-500">{t("account.passwordHint")}</p>
          <ErrorText error={change.error} />
          {change.isSuccess && (
            <p role="status" className="text-sm text-emerald-700">
              {t("account.passwordChanged")}
            </p>
          )}
          <Button type="submit" disabled={change.isPending}>
            {t("account.changePassword")}
          </Button>
        </div>
      </form>
    </Card>
  );
}

function TotpCard({ enabled }: { enabled: boolean }) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [setup, setSetup] = useState<TotpSetup | null>(null);
  const [code, setCode] = useState("");
  const done = async () => {
    setSetup(null);
    setCode("");
    await queryClient.invalidateQueries({ queryKey: ["me"] });
  };
  const start = useMutation({ mutationFn: api.totpSetup, onSuccess: setSetup });
  const enable = useMutation({ mutationFn: () => api.totpEnable(code), onSuccess: done });
  const disable = useMutation({ mutationFn: () => api.totpDisable(code), onSuccess: done });

  const submit = (event: FormEvent) => {
    event.preventDefault();
    (enabled ? disable : enable).mutate();
  };
  const codeField = (
    <Field
      label={t("auth.otpCode")}
      inputMode="numeric"
      autoComplete="one-time-code"
      required
      value={code}
      onChange={(e) => setCode(e.target.value)}
    />
  );

  return (
    <Card title={t("account.totp")}>
      <p className="mb-3 text-sm text-slate-600">
        {enabled ? t("account.totpOn") : t("account.totpIntro")}
      </p>
      {enabled ? (
        <form onSubmit={submit} className="max-w-xs space-y-3">
          {codeField}
          <ErrorText error={disable.error} />
          <Button type="submit" variant="danger" disabled={disable.isPending}>
            {t("account.totpDisable")}
          </Button>
        </form>
      ) : setup ? (
        <form onSubmit={submit} className="space-y-3">
          <p className="text-sm">{t("account.totpScan")}</p>
          <img src={setup.qr_svg} alt={t("account.totpQr")} className="h-44 w-44" />
          <p className="text-xs text-slate-500">
            {t("account.totpManual")} <code className="break-all">{setup.secret}</code>
          </p>
          <div className="max-w-xs">{codeField}</div>
          <ErrorText error={enable.error} />
          <Button type="submit" disabled={enable.isPending}>
            {t("account.totpConfirm")}
          </Button>
        </form>
      ) : (
        <>
          <ErrorText error={start.error} />
          <Button onClick={() => start.mutate()} disabled={start.isPending}>
            {t("account.totpEnable")}
          </Button>
        </>
      )}
    </Card>
  );
}

function DeleteAccountCard({ totp }: { totp: boolean }) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const remove = useMutation({
    mutationFn: () => api.deleteAccount(password, code),
    onSuccess: async () => {
      await endSession(queryClient);
      await navigate({ to: "/" });
    },
  });
  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (window.confirm(t("account.deleteConfirm"))) remove.mutate();
  };
  return (
    <Card title={t("account.delete")}>
      <form onSubmit={submit} className="space-y-3">
        <p className="text-sm text-slate-600">{t("account.deleteIntro")}</p>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field
            label={t("account.confirmPassword")}
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          {totp && (
            <Field
              label={t("auth.otpCode")}
              inputMode="numeric"
              autoComplete="one-time-code"
              required
              value={code}
              onChange={(e) => setCode(e.target.value)}
            />
          )}
        </div>
        <ErrorText error={remove.error} />
        <Button type="submit" variant="danger" disabled={remove.isPending}>
          {t("account.deleteAction")}
        </Button>
      </form>
    </Card>
  );
}

function SessionsCard() {
  const { t, i18n } = useTranslation();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const sessions = useQuery({ queryKey: ["sessions"], queryFn: api.sessions });
  const logoutAll = useMutation({
    mutationFn: api.logoutAll,
    onSuccess: async () => {
      await endSession(queryClient);
      await navigate({ to: "/login" });
    },
  });
  const date = (value: string) =>
    new Date(value).toLocaleString(i18n.language, { dateStyle: "medium", timeStyle: "short" });
  return (
    <Card title={t("account.sessions")}>
      <ul className="divide-y divide-slate-100">
        {sessions.data?.map((s) => (
          <li key={s.id} className="py-2 text-sm">
            <p className="truncate font-medium">
              {s.user_agent || t("account.unknownDevice")}
              {s.current && (
                <span className="ml-2 text-xs text-emerald-700">{t("account.thisDevice")}</span>
              )}
            </p>
            <p className="text-xs text-slate-500">
              {t("account.openedOn", { date: date(s.created_at) })}
            </p>
          </li>
        ))}
      </ul>
      <ErrorText error={sessions.error ?? logoutAll.error} />
      <Button variant="danger" className="mt-3" onClick={() => logoutAll.mutate()}>
        {t("account.logoutAll")}
      </Button>
    </Card>
  );
}
