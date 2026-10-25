import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { buttonVariants } from "@/components/ui/button";
import { type Cycle, FEATURES } from "@/lib/billing";
import { catalogQuery } from "@/lib/queries";
import { cn } from "@/lib/utils";

import { CycleToggle, PlanCard } from "./plans";
import { SectionTitle, SiteLayout } from "./SiteLayout";

const FAQ = ["credit", "trial", "switch", "cancel", "currency"] as const;

export function PricingPage() {
  const { t } = useTranslation();
  const [cycle, setCycle] = useState<Cycle>("monthly");
  const { data: catalog, error } = useQuery(catalogQuery);
  const plans = catalog?.plans ?? [];

  return (
    <SiteLayout>
      <section className="bg-gradient-to-b from-brand-50 to-white px-4 pt-14 pb-10">
        <div className="mx-auto max-w-3xl text-center">
          <h1 className="text-3xl font-bold tracking-tight text-slate-900 sm:text-4xl">
            {t("site.pricing.title")}
          </h1>
          <p className="mt-4 text-lg text-slate-600">{t("site.pricing.subtitle")}</p>
          <div className="mt-8">
            <CycleToggle value={cycle} onChange={setCycle} />
          </div>
        </div>
      </section>

      <section className="mx-auto max-w-6xl px-4 pb-16">
        {error && (
          <p role="alert" className="text-center text-sm text-red-700">
            {t("common.error")}
          </p>
        )}
        {!catalog && !error && <p className="text-center text-slate-500">{t("common.loading")}</p>}
        <div className="grid gap-6 md:grid-cols-3">
          {catalog &&
            plans.map((plan, index) => (
              <PlanCard
                key={plan.id}
                plan={plan}
                previous={index > 0 ? plans[index - 1] : undefined}
                cycle={cycle}
                catalog={catalog}
                highlighted={plan.id === "team"}
                action={
                  <Link
                    to="/register"
                    search={{ type: plan.account_type, plan: plan.id, cycle }}
                    className={cn(
                      buttonVariants({
                        variant: plan.id === "team" ? "default" : "outline",
                        size: "lg",
                      }),
                      "w-full",
                    )}
                  >
                    {t("site.pricing.choose", { plan: t(`billing.plans.${plan.id}`) })}
                  </Link>
                }
              />
            ))}
        </div>
      </section>

      {catalog && (
        <section className="bg-slate-50 px-4 py-16">
          <SectionTitle title={t("site.pricing.compareTitle")} />
          <div className="mx-auto mt-8 max-w-5xl overflow-x-auto rounded-xl border border-slate-200 bg-white">
            <table className="w-full min-w-[36rem] text-sm">
              <thead>
                <tr className="border-b border-slate-200 text-left">
                  <th className="p-3 font-medium text-slate-500">{t("site.features.feature")}</th>
                  {plans.map((plan) => (
                    <th key={plan.id} className="p-3 text-center font-semibold text-slate-900">
                      {t(`billing.plans.${plan.id}`)}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {(["projects", "members", "ai"] as const).map((limit) => (
                  <tr key={limit} className="border-b border-slate-100">
                    <th scope="row" className="p-3 text-left font-normal text-slate-700">
                      {t(`site.pricing.limits.${limit}`)}
                    </th>
                    {plans.map((plan) => {
                      const value =
                        limit === "ai" ? plan.limits.monthly_credits : plan.limits[limit];
                      return (
                        <td key={plan.id} className="p-3 text-center text-slate-900">
                          {value ?? t("site.pricing.unlimited")}
                        </td>
                      );
                    })}
                  </tr>
                ))}
                {FEATURES.map((feature) => (
                  <tr key={feature} className="border-b border-slate-100 last:border-0">
                    <th scope="row" className="p-3 text-left font-normal text-slate-700">
                      {t(`billing.features.${feature}`)}
                    </th>
                    {plans.map((plan) => {
                      const ok = plan.features.includes(feature);
                      return (
                        <td key={plan.id} className="p-3 text-center">
                          <span
                            className={ok ? "font-bold text-brand-600" : "text-slate-300"}
                            aria-label={t(
                              ok ? "site.pricing.included" : "site.pricing.notIncluded",
                            )}
                          >
                            {ok ? "✓" : "–"}
                          </span>
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      <section className="px-4 py-16">
        <SectionTitle title={t("site.pricing.faqTitle")} />
        <div className="mx-auto mt-8 max-w-3xl divide-y divide-slate-200 rounded-xl border border-slate-200">
          {FAQ.map((key) => (
            <details key={key} className="group p-5">
              <summary className="cursor-pointer list-none font-medium text-slate-900 marker:hidden">
                <span className="mr-2 inline-block text-brand-600 transition group-open:rotate-90">
                  ›
                </span>
                {t(`site.pricing.faq.${key}.q`)}
              </summary>
              <p className="mt-3 pl-5 text-sm text-slate-600">{t(`site.pricing.faq.${key}.a`)}</p>
            </details>
          ))}
        </div>
      </section>
    </SiteLayout>
  );
}
