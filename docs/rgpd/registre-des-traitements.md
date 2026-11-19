# Registre des traitements

Responsable de traitement : `[nom de l'organisation, adresse]`.
Contact pour les droits des personnes : `[e-mail ou téléphone]`, repris dans l'accusé de
réception des SMS (page *Données personnelles*).
Délégué à la protection des données : `[nom, ou « non désigné »]`.

Mesures communes à tous les traitements : chaque organisation ne voit que ses données (Row
Level Security dans PostgreSQL), connexions chiffrées (HTTPS, HSTS), mots de passe hachés,
connexions limitées, double authentification, sessions révocables, journal des actions et des
consultations, sauvegardes chiffrées (AES-256) gardées 14 jours.

## 1. Comptes des membres de l'équipe

- **Finalité** : accès à l'application, attribution des saisies et des validations.
- **Base légale** : exécution du contrat de travail ou de bénévolat ; intérêt légitime.
- **Personnes** : salariés, bénévoles, consultants de l'organisation.
- **Données** : nom, adresse e-mail, rôle, mot de passe haché, sessions (appareil, date).
- **Destinataires** : administrateurs de l'organisation.
- **Durée** : tant que la personne est membre. Un compte supprimé est anonymisé (nom et e-mail
  effacés) ; les sessions expirées sont effacées après 30 jours.

## 2. Plaintes et retours des communautés (redevabilité)

- **Finalité** : recevoir, traiter et répondre aux plaintes, suggestions et alertes ; suivre les
  engagements de redevabilité (CHS, PSEA).
- **Base légale** : intérêt légitime ; pour les alertes graves (exploitation et abus sexuels,
  fraude), protection des intérêts vitaux des personnes.
- **Personnes** : membres des communautés, participants, tiers cités.
- **Données** : description, contact (nom, téléphone), échanges SMS ou WhatsApp, lieu,
  catégorie. Données sensibles possibles (santé, violences).
- **Destinataires** : retours sensibles visibles seulement des responsables désignés ; chaque
  consultation est inscrite au journal.
- **Durée** : `[36]` mois après la clôture (réglable), puis anonymisation automatique ; les SMS
  qu'aucun projet ne reconnaît sont effacés après 30 jours.
- **Information** : accusé de réception par SMS avec la phrase d'information et le contact.

## 3. Preuves des activités (photos, listes de présence, comptes rendus)

- **Finalité** : justifier les activités auprès des bailleurs, suivre les indicateurs.
- **Base légale** : intérêt légitime et obligations contractuelles envers les bailleurs ;
  consentement pour les photos de personnes identifiables.
- **Personnes** : participants, enfants (avec l'accord d'un tuteur), équipe.
- **Données** : photos (visages floutés dans les vignettes et les rapports), listes de
  présence, mode de recueil du consentement (oral, écrit, tuteur, communauté), date et position
  de la prise de vue (gardées en base, retirées du fichier).
- **Destinataires** : équipe du projet ; originaux non floutés réservés aux responsables, et
  chaque ouverture est journalisée. Les listes de présence ne sont jamais envoyées à l'IA.
- **Durée** : durée du projet plus `[5]` ans (obligations des bailleurs), puis suppression du
  projet, qui efface aussi ses fichiers.

## 4. Formulaires de collecte (enquêtes, suivi post-distribution)

- **Finalité** : mesurer les résultats et la satisfaction.
- **Base légale** : intérêt légitime ; consentement du répondant à l'enquête.
- **Personnes** : ménages et participants enquêtés.
- **Données** : réponses ; les questions marquées « Donnée personnelle » (nom, téléphone,
  santé…) sont absentes de la synthèse et de l'export simple.
- **Destinataires** : responsables et chargés de suivi-évaluation ; tout export est journalisé.
- **Durée** : `[durée du projet plus 2 ans]`.

## 5. Journal des actions et des consultations

- **Finalité** : sécurité, traçabilité, preuve en cas de contestation.
- **Base légale** : intérêt légitime, obligation de sécurité.
- **Données** : qui a fait ou consulté quoi, quand ; jamais le contenu consulté ni les termes
  d'une recherche de personne.
- **Durée** : consultations 365 jours ; actions tant que l'espace existe.

## Exercice des droits

Accès, rectification, effacement : page *Données personnelles*, « Demande d'une personne »
(recherche par nom, numéro ou e-mail, copie JSON, effacement motivé). Réponse sous un mois.
