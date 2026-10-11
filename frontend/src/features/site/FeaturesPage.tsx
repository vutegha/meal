import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { useTranslation } from "react-i18next";

import { Badge } from "@/components/ui";
import { buttonVariants } from "@/components/ui/button";
import { FEATURES } from "@/lib/billing";
import { catalogQuery } from "@/lib/queries";

import { SectionTitle, SiteLayout } from "./SiteLayout";

const GROUPS = {
  plan: ["extraction", "citations", "logframe", "indicators", "budget", "gantt"],
  execute: ["tor", "offline", "forms", "evidence", "search"],
  report: ["narrative", "dashboard", "periodic", "feedback", "exports"],
  team: ["roles", "templates", "lessons", "audit"],
} as const;

export function FeaturesPage() {
  const { t } = useTranslation();
  const { data: catalog } = useQuery(catalogQuery);
  const featuresOf = (type: "individual" | "organization") =>
    new Set(catalog?.plans.filter((p) => p.account_type === type).flatMap((p) => p.features));
  const individual = featuresOf("individual");
  const organization = featuresOf("organization");

  return (
    <SiteLayout>
      <section className="bg-gradient-to-b from-brand-50 to-white px-4 pt-14 pb-10">
        <div className="mx-auto max-w-3xl text-center">
          <h1 className="text-3xl font-bold tracking-tight text-slate-900 sm:text-4xl">
            {t("site.features.title")}
          </h1>
          <p className="mt-4 text-lg text-slate-600">{t("site.features.intro")}</p>
        </div>
      </section>

      <section className="mx-auto grid max-w-6xl gap-6 px-4 pb-16 md:grid-cols-2">
        {Object.entries(GROUPS).map(([group, items]) => (
          <div key={group} className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-lg font-semibold text-slate-900">
                {t(`site.features.groups.${group}.title`)}
              </h2>
              {group === "team" && <Badge tone="brand">{t("site.features.orgOnly")}</Badge>}
            </div>
            <ul className="mt-4 space-y-3 text-sm text-slate-700">
              {items.map((item) => (
                <li key={item} className="flex gap-2">
                  <span aria-hidden className="font-bold text-brand-600">
                    ✓
                  </span>
                  <span>{t(`site.features.groups.${group}.items.${item}`)}</span>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </section>

      {catalog && (
        <section className="bg-slate-50 px-4 py-16">
          <SectionTitle title={t("site.features.tableTitle")} />
          <div className="mx-auto mt-8 max-w-3xl overflow-x-auto rounded-xl border border-slate-200 bg-white">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-200 text-left">
                  <th className="p-3 font-medium text-slate-500">{t("site.features.feature")}</th>
                  <th className="p-3 text-center font-semibold">{t("auth.individual")}</th>
                  <th className="p-3 text-center font-semibold">{t("auth.organization")}</th>
                </tr>
              </thead>
              <tbody>
                {FEATURES.map((feature) => (
                  <tr key={feature} className="border-b border-slate-100 last:border-0">
                    <th scope="row" className="p-3 text-left font-normal text-slate-700">
                      {t(`billing.features.${feature}`)}
                    </th>
                    {[individual, organization].map((set, i) => (
                      <td key={i} className="p-3 text-center">
                        {set.has(feature) ? (
                          <span
                            className="font-bold text-brand-600"
                            aria-label={t("site.pricing.included")}
                          >
                            ✓
                          </span>
                        ) : (
                          <span
                            className="text-slate-300"
                            aria-label={t("site.pricing.notIncluded")}
                          >
                            –
                          </span>
                        )}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="mt-8 text-center">
            <Link to="/tarifs" className={buttonVariants({ size: "lg" })}>
              {t("site.home.ctaSecondary")}
            </Link>
          </p>
        </section>
      )}
    </SiteLayout>
  );
}
