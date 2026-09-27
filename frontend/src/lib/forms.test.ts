import { describe, expect, it } from "vitest";

import type { FormField } from "./api";
import { blankField, formatAnswer, toAnswers, withKeys } from "./forms";

const field = (patch: Partial<FormField>): FormField => ({ ...blankField([]), ...patch });

describe("withKeys", () => {
  it("dérive des clés uniques des libellés et retire les choix inutiles", () => {
    const fields = withKeys(
      [
        field({ label: "Ménage satisfait ?", type: "yesno", options: ["a"] }),
        field({ label: "Ménage satisfait ?", type: "select", options: ["Oui", "Non"] }),
      ],
      false,
    );
    expect(fields.map((f) => f.key)).toEqual(["menage_satisfait", "menage_satisfait_2"]);
    expect(fields[0].options).toEqual([]);
    expect(fields[1].options).toEqual(["Oui", "Non"]);
  });

  it("garde les clés d'un formulaire qui a déjà des réponses", () => {
    const fields = [field({ key: "q1", label: "Autre libellé" })];
    expect(withKeys(fields, true)[0].key).toBe("q1");
  });
});

describe("toAnswers", () => {
  it("convertit les nombres, garde l'ordre des choix et omet les vides", () => {
    const fields = [
      field({ key: "n", type: "integer" }),
      field({ key: "m", type: "number" }),
      field({ key: "c", type: "multiselect", options: ["Riz", "Huile", "Sel"] }),
      field({ key: "y", type: "yesno" }),
      field({ key: "t", type: "text" }),
      field({ key: "vide", type: "multiselect", options: ["a", "b"] }),
    ];
    expect(
      toAnswers(fields, { n: "4", m: "2,5", c: ["Sel", "Riz"], y: false, t: "  ", vide: [] }),
    ).toEqual({ n: 4, m: 2.5, c: ["Riz", "Sel"], y: false });
  });
});

describe("formatAnswer", () => {
  it("affiche oui/non, listes et nombres", () => {
    const yesNo = { yes: "Oui", no: "Non" };
    expect(formatAnswer(true, yesNo, "fr")).toBe("Oui");
    expect(formatAnswer(["a", "b"], yesNo, "fr")).toBe("a, b");
    expect(formatAnswer(1500, yesNo, "en")).toBe("1,500");
    expect(formatAnswer(undefined, yesNo, "fr")).toBe("");
  });
});
