import { expect, test } from "@playwright/test";

test("réglages des données personnelles, recherche d'une personne puis fermeture de l'espace", async ({
  page,
}) => {
  const email = `donnees-${Date.now()}@wemeal.org`;
  page.on("dialog", (dialog) => dialog.accept());
  await page.goto("/register");
  await page.getByLabel("Nom complet").fill("Admin Données");
  await page.getByLabel("Nom de votre organisation").fill("ONG protectrice");
  await page.getByLabel("Adresse e-mail").fill(email);
  await page.getByLabel("Mot de passe").fill("motdepasse-e2e");
  await page.getByRole("button", { name: "Créer mon compte" }).click();

  await page.getByRole("link", { name: "Données personnelles" }).click();
  await expect(page.getByRole("heading", { name: "Données personnelles" })).toBeVisible();
  await page.getByLabel(/Utiliser l'IA/).uncheck();
  await page.getByLabel(/Contact pour exercer ses droits/).fill("protection@ong.org");
  await page.getByRole("button", { name: "Enregistrer" }).click();
  await expect(page.getByText("Réglages enregistrés.")).toBeVisible();

  await page.reload();
  await expect(page.getByLabel(/Utiliser l'IA/)).not.toBeChecked();

  await page.getByLabel("Nom, numéro ou e-mail").fill("Inconnu");
  await page.getByRole("button", { name: "Rechercher" }).click();
  await expect(page.getByText("0 élément trouvé.")).toBeVisible();

  // Fermeture de l'unique espace, compte compris : plus de connexion possible.
  await page.getByLabel(/Recopiez le nom de l'espace/).fill("ONG protectrice");
  await page.getByLabel("Votre mot de passe, pour confirmer").fill("motdepasse-e2e");
  await page.getByRole("button", { name: "Fermer et tout effacer" }).click();
  await expect(page).toHaveURL(/\/$/);
  await page.goto("/login");
  await page.getByLabel("Adresse e-mail").fill(email);
  await page.getByLabel("Mot de passe").fill("motdepasse-e2e");
  await page.getByRole("button", { name: "Se connecter" }).click();
  await expect(page.getByText("Identifiants invalides")).toBeVisible();
});
