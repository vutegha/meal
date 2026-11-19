# Sous-traitants

Services externes qui peuvent recevoir des données, selon la configuration du serveur (`.env`).
Sans clé ou avec le mode « simulated », aucun envoi n'a lieu.

| Service | Données envoyées | Quand | Comment le couper |
| --- | --- | --- | --- |
| Hébergeur du serveur `[nom, pays]` | Toutes (base, fichiers, sauvegardes) | Toujours | — |
| Anthropic (États-Unis) | Textes des documents de projet (pages scannées en image, pour les lire), notes, texte des retours à classer, brouillons de rapport | Fonctions d'IA | Page *Données personnelles* : « Utiliser l'IA » ; ou `ANTHROPIC_API_KEY` vide |
| Voyage AI (États-Unis) | Extraits de texte pour la recherche | Recherche sémantique | Même réglage ; ou `VOYAGE_API_KEY` vide |
| Twilio (États-Unis) | Numéro et texte des SMS ou WhatsApp | Plaintes par SMS | `SMS_PROVIDER` / `WHATSAPP_PROVIDER` à `simulated` |
| Africa's Talking (Kenya) | Numéro et texte des SMS | Plaintes par SMS | `SMS_PROVIDER` à `simulated` |
| Meta, WhatsApp Cloud API (États-Unis) | Numéro et texte des messages | Plaintes par WhatsApp | `WHATSAPP_PROVIDER` à `simulated` |
| Fournisseur SMTP `[nom]` | Adresse e-mail, lien de réinitialisation | Mot de passe oublié | `SMTP_HOST` vide |

Ce qui n'est jamais envoyé à l'IA : listes de présence, photos de personnes, contacts des
plaignants, réponses aux formulaires.

Pour chaque service actif, l'organisation doit disposer d'un contrat de sous-traitance (DPA) et,
hors Union européenne, de garanties de transfert (clauses contractuelles types). `[Lien vers les
contrats signés]`.
