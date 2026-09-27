import type { ReactNode } from "react";

import { parseMarkdown } from "@/lib/markdown";

/** Affiche le Markdown simple des documents rédigés (même sous-ensemble que les exports). */

function Inline({ text }: { text: string }): ReactNode {
  return text
    .split(/\*\*(.+?)\*\*/)
    .map((part, index) => (index % 2 ? <strong key={index}>{part}</strong> : part));
}

export function Markdown({ source }: { source: string }) {
  return (
    <div className="space-y-2 text-sm leading-relaxed text-slate-800">
      {parseMarkdown(source).map((block, index) => {
        if (block.kind === "heading")
          return (
            <h4 key={index} className="font-semibold">
              <Inline text={block.text} />
            </h4>
          );
        if (block.kind === "paragraph")
          return (
            <p key={index}>
              <Inline text={block.text} />
            </p>
          );
        if (block.kind === "table") {
          const [head, ...body] = block.rows;
          return (
            <div key={index} className="overflow-x-auto">
              <table className="text-left text-xs">
                <thead>
                  <tr>
                    {head.map((cell, i) => (
                      <th key={i} className="border border-slate-200 bg-slate-50 px-2 py-1">
                        <Inline text={cell} />
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {body.map((row, r) => (
                    <tr key={r}>
                      {row.map((cell, i) => (
                        <td key={i} className="border border-slate-200 px-2 py-1">
                          <Inline text={cell} />
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          );
        }
        if (block.kind !== "bullets" && block.kind !== "numbered") return null;
        const List = block.kind === "bullets" ? "ul" : "ol";
        return (
          <List
            key={index}
            className={`pl-5 ${block.kind === "bullets" ? "list-disc" : "list-decimal"}`}
          >
            {block.items.map((item, i) => (
              <li key={i}>
                <Inline text={item} />
              </li>
            ))}
          </List>
        );
      })}
    </div>
  );
}
