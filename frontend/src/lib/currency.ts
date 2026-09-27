import type { ExchangeRate } from "./api";

/** Taux du projet en vigueur à une date (le plus récent dont la date de début la précède). */
export function rateOn(rates: ExchangeRate[], currency: string, on: string): string | undefined {
  return rates
    .filter((r) => r.currency === currency && r.valid_from <= on)
    .sort((a, b) => a.valid_from.localeCompare(b.valid_from))
    .at(-1)?.rate;
}
