import type { Organization } from "./api";
import { client, unwrap } from "./client";
import type { components } from "./schema.gen";

/** Formules, abonnement et paiements, par le client généré depuis l'OpenAPI. */

type S = components["schemas"];
export type Catalog = S["Catalog"];
export type Plan = S["PlanOut"];
export type Subscription = S["SubscriptionOut"];
export type Payment = S["PaymentOut"];
export type Cycle = S["CheckoutIn"]["cycle"];

export const CYCLES: Cycle[] = ["monthly", "annual", "usage"];

/** Fonctions de chaque formule, dans l'ordre d'affichage ; les quatre dernières sont réservées
 * aux organisations. */
export const FEATURES = [
  "projects",
  "ai_extraction",
  "tor",
  "offline_collection",
  "reports",
  "dashboard",
  "accountability",
  "periodic_reports",
  "exports",
  "team",
  "templates",
  "org_lessons",
  "audit",
] as const;
export type Feature = (typeof FEATURES)[number];

export const hasFeature = (org: Organization | undefined, feature: Feature) =>
  !!org && org.features.includes(feature);

export function formatPrice(value: string | number, currency: string, language = "fr"): string {
  const amount = Number(value);
  return new Intl.NumberFormat(language, {
    style: "currency",
    currency,
    minimumFractionDigits: Number.isInteger(amount) ? 0 : 2,
    maximumFractionDigits: 2,
  }).format(amount);
}

const ORG = "/api/v1/orgs/{org_id}/billing";

export const billingApi = {
  catalog: () => unwrap(client.GET("/api/v1/billing/plans")),
  get: (orgId: string) => unwrap(client.GET(ORG, { params: { path: { org_id: orgId } } })),
  payments: (orgId: string) =>
    unwrap(client.GET(`${ORG}/payments`, { params: { path: { org_id: orgId } } })),
  checkout: (orgId: string, body: S["CheckoutIn"]) =>
    unwrap(client.POST(`${ORG}/checkout`, { params: { path: { org_id: orgId } }, body })),
  cancel: (orgId: string) =>
    unwrap(client.POST(`${ORG}/cancel`, { params: { path: { org_id: orgId } } })),
};
