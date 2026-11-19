# Violation de données : que faire

Une violation, c'est une perte de confidentialité, d'intégrité ou de disponibilité de données
personnelles : téléphone perdu avec une session ouverte, mot de passe divulgué, export envoyé à
la mauvaise personne, serveur compromis, sauvegarde perdue.

Responsable de la procédure : `[nom, téléphone joignable]`. Suppléant : `[nom]`.

## 1. Contenir (dans l'heure)

- **Compte compromis ou téléphone perdu** : la personne clique *Mon compte*, « Déconnecter
  tous mes appareils », depuis un autre appareil, ou l'exploitant ferme ses sessions :
  `docker compose exec api python -m app.scripts.revoke_sessions personne@ong.org`.
  Un administrateur lui remet ensuite un lien de réinitialisation (page *Membres*).
- **Plusieurs comptes ou doute général** : fermer toutes les sessions,
  `docker compose exec api python -m app.scripts.revoke_sessions`.
- **Serveur compromis ou `SECRET_KEY` divulguée** : changer `SECRET_KEY` (et
  `POSTGRES_PASSWORD`, les clés des prestataires), redémarrer, puis
  `docker compose exec api python -m app.scripts.revoke_sessions --unreadable-totp`.
  Changer aussi `BACKUP_PASSPHRASE` si les sauvegardes ont pu être lues.
- **Fournisseur externe en cause** : le couper (voir [sous-traitants](sous-traitants.md)).

## 2. Évaluer (dans les 24 heures)

Avec le journal (page *Membres*, carte « Journal d'audit ») : quelles données, combien de personnes, depuis
quand, qui a consulté ou exporté (`feedback.viewed`, `evidence.original_viewed`,
`form.exported`…). Le risque est élevé si la fuite touche des plaintes sensibles (violences,
exploitation et abus sexuels), des données de santé, des enfants, ou permet de localiser des
personnes.

## 3. Notifier (dans les 72 heures)

- **Autorité de contrôle** `[CNIL, APD… selon le pays du responsable]` : sauf si la violation
  ne présente aucun risque pour les personnes. Une notification incomplète vaut mieux qu'une
  notification tardive ; elle se complète ensuite.
- **Personnes concernées** : sans tarder si le risque est élevé, dans leur langue et par un
  canal sûr pour elles (pas un SMS qui révélerait une plainte sensible à un tiers).
- **Bailleurs** : selon les clauses des contrats `[à vérifier]`.

## 4. Documenter

Tenir un registre, même pour les violations non notifiées : date, découverte, nature, données
et personnes concernées, mesures prises, notifications faites ou raison de ne pas notifier.

| Date | Découverte par | Nature | Personnes | Mesures | Notifié à |
| --- | --- | --- | --- | --- | --- |
| | | | | | |
