/**
 * Calculs du chronogramme (diagramme de Gantt) : les périodes sont gérées au mois près, par un
 * index de mois (année × 12 + mois − 1) facile à décaler lors d'un glisser-déposer.
 */
import type { Execution, Indicator, LogframeNode } from "./api";

export type ActivityState = "unscheduled" | "planned" | "in_progress" | "executed";

export function monthIndex(iso: string): number {
  const [year, month] = iso.split("-").map(Number);
  return year * 12 + month - 1;
}

const pad = (value: number) => String(value).padStart(2, "0");

/** Premier jour du mois, au format AAAA-MM-JJ. */
export function monthStartIso(index: number): string {
  return `${Math.floor(index / 12)}-${pad((index % 12) + 1)}-01`;
}

/** Dernier jour du mois, au format AAAA-MM-JJ. */
export function monthEndIso(index: number): string {
  const year = Math.floor(index / 12);
  const month = (index % 12) + 1;
  const last = new Date(Date.UTC(year, month, 0)).getUTCDate();
  return `${year}-${pad(month)}-${pad(last)}`;
}

export function todayIndex(now = new Date()): number {
  return now.getFullYear() * 12 + now.getMonth();
}

/**
 * Mois couverts par le chronogramme : la durée du projet, élargie aux activités planifiées en
 * dehors ; sans dates, les douze mois à venir.
 */
export function timelineRange(
  project: { start_date: string | null; end_date: string | null },
  activities: Pick<LogframeNode, "planned_start" | "planned_end">[],
  now = new Date(),
): { first: number; last: number } {
  const starts = activities.flatMap((a) => (a.planned_start ? [monthIndex(a.planned_start)] : []));
  const ends = activities.flatMap((a) => (a.planned_end ? [monthIndex(a.planned_end)] : []));
  let first = project.start_date ? monthIndex(project.start_date) : null;
  let last = project.end_date ? monthIndex(project.end_date) : null;
  first = Math.min(first ?? Infinity, ...starts);
  last = Math.max(last ?? -Infinity, ...ends);
  if (!Number.isFinite(first)) first = Number.isFinite(last) ? last - 11 : todayIndex(now);
  if (!Number.isFinite(last) || last < first) last = first + 11;
  return { first, last };
}

/** État d'une activité : exécutée dès qu'une exécution est terminée, en cours sinon. */
export function activityState(
  activity: Pick<LogframeNode, "id" | "planned_start">,
  executions: Pick<Execution, "activity_id" | "status">[],
): ActivityState {
  const own = executions.filter((e) => e.activity_id === activity.id);
  if (own.some((e) => e.status === "completed")) return "executed";
  if (own.length) return "in_progress";
  return activity.planned_start ? "planned" : "unscheduled";
}

/**
 * Indicateurs qui renseignent sur une activité : les siens, ceux de ses sous-activités, puis
 * ceux des éléments auxquels elle contribue (activité parente, résultat).
 */
export function relatedIndicators(
  activity: LogframeNode,
  nodes: Map<string, LogframeNode>,
  indicators: Indicator[],
): Indicator[] {
  // Distance de chaque élément à l'activité : les indicateurs les plus proches d'abord.
  const distance = new Map<string, number>([[activity.id, 0]]);
  for (const child of activity.children) distance.set(child.id, 0);
  let parent = activity.parent_id ? nodes.get(activity.parent_id) : undefined;
  let depth = 1;
  while (parent && (parent.level === "activity" || parent.level === "output")) {
    distance.set(parent.id, depth++);
    parent = parent.parent_id ? nodes.get(parent.parent_id) : undefined;
  }
  return indicators
    .filter((i) => distance.has(i.node_id))
    .sort((a, b) => distance.get(a.node_id)! - distance.get(b.node_id)!);
}

export type DragMode = "move" | "start" | "end" | "create";

/** Nouvelle période après un déplacement de `delta` mois, bornée au chronogramme. */
export function dragPeriod(
  mode: DragMode,
  start: number,
  end: number,
  delta: number,
  bounds: { first: number; last: number },
): [number, number] {
  if (mode === "move") {
    const shift = Math.max(bounds.first - start, Math.min(bounds.last - end, delta));
    return [start + shift, end + shift];
  }
  if (mode === "start") return [Math.max(bounds.first, Math.min(end, start + delta)), end];
  if (mode === "end") return [start, Math.min(bounds.last, Math.max(start, end + delta))];
  // Création : du mois de départ au mois atteint, dans un sens ou dans l'autre.
  const reached = Math.max(bounds.first, Math.min(bounds.last, start + delta));
  return [Math.min(start, reached), Math.max(start, reached)];
}
