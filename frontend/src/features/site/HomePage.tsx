import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { useTranslation } from "react-i18next";

import { buttonVariants } from "@/components/ui/button";
import { catalogQuery } from "@/lib/queries";
import { cn } from "@/lib/utils";

import { SectionTitle, SiteLayout } from "./SiteLayout";

const STEPS = ["plan", "prepare", "collect", "report"] as const;
const TRUST = ["validation", "offline", "security"] as const;

export function HomePage() {
  const { t } = useTranslation();
  const { data: catalog } = useQuery(catalogQuery);
  const trialDays = catalog?.trial_days ?? 14;

  return (
    <SiteLayout>
      <section className="overflow-hidden bg-gradient-to-b from-brand-50 via-white to-white px-4 pt-16 pb-12">
        <div className="mx-auto grid max-w-6xl items-center gap-12 lg:grid-cols-[1fr_1.1fr]">
          <div>
            <p className="text-sm font-semibold tracking-wide text-brand-700 uppercase">
              {t("site.home.eyebrow")}
            </p>
            <h1 className="mt-3 text-4xl font-bold tracking-tight text-slate-900 sm:text-5xl">
              {t("site.home.title")}
            </h1>
            <p className="mt-5 text-lg text-slate-600">{t("site.home.subtitle")}</p>
            <div className="mt-8 flex flex-wrap gap-3">
              <Link to="/register" className={buttonVariants({ size: "lg" })}>
                {t("site.home.ctaPrimary")}
              </Link>
              <Link to="/tarifs" className={buttonVariants({ size: "lg", variant: "outline" })}>
                {t("site.home.ctaSecondary")}
              </Link>
            </div>
            <p className="mt-3 text-sm text-slate-500">
              {t("site.home.trialNote", { days: trialDays })}
            </p>
          </div>
          <div className="rounded-xl border border-slate-200 bg-white p-2 shadow-xl shadow-brand-900/10">
            <img
              src="/site/apercu.webp"
              alt={t("site.home.previewAlt")}
              className="w-full rounded-lg"
              width={1280}
              height={800}
            />
          </div>
        </div>
      </section>

      <section className="px-4 py-16">
        <SectionTitle title={t("site.home.cycleTitle")} intro={t("site.home.cycleIntro")} />
        <ol className="mx-auto mt-10 grid max-w-6xl gap-6 sm:grid-cols-2 lg:grid-cols-4">
          {STEPS.map((step, index) => (
            <li key={step} className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
              <span className="flex size-9 items-center justify-center rounded-full bg-brand-700 font-semibold text-white">
                {index + 1}
              </span>
              <h3 className="mt-4 text-lg font-semibold text-slate-900">
                {t(`site.home.steps.${step}.title`)}
              </h3>
              <p className="mt-2 text-sm text-slate-600">{t(`site.home.steps.${step}.text`)}</p>
            </li>
          ))}
        </ol>
      </section>

      <section className="bg-brand-900 px-4 py-16 text-white">
        <div className="mx-auto max-w-6xl">
          <h2 className="text-center text-2xl font-bold tracking-tight sm:text-3xl">
            {t("site.home.trustTitle")}
          </h2>
          <div className="mt-10 grid gap-8 md:grid-cols-3">
            {TRUST.map((key) => (
              <div key={key}>
                <h3 className="text-lg font-semibold">{t(`site.home.trust.${key}.title`)}</h3>
                <p className="mt-2 text-sm text-brand-100">{t(`site.home.trust.${key}.text`)}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="px-4 py-16">
        <SectionTitle title={t("site.home.audienceTitle")} />
        <div className="mx-auto mt-10 grid max-w-4xl gap-6 md:grid-cols-2">
          {(["individual", "organization"] as const).map((type) => (
            <div
              key={type}
              className={cn(
                "flex flex-col rounded-xl border p-6",
                type === "organization" ? "border-brand-600 bg-brand-50" : "border-slate-200",
              )}
            >
              <h3 className="text-lg font-semibold text-slate-900">
                {t(`site.home.${type}.title`)}
              </h3>
              <p className="mt-2 flex-1 text-sm text-slate-600">{t(`site.home.${type}.text`)}</p>
              <Link
                to="/register"
                search={{ type }}
                className={cn(buttonVariants({ variant: "outline" }), "mt-5 self-start")}
              >
                {t("site.nav.signup")}
              </Link>
            </div>
          ))}
        </div>
        <p className="mt-6 text-center">
          <Link
            to="/fonctionnalites"
            className="text-sm font-medium text-brand-700 hover:underline"
          >
            {t("site.home.compare")} →
          </Link>
        </p>
      </section>

      <section className="px-4 pb-20">
        <div className="mx-auto max-w-4xl rounded-2xl bg-brand-700 px-6 py-12 text-center text-white">
          <h2 className="text-2xl font-bold tracking-tight">{t("site.home.finalTitle")}</h2>
          <p className="mx-auto mt-3 max-w-xl text-brand-50">{t("site.home.finalText")}</p>
          <Link
            to="/register"
            className={cn(
              buttonVariants({ size: "lg", variant: "secondary" }),
              "mt-6 bg-white text-brand-800",
            )}
          >
            {t("site.home.ctaPrimary")}
          </Link>
        </div>
      </section>
    </SiteLayout>
  );
}
