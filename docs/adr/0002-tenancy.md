# ADR 0002 : isolation des organisations

- Statut : accepté
- Date : 2026-09-27

## Contexte
Plusieurs organisations partagent la même base. Une fuite de données entre organisations est le risque le plus grave de l'application.

## Décision
1. **Dès l'étape 1**, isolation applicative : toutes les routes métier sont sous `/api/v1/orgs/{org_id}/…` et passent par la dépendance `require_membership`, qui renvoie 404 si l'utilisateur n'est pas membre. Chaque requête SQL métier filtre sur `organization_id`.
2. **Dans une PR dédiée après l'étape 2**, ajout d'une défense en profondeur par Row Level Security PostgreSQL. Toutes les tables métier portent déjà `organization_id`. Il faut un rôle applicatif non propriétaire des tables, car le propriétaire et les superutilisateurs contournent la RLS. L'API positionne `SET LOCAL app.current_org` dans chaque transaction et des politiques RLS filtrent sur `organization_id`.
3. Des tests automatisés vérifient qu'un membre d'une organisation ne peut ni lire ni modifier les données d'une autre.

## Mise en œuvre de la RLS (migration 0008, `app/core/rls.py`)
- La connexion se fait avec le rôle propriétaire des tables (migrations, données de démonstration), puis chaque connexion de l'API endosse le rôle `meal_app` (`DB_APP_ROLE`), qui n'est pas propriétaire et subit donc la RLS. Le changement de rôle est sans effet tant que la migration n'a pas créé ce rôle.
- Chaque transaction reçoit `app.current_org` (positionné par `require_membership`, la création d'organisation et le worker via `bind_org`). Sans organisation liée, une session ne voit aucune ligne métier.
- Les tâches internes (worker avant de connaître l'organisation, données de démonstration) utilisent `system_session()`, qui positionne `app.system`. Aucune requête HTTP ne le fait.
- La politique `tenant_isolation` (lecture et écriture) couvre les 22 tables portant `organization_id`, sauf `memberships`. Toute nouvelle table portant `organization_id` doit l'ajouter dans sa migration avec `rls.enable_statements(...)` et dans `TENANT_TABLES` ; un test échoue sinon.

## Conséquences
- Les tables du socle (`users`, `organizations`, `memberships`) ne sont pas sous RLS : un utilisateur peut appartenir à plusieurs organisations.
- Les routes renvoient 404 plutôt que 403 pour une organisation étrangère afin de ne pas révéler son existence.
