import { Editor } from "@tiptap/core";
import { describe, expect, it } from "vitest";

import { parseMarkdown } from "./markdown";
import { cleanMarkdown, editorMarkdown, RICH_EXTENSIONS } from "./richtext";

const SOURCE = `Intro avec **gras** et renvois [S1] et [P2] puis [source introuvable].

### Sous-titre

- un
- deux

1. premier
2. second

| Ligne | Montant (USD) |
|---|---|
| Kits | 2 730 |

[À compléter : date de la formation] et 50 % des 1 200 participants.`;

const roundTrip = (markdown: string) => {
  const editor = new Editor({
    extensions: RICH_EXTENSIONS,
    content: markdown,
    contentType: "markdown",
  });
  const result = editorMarkdown(editor);
  editor.destroy();
  return result;
};

describe("éditeur riche", () => {
  it("rend le même document après un aller-retour", () => {
    const result = roundTrip(SOURCE);
    expect(result).toContain("[S1] et [P2] puis [source introuvable]");
    expect(result).toContain("[À compléter : date de la formation]");
    // Même structure pour les exports.
    const blocks = (md: string) =>
      parseMarkdown(md).map((b) =>
        b.kind === "table" ? { ...b, rows: b.rows.map((r) => r.map((c) => c.trim())) } : b,
      );
    expect(blocks(result)).toEqual(blocks(SOURCE));
  });

  it("nettoie les échappements et les lignes vides en trop", () => {
    expect(cleanMarkdown("a \\[S1\\] b\\_c\n\n\n\n| x |")).toBe("a [S1] b_c\n\n| x |");
  });
});
