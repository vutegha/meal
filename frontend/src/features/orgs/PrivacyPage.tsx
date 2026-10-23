import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";
import { useTranslation } from "react-i18next";

import { Button, Card, ErrorText, Field } from "@/components/ui";
import { api, type PersonalData, type PrivacySettings } from "@/lib/api";

import { useCurrentOrg } from "./useCurrentOrg";

/** Données personnelles : réglages de l'espace et réponse aux demandes des personnes. */
export function PrivacyPage() {
  const { t } = useTranslation();
  const { orgId, role } = useCurrentOrg();
  if (role !== "admin") return <p className="text-sm text-slate-600">{t("privacy.adminOnly")}</p>;
  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold">{t("privacy.title")}</h1>
      <SettingsCard orgId={orgId} />
      <PersonCard orgId={orgId} />
    </div>
  );
}

function SettingsCard({ orgId }: { orgId: string }) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const key = ["orgs", orgId, "privacy"];
  const settings = useQuery({ queryKey: key, queryFn: () => api.privacy(orgId) });
  const [draft, setDraft] = useState<Partial<PrivacySettings>>({});
  const save = useMutation({
    mutationFn: () => api.updatePrivacy(orgId, draft),
    onSuccess: (data) => {
      queryClient.setQueryData(key, data);
      setDraft({});
    },
  });
  if (!settings.data) return <ErrorText error={settings.error} />;
  const value = { ...settings.data, ...draft };
  const submit = (event: FormEvent) => {
    event.preventDefault();
    save.mutate();
  };
  return (
    <Card title={t("privacy.settings")}>
      <form onSubmit={submit} className="space-y-4">
        <label className="flex items-start gap-2 text-sm">
          <input
            type="checkbox"
            className="mt-1"
            checked={value.ai_enabled}
            onChange={(e) => setDraft({ ...draft, ai_enabled: e.target.checked })}
          />
          <span>
            {t("privacy.aiEnabled")}
            <span className="block text-xs text-slate-500">{t("privacy.aiHint")}</span>
          </span>
        </label>
        <label className="flex items-start gap-2 text-sm">
          <input
            type="checkbox"
            className="mt-1"
            checked={value.sms_acknowledgement}
            onChange={(e) => setDraft({ ...draft, sms_acknowledgement: e.target.checked })}
          />
          <span>
            {t("privacy.smsAck")}
            <span className="block text-xs text-slate-500">{t("privacy.smsAckHint")}</span>
          </span>
        </label>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field
            label={t("privacy.retention")}
            hint={t("privacy.retentionHint")}
            type="number"
            min={0}
            max={240}
            value={value.feedback_retention_months}
            onChange={(e) =>
              setDraft({ ...draft, feedback_retention_months: Number(e.target.value) })
            }
          />
          <Field
            label={t("privacy.contact")}
            hint={t("privacy.contactHint")}
            maxLength={200}
            value={value.privacy_contact}
            onChange={(e) => setDraft({ ...draft, privacy_contact: e.target.value })}
          />
        </div>
        <ErrorText error={save.error} />
        {save.isSuccess && (
          <p role="status" className="text-sm text-emerald-700">
            {t("privacy.saved")}
          </p>
        )}
        <Button type="submit" disabled={save.isPending || Object.keys(draft).length === 0}>
          {t("common.save")}
        </Button>
      </form>
    </Card>
  );
}

function downloadJson(data: PersonalData) {
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `donnees-personnelles-${new Date().toISOString().slice(0, 10)}.json`;
  link.click();
  URL.revokeObjectURL(url);
}

