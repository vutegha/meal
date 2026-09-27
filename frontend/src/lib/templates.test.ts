import { expect, it } from "vitest";

import { move, sectionKey, startTemplate } from "./templates";

it("derives stable section keys from titles", () => {
  expect(sectionKey("Rôles et responsabilités")).toBe("roles_et_responsabilites");
  expect(sectionKey("Visibilité", ["visibilite"])).toBe("visibilite_2");
  expect(sectionKey("!!!")).toBe("section");
});

it("moves sections without going out of bounds", () => {
  expect(move(["a", "b", "c"], 1, -1)).toEqual(["b", "a", "c"]);
  expect(move(["a", "b"], 1, 1)).toEqual(["a", "b"]);
});

it("starts a template from the built-in sections", () => {
  const builtin = {
    tor: [{ key: "budget", title: "Budget", computed: true }],
    report: [],
    periodic: [],
  };
  expect(startTemplate("tor", builtin).sections).toEqual([
    { key: "budget", title: "Budget", guidance: "" },
  ]);
});
