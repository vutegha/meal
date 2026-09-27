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
- [x] 2.6 Row Level Security PostgreSQL sur les tables métier : rôle applicatif `meal_app` non propriétaire, organisation positionnée à chaque transaction, tests dédiés
- [ ] 2.7 Client API TypeScript généré depuis l'OpenAPI ; composants shadcn/ui
- [x] 2.9 Cibles intermédiaires par période (atteint et taux par période) ; taux de change du projet et dépenses saisies en devise étrangère, converties au taux en vigueur ou saisi, montant d'origine conservé ; export PDF et Word du cadre logique, des indicateurs et du budget

## Étape 3 : import et extraction IA
- [x] 3.1 Upload (stockage local ou S3/MinIO), extraction du texte page par page (PyMuPDF, python-docx, openpyxl, texte)
- [x] 3.2 Indexation et recherche plein texte en français (PostgreSQL `tsvector`)
- [x] 3.3 Couche `llm/` : client Claude, sorties structurées, cache de prompt, journal des coûts, plafond mensuel par organisation
- [x] 3.4 Extraction du cadre logique, du budget et des indicateurs avec citations vérifiées dans le texte
- [x] 3.5 Écran de validation des propositions (sélection en cascade, titres modifiables, application ou rejet)
- [x] 3.6 Jeu d'évaluation des prompts (`uv run python -m app.llm.evals.run`, clé API requise)
- [x] 3.7 OCR des documents scannés et des photos de pages : page rendue en image puis lue par Claude (vision), sans dépendance système ; pages peu lisibles signalées ; 40 pages au plus par document (`OCR_MAX_PAGES`)
- [x] 3.8 Recherche sémantique pgvector (embeddings Voyage AI, facultatifs : `VOYAGE_API_KEY`) fusionnée avec le plein texte (RRF) pour la recherche de documents et les passages des TdR ; pages vectorisées à la demande, coûts journalisés ; sans clé ou en cas de panne, plein texte seul
- [x] 3.9 Suivi de l'usage IA dans l'administration : coût du mois et plafond, six derniers mois, répartition par usage et par projet, derniers appels

## Étape 4 : TdR
- [x] 4.1 Modèle de sections des TdR (12 sections, dont redevabilité et protection)
- [x] 4.2 Rédaction IA d'un TdR par activité : cadre logique, indicateurs, passages des documents, consignes ; budget calculé depuis le budget du projet
- [x] 4.3 Édition par section, versions, circuit de validation (soumission, approbation, renvoi commenté, réouverture)
- [x] 4.4 Export Word (python-docx) et PDF (PyMuPDF, sans dépendance système)
- [x] 4.5 Modèles de sections (titres, ordre, consignes transmises à l'IA) et de mise en page (en-tête, pied de page, couleur, numéros de page) propres à chaque organisation, pour les TdR et les rapports
- [x] 4.6 Éditeur riche (TipTap) des TdR et rapports : intertitres, gras, listes, tableaux ; contenu toujours enregistré en Markdown simple (mêmes exports), bascule vers le texte brut ; chargé à la demande

## Étape 5 : exécution et collecte
- [x] 5.1 Exécution d'activité : dates, lieu et position GPS, participants désagrégés (sexe, âge, handicap), déroulement et écarts, dépenses réelles rattachées
- [x] 5.2 Dépôt de preuves : photos (date et GPS lus dans l'EXIF, vignette WebP sans métadonnées), consentement, comptes rendus et listes de présence dont le texte est extrait
- [x] 5.3 PWA hors ligne (vite-plugin-pwa/Workbox, file d'envoi Dexie/IndexedDB), synchronisation idempotente par `client_uuid`
- [x] 5.4 Floutage automatique des visages sur les vignettes (affichage et rapports), détecteurs OpenCV locaux ; original réservé aux responsables et à l'auteur ; visages montrés seulement avec consentement, refloutés si le consentement est retiré ; reprise des anciennes photos : `uv run python -m app.scripts.blur_faces`
- [x] 5.5 Audio et vidéo (mémos vocaux, vidéos du téléphone, 200 Mo au plus : `MAX_MEDIA_MB`), écoutés et vus dans l'application, consentement demandé ; photos réduites (2048 px, JPEG) sur le téléphone avant la file d'envoi, date et position lues dans l'EXIF avant compression
- [x] 5.6 Formulaires de collecte personnalisables (enquêtes, suivi post-distribution) : questions texte, nombre, choix unique ou multiple, oui/non, date ; publication et clôture ; saisie hors ligne par la file d'envoi ; synthèse par question, tableau des réponses, export Excel ; questions figées une fois des réponses reçues

## Étape 6 : rapport narratif
- [x] 6.1 Rédaction IA traçable prévu/réalisé : chaque fait renvoie à sa source (notes [S1], TdR, comptes rendus, photos [P1]) ; renvois inconnus signalés, manques listés ; participants et budget calculés
- [x] 6.2 Édition, versions, circuit de validation, export Word et PDF avec les photos consenties
- [x] 6.3 Valeurs d'indicateurs proposées depuis les sources, vérifiées puis enregistrées ; tableau de bord du projet (budget, activités, personnes atteintes, indicateurs, suivi par activité)
- [x] 6.4 Tests de bout en bout Playwright du parcours complet dans la CI (`npm run e2e`, faux modèle IA, base `meal_e2e`)

## Étape 7 : agrégation et redevabilité
- [x] 7.1 Rapports périodiques (mensuel, trimestriel, annuel) et bailleur : tableaux calculés (activités de la période, indicateurs sur la période et en cumul, budget prévu, dépensé sur la période et cumulé), texte rédigé par l'IA à partir des rapports d'activité, des retours et des leçons, avec renvois aux sources ; même circuit de validation et mêmes exports que les autres documents
- [x] 7.2 Registre des plaintes et retours : référence, canal, type, délai de réponse (14 jours, 3 pour les cas sensibles), attribution, réponse, statistiques ; cas sensibles (fraude, exploitation et abus sexuels, sécurité) visibles des seuls responsables et personnes concernées ; contact masqué
- [x] 7.3 Registre des leçons apprises : recherche, étiquettes, lien avec l'activité et le rapport d'origine ; API de consultation à l'échelle de l'organisation
- [x] 7.4 Écran des leçons de toute l'organisation : recherche, étiquettes, filtre par projet, lien vers le projet
- [x] 7.5 Classification IA des retours (modèle léger, seul le texte est envoyé ; catégorie sensible forcée confidentielle et urgente) et saisie hors ligne des retours par la file d'envoi
- [x] 7.6 Modèles propres à chaque bailleur, choisis selon le bailleur du projet, ou au cas par cas pour un rapport périodique
