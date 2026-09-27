import type { Role } from "./api";

const can =
  (...roles: Role[]) =>
  (role: Role | undefined) =>
    !!role && roles.includes(role);

export const permissions = {
  manageOrg: can("admin"),
  manageProjects: can("admin", "project_manager"),
  plan: can("admin", "project_manager", "meal_officer"),
  editBudget: can("admin", "project_manager", "finance"),
  recordValues: can("admin", "project_manager", "meal_officer", "field_agent"),
};
