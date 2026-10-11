import { expect, test } from "@playwright/test";

test("du site public à l'abonnement d'un compte individuel", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));

  // Site public : accueil, puis tarifs
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: /Du document de projet au rapport final/ }),
  ).toBeVisible();
  await page.getByRole("banner").getByRole("link", { name: "Tarifs" }).click();
  await page.getByRole("radio", { name: /Annuel/ }).click();
  const solo = page.getByRole("article", { name: "Solo" });
  await expect(solo.getByText("120 $US")).toBeVisible();
  await solo.getByRole("link", { name: "Choisir Solo" }).click();

  // Inscription d'un compte individuel : pas de nom d'organisation
  await expect(page.getByRole("radio", { name: /Individuel/ })).toBeChecked();
  await expect(page.getByLabel("Nom de votre organisation")).toHaveCount(0);
  await page.getByLabel("Nom complet").fill("Awa Consultante");
  await page.getByLabel("Adresse e-mail").fill(`solo-${Date.now()}@wemeal.org`);
  await page.getByLabel("Mot de passe").fill("motdepasse-e2e");
  await page.getByRole("button", { name: "Créer mon compte" }).click();

  // Espace individuel : pas de membres ni de modèles, essai en cours
  await expect(page.getByRole("heading", { name: "Projets" })).toBeVisible();
  await expect(page.getByText(/Essai gratuit : encore 14 jour/)).toBeVisible();
  const nav = page.getByRole("navigation");
  await expect(nav.getByRole("link", { name: "Modèles" })).toHaveCount(0);
  await expect(nav.getByRole("link", { name: "Membres et audit" })).toHaveCount(0);

  // Passage à l'usage : achat d'un pack de crédits (paiement simulé)
  await nav.getByRole("link", { name: "Abonnement" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Solo" })).toBeVisible();
  await page.getByRole("radio", { name: "À l'usage" }).click();
  await page.getByRole("button", { name: "Payer 20 $US" }).click();
  await expect(page.getByText(/Paiement reçu \(réf\. SIM-/)).toBeVisible();
  await expect(page.getByText("Crédits restants")).toBeVisible();
  await expect(page.getByRole("cell", { name: "Solo · À l'usage · 10 crédits" })).toBeVisible();

  expect(errors).toEqual([]);
});
