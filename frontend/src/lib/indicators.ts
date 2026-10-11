import type { Indicator, LogframeNode } from "./api";

/** Minuscules sans accents, pour une recherche tolérante. */
const fold = (text: string) => text.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();

/** Désagrégations saisies en une ligne : « Sexe, Âge ; Province » → trois entrées. */
export function parseList(text: string): string[] {
  return text
    .split(/[,;\n]/)
    .map((item) => item.trim())
    .filter(Boolean);
}

/**
 * Indicateurs rattachés à un élément du cadre logique ou à ses descendants, et dont le code,
 * le libellé, la source ou une désagrégation contient la recherche.
 */
export function filterIndicators(
  indicators: Indicator[],
  nodes: Pick<LogframeNode, "id" | "parent_id">[],
  { query, nodeId }: { query: string; nodeId: string },
): Indicator[] {
  let scope: Set<string> | null = null;
  if (nodeId) {
    const parent = new Map(nodes.map((n) => [n.id, n.parent_id]));
    const within = (id: string | null): boolean =>
      id === nodeId || (id !== null && within(parent.get(id) ?? null));
    scope = new Set(nodes.filter((n) => within(n.id)).map((n) => n.id));
  }
  const words = fold(query).split(/\s+/).filter(Boolean);
  return indicators.filter((indicator) => {
    if (scope && !scope.has(indicator.node_id)) return false;
    const haystack = fold(
      [
        indicator.code,
        indicator.name,
        indicator.source_of_verification,
        ...indicator.disaggregations,
      ].join(" "),
    );
    return words.every((word) => haystack.includes(word));
  });
}
