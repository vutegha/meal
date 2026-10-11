import { Link } from "@tanstack/react-router";
import { type ReactNode, useState } from "react";
import { useTranslation } from "react-i18next";

import { buttonVariants } from "@/components/ui/button";
import { tokenStore } from "@/lib/tokens";
import { cn } from "@/lib/utils";

const navLink =
  "rounded-md px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100 " +
  "[&.active]:text-brand-800";

/** Gabarit des pages publiques : présentation, fonctionnalités, tarifs. */
export function SiteLayout({ children }: { children: ReactNode }) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const signedIn = !!tokenStore.get();

  const links = (
    <>
      <Link to="/fonctionnalites" className={navLink} onClick={() => setOpen(false)}>
        {t("site.nav.features")}
      </Link>
      <Link to="/tarifs" className={navLink} onClick={() => setOpen(false)}>
        {t("site.nav.pricing")}
      </Link>
    </>
  );
  const account = signedIn ? (
    <Link to="/" className={buttonVariants()}>
      {t("site.nav.openApp")}
    </Link>
  ) : (
    <>
      <Link to="/login" className={navLink}>
        {t("site.nav.login")}
      </Link>
      <Link to="/register" className={buttonVariants()}>
        {t("site.nav.signup")}
      </Link>
    </>
  );

  return (
    <div className="flex min-h-screen flex-col bg-white">
      <header className="sticky top-0 z-20 border-b border-slate-200 bg-white/90 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center gap-2 px-4 py-3">
          <Link to="/" className="mr-4 flex items-center gap-2 text-lg font-bold text-brand-700">
            <img src="/favicon.svg" alt="" className="size-7" />
            {t("app.name")}
          </Link>
          <nav className="hidden items-center gap-1 md:flex">{links}</nav>
          <div className="ml-auto hidden items-center gap-1 md:flex">{account}</div>
          <button
            type="button"
            className={cn(buttonVariants({ variant: "outline" }), "ml-auto md:hidden")}
            aria-expanded={open}
            onClick={() => setOpen((v) => !v)}
          >
            {t("site.nav.menu")}
          </button>
        </div>
        {open && (
          <nav className="flex flex-col gap-1 border-t border-slate-200 px-4 py-3 md:hidden">
            {links}
            <div className="mt-2 flex flex-wrap gap-2">{account}</div>
          </nav>
        )}
      </header>
      <main className="flex-1">{children}</main>
      <footer className="border-t border-slate-200 bg-slate-50">
        <div className="mx-auto grid max-w-6xl gap-8 px-4 py-10 text-sm sm:grid-cols-[2fr_1fr_1fr]">
          <div className="space-y-2">
            <p className="text-base font-bold text-brand-700">{t("app.name")}</p>
            <p className="max-w-sm text-slate-600">{t("site.footer.tagline")}</p>
            <p className="text-slate-500">
              {t("site.footer.rights", { year: new Date().getFullYear() })}
            </p>
          </div>
          <div className="space-y-2">
            <p className="font-semibold text-slate-900">{t("site.footer.product")}</p>
            <ul className="space-y-1 text-slate-600">
              <li>
                <Link to="/fonctionnalites" className="hover:text-brand-700">
                  {t("site.nav.features")}
                </Link>
              </li>
              <li>
                <Link to="/tarifs" className="hover:text-brand-700">
                  {t("site.nav.pricing")}
                </Link>
              </li>
            </ul>
          </div>
          <div className="space-y-2">
            <p className="font-semibold text-slate-900">{t("site.footer.account")}</p>
            <ul className="space-y-1 text-slate-600">
              <li>
                <Link to="/login" className="hover:text-brand-700">
                  {t("site.nav.login")}
                </Link>
              </li>
              <li>
                <Link to="/register" className="hover:text-brand-700">
                  {t("site.nav.signup")}
                </Link>
              </li>
            </ul>
          </div>
        </div>
      </footer>
    </div>
  );
}

export function SectionTitle({ title, intro }: { title: string; intro?: string }) {
  return (
    <div className="mx-auto max-w-2xl text-center">
      <h2 className="text-2xl font-bold tracking-tight text-slate-900 sm:text-3xl">{title}</h2>
      {intro && <p className="mt-3 text-slate-600">{intro}</p>}
    </div>
  );
}
