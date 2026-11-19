import { describe, expect, it } from "vitest";

import type { Indicator } from "./api";
import { filterIndicators, parseList } from "./indicators";

const indicator = (id: string, nodeId: string, name: string, extra: Partial<Indicator> = {}) =>
  ({
    id,
    node_id: nodeId,
    code: id,
    name,
    source_of_verification: "",
    disaggregations: [],
    ...extra,
  }) as Indicator;

const nodes = [
  { id: "OS1", parent_id: "OG" },
  { id: "R1.1", parent_id: "OS1" },
  { id: "A1.1.1", parent_id: "R1.1" },
  { id: "R1.2", parent_id: "OS1" },
];

const all = [
  indicator("I1", "R1.1", "Nombre de concertations", { source_of_verification: "Rapports" }),
  indicator("I2", "A1.1.1", "Ateliers organisés", { disaggregations: ["Sexe"] }),
  indicator("I3", "R1.2", "Degré de collaboration"),
];

const ids = (list: Indicator[]) => list.map((i) => i.id);

describe("filterIndicators", () => {
  it("garde les indicateurs du résultat et de ses activités", () => {
    expect(ids(filterIndicators(all, nodes, { query: "", nodeId: "R1.1" }))).toEqual(["I1", "I2"]);
    expect(ids(filterIndicators(all, nodes, { query: "", nodeId: "OS1" }))).toEqual([
      "I1",
      "I2",
      "I3",
    ]);
  });

  it("cherche dans le libellé, la source et les désagrégations, sans tenir compte des accents", () => {
    expect(ids(filterIndicators(all, nodes, { query: "degre", nodeId: "" }))).toEqual(["I3"]);
    expect(ids(filterIndicators(all, nodes, { query: "rapports", nodeId: "" }))).toEqual(["I1"]);
    expect(ids(filterIndicators(all, nodes, { query: "sexe", nodeId: "R1.1" }))).toEqual(["I2"]);
  });
});

describe("parseList", () => {
  it("sépare sur les virgules et points-virgules", () => {
    expect(parseList("Sexe, Âge ; Province ,")).toEqual(["Sexe", "Âge", "Province"]);
  });
});
