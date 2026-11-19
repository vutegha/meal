import type { NodeLevel } from "./api";

const PREFIX: Record<NodeLevel, string> = {
  goal: "OG",
  outcome: "OS",
  output: "R",
  activity: "A",
  sub_activity: "SA",
};

const TRAILING_NUMBER = /(\d+(?:\.\d+)*)\s*$/;

/** Code proposé pour un nouvel élément du cadre logique, d'après ses frères et son parent :
 * « Activité 1.1.5 » suivi de « Activité 1.1.6 », ou « 1.1 » + « .1 » pour un premier enfant. */
export function suggestCode(
  level: NodeLevel,
  parentCode: string | null,
  siblingCodes: string[],
): string {
  let best: { prefix: string; parts: number[] } | null = null;
  for (const code of siblingCodes) {
    const match = TRAILING_NUMBER.exec(code);
    if (!match) continue;
    const parts = match[1].split(".").map(Number);
    if (!best || parts[parts.length - 1] >= best.parts[best.parts.length - 1]) {
      best = { prefix: code.slice(0, match.index), parts };
    }
  }
  if (best) {
    const parts = [...best.parts];
    parts[parts.length - 1] += 1;
    return best.prefix + parts.join(".");
  }
  if (level === "goal")
    return siblingCodes.length ? `${PREFIX.goal}${siblingCodes.length + 1}` : PREFIX.goal;
  const parentNumber = parentCode ? TRAILING_NUMBER.exec(parentCode)?.[1] : undefined;
  const number = parentNumber ? `${parentNumber}.1` : `${siblingCodes.length + 1}`;
  return `${PREFIX[level]}${number}`;
}
