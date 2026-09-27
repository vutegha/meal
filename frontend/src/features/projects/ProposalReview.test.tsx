import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";

import type { Proposal, ProposedBudgetLine, ProposedNode } from "@/lib/api";

import { ProposalReview } from "./ProposalReview";

const source = { source_document: 1, source_page: 2, source_quote: "extrait", verified: true };
const node = (ref: string, parent_ref: string | null, level: ProposedNode["level"]) => ({
  ...source,
  ref,
  parent_ref,
  level,
  code: ref,
  title: `Titre ${ref}`,
  assumptions: "",
});
const line = (activity_ref: string | null, label: string): ProposedBudgetLine => ({
  ...source,
  activity_ref,
  donor_line_code: "",
  label,
  category: "",
  quantity: 2,
  unit: "",
  unit_cost: 100,
  frequency: 3,
  is_estimate: false,
});

const proposal: Proposal = {
  id: "prop-1",
  kind: "logframe",
  status: "pending",
  created_at: "2026-09-27T10:00:00Z",
  reviewed_at: null,
  payload: {
    summary: "Résumé",
    currency: "USD",
    documents: ["proposition.pdf"],
    nodes: [
      node("OG", null, "goal"),
      node("OS1", "OG", "outcome"),
      node("R1", "OS1", "output"),
      node("A1", "R1", "activity"),
      { ...node("A2", "R1", "activity"), verified: false },
    ],
    indicators: [],
    budget_lines: [line("A1", "Formateurs"), line(null, "Loyer")],
    missing_information: ["Aucune valeur de référence"],
  },
};

afterEach(() => vi.restoreAllMocks());

it("cascades selection and sends only the retained items", async () => {
  const fetch = vi
    .spyOn(globalThis, "fetch")
    .mockResolvedValue(new Response(JSON.stringify({ ...proposal, status: "applied" })));
  const user = userEvent.setup();
  render(
    <QueryClientProvider client={new QueryClient()}>
      <ProposalReview orgId="o" projectId="p" proposal={proposal} currency="USD" canPlan />
    </QueryClientProvider>,
  );

  expect(screen.getByText("Aucune valeur de référence")).toBeInTheDocument();
  expect(screen.getByText("Citation introuvable, à vérifier")).toBeInTheDocument();

  // Écarter R1 écarte ses activités et la ligne budgétaire de A1.
  await user.click(screen.getByLabelText("R1 Titre R1"));
  expect(screen.getByLabelText("A1 Titre A1")).not.toBeChecked();
  expect(screen.getByLabelText("Formateurs")).not.toBeChecked();
  expect(screen.getByLabelText("Loyer")).toBeChecked();

  // Retenir A1 retient de nouveau son parent R1.
  await user.click(screen.getByLabelText("A1 Titre A1"));
  expect(screen.getByLabelText("R1 Titre R1")).toBeChecked();
  expect(screen.getByLabelText("A2 Titre A2")).not.toBeChecked();

  await user.click(screen.getByRole("button", { name: "Enregistrer les 4 éléments retenus" }));
  const body = JSON.parse(fetch.mock.calls[0][1]!.body as string) as {
    nodes: ProposedNode[];
    budget_lines: ProposedBudgetLine[];
  };
  expect(body.nodes.map((n) => n.ref)).toEqual(["OG", "OS1", "R1", "A1"]);
  expect(body.budget_lines.map((l) => l.label)).toEqual(["Formateurs", "Loyer"]);
});
