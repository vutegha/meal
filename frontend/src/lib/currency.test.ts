import { describe, expect, it } from "vitest";

import { rateOn } from "./currency";

const rates = [
  { currency: "CDF", rate: "0.0004", valid_from: "2026-03-01" },
  { currency: "CDF", rate: "0.00035", valid_from: "2026-01-01" },
  { currency: "USD", rate: "0.92", valid_from: "2026-01-01" },
];

describe("rateOn", () => {
  it("prend le taux en vigueur à la date", () => {
    expect(rateOn(rates, "CDF", "2026-02-15")).toBe("0.00035");
    expect(rateOn(rates, "CDF", "2026-03-01")).toBe("0.0004");
    expect(rateOn(rates, "CDF", "2025-12-31")).toBeUndefined();
    expect(rateOn(rates, "EUR", "2026-03-01")).toBeUndefined();
  });
});
