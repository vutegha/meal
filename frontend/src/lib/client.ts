import createClient from "openapi-fetch";

import { ApiError, authFetch, detailMessage } from "./api";
import type { paths } from "./schema.gen";

/**
 * Client typé, généré depuis l'OpenAPI de l'API (`npm run api:generate`) : chemins,
 * paramètres et corps sont vérifiés par TypeScript. Les nouveaux modules l'utilisent.
 */
export const client = createClient<paths>({ fetch: authFetch });

/** Données de la réponse, ou ApiError avec le message du serveur. */
export async function unwrap<T>(
  call: Promise<{ data?: T; error?: unknown; response: Response }>,
): Promise<T> {
  const { data, error, response } = await call;
  if (!response.ok) throw new ApiError(response.status, detailMessage(error, response.statusText));
  return data as T;
}
