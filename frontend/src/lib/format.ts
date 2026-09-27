export function formatNumber(value: string | number | null | undefined, language = "fr"): string {
  if (value === null || value === undefined || value === "") return "–";
  return new Intl.NumberFormat(language, { maximumFractionDigits: 2 }).format(Number(value));
}

export function formatMoney(value: string | number, currency: string, language = "fr"): string {
  return new Intl.NumberFormat(language, {
    style: "currency",
    currency,
    maximumFractionDigits: 0,
  }).format(Number(value));
}

export function formatRate(rate: number | null | undefined, language = "fr"): string {
  if (rate === null || rate === undefined) return "–";
  return new Intl.NumberFormat(language, { style: "percent", maximumFractionDigits: 0 }).format(
    rate,
  );
}

export function flattenTree<T extends { children: T[] }>(nodes: T[]): T[] {
  return nodes.flatMap((node) => [node, ...flattenTree(node.children)]);
}
