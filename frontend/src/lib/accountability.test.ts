import { expect, it } from "vitest";

import { lastPeriod, lessonFromReport } from "./accountability";
import type { Project, Report } from "./api";

it("propose la dernière période écoulée", () => {
  const now = new Date(2026, 4, 20); // 20 mai 2026
  const project = { start_date: "2026-01-01", end_date: "2027-12-31" } as Project;
  expect(lastPeriod("monthly", project, now)).toEqual(["2026-04-01", "2026-04-30"]);
  expect(lastPeriod("quarterly", project, now)).toEqual(["2026-01-01", "2026-03-31"]);
  expect(lastPeriod("annual", project, now)).toEqual(["2025-01-01", "2025-12-31"]);
  expect(lastPeriod("donor", project, now)).toEqual(["2026-01-01", "2027-12-31"]);
});

it("pré-remplit une leçon depuis un rapport", () => {
  const report = {
    id: "r1",
    sections: [
      {
        key: "lecons",
        title: "Leçons",
        content: "- Visiter les salles avant la formation [S1].\n- **Prévoir** un interprète [S2]",
      },
    ],
  } as Report;
  const lesson = lessonFromReport(report);
  expect(lesson.title).toBe("Visiter les salles avant la formation.");
  expect(lesson.description).not.toContain("[S1]");
  expect(lesson.source_report_id).toBe("r1");
});
