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
- [ ] 1.11 Données de démonstration (reportées à l'étape 2, quand il y aura des projets)

## Étape 2 : cadre logique manuel
- 2.1 Projets (CRUD, statut, devise, zones, groupes cibles)
- 2.2 Arbre du cadre logique (objectifs → résultats → activités → sous-activités)
- 2.3 Lignes budgétaires, taux de change, prévu/engagé/dépensé
- 2.4 Indicateurs, cibles, valeurs, calcul du taux d'atteinte
- 2.5 Export XLSX/PDF du cadre logique
- 2.6 Row Level Security PostgreSQL sur les tables métier
- 2.7 Client API TypeScript généré depuis l'OpenAPI ; composants shadcn/ui
- 2.8 Données de démonstration

## Étape 3 : import et extraction IA
- 3.1 Upload vers S3, extraction du texte (PyMuPDF, python-docx, openpyxl, OCR)
- 3.2 Découpage et indexation pgvector
- 3.3 Couche `llm/` : client Claude, sorties structurées, cache de prompt, journal des coûts
- 3.4 Extraction du cadre logique, du budget et des indicateurs avec citations
- 3.5 Écran de validation des propositions
- 3.6 Jeu d'évaluation des prompts

## Étape 4 : TdR
- 4.1 Modèles DOCX par organisation
- 4.2 Génération IA d'un TdR par activité
- 4.3 Éditeur TipTap, versions, circuit de validation
- 4.4 Export DOCX (docxtpl) et PDF (WeasyPrint)

## Étape 5 : exécution et collecte
- 5.1 Exécution d'activité, participants désagrégés, dépenses réelles
- 5.2 Dépôt de pièces, EXIF, vignettes WebP, consentement, floutage
- 5.3 PWA hors ligne (Workbox, Dexie), synchronisation idempotente

## Étape 6 : rapport narratif
- 6.1 Génération traçable prévu/réalisé, informations manquantes signalées
- 6.2 Édition, validation, export
- 6.3 Mise à jour des indicateurs et de l'exécution budgétaire ; tableaux de bord
- 6.4 Tests de bout en bout Playwright du parcours complet

## Étape 7 : agrégation et redevabilité
- 7.1 Rapports périodiques et bailleur
- 7.2 Registre des plaintes et retours
- 7.3 Registre des leçons apprises
