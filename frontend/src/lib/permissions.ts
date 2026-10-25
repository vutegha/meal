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

const everyone = (role: Role | undefined) => !!role;

/** Opérations présentées dans le tableau des droits, dans l'ordre d'affichage. */
export const OPERATIONS = [
  { key: "view", allowed: everyone },
  { key: "record", allowed: permissions.recordValues },
  { key: "plan", allowed: permissions.plan },
  { key: "budget", allowed: permissions.editBudget },
  { key: "projects", allowed: permissions.manageProjects },
  { key: "sensitive", allowed: permissions.manageProjects },
  { key: "org", allowed: permissions.manageOrg },
] as const;
