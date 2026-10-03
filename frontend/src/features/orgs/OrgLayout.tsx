import { useMutation, useQueryClient, useSuspenseQuery } from "@tanstack/react-query";
import { Link, Outlet, useNavigate, useParams, useRouterState } from "@tanstack/react-router";
import { type FormEvent, useState } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui";
import { api } from "@/lib/api";
import { meQuery } from "@/lib/queries";
import { countPending } from "@/lib/outbox";
import { endSession } from "@/lib/session";
import { useOnline } from "@/lib/useOnline";
import { useOutboxSync } from "@/lib/useOutboxSync";

export function OrgLayout() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { orgId } = useParams({ from: "/orgs/$orgId" });
  const online = useOnline();
  // « Projets » reste actif sur la liste et sur chaque projet.
  const path = useRouterState({ select: (state) => state.location.pathname });
  const onProjects = !/\/(lessons|templates|members)\/?$/.test(path);
  useOutboxSync();
  const { data: me } = useSuspenseQuery(meQuery);
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");

  const create = useMutation({
    mutationFn: () => api.createOrganization(name),
    onSuccess: async (org) => {
      await queryClient.invalidateQueries({ queryKey: ["me"] });
      setCreating(false);
      setName("");
      await navigate({ to: "/orgs/$orgId", params: { orgId: org.id } });
    },
  });

  const logout = async () => {
    // La file d'envoi est effacée avec la session : prévenir s'il reste des saisies non envoyées.
    const pending = await countPending();
    if (pending > 0 && !window.confirm(t("auth.logoutPending", { count: pending }))) return;
    await endSession(queryClient);
    await navigate({ to: "/login" });
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    create.mutate();
  };

  return (
    <div className="min-h-screen">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-5xl flex-wrap items-center gap-3 px-4 py-3">
          <span className="text-lg font-bold text-brand-700">{t("app.name")}</span>
          {!online && (
            <span
              role="status"
              className="rounded bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-800"
            >
              {t("offline.badge")}
            </span>
          )}
          <label className="sr-only" htmlFor="org-switch">
            {t("orgs.switch")}
          </label>
          <select
            id="org-switch"
            className="rounded-md border border-slate-300 px-2 py-1.5 text-sm"
            value={orgId}
            onChange={(e) => navigate({ to: "/orgs/$orgId", params: { orgId: e.target.value } })}
          >
            {me.organizations.map((org) => (
              <option key={org.id} value={org.id}>
                {org.name}
              </option>
            ))}
          </select>
          <nav className="flex gap-1 text-sm">
            <Link
              to="/orgs/$orgId"
              params={{ orgId }}
              activeOptions={{ exact: true, includeSearch: false }}
              className={`rounded-md px-2 py-1.5 text-slate-700 hover:bg-slate-100 ${
                onProjects ? "font-semibold text-brand-800" : ""
              }`}
            >
              {t("nav.projects")}
            </Link>
            <Link
              to="/orgs/$orgId/lessons"
              params={{ orgId }}
              className="rounded-md px-2 py-1.5 text-slate-700 hover:bg-slate-100 [&.active]:font-semibold [&.active]:text-brand-800"
            >
              {t("nav.lessons")}
            </Link>
            <Link
              to="/orgs/$orgId/templates"
              params={{ orgId }}
              className="rounded-md px-2 py-1.5 text-slate-700 hover:bg-slate-100 [&.active]:font-semibold [&.active]:text-brand-800"
            >
              {t("nav.templates")}
            </Link>
            <Link
              to="/orgs/$orgId/members"
              params={{ orgId }}
              className="rounded-md px-2 py-1.5 text-slate-700 hover:bg-slate-100 [&.active]:font-semibold [&.active]:text-brand-800"
            >
              {t("nav.members")}
            </Link>
          </nav>
          <Button variant="ghost" onClick={() => setCreating((v) => !v)}>
            + {t("orgs.newOrganization")}
          </Button>
          <span className="ml-auto text-sm text-slate-600">{me.full_name}</span>
          <Button variant="ghost" onClick={logout}>
            {t("common.logout")}
          </Button>
        </div>
        {creating && (
          <form onSubmit={submit} className="mx-auto flex max-w-5xl gap-2 px-4 pb-3">
            <input
              aria-label={t("orgs.newOrganization")}
              className="flex-1 rounded-md border border-slate-300 px-3 py-1.5 text-sm"
              required
              minLength={2}
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
            <Button type="submit" disabled={create.isPending}>
              {t("orgs.create")}
            </Button>
          </form>
        )}
      </header>
      <main className="mx-auto max-w-5xl space-y-6 px-4 py-6">
        <Outlet />
      </main>
    </div>
  );
}
