import { fileURLToPath, URL } from "node:url";

import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { VitePWA } from "vite-plugin-pwa";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    // Application installable et utilisable hors ligne sur le terrain : l'interface est mise en
    // cache, les lectures d'API repassent par le cache quand le réseau manque, et les saisies
    // attendent dans la file d'envoi (src/lib/outbox.ts).
    VitePWA({
      registerType: "autoUpdate",
      includeAssets: ["favicon.svg"],
      manifest: {
        name: "We MEAL",
        short_name: "We MEAL",
        description: "Suivi, évaluation, redevabilité et apprentissage des projets",
        lang: "fr",
        theme_color: "#0f766e",
        background_color: "#f8fafc",
        display: "standalone",
        start_url: "/",
        icons: [
          { src: "/icon-192.png", sizes: "192x192", type: "image/png" },
          { src: "/icon-512.png", sizes: "512x512", type: "image/png" },
          { src: "/icon-maskable-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
        ],
      },
      workbox: {
        // L'éditeur riche des TdR (le plus gros fichier) et la version anglaise ne sont pas
        // installés d'avance : ils se téléchargent à la première ouverture, puis restent en cache.
        globIgnores: ["**/RichEditor-*.js", "**/en-*.js"],
        navigateFallback: "/index.html",
        navigateFallbackDenylist: [/^\/api\//, /^\/health/],
        runtimeCaching: [
          {
            urlPattern: ({ url, request }) =>
              url.pathname.startsWith("/api/v1/orgs/") &&
              request.method === "GET" &&
              !url.pathname.includes("/export") &&
              // Photos, audios et vidéos des bénéficiaires : jamais gardés sur le téléphone.
              !url.pathname.includes("/evidence/") &&
              // Plaintes (contacts, signalements sensibles) et recherches de personnes : jamais
              // gardées sur le téléphone, qui peut être perdu ou partagé.
              !url.pathname.includes("/feedback") &&
              !url.pathname.includes("/personal-data") &&
              !url.pathname.includes("/sms"),
            handler: "NetworkFirst",
            options: {
              cacheName: "api",
              networkTimeoutSeconds: 6,
              expiration: { maxEntries: 400, maxAgeSeconds: 7 * 24 * 3600 },
            },
          },
          {
            urlPattern: ({ url }) => /\/assets\/(RichEditor|en)-.*\.js$/.test(url.pathname),
            handler: "CacheFirst",
            options: { cacheName: "lazy-assets", expiration: { maxEntries: 20 } },
          },
        ],
      },
    }),
  ],
  resolve: { alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) } },
  server: {
    proxy: { "/api": "http://localhost:8000" },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test-setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
  },
});
