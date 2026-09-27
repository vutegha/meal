export const PROJECT_TABS = ["logframe", "budget", "indicators"] as const;
export type ProjectTab = (typeof PROJECT_TABS)[number];
