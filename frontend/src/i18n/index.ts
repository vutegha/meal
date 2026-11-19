import i18n from "i18next";
import { initReactI18next } from "react-i18next";

import { fr } from "./fr";

// Seul le français, langue de l'interface, part avec l'application. L'anglais est un fichier à
// part, chargé seulement si on le demande (`setLanguage("en")`).
void i18n.use(initReactI18next).init({
  resources: { fr: { translation: fr } },
  lng: "fr",
  fallbackLng: "fr",
  interpolation: { escapeValue: false },
});

const loaders: Record<string, () => Promise<Record<string, unknown>>> = {
  en: () => import("./en").then((m) => m.en),
};

export async function setLanguage(lng: string): Promise<void> {
  if (!i18n.hasResourceBundle(lng, "translation") && loaders[lng])
    i18n.addResourceBundle(lng, "translation", await loaders[lng](), true, true);
  await i18n.changeLanguage(lng);
}

export default i18n;
