#!/bin/sh
# Restauration d'une sauvegarde faite par backup.sh. Remplace la base et les fichiers.
#   docker compose stop api worker
#   docker compose run --rm --entrypoint /ops/restore.sh backup wemeal-AAAAMMJJ-HHMMSS.tar.gpg
#   docker compose start api worker
set -eu

: "${BACKUP_PASSPHRASE:?BACKUP_PASSPHRASE est requise}"
export PGPASSWORD="${POSTGRES_PASSWORD:?POSTGRES_PASSWORD est requise}"
archive="/backups/${1:?Indiquer le fichier de sauvegarde (voir : backup.sh list)}"
[ -f "$archive" ] || { echo "Introuvable : $archive" >&2; exit 1; }

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
gpg --batch --quiet --pinentry-mode loopback --passphrase-fd 3 --decrypt "$archive" 3<<PASS \
  | tar -C "$work" -xf -
$BACKUP_PASSPHRASE
PASS
pg_restore -h db -U meal -d meal --clean --if-exists --no-owner --exit-on-error "$work/db.dump"
find /data/files -mindepth 1 -delete
tar -C /data -xzf "$work/files.tar.gz"
echo "Restauré depuis $archive"
