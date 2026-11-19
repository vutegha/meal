import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { Card } from "@/components/ui";
import { buttonVariants } from "@/components/ui/button";
import { type Feature, hasFeature, lowestPlanWith } from "@/lib/billing";
import { catalogQuery } from "@/lib/queries";

import { useCurrentOrg } from "./useCurrentOrg";

/** Affiche le contenu si la formule de l'espace ouvre la fonction, sinon une invitation à passer
 * à la formule qui l'ouvre (l'API refuse de toute façon avec 402). `inline` : une simple ligne,
 * pour une partie de page. */
export function FeatureGate({
  feature,
  inline = false,
  children,
}: {
  feature: Feature;
  inline?: boolean;
  children: ReactNode;
}) {
  const { t } = useTranslation();
  const { orgId, org } = useCurrentOrg();
  const { data: catalog } = useQuery(catalogQuery);
  if (hasFeature(org, feature)) return <>{children}</>;
  const lowest = lowestPlanWith(catalog, feature);
  const plan = lowest ? t(`billing.plans.${lowest.id}`) : "";
  const name = t(`billing.features.${feature}`);
  const link = (className: string) => (
    <Link to="/orgs/$orgId/billing" params={{ orgId }} className={className}>
      {t("billing.locked.action")}
    </Link>
  );
  if (inline)
    return (
      <p className="rounded-md bg-slate-50 px-3 py-2 text-sm text-slate-600">
        <span aria-hidden>🔒 </span>
        {t("billing.locked.inline", { feature: name, plan })}{" "}
        {link("font-medium text-brand-700 underline underline-offset-2")}
      </p>
    );
  return (
    <Card>
      <p className="text-xs font-semibold tracking-wide text-brand-700 uppercase">
        {t("billing.locked.eyebrow", { plan })}
      </p>
      <h1 className="mt-1 text-lg font-semibold">{name}</h1>
      <p className="mt-2 max-w-2xl text-sm text-slate-600">
        {t(`billing.locked.why.${feature}`, { defaultValue: "" })}{" "}
        {t("billing.locked.text", { plan })}
      </p>
      {link(buttonVariants({ className: "mt-4" }))}
    </Card>
  );
}
