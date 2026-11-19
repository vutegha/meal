import { createHmac } from "node:crypto";

import { expect, test } from "@playwright/test";

// Code TOTP (RFC 6238) calculé comme le ferait l'application d'authentification.
function totp(secret: string): string {
  const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";
  let bits = "";
  for (const char of secret) bits += alphabet.indexOf(char).toString(2).padStart(5, "0");
  const key = Buffer.from(bits.match(/.{8}/g)!.map((byte) => parseInt(byte, 2)));
  const counter = Buffer.alloc(8);
  counter.writeBigUInt64BE(BigInt(Math.floor(Date.now() / 30_000)));
  const digest = createHmac("sha1", key).update(counter).digest();
  const offset = digest[digest.length - 1]! & 0x0f;
  return String((digest.readUInt32BE(offset) & 0x7fffffff) % 1_000_000).padStart(6, "0");
}

test("mot de passe changé et double authentification", async ({ page }) => {
  const email = `compte-${Date.now()}@wemeal.org`;
  await page.goto("/register");
  await page.getByLabel("Nom complet").fill("Admin Sécurité");
  await page.getByLabel("Nom de votre organisation").fill("ONG sécurisée");
  await page.getByLabel("Adresse e-mail").fill(email);
  await page.getByLabel("Mot de passe").fill("motdepasse-e2e");
  await page.getByRole("button", { name: "Créer mon compte" }).click();

  // Administrateur sans double authentification : le bandeau l'y invite.
  await expect(page.getByText(/activez la double authentification/)).toBeVisible();
  await page.getByRole("link", { name: "Mon compte" }).first().click();

  await page.getByLabel("Mot de passe actuel").fill("motdepasse-e2e");
  await page.getByLabel("Nouveau mot de passe").fill("nouveau-mdp-e2e");
  await page.getByRole("button", { name: "Changer le mot de passe" }).click();
  await expect(page.getByText(/Mot de passe changé/)).toBeVisible();

  await page.getByRole("button", { name: "Activer" }).click();
  await expect(page.getByAltText("QR code de la double authentification")).toBeVisible();
  const secret = (await page.locator("code").textContent())!.trim();
  await page.getByLabel("Code de vérification").fill(totp(secret));
  await page.getByRole("button", { name: "Confirmer" }).click();
  await expect(page.getByText(/Active : un code vous est demandé/)).toBeVisible();

  await page.getByRole("button", { name: "Se déconnecter" }).click();
  await expect(page).toHaveURL(/\/login/);
  await page.getByLabel("Adresse e-mail").fill(email);
  await page.getByLabel("Mot de passe").fill("nouveau-mdp-e2e");
  await page.getByRole("button", { name: "Se connecter" }).click();
  await page.getByLabel("Code de vérification").fill(totp(secret));
  await page.getByRole("button", { name: "Se connecter" }).click();
  await expect(page.getByRole("heading", { name: "Projets" })).toBeVisible();
});
