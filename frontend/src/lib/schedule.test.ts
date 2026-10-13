import { describe, expect, it } from "vitest";

import type { Indicator, LogframeNode } from "./api";
import {
  activityState,
  dragPeriod,
  monthEndIso,
  monthIndex,
  monthStartIso,
  relatedIndicators,
  scheduleRows,
  timelineRange,
} from "./schedule";

const node = (id: string, level: LogframeNode["level"], parent: string | null): LogframeNode => ({
  id,
  parent_id: parent,
  level,
  code: id,
  title: id,
  description: "",
  assumptions: "",
  position: 0,
  planned_start: null,
  planned_end: null,
  children: [],
});

describe("chronogramme", () => {
  it("convertit les mois en dates", () => {
    const jan = monthIndex("2026-01-15");
    expect(monthStartIso(jan)).toBe("2026-01-01");
    expect(monthEndIso(jan + 1)).toBe("2026-02-28");
    expect(monthEndIso(jan + 11)).toBe("2026-12-31");
    expect(monthStartIso(jan + 12)).toBe("2027-01-01");
  });

  it("couvre la durée du projet et les activités qui en sortent", () => {
    const project = { start_date: "2026-01-01", end_date: "2026-12-31" };
    const range = timelineRange(project, [
      { planned_start: "2026-11-01", planned_end: "2027-02-28" },
    ]);
    expect(range).toEqual({ first: monthIndex("2026-01-01"), last: monthIndex("2027-02-01") });
    const now = new Date(2026, 4, 10);
    expect(timelineRange({ start_date: null, end_date: null }, [], now)).toEqual({
      first: monthIndex("2026-05-01"),
      last: monthIndex("2027-04-01"),
    });
  });

  it("déduit l'état de l'activité de ses exécutions", () => {
    const activity = { id: "a", planned_start: "2026-01-01" };
    expect(activityState(activity, [])).toBe("planned");
    expect(activityState({ id: "a", planned_start: null }, [])).toBe("unscheduled");
    expect(activityState(activity, [{ activity_id: "a", status: "in_progress" }])).toBe(
      "in_progress",
    );
    expect(
      activityState(activity, [
        { activity_id: "a", status: "in_progress" },
        { activity_id: "a", status: "completed" },
      ]),
    ).toBe("executed");
  });

  it("borne les déplacements au chronogramme", () => {
    const bounds = { first: 0, last: 11 };
    expect(dragPeriod("move", 2, 4, 3, bounds)).toEqual([5, 7]);
    expect(dragPeriod("move", 2, 4, 20, bounds)).toEqual([9, 11]);
    expect(dragPeriod("move", 2, 4, -5, bounds)).toEqual([0, 2]);
    expect(dragPeriod("start", 2, 4, 5, bounds)).toEqual([4, 4]);
    expect(dragPeriod("end", 2, 4, -5, bounds)).toEqual([2, 2]);
    expect(dragPeriod("create", 6, 6, -2, bounds)).toEqual([4, 6]);
  });

  it("retrouve les indicateurs de l'activité et de son résultat", () => {
    const output = node("r", "output", "os");
    const activity = node("a", "activity", "r");
    const sub = node("s", "sub_activity", "a");
    activity.children = [sub];
    const nodes = new Map(
      [output, activity, sub, node("os", "outcome", null)].map((n) => [n.id, n]),
    );
    const indicator = (id: string, nodeId: string) => ({ id, node_id: nodeId }) as Indicator;
    const all = [indicator("i-os", "os"), indicator("i-r", "r"), indicator("i-a", "a")];
    expect(relatedIndicators(activity, nodes, all).map((i) => i.id)).toEqual(["i-a", "i-r"]);
    expect(relatedIndicators(sub, nodes, all).map((i) => i.id)).toEqual(["i-a", "i-r"]);
  });

  it("filtre le diagramme par effet et par résultat", () => {
    const tree = [
      node("os1", "outcome", null),
      node("r1", "output", "os1"),
      node("a1", "activity", "r1"),
      node("s1", "sub_activity", "a1"),
      node("r2", "output", "os1"),
      node("a2", "activity", "r2"),
      node("os2", "outcome", null),
      node("r3", "output", "os2"),
      node("a3", "activity", "r3"),
    ];
    const byId = new Map(tree.map((n) => [n.id, n]));
    const ids = (outcome: string | null, outputs: string[]) =>
      scheduleRows(tree, byId, { outcome, outputs }).map((n) => n.id);
    expect(ids(null, [])).toEqual(["r1", "a1", "s1", "r2", "a2", "r3", "a3"]);
    expect(ids("os2", [])).toEqual(["r3", "a3"]);
    expect(ids(null, ["r1", "r3"])).toEqual(["r1", "a1", "s1", "r3", "a3"]);
    expect(ids("os1", ["r2"])).toEqual(["r2", "a2"]);
  });
});