function PersonCard({ orgId }: { orgId: string }) {
  const { t } = useTranslation();
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [reason, setReason] = useState("");
  const search = useMutation({
    mutationFn: () => api.searchPerson(orgId, query.trim()),
    onSuccess: (data) =>
      setSelected(
        new Set([
          ...data.feedback.filter((f) => !f.anonymized).map((f) => f.id),
          ...data.submissions.map((s) => s.id),
        ]),
      ),
  });
  const erase = useMutation({
    mutationFn: () => {
      const data = search.data!;
      return api.erasePerson(orgId, {
        feedback_ids: data.feedback.filter((f) => selected.has(f.id)).map((f) => f.id),
        submission_ids: data.submissions.filter((s) => selected.has(s.id)).map((s) => s.id),
        reason,
      });
    },
    onSuccess: () => {
      setReason("");
      search.mutate();
    },
  });
  const toggle = (id: string) =>
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  const data = search.data;
  const found = data ? data.feedback.length + data.submissions.length + data.evidence.length : 0;

  return (
    <Card title={t("privacy.person")}>
      <p className="mb-3 text-sm text-slate-600">{t("privacy.personIntro")}</p>
      <form
        className="flex flex-wrap gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          search.mutate();
        }}
      >
        <input
          aria-label={t("privacy.query")}
          placeholder={t("privacy.query")}
          className="min-w-0 flex-1 rounded-md border border-slate-300 px-3 py-1.5 text-sm"
          minLength={3}
          required
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <Button type="submit" disabled={search.isPending}>
          {t("privacy.search")}
        </Button>
      </form>
      <ErrorText error={search.error} />

      {data && (
        <div className="mt-4 space-y-4">
          <p className="text-sm">{t("privacy.found", { count: found })}</p>
          {data.feedback.length > 0 && (
            <section>
              <h3 className="text-sm font-semibold">{t("privacy.feedback")}</h3>
              <ul className="divide-y divide-slate-100">
                {data.feedback.map((f) => (
                  <li key={f.id} className="flex gap-2 py-2 text-sm">
                    <input
                      type="checkbox"
                      aria-label={f.reference}
                      disabled={f.anonymized}
                      checked={selected.has(f.id)}
                      onChange={() => toggle(f.id)}
                    />
                    <div className="min-w-0">
                      <p className="font-medium">
                        {f.project_code} · {f.reference} · {f.received_on}
                        {f.anonymized && (
                          <span className="ml-2 text-xs text-slate-500">
                            {t("privacy.anonymized")}
                          </span>
                        )}
                      </p>
                      <p className="line-clamp-2 text-slate-600">{f.description}</p>
                      {f.messages.length > 0 && (
                        <p className="text-xs text-slate-500">
                          {t("privacy.messages", { count: f.messages.length })}
                        </p>
                      )}
                    </div>
                  </li>
                ))}
              </ul>
            </section>
          )}
          {data.submissions.length > 0 && (
            <section>
              <h3 className="text-sm font-semibold">{t("privacy.submissions")}</h3>
              <ul className="divide-y divide-slate-100">
                {data.submissions.map((s) => (
                  <li key={s.id} className="flex gap-2 py-2 text-sm">
                    <input
                      type="checkbox"
                      aria-label={s.form_title}
                      checked={selected.has(s.id)}
                      onChange={() => toggle(s.id)}
                    />
                    <p>
                      {s.project_code} · {s.form_title} · {s.collected_at.slice(0, 10)}
                    </p>
                  </li>
                ))}
              </ul>
            </section>
          )}
          {data.evidence.length > 0 && (
            <section>
              <h3 className="text-sm font-semibold">{t("privacy.evidence")}</h3>
              <p className="text-xs text-slate-500">{t("privacy.evidenceHint")}</p>
              <ul className="divide-y divide-slate-100">
                {data.evidence.map((e) => (
                  <li key={e.id} className="py-2 text-sm">
                    <p className="font-medium">
                      {e.project_code} · {e.filename}
                    </p>
                    <p className="text-xs text-slate-600">{e.caption || e.excerpt}</p>
                  </li>
                ))}
              </ul>
            </section>
          )}
          {found > 0 && (
            <div className="space-y-3 border-t border-slate-100 pt-4">
              <Button variant="ghost" onClick={() => downloadJson(data)}>
                {t("privacy.export")}
              </Button>
              <form
                className="space-y-2"
                onSubmit={(event) => {
                  event.preventDefault();
                  if (window.confirm(t("privacy.eraseConfirm", { count: selected.size })))
                    erase.mutate();
                }}
              >
                <Field
                  label={t("privacy.reason")}
                  placeholder={t("privacy.reasonPlaceholder")}
                  minLength={3}
                  required
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                />
                <ErrorText error={erase.error} />
                {erase.isSuccess && (
                  <p role="status" className="text-sm text-emerald-700">
                    {t("privacy.erased", {
                      feedback: erase.data.feedback,
                      submissions: erase.data.submissions,
                    })}
                  </p>
                )}
                <Button
                  type="submit"
                  variant="danger"
                  disabled={selected.size === 0 || erase.isPending}
                >
                  {t("privacy.erase", { count: selected.size })}
                </Button>
              </form>
            </div>
          )}
        </div>
      )}
    </Card>
  );
}
