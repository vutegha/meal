export const PROJECT_TABS = [
  "logframe",
  "budget",
  "indicators",
  "tor",
  "execution",
  "documents",
] as const;
export type ProjectTab = (typeof PROJECT_TABS)[number];
