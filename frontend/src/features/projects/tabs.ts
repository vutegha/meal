export const PROJECT_TABS = [
  "dashboard",
  "logframe",
  "budget",
  "indicators",
  "tor",
  "execution",
  "reports",
  "feedback",
  "lessons",
  "documents",
] as const;
export type ProjectTab = (typeof PROJECT_TABS)[number];
