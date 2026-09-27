/** Analyseur du Markdown simple des documents rédigés (même sous-ensemble que les exports). */

export type Block =
  | { kind: "heading" | "paragraph"; text: string }
  | { kind: "bullets" | "numbered"; items: string[] }
  | { kind: "table"; rows: string[][] };

const BULLET = /^\s*[-*•]\s+(.*)$/;
const NUMBERED = /^\s*\d+[.)]\s+(.*)$/;
const HEADING = /^#{1,3}\s+(.*)$/;
const SEPARATOR = /^\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?$/;

const cells = (line: string) =>
  line
    .trim()
    .replace(/^\||\|$/g, "")
    .split("|")
    .map((cell) => cell.trim());

export function parseMarkdown(markdown: string): Block[] {
  const blocks: Block[] = [];
  let paragraph: string[] = [];
  const close = () => {
    if (paragraph.length) blocks.push({ kind: "paragraph", text: paragraph.join(" ") });
    paragraph = [];
  };
  for (const raw of markdown.split(/\r?\n/)) {
    const line = raw.trimEnd();
    const last = blocks[blocks.length - 1];
    if (!line.trim()) {
      close();
    } else if (HEADING.test(line)) {
      close();
      blocks.push({ kind: "heading", text: line.replace(HEADING, "$1").trim() });
    } else if (line.trimStart().startsWith("|")) {
      close();
      if (SEPARATOR.test(line.trim())) continue;
      if (last?.kind === "table") last.rows.push(cells(line));
      else blocks.push({ kind: "table", rows: [cells(line)] });
    } else if (BULLET.test(line) || NUMBERED.test(line)) {
      close();
      const kind = BULLET.test(line) ? "bullets" : "numbered";
      const item = line.replace(kind === "bullets" ? BULLET : NUMBERED, "$1").trim();
      if (last?.kind === kind) last.items.push(item);
      else blocks.push({ kind, items: [item] });
    } else {
      paragraph.push(line.trim());
    }
  }
  close();
  return blocks;
}
