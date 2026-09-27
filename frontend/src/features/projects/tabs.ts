export const PROJECT_TABS = ["logframe", "budget", "indicators", "documents"] as const;
export type ProjectTab = (typeof PROJECT_TABS)[number];
