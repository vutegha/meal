import { EditorContent, useEditor, useEditorState } from "@tiptap/react";
import { type ReactNode, useState } from "react";
import { useTranslation } from "react-i18next";

import { editorMarkdown, RICH_EXTENSIONS } from "@/lib/richtext";

const CONTENT =
  "min-h-24 px-3 py-2 text-sm leading-relaxed text-slate-800 focus:outline-none " +
  "[&_h1]:font-semibold [&_h2]:font-semibold [&_h3]:font-semibold [&_p]:my-1.5 " +
  "[&_ul]:list-disc [&_ul]:pl-5 [&_ol]:list-decimal [&_ol]:pl-5 " +
  "[&_table]:my-2 [&_table]:border-collapse [&_table]:text-xs " +
  "[&_td]:border [&_td]:border-slate-300 [&_td]:px-2 [&_td]:py-1 " +
  "[&_th]:border [&_th]:border-slate-300 [&_th]:bg-slate-50 [&_th]:px-2 [&_th]:py-1 " +
  "[&_.selectedCell]:bg-brand-50";

function Tool({
  label,
  active,
  disabled,
  onClick,
  children,
}: {
  label: string;
  active?: boolean;
  disabled?: boolean;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      title={label}
      aria-label={label}
      aria-pressed={active}
      disabled={disabled}
      onMouseDown={(e) => e.preventDefault()}
      onClick={onClick}
      className={`min-w-7 rounded px-1.5 py-0.5 text-xs disabled:opacity-40 ${
        active ? "bg-brand-100 text-brand-900" : "text-slate-700 hover:bg-slate-100"
      }`}
    >
      {children}
    </button>
  );
}

/**
 * Éditeur riche d'une section (titres, gras, listes, tableaux), enregistré en Markdown.
 * Un bouton bascule vers le texte brut pour les cas que la barre d'outils ne couvre pas.
 */
export function RichEditor({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (markdown: string) => void;
}) {
  const { t } = useTranslation();
  const [raw, setRaw] = useState(false);
  const editor = useEditor({
    extensions: RICH_EXTENSIONS,
    content: value,
    contentType: "markdown",
    immediatelyRender: true,
    editorProps: {
      attributes: {
        "aria-label": label,
        role: "textbox",
        "aria-multiline": "true",
        class: CONTENT,
      },
    },
    onUpdate: ({ editor }) => onChange(editorMarkdown(editor)),
  });
  const state = useEditorState({
    editor,
    selector: ({ editor }) => ({
      bold: editor.isActive("bold"),
      heading: editor.isActive("heading"),
      bullets: editor.isActive("bulletList"),
      numbered: editor.isActive("orderedList"),
      table: editor.isActive("table"),
      undo: editor.can().undo(),
      redo: editor.can().redo(),
    }),
  });
  const chain = () => editor.chain().focus();

  return (
    <div className="rounded-md border border-slate-300 bg-white focus-within:border-brand-600 focus-within:ring-2 focus-within:ring-brand-100">
      <div
        role="toolbar"
        aria-label={t("editor.toolbar")}
        className="flex flex-wrap items-center gap-0.5 border-b border-slate-200 px-1.5 py-1"
      >
        {!raw && (
          <>
            <Tool
              label={t("editor.heading")}
              active={state.heading}
              onClick={() => chain().toggleHeading({ level: 3 }).run()}
            >
              T
            </Tool>
            <Tool
              label={t("editor.bold")}
              active={state.bold}
              onClick={() => chain().toggleBold().run()}
            >
              <b>G</b>
            </Tool>
            <Tool
              label={t("editor.bullets")}
              active={state.bullets}
              onClick={() => chain().toggleBulletList().run()}
            >
              •
            </Tool>
            <Tool
              label={t("editor.numbered")}
              active={state.numbered}
              onClick={() => chain().toggleOrderedList().run()}
            >
              1.
            </Tool>
            <span className="mx-1 h-4 w-px bg-slate-200" />
            {state.table ? (
              <>
                <Tool label={t("editor.addRow")} onClick={() => chain().addRowAfter().run()}>
                  +≡
                </Tool>
                <Tool label={t("editor.addColumn")} onClick={() => chain().addColumnAfter().run()}>
                  +‖
                </Tool>
                <Tool label={t("editor.deleteRow")} onClick={() => chain().deleteRow().run()}>
                  −≡
                </Tool>
                <Tool label={t("editor.deleteColumn")} onClick={() => chain().deleteColumn().run()}>
                  −‖
                </Tool>
                <Tool label={t("editor.deleteTable")} onClick={() => chain().deleteTable().run()}>
                  ✕▦
                </Tool>
              </>
            ) : (
              <Tool
                label={t("editor.table")}
                onClick={() => chain().insertTable({ rows: 3, cols: 3, withHeaderRow: true }).run()}
              >
                ▦
              </Tool>
            )}
            <span className="mx-1 h-4 w-px bg-slate-200" />
            <Tool
              label={t("editor.undo")}
              disabled={!state.undo}
              onClick={() => chain().undo().run()}
            >
              ↶
            </Tool>
            <Tool
              label={t("editor.redo")}
              disabled={!state.redo}
              onClick={() => chain().redo().run()}
            >
              ↷
            </Tool>
          </>
        )}
        <span className="flex-1" />
        <Tool
          label={t("editor.rawHint")}
          active={raw}
          onClick={() => {
            // Retour à l'éditeur riche : il reprend le texte brut modifié.
            if (raw) editor.commands.setContent(value, { contentType: "markdown" });
            setRaw(!raw);
          }}
        >
          {raw ? t("editor.rich") : "Markdown"}
        </Tool>
      </div>
      {raw ? (
        <textarea
          aria-label={label}
          className="block w-full rounded-b-md px-3 py-2 font-mono text-[13px] leading-relaxed focus:outline-none"
          rows={Math.min(18, Math.max(4, value.split("\n").length + 1))}
          value={value}
          onChange={(e) => onChange(e.target.value)}
        />
      ) : (
        <EditorContent editor={editor} />
      )}
    </div>
  );
}
