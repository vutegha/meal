# ADR 0002 : isolation des organisations

- Statut : accepté
- Date : 2026-09-27

## Contexte
Plusieurs organisations partagent la même base. Une fuite de données entre organisations est le risque le plus grave de l'application.

## Décision
1. **Dès l'étape 1**, isolation applicative : toutes les routes métier sont sous `/api/v1/orgs/{org_id}/…` et passent par la dépendance `require_membership`, qui renvoie 404 si l'utilisateur n'est pas membre. Chaque requête SQL métier filtre sur `organization_id`.
2. **À l'étape 2**, avec les premières tables métier (projets, cadre logique…), ajout d'une défense en profondeur par Row Level Security PostgreSQL : l'API positionne `SET LOCAL app.current_org` dans chaque transaction et des politiques RLS filtrent sur `organization_id`.
3. Des tests automatisés vérifient qu'un membre d'une organisation ne peut ni lire ni modifier les données d'une autre.

## Conséquences
- Les tables du socle (`users`, `organizations`, `memberships`) ne sont pas sous RLS : un utilisateur peut appartenir à plusieurs organisations.
- Les routes renvoient 404 plutôt que 403 pour une organisation étrangère afin de ne pas révéler son existence.
