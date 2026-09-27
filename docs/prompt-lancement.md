# Prompt de lancement : application MEAL

> **Hypothèse de lecture.** « MEAL » est compris ici au sens humanitaire et développement : *Monitoring, Evaluation, Accountability and Learning* (Suivi, Évaluation, Redevabilité et Apprentissage). C'est cohérent avec le README du dépôt (« design to facilitate meal activities for organizations »). Si le sens visé est différent, corriger la section 1 avant d'utiliser ce prompt.

Copier tout ce qui suit la ligne horizontale et le donner tel quel à l'agent de développement (Claude Code ou autre), à la racine du dépôt `vutegha/meal`.

---

## 1. Rôle et contexte

Tu es un·e architecte logiciel et développeur·se full-stack senior, avec une bonne connaissance des pratiques MEAL des ONG et agences de développement (cadre logique, théorie du changement, indicateurs SMART, plans de suivi, redevabilité envers les communautés, standards type CHS et IATI).

Tu démarres le développement de **« We MEAL »**, une application web multi-organisations qui accompagne tout le cycle d'un projet :

1. **Planifier** : à partir d'un document de projet (proposition, note conceptuelle, cadre logique), le système *déduit* les résultats, les activités, le budget associé à chaque activité et les indicateurs.
2. **Préparer** : pour chaque activité planifiée, le système *produit les Termes de Référence (TdR)*.
3. **Exécuter et documenter** : après l'activité, l'équipe terrain fournit les éléments (rapports bruts, comptes rendus, listes de présence, photos, audios, données chiffrées, autres informations contextuelles).
4. **Rapporter** : le système en *dégage un rapport narratif* de l'activité, relié aux indicateurs et au budget, puis agrège ces rapports au niveau projet.

Le dépôt est actuellement vide (seulement un README). Tu poses toutes les fondations.

## 2. Périmètre fonctionnel

### 2.1 Organisations, utilisateurs et droits
- Multi-tenant : chaque organisation a ses projets, utilisateurs et modèles de documents, isolés des autres.
- Rôles : administrateur d'organisation, chef de projet, chargé MEAL, agent terrain, finance, lecteur (bailleur ou partenaire, en lecture seule).
- Journal d'audit de toutes les modifications (qui, quoi, quand) pour la redevabilité.

### 2.2 Projet et cadre logique
- Import d'un document de projet (PDF, DOCX, XLSX) ou saisie manuelle.
- **Extraction assistée par IA** : objectif général, objectifs spécifiques, résultats attendus, activités, sous-activités, hypothèses et risques, zones géographiques, groupes cibles, durée.
- Chaque élément extrait est présenté comme **proposition à valider** (accepter, modifier, rejeter), avec la citation du passage source. Rien n'est enregistré comme définitif sans validation humaine.
- Vue arborescente du cadre logique et export au format tableau (XLSX, PDF).

### 2.3 Budget
- Lignes budgétaires rattachées aux activités (quantité, coût unitaire, fréquence, devise, ligne bailleur).
- Déduction assistée du budget par activité quand le document source contient un budget ; sinon, proposition d'une estimation marquée comme telle.
- Suivi prévu / engagé / dépensé, taux d'exécution, alertes de dépassement.
- Multi-devises avec taux de change daté.

### 2.4 Indicateurs et plan de suivi
- Indicateurs par niveau (impact, effet, extrant, activité) : définition, formule, unité, désagrégations (sexe, âge, handicap, zone), baseline, cibles par période, source et méthode de collecte, fréquence, responsable.
- Proposition IA d'indicateurs SMART pour chaque résultat et activité, avec contrôle de cohérence (chaque résultat a au moins un indicateur, chaque indicateur a une source de vérification).
- Saisie des valeurs réalisées, calcul automatique des taux d'atteinte, tableau de bord.

