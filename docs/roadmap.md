# Découpage en tickets

Chaque étape est livrée par une ou plusieurs pull requests relues, testées et déployables.

## Étape 1 : fondations
- [x] 1.1 Documentation : architecture, modèle de données, tickets, ADR
- [x] 1.2 Backend FastAPI : configuration, base de données, migrations Alembic
- [x] 1.3 Authentification : inscription (utilisateur + organisation), connexion, rafraîchissement, profil
- [x] 1.4 Organisations et membres : liste, création, modification, ajout/changement de rôle/retrait de membres
- [x] 1.5 Journal d'audit et sa consultation
- [x] 1.6 Tests d'isolation entre organisations
- [x] 1.7 Worker ARQ (squelette)
- [x] 1.8 Frontend : connexion, inscription, tableau de bord, gestion des membres, i18n français
- [x] 1.9 Docker Compose (Postgres + pgvector, Redis, MinIO, API, worker, Caddy)
- [x] 1.10 CI GitHub Actions : lint, typage, tests, build
- [x] 1.11 Données de démonstration (livrées avec l'étape 2)

## Étape 2 : cadre logique manuel
- [x] 2.1 Projets (CRUD, statut, devise, zones, groupes cibles)
- [x] 2.2 Arbre du cadre logique (objectifs → résultats → activités → sous-activités)
- [x] 2.3 Lignes budgétaires, dépenses, synthèse prévu/dépensé par activité
- [x] 2.4 Indicateurs, valeurs périodiques désagrégées, calcul du taux d'atteinte
- [x] 2.5 Export XLSX du cadre logique, du budget et des indicateurs ; contrôles de cohérence
- [x] 2.8 Données de démonstration (`uv run python -m app.scripts.seed`)
- [ ] 2.6 Row Level Security PostgreSQL sur les tables métier (PR dédiée, avec un rôle applicatif non propriétaire)
- [ ] 2.7 Client API TypeScript généré depuis l'OpenAPI ; composants shadcn/ui
- [ ] 2.9 Cibles par période, multi-devises et taux de change, export PDF

## Étape 3 : import et extraction IA
- [x] 3.1 Upload (stockage local ou S3/MinIO), extraction du texte page par page (PyMuPDF, python-docx, openpyxl, texte)
- [x] 3.2 Indexation et recherche plein texte en français (PostgreSQL `tsvector`)
- [x] 3.3 Couche `llm/` : client Claude, sorties structurées, cache de prompt, journal des coûts, plafond mensuel par organisation
- [x] 3.4 Extraction du cadre logique, du budget et des indicateurs avec citations vérifiées dans le texte
- [x] 3.5 Écran de validation des propositions (sélection en cascade, titres modifiables, application ou rejet)
- [x] 3.6 Jeu d'évaluation des prompts (`uv run python -m app.llm.evals.run`, clé API requise)
- [ ] 3.7 OCR des documents scannés (aujourd'hui refusés avec un message explicite)
- [ ] 3.8 Recherche sémantique pgvector, si la recherche plein texte ne suffit pas pour les TdR et rapports
- [ ] 3.9 Suivi de l'usage IA dans l'interface d'administration (l'API `GET /orgs/{id}/ai/usage` existe)

## Étape 4 : TdR
- [x] 4.1 Modèle de sections des TdR (12 sections, dont redevabilité et protection)
- [x] 4.2 Rédaction IA d'un TdR par activité : cadre logique, indicateurs, passages des documents, consignes ; budget calculé depuis le budget du projet
- [x] 4.3 Édition par section, versions, circuit de validation (soumission, approbation, renvoi commenté, réouverture)
- [x] 4.4 Export Word (python-docx) et PDF (PyMuPDF, sans dépendance système)
- [ ] 4.5 Modèles de sections et de mise en page propres à chaque organisation
- [ ] 4.6 Éditeur riche (TipTap) à la place du Markdown simple

## Étape 5 : exécution et collecte
- [x] 5.1 Exécution d'activité : dates, lieu et position GPS, participants désagrégés (sexe, âge, handicap), déroulement et écarts, dépenses réelles rattachées
- [x] 5.2 Dépôt de preuves : photos (date et GPS lus dans l'EXIF, vignette WebP sans métadonnées), consentement, comptes rendus et listes de présence dont le texte est extrait
- [x] 5.3 PWA hors ligne (vite-plugin-pwa/Workbox, file d'envoi Dexie/IndexedDB), synchronisation idempotente par `client_uuid`
- [ ] 5.4 Floutage automatique des visages
- [ ] 5.5 Audio et vidéo ; compression des photos côté téléphone avant envoi
- [ ] 5.6 Formulaires de collecte personnalisables (enquêtes, suivi post-distribution)

## Étape 6 : rapport narratif
- [x] 6.1 Rédaction IA traçable prévu/réalisé : chaque fait renvoie à sa source (notes [S1], TdR, comptes rendus, photos [P1]) ; renvois inconnus signalés, manques listés ; participants et budget calculés
- [x] 6.2 Édition, versions, circuit de validation, export Word et PDF avec les photos consenties
- [x] 6.3 Valeurs d'indicateurs proposées depuis les sources, vérifiées puis enregistrées ; tableau de bord du projet (budget, activités, personnes atteintes, indicateurs, suivi par activité)
- [ ] 6.4 Tests de bout en bout Playwright du parcours complet dans la CI

## Étape 7 : agrégation et redevabilité
- 7.1 Rapports périodiques et bailleur
- 7.2 Registre des plaintes et retours
- 7.3 Registre des leçons apprises
