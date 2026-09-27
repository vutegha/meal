import type { AnswerValue, FieldType, FormField } from "./api";
import { sectionKey } from "./templates";

/** Saisie en cours d'une question : texte libre, cases cochées ou oui/non. */
export type Draft = string | string[] | boolean | null;

export const withOptions = (type: FieldType) => type === "select" || type === "multiselect";

export function blankField(taken: string[], label = ""): FormField {
  return {
    key: sectionKey(label || "question", taken),
    label,
    type: "text",
    required: false,
    options: [],
    hint: "",
  };
}

/** Clés stables pour les questions : dérivées du libellé, sans doublon. */
export function withKeys(fields: FormField[], locked: boolean): FormField[] {
  if (locked) return fields;
  const taken: string[] = [];
  return fields.map((field) => {
    const key = sectionKey(field.label || "question", taken);
    taken.push(key);
    return { ...field, key, options: withOptions(field.type) ? field.options : [] };
  });
}

export function emptyDraft(field: FormField): Draft {
  if (field.type === "multiselect") return [];
  if (field.type === "yesno") return null;
  return "";
}

/** Réponses à envoyer : les questions laissées vides sont omises. */
export function toAnswers(
  fields: FormField[],
  drafts: Record<string, Draft>,
): Record<string, AnswerValue> {
  const answers: Record<string, AnswerValue> = {};
  for (const field of fields) {
    const draft = drafts[field.key];
    if (draft === null || draft === undefined) continue;
    if (Array.isArray(draft)) {
      if (draft.length) answers[field.key] = field.options.filter((o) => draft.includes(o));
    } else if (typeof draft === "boolean") {
      answers[field.key] = draft;
    } else if (draft.trim()) {
      const text = draft.trim();
      const number = Number(text.replace(",", "."));
      answers[field.key] =
        (field.type === "number" || field.type === "integer") && !Number.isNaN(number)
          ? number
          : text;
    }
  }
  return answers;
}

export function formatAnswer(
  value: AnswerValue | undefined,
  yesNo: { yes: string; no: string },
  locale: string,
): string {
  if (value === undefined) return "";
  if (typeof value === "boolean") return value ? yesNo.yes : yesNo.no;
  if (Array.isArray(value)) return value.join(", ");
  if (typeof value === "number") return new Intl.NumberFormat(locale).format(value);
  return value;
}
