import type { BuiltinTemplates, TemplateIn, TemplateKind, TemplateSection } from "./api";

/** Clé technique d'une section à partir de son titre : « Rôles et responsabilités » → roles_et_responsabilites. */
export function sectionKey(title: string, taken: string[] = []): string {
  const base =
    title
      .normalize("NFD")
      .replace(/[̀-ͯ]/g, "")
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "_")
      .replace(/^_+|_+$/g, "")
      .slice(0, 36) || "section";
  let key = base;
  for (let n = 2; taken.includes(key); n += 1) key = `${base}_${n}`;
  return key;
}

export function move<T>(items: T[], index: number, delta: -1 | 1): T[] {
  const target = index + delta;
  if (target < 0 || target >= items.length) return items;
  const next = [...items];
  [next[index], next[target]] = [next[target], next[index]];
  return next;
}

/** Nouveau modèle : on part des sections intégrées à l'application. */
export function startTemplate(kind: TemplateKind, builtin: BuiltinTemplates): TemplateIn {
  return {
    kind,
    name: "",
    donor: "",
    is_default: false,
    sections: builtin[kind].map(({ key, title }): TemplateSection => ({
      key,
      title,
      guidance: "",
    })),
    layout: { header: "", footer: "", color: "#0f5b52" },
  };
}
