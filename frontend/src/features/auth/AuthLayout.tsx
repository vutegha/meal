import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

export function AuthLayout({ title, children }: { title: string; children: ReactNode }) {
  const { t } = useTranslation();
  return (
    <main className="flex min-h-screen items-center justify-center px-4 py-10">
      <div className="w-full max-w-sm space-y-6">
        <div className="text-center">
          <p className="text-2xl font-bold text-brand-700">{t("app.name")}</p>
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
