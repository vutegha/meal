import { useMutation, useQuery, useQueryClient, useSuspenseQuery } from "@tanstack/react-query";
import { Link, Outlet, useNavigate, useParams, useRouterState } from "@tanstack/react-router";
import { type FormEvent, useState } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui";
import { api } from "@/lib/api";
import { type Feature, hasFeature } from "@/lib/billing";
import { countPending } from "@/lib/outbox";
import { meQuery, subscriptionQuery } from "@/lib/queries";
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
  const onProjects = !/\/(lessons|templates|members|billing|privacy|account)\/?$/.test(path);
  // Une page de projet porte un menu vertical : on lui laisse plus de largeur.
  const width = /\/projects\/[^/]+/.test(path) ? "max-w-7xl" : "max-w-5xl";
  useOutboxSync();
  const { data: me } = useSuspenseQuery(meQuery);
  const org = me.organizations.find((o) => o.id === orgId);
  const isAdmin = org?.role === "admin";
  // Les pages réservées aux organisations n'apparaissent pas dans le menu d'un compte individuel.
  const shows = (feature: Feature) => !org || hasFeature(org, feature);
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
        <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-3 px-4 py-3">
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
            {(
              [
                ["/orgs/$orgId/lessons", "nav.lessons", "org_lessons"],
                ["/orgs/$orgId/templates", "nav.templates", "templates"],
                ["/orgs/$orgId/members", "nav.members", "team"],
                ["/orgs/$orgId/billing", "nav.billing", null],
                ["/orgs/$orgId/privacy", "nav.privacy", null],
              ] as const
            )
              .filter(([to]) => to !== "/orgs/$orgId/privacy" || isAdmin)
              .filter(([, , feature]) => !feature || shows(feature))
              .map(([to, label]) => (
                <Link
                  key={to}
                  to={to}
                  params={{ orgId }}
                  className="rounded-md px-2 py-1.5 text-slate-700 hover:bg-slate-100 [&.active]:font-semibold [&.active]:text-brand-800"
                >
                  {t(label)}
                </Link>
              ))}
          </nav>
          <Button variant="ghost" onClick={() => setCreating((v) => !v)}>
            + {t("orgs.newOrganization")}
          </Button>
          {/* Le nom cède la place au menu sur les écrans moyens. */}
          <Link
            to="/orgs/$orgId/account"
            params={{ orgId }}
            className="ml-auto rounded-md px-2 py-1.5 text-sm text-slate-700 hover:bg-slate-100 [&.active]:font-semibold"
          >
            <span className="hidden 2xl:inline">{me.full_name}</span>
            <span className="2xl:hidden">{t("account.nav")}</span>
          </Link>
          {me.is_platform_admin && (
            <Link
              to="/admin"
              className="rounded-md px-2 py-1.5 text-sm text-slate-700 hover:bg-slate-100"
            >
              {t("admin.badge")}
            </Link>
          )}
          <Button variant="ghost" onClick={logout}>
            {t("common.logout")}
          </Button>
        </div>
        {creating && (
          <form onSubmit={submit} className={`mx-auto flex ${width} gap-2 px-4 pb-3`}>
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
      <SecurityBanner orgId={orgId} width={width} />
      <SubscriptionBanner orgId={orgId} width={width} />
      <main className={`mx-auto ${width} space-y-6 px-4 py-6`}>
        <Outlet />
      </main>
    </div>
  );
}

/** Mot de passe initial à remplacer, ou double authentification conseillée à un administrateur. */
function SecurityBanner({ orgId, width }: { orgId: string; width: string }) {
  const { t } = useTranslation();
  const { data: me } = useSuspenseQuery(meQuery);
  const onAccount = useRouterState({ select: (s) => s.location.pathname.endsWith("/account") });
  if (onAccount || !(me.must_change_password || me.mfa_recommended)) return null;
  return (
    <div className="bg-amber-50 text-amber-900">
      <div className={`mx-auto flex ${width} flex-wrap items-center gap-3 px-4 py-2 text-sm`}>
        <span>
          {me.must_change_password ? t("account.mustChange") : t("account.mfaRecommended")}
        </span>
        <Link
          to="/orgs/$orgId/account"
          params={{ orgId }}
          className="font-medium underline underline-offset-2"
        >
          {t("account.goToAccount")}
        </Link>
      </div>
    </div>
  );
}

/** Rappel de l'essai en cours, de l'abonnement expiré ou des crédits épuisés. */
function SubscriptionBanner({ orgId, width }: { orgId: string; width: string }) {
  const { t } = useTranslation();
  const { data: sub } = useQuery(subscriptionQuery(orgId));
  const [now] = useState(() => Date.now());
  if (!sub) return null;
  let text = "";
  let tone = "bg-sky-50 text-sky-900";
  if (sub.status === "expired") {
    text = t("billing.banner.expired");
    tone = "bg-red-50 text-red-900";
  } else if (sub.status === "trialing" && sub.trial_ends_at) {
    const days = Math.max(0, Math.ceil((Date.parse(sub.trial_ends_at) - now) / 86_400_000));
    text = t("billing.banner.trial", { count: days });
  } else if (sub.cycle === "usage" && sub.credits === 0) {
    text = t("billing.banner.noCredits");
    tone = "bg-amber-50 text-amber-900";
  }
  if (!text) return null;
  return (
    <div className={tone}>
      <div className={`mx-auto flex ${width} flex-wrap items-center gap-3 px-4 py-2 text-sm`}>
        <span>{text}</span>
        <Link
          to="/orgs/$orgId/billing"
          params={{ orgId }}
          className="font-medium underline underline-offset-2"
        >
          {t("billing.banner.action")}
        </Link>
      </div>
    </div>
  );
}
