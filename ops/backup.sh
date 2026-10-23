#!/bin/sh
# Sauvegarde chiffrée de la base et des fichiers, chaque jour à BACKUP_HOUR (heure UTC).
#   docker compose run --rm backup now      une sauvegarde tout de suite
#   docker compose run --rm backup list     les sauvegardes présentes
# Chaque sauvegarde est un fichier wemeal-AAAAMMJJ-HHMMSS.tar.gpg dans /backups, chiffré
# (AES-256) avec BACKUP_PASSPHRASE. Sans cette phrase, la sauvegarde est illisible :
# la garder hors du serveur, dans un gestionnaire de mots de passe.
set -eu

: "${BACKUP_PASSPHRASE:?BACKUP_PASSPHRASE est requise}"
BACKUP_HOUR="${BACKUP_HOUR:-2}"
BACKUP_KEEP_DAYS="${BACKUP_KEEP_DAYS:-14}"
export PGPASSWORD="${POSTGRES_PASSWORD:?POSTGRES_PASSWORD est requise}"

backup() {
  stamp=$(date -u +%Y%m%d-%H%M%S)
  work=$(mktemp -d)
  trap 'rm -rf "$work"' EXIT
  pg_dump -h db -U meal -d meal -Fc -f "$work/db.dump"
  tar -C /data -czf "$work/files.tar.gz" files
  tar -C "$work" -cf - db.dump files.tar.gz \
    | gpg --batch --yes --quiet --pinentry-mode loopback --passphrase-fd 3 \
        --symmetric --cipher-algo AES256 -o "/backups/wemeal-$stamp.tar.gpg" \
        3<<PASS
$BACKUP_PASSPHRASE
PASS
  rm -rf "$work"
  trap - EXIT
  # Les sauvegardes plus anciennes que BACKUP_KEEP_DAYS jours sont supprimées.
  find /backups -name 'wemeal-*.tar.gpg' -mtime +"$BACKUP_KEEP_DAYS" -delete
  echo "Sauvegarde /backups/wemeal-$stamp.tar.gpg ($(du -h "/backups/wemeal-$stamp.tar.gpg" | cut -f1))"
}

case "${1:-schedule}" in
  now) backup ;;
  list) ls -lh /backups ;;
  schedule)
    echo "Sauvegarde quotidienne à ${BACKUP_HOUR} h UTC, conservée ${BACKUP_KEEP_DAYS} jours"
    while true; do
      now=$(date -u +%s)
      next=$(date -u -d "today ${BACKUP_HOUR}:00" +%s)
      [ "$next" -le "$now" ] && next=$(date -u -d "tomorrow ${BACKUP_HOUR}:00" +%s)
      sleep $((next - now))
      backup || echo "ÉCHEC de la sauvegarde" >&2
    done
    ;;
  *) echo "Usage : backup.sh [schedule|now|list]" >&2; exit 2 ;;
esac
