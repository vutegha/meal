import { defineConfig, devices } from "@playwright/test";

// Parcours complet contre la vraie API (base PostgreSQL dédiée, faux modèle IA).
const database =
  process.env.E2E_DATABASE_URL ?? "postgresql+asyncpg://meal:meal@localhost:5432/meal_e2e";

export default defineConfig({
  testDir: "./e2e",
  timeout: 120_000,
  expect: { timeout: 20_000 },
  fullyParallel: false,
  retries: 0,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: "http://localhost:5173",
    locale: "fr-FR",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "chromium",
      testIgnore: /hors-ligne/,
      use: { ...devices["Desktop Chrome"] },
    },
    {
      // Version construite, avec le service worker : réouverture de l'application sans réseau.
      name: "hors-ligne",
      testMatch: /hors-ligne/,
      use: { ...devices["Desktop Chrome"], baseURL: "http://localhost:4173" },
    },
  ],
  webServer: [
    {
      command: "uv run alembic upgrade head && uv run python -m tests.e2e_server",
      cwd: "../backend",
      url: "http://localhost:8000/health",
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
      env: {
        DATABASE_URL: database,
        JOBS_INLINE: "true",
        SECRET_KEY: "e2e-secret-key-not-used-outside-tests-0123456789",
        STORAGE_LOCAL_PATH: "/tmp/wemeal-e2e-files",
      },
    },
    {
      command: "npm run dev -- --port 5173 --strictPort",
      url: "http://localhost:5173",
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
    },
    {
      command: "npx vite build && npx vite preview --port 4173 --strictPort",
      url: "http://localhost:4173",
      reuseExistingServer: !process.env.CI,
      timeout: 240_000,
    },
  ],
});
