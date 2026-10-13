import type { TFunction } from "i18next";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { Badge } from "@/components/ui";
import {
  type Catalog,
  type Cycle,
  CYCLES,
  type Feature,
  formatPrice,
  type Plan,
} from "@/lib/billing";
import { cn } from "@/lib/utils";

/** Bascule mensuel / annuel / à l'usage. */
export function CycleToggle({ value, onChange }: { value: Cycle; onChange: (c: Cycle) => void }) {
  const { t } = useTranslation();
  return (
    <div
      role="radiogroup"
      aria-label={t("billing.cycle")}
      className="inline-flex rounded-lg border border-slate-200 bg-slate-100 p-1"
    >
      {CYCLES.map((cycle) => (
        <button
          key={cycle}
          type="button"
          role="radio"
          aria-checked={value === cycle}
          onClick={() => onChange(cycle)}
          className={cn(
            "rounded-md px-3 py-1.5 text-sm font-medium text-slate-600 transition",
            value === cycle && "bg-white text-slate-900 shadow-sm",
          )}
        >
          {t(`site.pricing.cycles.${cycle}`)}
          {cycle === "annual" && (
            <span className="ml-1.5 rounded bg-brand-50 px-1.5 py-0.5 text-xs text-brand-800">
              {t("site.pricing.annualSaving")}
            </span>
          )}
        </button>
      ))}
    </div>
  );
}

export function PlanPrice({
  plan,
  cycle,
  catalog,
}: {
  plan: Plan;
  cycle: Cycle;
  catalog: Catalog;
}) {
  const { t, i18n } = useTranslation();
  const price = (value: string | number) => formatPrice(value, catalog.currency, i18n.language);
  const amount =
    cycle === "monthly"
      ? plan.prices.monthly
      : cycle === "annual"
        ? plan.prices.annual
        : plan.prices.credit;
  const unit = {
    monthly: t("site.pricing.perMonth"),
    annual: t("site.pricing.perYear"),
    usage: t("site.pricing.perCredit"),
  }[cycle];
  return (
    <div>
      <p className="flex items-baseline gap-1">
        <span className="text-3xl font-bold tracking-tight text-slate-900">{price(amount)}</span>
        <span className="text-sm text-slate-500">{unit}</span>
      </p>
      <p className="mt-1 min-h-5 text-xs text-slate-500">
        {cycle === "annual" &&
          t("site.pricing.annualEquivalent", { price: price(Number(plan.prices.annual) / 12) })}
        {cycle === "usage" &&
          t("site.pricing.usageNote", {
            packs: new Intl.ListFormat(i18n.language, { type: "disjunction" }).format(
              catalog.credit_packs.map(String),
            ),
          })}
      </p>
    </div>
  );
}

function limitLines(plan: Plan, cycle: Cycle, t: TFunction) {
  const { projects, members, monthly_credits } = plan.limits;
  return [
    projects === null
      ? t("site.pricing.projectsUnlimited")
      : t("site.pricing.projects", { count: projects }),
    members === null
      ? t("site.pricing.membersUnlimited")
      : members === 1
        ? t("site.pricing.membersOne")
        : t("site.pricing.members", { count: members }),
    cycle === "usage"
      ? t("site.pricing.creditsOnDemand")
      : t("site.pricing.monthlyCredits", { count: monthly_credits }),
  ];
}

function Check({ children, muted }: { children: ReactNode; muted?: boolean }) {
  return (
    <li className={cn("flex gap-2", muted && "text-slate-400")}>
      <span aria-hidden className={cn("font-bold", muted ? "text-slate-300" : "text-brand-600")}>
        {muted ? "–" : "✓"}
      </span>
      <span>{children}</span>
    </li>
  );
}

/** Carte d'une formule : prix selon le cycle, limites, fonctions ; le bouton est fourni. */
export function PlanCard({
  plan,
  previous,
  cycle,
  catalog,
  highlighted,
  selected,
  inApp,
  action,
}: {
  plan: Plan;
  /** Formule précédente dans la gamme : la carte n'en liste que les ajouts. */
  previous?: Plan;
  cycle: Cycle;
  catalog: Catalog;
  highlighted?: boolean;
  selected?: boolean;
  /** Dans l'espace (page Abonnement) : l'essai gratuit ne concerne que l'inscription. */
  inApp?: boolean;
  action: ReactNode;
}) {
  const { t } = useTranslation();
  const added = plan.features.filter((f) => !previous?.features.includes(f)) as Feature[];
  return (
    <article
      aria-label={t(`billing.plans.${plan.id}`)}
      className={cn(
        "flex flex-col rounded-xl border bg-white p-6 shadow-sm",
        highlighted ? "border-brand-600 ring-1 ring-brand-600" : "border-slate-200",
        selected && "border-brand-700 ring-2 ring-brand-700",
      )}
    >
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone={plan.account_type === "individual" ? "info" : "brand"}>
          {t(`billing.accountType.${plan.account_type}`)}
        </Badge>
      </div>
      <h3 className="mt-3 text-xl font-semibold text-slate-900">{t(`billing.plans.${plan.id}`)}</h3>
      <p className="mt-1 min-h-10 text-sm text-slate-600">{t(`billing.planTaglines.${plan.id}`)}</p>
      <div className="mt-4">
        <PlanPrice plan={plan} cycle={cycle} catalog={catalog} />
      </div>
      {!inApp && (
        <p className="mt-2 text-xs font-medium text-brand-800">
          {cycle === "usage"
            ? t("site.pricing.welcomeCredits", { count: catalog.welcome_credits })
            : t("site.pricing.trial", { days: catalog.trial_days })}
        </p>
      )}
      <div className="mt-5">{action}</div>
      <ul className="mt-6 space-y-2 text-sm text-slate-700">
        {limitLines(plan, cycle, t).map((line) => (
          <Check key={line}>{line}</Check>
        ))}
      </ul>
      <div className="mt-5 border-t border-slate-100 pt-5">
        {previous && (
          <p className="mb-2 text-sm font-medium text-slate-900">
            {t(added.length ? "site.pricing.allOf" : "site.pricing.sameAs", {
              plan: t(`billing.plans.${previous.id}`),
            })}
          </p>
        )}
        <ul className="space-y-2 text-sm text-slate-700">
          {added.map((feature) => (
            <Check key={feature}>{t(`billing.features.${feature}`)}</Check>
          ))}
        </ul>
      </div>
    </article>
  );
}
