import type { Editor, Extensions } from "@tiptap/core";
import { TableKit } from "@tiptap/extension-table";
import { Markdown } from "@tiptap/markdown";
import StarterKit from "@tiptap/starter-kit";

/**
 * Éditeur riche des documents rédigés. Le contenu reste enregistré en Markdown simple, le seul
 * format que lisent les exports Word et PDF : titres, paragraphes, gras, listes, tableaux.
 * Les autres mises en forme sont désactivées pour ne rien perdre à l'export.
 */
export const RICH_EXTENSIONS: Extensions = [
  StarterKit.configure({
    heading: { levels: [1, 2, 3] },
    italic: false,
    strike: false,
    code: false,
    codeBlock: false,
    blockquote: false,
    horizontalRule: false,
    link: false,
    underline: false,
  }),
  TableKit.configure({ table: { resizable: false } }),
  Markdown,
];

/**
 * Markdown produit par l'éditeur, ramené au dialecte des documents : les crochets des renvois
 * ([S1], [P2], [À compléter]) ne sont pas échappés et les lignes vides ne s'accumulent pas.
 */
export function cleanMarkdown(markdown: string): string {
  return markdown
    .replace(/\\([[\]_])/g, "$1")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

export const editorMarkdown = (editor: Editor) => cleanMarkdown(editor.getMarkdown());
