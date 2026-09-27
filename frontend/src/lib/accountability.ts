import type { LessonIn, PeriodicKind, Project, Report } from "./api";

export const EMPTY_LESSON: LessonIn = {
  title: "",
  description: "",
  recommendation: "",
  tags: [],
  activity_id: null,
  source_report_id: null,
};

const plain = (markdown: string) =>
  markdown
    .replace(/\s*\[(?:[SP]\d+|source introuvable)\]/g, "")
    .replace(/\*\*/g, "")
    .trim();

/** Pré-remplit une leçon avec la section « Leçons apprises » d'un rapport narratif. */
export function lessonFromReport(report: Report): LessonIn {
  const content = plain(report.sections.find((s) => s.key === "lecons")?.content ?? "");
  const first = content
    .split("\n")
    .map((line) => line.replace(/^\s*(?:[-*•]|\d+[.)])\s*/, "").trim())
    .find((line) => line && !line.startsWith("[À compléter"));
  return {
    ...EMPTY_LESSON,
    title: (first ?? "").slice(0, 200),
    description: content.startsWith("[À compléter") ? "" : content,
    source_report_id: report.id,
  };
}

const iso = (d: Date) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;

/** Période écoulée la plus récente pour le type de rapport choisi. */
export function lastPeriod(kind: PeriodicKind, project: Project, now = new Date()) {
  const y = now.getFullYear();
  const m = now.getMonth();
  if (kind === "monthly") return [iso(new Date(y, m - 1, 1)), iso(new Date(y, m, 0))];
  if (kind === "quarterly") {
    const q = Math.floor(m / 3) * 3;
    return [iso(new Date(y, q - 3, 1)), iso(new Date(y, q, 0))];
  }
  if (kind === "annual") return [iso(new Date(y - 1, 0, 1)), iso(new Date(y - 1, 11, 31))];
  return [project.start_date ?? iso(new Date(y, 0, 1)), project.end_date ?? iso(now)];
}
