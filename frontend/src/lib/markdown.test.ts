import { expect, it } from "vitest";

import { parseMarkdown } from "./markdown";

it("parses the markdown subset used in drafted documents", () => {
  const blocks = parseMarkdown(
    "Intro **gras**\nsuite\n\n- un\n- deux\n1. premier\n\n| A | B |\n|---|---|\n| 1 | 2 |\n## Titre",
  );
  expect(blocks.map((b) => b.kind)).toEqual([
    "paragraph",
    "bullets",
    "numbered",
    "table",
    "heading",
  ]);
  expect(blocks[0]).toEqual({ kind: "paragraph", text: "Intro **gras** suite" });
  expect(blocks[3]).toEqual({
    kind: "table",
    rows: [
      ["A", "B"],
      ["1", "2"],
    ],
  });
});
