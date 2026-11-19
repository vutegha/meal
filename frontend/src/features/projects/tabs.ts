import type { Feature } from "@/lib/billing";

export const PROJECT_TABS = [
  "dashboard",
  "logframe",
  "schedule",
  "budget",
  "indicators",
  "tor",
  "execution",
  "forms",
  "reports",
  "feedback",
  "lessons",
  "documents",
] as const;
export type ProjectTab = (typeof PROJECT_TABS)[number];

/** Regroupement des onglets dans le menu vertical du projet. */
export const TAB_GROUPS: { key: string; tabs: ProjectTab[] }[] = [
  { key: "planning", tabs: ["dashboard", "logframe", "schedule", "budget", "indicators"] },
  { key: "implementation", tabs: ["tor", "execution", "forms"] },
  { key: "learning", tabs: ["reports", "feedback", "lessons"] },
  { key: "sources", tabs: ["documents"] },
];

/** Onglets ouverts par une formule supérieure : visibles, avec un cadenas, et une invitation à
 * changer de formule à la place du contenu. */
export const TAB_FEATURES: Partial<Record<ProjectTab, Feature>> = {
  forms: "forms",
  reports: "periodic_reports",
};
