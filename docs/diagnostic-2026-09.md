# Diagnostic du système We MEAL (29 septembre 2026)

Analyse faite sur la branche de la PR #3 (`claude/project-thread-4oeozf`, pas encore fusionnée).
Légende : **[V]** vérifié (code lu ou commande exécutée), **[S]** supposé.

## 1. État général

| Contrôle | Résultat |
|---|---|
| Tests backend (pytest) | 75 réussis sur une base PostgreSQL 16 + pgvector [V] |
| Lint, format, typage backend (ruff, mypy) | aucun problème [V] |
| Migrations 0001 → 0014 aller-retour, `alembic check` | OK [V] |
| Tests frontend (vitest), lint, typecheck | 28 réussis, 0 erreur [V] |
| Build frontend | OK, mais bundle principal de 739 kB (220 kB gzip) [V] |
| `npm audit` | 0 vulnérabilité [V] |
| CI GitHub de la PR #3 (backend, frontend, e2e) | verte [V] |
| API + données de démo | démarre, `/health` répond, connexion de démo OK [V] |

Le socle est sain : isolation entre organisations solide (chaque route vérifie
l'appartenance puis le projet, et la Row Level Security PostgreSQL est réellement active à
l'exécution via le rôle `meal_app`), pas de XSS trouvée dans l'interface, exports PDF
échappés. Les faiblesses se concentrent sur le mode hors ligne, les sessions, quelques règles
métier de confidentialité et l'exploitation en production.

## 2. Problèmes à corriger en priorité

### Critique

1. **L'application ne s'ouvre pas hors ligne** [V, lecture de code].
   Au démarrage, `loadMe` (`frontend/src/router.tsx:32-39`) appelle `/auth/me` ; ce
   chemin n'est pas mis en cache par le service worker (`vite.config.ts:36-50`, seul
   `/api/v1/orgs/*` l'est). Sans réseau, l'appel échoue, le jeton est effacé et l'agent est
   renvoyé à la connexion, qui exige le réseau. Un agent qui rouvre l'application sur le
   terrain ne peut donc plus rien saisir. Le test e2e ne le voit pas (il tourne sans service
   worker et ne recharge jamais la page hors ligne).
2. **Une coupure réseau pendant le rafraîchissement du jeton déconnecte l'utilisateur** [V].
   `frontend/src/lib/api.ts:79-86` : `.catch(() => null)` puis `tokenStore.set(null)`.
   Fréquent en 2G/3G.
3. **Une plainte sensible peut être rendue visible de tous** [V].
   `backend/app/api/accountability.py:132` : la catégorie sensible (exploitation et abus
   sexuels, fraude, sécurité) n'impose la confidentialité que si `sensitive` n'est pas envoyé.
   Envoyer `sensitive=false` avec une catégorie sensible rend le retour visible par tous les
   membres. Le rejeu hors ligne (`client_uuid`, lignes 119-128) renvoie aussi l'entrée sans
   vérifier `can_see`.
4. **Données sensibles conservées sur le téléphone après déconnexion** [V].
   La file d'envoi hors ligne (IndexedDB `wemeal-outbox`) contient en clair les plaintes
   (description, contact) et n'est pas vidée à la déconnexion ; elle n'est pas liée à
   l'utilisateur, donc au login suivant les saisies de l'agent A partent avec le compte de
   l'agent B. Le cache du service worker garde 7 jours les réponses de l'API, photos de
   bénéficiaires comprises.

### Élevée

5. **Pas de limitation des tentatives de connexion** [V] : 7 mauvais mots de passe d'affilée
   donnent 7 réponses 401, sans blocage. Aucun limiteur dans le code ; mot de passe de
   connexion sans longueur maximale.
6. **Sessions non révocables** [V] : pas de déconnexion côté serveur, pas de changement ni
   de réinitialisation de mot de passe, refresh token réutilisable jusqu'à expiration et stocké
   dans `localStorage`. Le mot de passe initial fixé par l'administrateur reste valable.
7. **Injection de formules dans les exports Excel** [V] : `backend/app/api/forms.py:295` et
   `services/export.py` écrivent tel quel le texte saisi ; une réponse commençant par `=`
   devient une formule chez la personne qui ouvre l'export.
8. **Rôle de base de données en mode « superutilisateur » dans Docker** [V] :
   `POSTGRES_USER=meal` est superutilisateur ; si le rôle `meal_app` manquait, l'API
   tournerait sans RLS, sans erreur (`core/db.py:148-161`). Ajouter une vérification au
   démarrage et un compte de connexion dédié, non superutilisateur.
9. **Tâches de fond (IA) fragiles** [V] : une tâche interrompue reste « en cours » pour
   toujours, une relivraison relance l'appel IA et le refacture, une panne Redis laisse la
   tâche « en attente » ; ce chemin n'est jamais testé (`JOBS_INLINE=true` en test).
10. **Aucun en-tête de sécurité HTTP** [V] : pas de CSP, HSTS, `nosniff` ni
    `frame-ancestors` dans `frontend/Caddyfile`.

### Moyenne

11. Type de fichier des preuves déclaré par le client puis renvoyé « inline » ; nom de
    fichier utilisé dans la clé de stockage ; pas d'antivirus ; fichier de 200 Mo chargé en
    mémoire ; image « bombe » → erreur 500.
12. Plafond de dépense IA contournable par des appels simultanés ; classification IA des
    retours appelable sans limite par tout agent.
13. Un chef de projet peut soumettre puis approuver son propre TdR ou rapport ; pas de
    verrou contre une double approbation.
14. Listes non paginées (retours, exécutions, réponses aux formulaires, documents) et
    statistiques des retours calculées en mémoire ; numérotation `RET-xxxx` sujette aux
    collisions lors de synchronisations simultanées.
15. Saisie refusée par le serveur annoncée « envoyée » à l'agent (`ExecutionForm.tsx:311`,
    `FormsTab.tsx:431`).
