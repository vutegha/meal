import { Link } from "@tanstack/react-router";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { cn } from "@/lib/utils";

export function AuthLayout({
  title,
  wide,
  children,
}: {
  title: string;
  wide?: boolean;
  children: ReactNode;
}) {
  const { t } = useTranslation();
  return (
    <main className="flex min-h-screen items-center justify-center px-4 py-10">
      <div className={cn("w-full space-y-6", wide ? "max-w-lg" : "max-w-sm")}>
        <div className="text-center">
          <Link to="/" className="text-2xl font-bold text-brand-700">
            {t("app.name")}
          </Link>
          <p className="text-sm text-slate-500">{t("app.tagline")}</p>
        </div>
        <div className="rounded-lg border border-slate-200 bg-white p-6 shadow-sm">
          <h1 className="mb-5 text-lg font-semibold">{title}</h1>
          {children}
        </div>
      </div>
    </main>
  );
}
