import { Link } from "@tanstack/react-router";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { Card } from "@/components/ui";
import { buttonVariants } from "@/components/ui/button";
import { type Feature, hasFeature } from "@/lib/billing";

import { useCurrentOrg } from "./useCurrentOrg";

/** Affiche la page si la formule de l'espace ouvre la fonction, une invitation à changer de
 * formule sinon (l'API refuse de toute façon avec 402). */
export function FeatureGate({ feature, children }: { feature: Feature; children: ReactNode }) {
  const { t } = useTranslation();
  const { orgId, org } = useCurrentOrg();
  if (hasFeature(org, feature)) return <>{children}</>;
  return (
    <Card>
      <h1 className="text-lg font-semibold">{t("billing.locked.title")}</h1>
      <p className="mt-2 max-w-2xl text-sm text-slate-600">{t("billing.locked.text")}</p>
      <Link
        to="/orgs/$orgId/billing"
        params={{ orgId }}
        className={buttonVariants({ className: "mt-4" })}
      >
        {t("billing.locked.action")}
      </Link>
    </Card>
  );
}
