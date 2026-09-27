import { fileURLToPath } from "node:url";

import { expect, test } from "@playwright/test";

// Proposition de projet utilisée par le jeu d'évaluation des prompts ; le faux modèle IA renvoie
// le cadre logique qui lui correspond (backend/tests/fake_llm.py).
const PROPOSAL = fileURLToPath(
  new URL("../../backend/app/llm/evals/proposition_avec.txt", import.meta.url),
);

test("du document de projet au rapport narratif validé", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("dialog", (dialog) => dialog.accept());

  // Inscription : utilisateur et organisation
  await page.goto("/register");
  await page.getByLabel("Nom complet").fill("Awa Kahindo");
  await page.getByLabel("Nom de votre organisation").fill("ONG de test");
  await page.getByLabel("Adresse e-mail").fill(`e2e-${Date.now()}@wemeal.org`);
  await page.getByLabel("Mot de passe").fill("motdepasse-e2e");
  await page.getByRole("button", { name: "Créer mon compte" }).click();

  // Projet
  await page.getByRole("button", { name: "+ Nouveau projet" }).click();
  await page.getByLabel("Code").fill("E2E-01");
  await page.getByLabel("Intitulé").fill("Résilience économique à Rutshuru");
  await page.getByLabel("Devise").fill("USD");
  await page.getByRole("button", { name: "Créer le projet" }).click();
  await page.getByText("Résilience économique à Rutshuru").click();

  // Import du document et extraction IA du cadre logique et du budget
  await page.getByRole("button", { name: "Documents et IA" }).click();
  await page.getByLabel("Importer des documents").setInputFiles(PROPOSAL);
  await expect(page.getByText("Texte extrait")).toBeVisible();
  await page.getByRole("button", { name: /Extraire le cadre logique/ }).click();
  await expect(page.getByText("Informations absentes des documents")).toBeVisible();
  await page.getByRole("button", { name: /Enregistrer les \d+ éléments retenus/ }).click();
  await expect(page.getByText("Aucune proposition en attente de validation.")).toBeVisible();
  await page.getByRole("button", { name: "Cadre logique", exact: true }).click();
  await expect(page.getByText("Former les membres des AVEC").first()).toBeVisible();

  // TdR rédigé par l'IA, soumis puis approuvé
  await page.getByRole("button", { name: "TdR", exact: true }).click();
  await page
    .getByRole("button", { name: /Rédiger avec l'IA/ })
    .first()
    .click();
  await page.getByRole("button", { name: "✨ Lancer la rédaction" }).click();
  await page.getByRole("button", { name: "Soumettre pour validation" }).click();
  await page.getByRole("button", { name: "Approuver" }).first().click();
  await page.getByRole("button", { name: "Approuver" }).last().click();
  await expect(page.getByText("Approuvé", { exact: true })).toBeVisible();
  const tor = page.waitForEvent("download");
  await page.getByRole("button", { name: "⬇ PDF" }).click();
  expect((await tor).suggestedFilename()).toMatch(/\.pdf$/);

  // Exécution sur le terrain
  await page.getByRole("button", { name: "Exécution", exact: true }).click();
  await page.getByRole("button", { name: "+ Nouvelle exécution" }).click();
  await page.getByLabel("Activité").selectOption({ index: 1 });
  await page.getByLabel("Intitulé (facultatif)").fill("Formation AVEC de Kiwanja");
  await page.getByLabel("Début").fill("2026-03-14");
  await page.getByLabel("Fin").fill("2026-03-16");
  await page.getByLabel("Lieu", { exact: true }).fill("Kiwanja");
  await page.getByLabel("Femmes").fill("22");
  await page.getByLabel("Hommes").fill("14");
  await page
    .getByLabel("Déroulement et écarts constatés")
    .fill("Deux groupes au lieu d'un, faute de salle assez grande.");
  await page.getByRole("button", { name: "Enregistrer" }).click();
  await page.getByRole("button", { name: /Formation AVEC de Kiwanja/ }).click();

  // Rapport narratif rédigé par l'IA, validé et exporté
  await page.getByRole("button", { name: /Rédiger le rapport avec l'IA/ }).click();
  await expect(page.getByText("Sources citées")).toBeVisible();
  await page.getByRole("button", { name: "Soumettre pour validation" }).click();
  await page.getByRole("button", { name: "Approuver" }).first().click();
  await page.getByRole("button", { name: "Approuver" }).last().click();
  await expect(page.getByText("Approuvé").first()).toBeVisible();
  const report = page.waitForEvent("download");
  await page.getByRole("button", { name: "⬇ PDF" }).click();
  expect((await report).suggestedFilename()).toMatch(/\.pdf$/);

  // Tableau de bord : l'activité réalisée et les 36 personnes atteintes
  await page.getByRole("button", { name: "Tableau de bord" }).click();
  await expect(page.getByText("Suivi par activité")).toBeVisible();
  await expect(page.getByText("36", { exact: true })).toBeVisible();

  expect(errors).toEqual([]);
});
