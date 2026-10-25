import { describe, expect, it } from "vitest";

import { suggestCode } from "./codes";

describe("suggestCode", () => {
  it("continue la numérotation des frères en gardant leur préfixe", () => {
    expect(suggestCode("activity", "Produit 1.1", ["Activité 1.1.1", "Activité 1.1.5"])).toBe(
      "Activité 1.1.6",
    );
    expect(suggestCode("outcome", "OG", ["R1", "R2"])).toBe("R3");
    expect(suggestCode("output", "R1", ["Produit 1.10", "Produit 1.9"])).toBe("Produit 1.11");
  });

  it("dérive le premier enfant du numéro du parent", () => {
    expect(suggestCode("sub_activity", "Activité 1.1.1", [])).toBe("SA1.1.1.1");
    expect(suggestCode("activity", "R2.3", [])).toBe("A2.3.1");
    expect(suggestCode("outcome", "OG", [])).toBe("OS1");
  });

  it("numérote les objectifs généraux", () => {
    expect(suggestCode("goal", null, [])).toBe("OG");
    expect(suggestCode("goal", null, ["OG"])).toBe("OG2");
    expect(suggestCode("goal", null, ["OG1"])).toBe("OG2");
  });
});
