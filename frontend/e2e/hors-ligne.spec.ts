import { expect, test } from "@playwright/test";

// Un agent rouvre l'application sur le terrain, sans réseau : il retrouve ses projets et peut
// saisir ; à la déconnexion, la file d'envoi est vidée du téléphone.
test("l'application se rouvre sans réseau puis vide la file à la déconnexion", async ({ page }) => {
  const dialogs: string[] = [];
  page.on("dialog", async (dialog) => {
    dialogs.push(dialog.message());
    await dialog.accept();
  });

  await page.goto("/register");
  await page.getByLabel("Nom complet").fill("Jean Bahati");
  await page.getByLabel("Nom de votre organisation").fill("ONG hors ligne");
  await page.getByLabel("Adresse e-mail").fill(`offline-${Date.now()}@wemeal.org`);
  await page.getByLabel("Mot de passe").fill("motdepasse-e2e");
  await page.getByRole("button", { name: "Créer mon compte" }).click();

  await page.getByRole("button", { name: "+ Nouveau projet" }).click();
  await page.getByLabel("Code").fill("OFF-01");
  await page.getByLabel("Intitulé").fill("Projet de terrain");
  await page.getByLabel("Devise").fill("USD");
  await page.getByRole("button", { name: "Créer le projet" }).click();
  await page.getByText("Projet de terrain").click();
  await page.getByRole("button", { name: "Plaintes et retours", exact: true }).click();
  await expect(page.getByRole("button", { name: "+ Enregistrer un retour" })).toBeVisible();

  // Le service worker prend la main, puis garde l'application et les données consultées.
  await page.evaluate("navigator.serviceWorker.ready.then(() => true)");
  await page.reload();
  await expect(page.getByRole("button", { name: "+ Enregistrer un retour" })).toBeVisible();
  await expect.poll(() => page.evaluate("!!navigator.serviceWorker.controller")).toBe(true);

  await page.context().setOffline(true);
  await page.reload();
  await expect(page).not.toHaveURL(/\/login/);
  await expect(page.getByText("Jean Bahati")).toBeVisible();

  await page.getByRole("button", { name: "+ Enregistrer un retour" }).click();
  await page.getByLabel("Ce qui a été dit").fill("Signalement recueilli sans réseau.");
  await page.getByRole("button", { name: "Enregistrer", exact: true }).click();
  await expect(page.getByText("1 retour en attente d'envoi.")).toBeVisible();

  await page.getByRole("button", { name: "Se déconnecter" }).click();
  await expect(page).toHaveURL(/\/login/);
  expect(dialogs.join(" ")).toContain("1 saisie n'a pas encore été envoyée");
  // Lecture directe d'IndexedDB (chaîne évaluée dans la page : pas de types DOM ici).
  const left = await page.evaluate(`new Promise((resolve, reject) => {
    const open = indexedDB.open("wemeal-outbox");
    open.onerror = () => reject(open.error);
    open.onsuccess = () => {
      const count = open.result.transaction(["feedback"]).objectStore("feedback").count();
      count.onsuccess = () => resolve(count.result);
    };
  })`);
  expect(left).toBe(0);
});