16. Stockage hors ligne non persistant (`navigator.storage.persist()` jamais appelé) : iOS
    peut effacer les saisies non envoyées.
17. Bundle unique de 739 kB : toutes les pages chargées au premier écran, lent en 3G.
18. Ajout d'un utilisateur existant à une organisation sans son accord.

### Faible

19. `SECRET_KEY` par défaut non refusée hors Docker ; `/api/docs` public en production.
20. `/health` ne vérifie ni la base ni Redis ; aucun journal structuré ni suivi des erreurs
    (Sentry) ; migrations lancées au démarrage de l'API.
21. Interface anglaise traduite mais inaccessible (langue forcée en français).
22. Gros composants (FormsTab 897 lignes, FeedbackTab 575, BudgetTab 555) et types d'API
    écrits à la main en double du client généré.
23. Recherche sémantique : index vectoriel global filtré après coup, le rappel baissera
    quand plusieurs organisations auront beaucoup de documents.

## 3. Exploitation (Docker sous Windows)

- **PR #3 à fusionner** : `main` référence encore une image MinIO qui bloque le lancement.
- **Pas de sauvegarde** de la base ni des fichiers (volumes `db-data`, `files`). À prévoir :
  `pg_dump` quotidien + copie du volume, et un test de restauration.
- **Téléphones de terrain** : `https://localhost` ne sert que le poste lui-même. Pour que les
  agents installent l'application (PWA, service worker, appareil photo, GPS), il faut un vrai
  nom de domaine dans `SITE_ADDRESS` avec un certificat reconnu, donc un serveur accessible
  (VPS) plutôt que Docker Desktop.
- Ports 80/443 parfois déjà pris sous Windows (IIS, Skype) : prévoir une variable pour
  changer les ports.
- Pas de `healthcheck` sur l'API ; le worker et Caddy démarrent sans attendre qu'elle soit
  prête.
- Modèle de rédaction `claude-sonnet-5` : passer à `claude-sonnet-5-5`, plus récent.
- `ANTHROPIC_API_KEY` pas encore renseignée : aucune fonction IA n'a été testée avec un vrai
  modèle.

## 4. Recommandations, dans l'ordre

1. **Fiabiliser le terrain** : ouverture hors ligne (points 1, 2, 15, 16) et test e2e
   « rechargement hors ligne » sur la version construite.
2. **Protéger les personnes** : confidentialité forcée des plaintes sensibles (3), file et
   cache purgés et liés à l'utilisateur (4), formules neutralisées dans les exports (7).
3. **Sécuriser les comptes** : limitation des tentatives, refresh token révocable en cookie
   HttpOnly, déconnexion serveur, changement et réinitialisation du mot de passe (5, 6).
4. **Durcir l'infrastructure** : rôle DB non superutilisateur vérifié au démarrage (8),
   en-têtes de sécurité (10), uploads contrôlés côté serveur (11), `SECRET_KEY` validée.
5. **Exploiter sereinement** : fusion de la PR #3, sauvegardes automatiques, `/health`
   réel, Sentry, tâches IA idempotentes et reprises (9), pagination (14).
6. **Aller en production** : serveur avec domaine et HTTPS, clé Anthropic, essai pilote avec
   2 ou 3 agents sur un vrai projet.
7. **Améliorer l'usage** : séparation soumission/approbation (13), sélecteur de langue,
   chargement à la demande des pages, invitations par e-mail.
