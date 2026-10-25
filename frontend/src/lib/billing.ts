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
export type CheckoutMethod = S["CheckoutIn"]["method"];
export type PaymentStatus = S["PaymentOut"]["status"];
export type PaymentMethod = S["PaymentOut"]["method"];
export const CHECKOUT_METHODS: CheckoutMethod[] = ["online", "mobile_money", "bank_transfer"];
export const PAYMENT_STATUS_TONE = {
  pending: "warning",
  paid: "success",
  canceled: "neutral",
  failed: "danger",
  refunded: "info",
} as const;

export const CYCLES: Cycle[] = ["monthly", "annual", "usage"];

/** Fonctions des formules, dans l'ordre d'affichage : celles de toutes les formules, puis celles
 * qu'ajoute Équipe, puis celles qu'ajoute Institution (le serveur fait foi, `PLANS`). */
export const FEATURES = [
  "projects",
  "ai_extraction",
  "tor",
  "offline_collection",
  "reports",
  "dashboard",
  "accountability",
  "exports",
  "forms",
  "periodic_reports",
  "team",
  "templates",
  "org_lessons",
  "audit",
  "messaging",
] as const;
export type Feature = (typeof FEATURES)[number];

export const hasFeature = (org: Organization | undefined, feature: Feature) =>
  !!org && org.features.includes(feature);

/** La formule la moins chère qui ouvre la fonction (le catalogue est classé par prix). */
export const lowestPlanWith = (catalog: Catalog | undefined, feature: Feature) =>
  catalog?.plans.find((plan) => plan.features.includes(feature));

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
  cancelPayment: (orgId: string, paymentId: string) =>
    unwrap(
      client.POST(`${ORG}/payments/{payment_id}/cancel`, {
        params: { path: { org_id: orgId, payment_id: paymentId } },
      }),
    ),
  /** Chemin du reçu PDF, pour `download` (relatif à /api/v1). */
  receiptPath: (orgId: string, paymentId: string) =>
    `/orgs/${orgId}/billing/payments/${paymentId}/receipt.pdf`,
};

export type AdminSubscriptions = S["AdminSubscriptions"];
export type AdminRow = S["AdminSubscriptionRow"];
export type AdminUpdate = S["AdminSubscriptionUpdate"];
export type AdminFilters = { q?: string; status?: string; plan?: string };
export type AdminPayments = S["AdminPayments"];
export type AdminPayment = S["AdminPaymentRow"];
export type AdminPaymentRecord = S["AdminPaymentRecord"];

export const adminApi = {
  subscriptions: (filters: AdminFilters) =>
    unwrap(client.GET("/api/v1/admin/subscriptions", { params: { query: filters } })),
  update: (orgId: string, body: AdminUpdate) =>
    unwrap(
      client.PATCH("/api/v1/admin/subscriptions/{org_id}", {
        params: { path: { org_id: orgId } },
        body,
      }),
    ),
  payments: (filters: { q?: string; status?: string }) =>
    unwrap(client.GET("/api/v1/admin/payments", { params: { query: filters } })),
  confirm: (paymentId: string, note: string) =>
    unwrap(
      client.POST("/api/v1/admin/payments/{payment_id}/confirm", {
        params: { path: { payment_id: paymentId } },
        body: { note },
      }),
    ),
  refund: (paymentId: string, note: string) =>
    unwrap(
      client.POST("/api/v1/admin/payments/{payment_id}/refund", {
        params: { path: { payment_id: paymentId } },
        body: { note },
      }),
    ),
  record: (orgId: string, body: AdminPaymentRecord) =>
    unwrap(
      client.POST("/api/v1/admin/subscriptions/{org_id}/payments", {
        params: { path: { org_id: orgId } },
        body,
      }),
    ),
  receiptPath: (paymentId: string) => `/admin/payments/${paymentId}/receipt.pdf`,
};