### 2.5 Termes de Référence (TdR)
- Génération d'un TdR pour toute activité planifiée : contexte, justification, objectifs, résultats attendus, méthodologie, participants et critères de sélection, lieu et dates, budget détaillé (issu des lignes budgétaires), indicateurs concernés, responsabilités, livrables, calendrier, considérations de protection et de genre.
- Modèles de TdR personnalisables par organisation (le modèle définit la structure, l'IA remplit le contenu).
- Édition en ligne, historique des versions, circuit de validation (brouillon, en revue, approuvé).
- Export DOCX et PDF à la charte de l'organisation.

### 2.6 Exécution et collecte de preuves
- Pour chaque activité réalisée : dépôt de comptes rendus, rapports bruts, listes de présence, photos, audios, vidéos courtes, fichiers de données, notes libres.
- Formulaire de collecte **utilisable hors ligne** sur mobile (PWA) avec synchronisation différée, pour les zones à faible connectivité.
- Métadonnées extraites automatiquement : date, géolocalisation (EXIF), auteur.
- Saisie des données réelles : participants désagrégés, dépenses réelles, valeurs d'indicateurs.
- Consentement et protection : case de consentement pour les photos de personnes, floutage optionnel des visages, pas de données personnelles sensibles dans les prompts IA sans nécessité.

### 2.7 Rapport narratif d'activité
- Génération à partir de toutes les pièces : TdR (le prévu) comparé aux éléments fournis (le réalisé).
- Structure : résumé, déroulement, participation (chiffres désagrégés), résultats obtenus, contribution aux indicateurs, écarts par rapport au TdR et explications, exécution budgétaire, difficultés, leçons apprises, recommandations, citations de bénéficiaires, annexes photo avec légendes générées.
- **Traçabilité** : chaque affirmation du rapport renvoie à la pièce source (document, page, photo). Les informations manquantes sont signalées comme telles, jamais inventées.
- Édition, validation, export DOCX et PDF.
- Agrégation : rapports périodiques (mensuel, trimestriel) et rapport bailleur au niveau projet à partir des rapports d'activité validés.

### 2.8 Redevabilité et apprentissage
- Registre des plaintes et retours communautaires (canal, catégorie, sensibilité, suivi, délai de réponse).
- Registre des leçons apprises, alimenté par les rapports narratifs, consultable et filtrable.

## 3. Principes de conception de l'IA
- L'IA **propose**, l'humain **valide**. Chaque sortie IA est un brouillon typé, validé explicitement.
- Sorties **structurées** : l'IA répond selon un schéma JSON strict (via l'appel d'outils de l'API), validé côté serveur par Pydantic avant enregistrement.
- **Ancrage sur les sources** : les documents importés sont découpés, indexés (recherche vectorielle) et cités ; interdiction de produire un chiffre sans source.
- **Choix du modèle selon la tâche** pour l'efficacité et le coût :
  - `claude-opus-5-5` : extraction du cadre logique et du budget sur de longs documents, rapports agrégés.
  - `claude-sonnet-5` : TdR et rapports narratifs d'activité.
  - `claude-haiku-4-5-20251001` : tâches courtes et volumineuses (légendes de photos, classification des plaintes, résumés de pièces).
- Mise en cache des prompts pour le contexte projet réutilisé, génération en tâche de fond avec streaming de l'avancement vers l'interface.
- Couche d'abstraction `llm/` pour pouvoir changer de fournisseur ou de modèle sans toucher au métier.
- Prompts versionnés dans le dépôt, avec un jeu de tests d'évaluation (documents de projet d'exemple et sorties attendues).

## 4. Stack technique recommandée

Critères : performance, efficacité de développement, robustesse hors ligne, coût d'hébergement faible, écosystème IA et génération de documents.

