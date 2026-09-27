import { lazy, Suspense } from "react";

// L'éditeur riche (TipTap) n'est chargé qu'à l'ouverture d'un document en édition.
const RichEditor = lazy(() =>
  import("./RichEditor").then((module) => ({ default: module.RichEditor })),
);

export function LazyRichEditor(props: {
  label: string;
  value: string;
  onChange: (markdown: string) => void;
}) {
  return (
    <Suspense
      fallback={
        <div className="h-28 animate-pulse rounded-md border border-slate-200 bg-slate-50" />
      }
    >
      <RichEditor {...props} />
    </Suspense>
  );
}
