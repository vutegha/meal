import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";
import { useTranslation } from "react-i18next";

import { Button, Card, ErrorText, Field, Select } from "@/components/ui";
import { api, ROLES, type Role } from "@/lib/api";
import { membersQuery } from "@/lib/queries";

const emptyForm = { email: "", role: "field_agent" as Role, full_name: "", initial_password: "" };

export function MembersPanel({
  orgId,
  isAdmin,
  currentUserId,
}: {
  orgId: string;
  isAdmin: boolean;
  currentUserId: string;
}) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const members = useQuery(membersQuery(orgId));
  const [form, setForm] = useState(emptyForm);

  const refresh = () => queryClient.invalidateQueries({ queryKey: ["orgs", orgId] });

  const add = useMutation({
    mutationFn: () =>
      api.addMember(orgId, {
        email: form.email,
        role: form.role,
        full_name: form.full_name || undefined,
        initial_password: form.initial_password || undefined,
      }),
    onSuccess: async () => {
      setForm(emptyForm);
      await refresh();
    },
  });
  const changeRole = useMutation({
    mutationFn: ({ id, role }: { id: string; role: Role }) => api.updateMember(orgId, id, role),
    onSettled: refresh,
  });
  const remove = useMutation({
    mutationFn: (id: string) => api.removeMember(orgId, id),
    onSettled: refresh,
  });
  const [resetFor, setResetFor] = useState<{ name: string; url: string } | null>(null);
  const resetLink = useMutation({
    mutationFn: ({ id }: { id: string; name: string }) => api.memberResetLink(orgId, id),
    onSuccess: (link, { name }) => setResetFor({ name, url: window.location.origin + link.path }),
  });

  const submit = (event: FormEvent) => {
    event.preventDefault();
    add.mutate();
  };

  return (
    <Card title={t("orgs.members")}>
      {members.isPending ? (
        <p className="text-sm text-slate-500">{t("common.loading")}</p>
      ) : (
        <ul className="divide-y divide-slate-100">
          {members.data?.map((member) => (
            <li key={member.id} className="flex flex-wrap items-center gap-3 py-2.5">
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium">{member.user.full_name}</p>
                <p className="truncate text-xs text-slate-500">{member.user.email}</p>
              </div>
              {isAdmin ? (
                <>
                  <select
                    aria-label={t("orgs.role")}
                    className="rounded-md border border-slate-300 px-2 py-1 text-sm"
                    value={member.role}
                    onChange={(e) =>
                      changeRole.mutate({ id: member.id, role: e.target.value as Role })
                    }
                  >
                    {ROLES.map((role) => (
                      <option key={role} value={role}>
                        {t(`roles.${role}`)}
                      </option>
                    ))}
                  </select>
                  {member.user.id !== currentUserId && (
                    <>
                      <Button
                        variant="ghost"
                        onClick={() =>
                          resetLink.mutate({ id: member.id, name: member.user.full_name })
                        }
                      >
                        {t("orgs.resetLink")}
                      </Button>
                      <Button variant="danger" onClick={() => remove.mutate(member.id)}>
                        {t("common.remove")}
                      </Button>
                    </>
                  )}
                </>
              ) : (
                <span className="text-sm text-slate-600">{t(`roles.${member.role}`)}</span>
              )}
            </li>
          ))}
        </ul>
      )}
      <ErrorText error={changeRole.error ?? remove.error ?? resetLink.error} />
      {resetFor && (
        <div role="status" className="mt-3 rounded-md bg-sky-50 p-3 text-sm text-sky-900">
          <p>{t("orgs.resetLinkReady", { name: resetFor.name })}</p>
          <input
            readOnly
            aria-label={t("orgs.resetLink")}
            className="mt-2 w-full rounded border border-sky-200 bg-white px-2 py-1 font-mono text-xs"
            value={resetFor.url}
            onFocus={(e) => e.target.select()}
          />
        </div>
      )}

      {isAdmin && (
        <form onSubmit={submit} className="mt-5 space-y-3 border-t border-slate-100 pt-5">
          <h3 className="text-sm font-semibold">{t("orgs.addMember")}</h3>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field
              label={t("common.email")}
              type="email"
              required
              value={form.email}
              onChange={(e) => setForm({ ...form, email: e.target.value })}
            />
            <Select
              label={t("orgs.role")}
              value={form.role}
              onChange={(e) => setForm({ ...form, role: e.target.value as Role })}
            >
              {ROLES.map((role) => (
                <option key={role} value={role}>
                  {t(`roles.${role}`)}
                </option>
              ))}
            </Select>
            <Field
              label={t("common.fullName")}
              value={form.full_name}
              onChange={(e) => setForm({ ...form, full_name: e.target.value })}
            />
            <Field
              label={t("orgs.initialPassword")}
              type="password"
              autoComplete="new-password"
              minLength={8}
              value={form.initial_password}
              onChange={(e) => setForm({ ...form, initial_password: e.target.value })}
            />
          </div>
          <p className="text-xs text-slate-500">{t("orgs.newUserHint")}</p>
          <ErrorText error={add.error} />
          <Button type="submit" disabled={add.isPending}>
            {t("orgs.add")}
          </Button>
        </form>
      )}
    </Card>
  );
}