| Couche | Choix | Justification |
|---|---|---|
| Backend API | **Python 3.12 + FastAPI** (async), Pydantic v2 | Parmi les frameworks Python les plus rapides ; validation stricte des schémas, idéale pour les sorties IA structurées ; meilleur écosystème pour l'IA, le traitement de documents et les données. Documentation OpenAPI automatique. |
| ORM et migrations | SQLAlchemy 2 (async) + Alembic | Mature, performant, migrations versionnées. |
| Base de données | **PostgreSQL 16** + extension **pgvector** | Relationnel solide pour cadre logique, budget et indicateurs ; JSONB pour les champs flexibles (désagrégations, formulaires) ; recherche vectorielle dans la même base, sans service supplémentaire. Row Level Security pour l'isolation multi-tenant. |
| Tâches de fond | **Redis** + **ARQ** (ou Celery si besoin de planification complexe) | Les générations IA, l'OCR et les exports ne bloquent pas l'API ; ARQ est async natif et léger. |
| Stockage fichiers | Stockage objet compatible S3 (**MinIO** en auto-hébergé, ou S3/R2) | Photos et pièces volumineuses hors base ; URLs signées ; compression et vignettes WebP à l'upload. |
| Frontend | **React 19 + TypeScript + Vite**, TanStack Query et TanStack Router, Tailwind CSS + shadcn/ui | Build rapide, bundle léger, typage de bout en bout (client généré depuis l'OpenAPI). |
| Mobile / terrain | **PWA** (Workbox) + **IndexedDB via Dexie** | Une seule base de code, installable sur Android, collecte hors ligne et synchronisation différée ; pas de publication sur store nécessaire. Passage à React Native possible plus tard si besoin natif. |
| Éditeur de documents | TipTap (ProseMirror) | Édition riche des TdR et rapports, stockage en JSON structuré. |
| Génération de documents | **docxtpl** (DOCX à partir de modèles Word de l'organisation) + **WeasyPrint** (PDF) | Les organisations fournissent leur propre modèle Word ; rendu fidèle et contrôlable. |
| Extraction de documents | PyMuPDF, python-docx, openpyxl ; OCR Tesseract pour les scans | Rapide et local ; l'IA ne reçoit que du texte propre et découpé. |
| IA | API Anthropic (Claude), SDK Python officiel | Qualité rédactionnelle en français, contexte long pour les documents de projet, lecture d'images pour les photos, sorties structurées par appel d'outils. |
| Authentification | JWT (access + refresh) avec rôles en base ; SSO via OIDC (Keycloak) en option | Simple au départ, compatible avec les annuaires des grandes organisations. |
| Déploiement | Docker Compose, reverse proxy **Caddy** (HTTPS automatique) | Démarre sur un seul VPS peu coûteux, évolue vers Kubernetes si nécessaire. |
| Qualité | Ruff, mypy, pytest (backend) ; ESLint, Vitest, Playwright (frontend) ; GitHub Actions | Contrôles rapides à chaque PR. |
| Observabilité | Logs structurés JSON, Sentry, suivi du coût et de la latence de chaque appel IA | Maîtrise des coûts IA par organisation. |

Alternative écartée : Laravel ou Django monolithique, plus rapides à démarrer pour du CRUD, mais moins adaptés au traitement asynchrone intensif et à l'écosystème IA ; Node/NestJS, bon en performance mais écosystème de traitement de documents et d'IA moins riche qu'en Python.

## 5. Architecture et organisation du dépôt

Monorepo :

```
/backend
  app/
    api/           # routes FastAPI par module
    core/          # config, sécurité, tenancy
    models/        # SQLAlchemy
    schemas/       # Pydantic (y compris schémas des sorties IA)
    services/      # logique métier (logframe, budget, indicateurs, tdr, rapports)
    llm/           # client IA, prompts versionnés, sélection de modèle
    documents/     # extraction, découpage, indexation, génération DOCX/PDF
    workers/       # tâches ARQ
  migrations/
  tests/
/frontend
  src/ (routes, features par module, composants, client API généré, stockage hors ligne)
/templates         # modèles DOCX par défaut (TdR, rapport narratif)
/docs              # décisions d'architecture (ADR), modèle de données
docker-compose.yml
```

Entités principales du modèle de données : Organisation, Utilisateur, Rôle, Projet, Document source, Fragment indexé, Objectif, Résultat, Activité, Ligne budgétaire, Dépense, Indicateur, Cible, Valeur mesurée, TdR (versions), Exécution d'activité, Pièce justificative, Rapport narratif (versions), Plainte/retour, Leçon apprise, Journal d'audit, Appel IA (modèle, jetons, coût, durée).

## 6. Exigences non fonctionnelles
- **Performance** : API p95 < 200 ms hors appels IA ; pages chargées en < 2 s sur 3G ; génération d'un TdR < 60 s, d'un rapport narratif < 2 min, avec progression visible.
- **Hors ligne** : la collecte terrain fonctionne sans réseau et se synchronise sans perte ni doublon.
- **Sécurité** : isolation stricte des organisations (tests dédiés), chiffrement en transit, URLs de fichiers signées et expirantes, protection des données personnelles des bénéficiaires.
- **Langues** : interface en français par défaut, prête pour l'anglais (i18n) ; documents générés dans la langue choisie par projet.
- **Accessibilité** : WCAG 2.1 AA sur les écrans principaux.
- **Coûts IA** : plafond configurable par organisation, journalisé.

## 7. Plan de livraison

Travaille par incréments, chacun livré dans une pull request relue, testée et déployable.

1. **Fondations** : monorepo, Docker Compose (Postgres, Redis, MinIO), FastAPI et React initialisés, authentification, organisations et rôles, CI.
2. **Cadre logique manuel** : projets, objectifs, résultats, activités, indicateurs, budget ; saisie et vues.
3. **Import et extraction IA** : upload de documents, extraction du texte, indexation, proposition du cadre logique, du budget et des indicateurs avec écran de validation.
4. **TdR** : génération, édition, validation, export DOCX/PDF avec modèle.
5. **Exécution** : dépôt des pièces, collecte PWA hors ligne, saisie du réalisé.
6. **Rapport narratif** : génération traçable, édition, validation, export ; tableau de bord des indicateurs et du budget.
7. **Agrégation et redevabilité** : rapports périodiques et bailleur, registre des plaintes, leçons apprises.

## 8. Critères d'acceptation du MVP (étapes 1 à 6)
- À partir d'un document de projet PDF réel, l'application propose un cadre logique avec activités, budget par activité et indicateurs, chaque élément citant sa source, et l'utilisateur peut tout valider ou corriger.
- Pour une activité validée, un TdR complet est généré et exporté en DOCX au modèle de l'organisation.
- Après dépôt d'un compte rendu, d'une liste de présence et de photos (y compris depuis un téléphone hors ligne), un rapport narratif est généré, compare prévu et réalisé, met à jour les indicateurs et l'exécution budgétaire, et signale les informations manquantes au lieu de les inventer.
- Deux organisations ne voient jamais les données l'une de l'autre (tests automatisés).
- La CI est verte : lint, typage, tests unitaires et tests de bout en bout du parcours principal.

## 9. Consignes de travail
- Commence par écrire `docs/architecture.md` et le schéma de données, puis propose le découpage en tickets avant de coder l'étape 1.
- Pose les questions bloquantes au début ; pour le reste, choisis une valeur par défaut raisonnable et documente-la dans un ADR.
- Code, commentaires techniques et noms en anglais ; interface utilisateur et documents générés en français.
- Écris les tests en même temps que le code. Ne commite jamais de secrets (`.env.example` uniquement).
- Fournis des données de démonstration (une organisation, un projet type avec document source, quelques activités) pour tester le parcours complet.
