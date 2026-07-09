#!/usr/bin/env bash
# KAYDAN SHIELD — Backup PostgreSQL avec rotation.
#
# Usage :
#   ./scripts/backup_db.sh                    # backup local
#   ./scripts/backup_db.sh /path/to/backups   # backup dans un dossier custom
#
# À planifier en cron nocturne :
#   0 2 * * *  /opt/kshield/scripts/backup_db.sh /backups
#
# Rotation : garde 30 backups quotidiens.
set -euo pipefail

cd "$(dirname "$0")/.."

BACKUP_DIR="${1:-./backups}"
mkdir -p "$BACKUP_DIR"

TS=$(date +%Y%m%d-%H%M%S)
FILE="$BACKUP_DIR/kshield-$TS.sql.gz"

# Extraire les creds depuis DATABASE_URL
if [ -f .env ]; then
    export $(grep -E "^(POSTGRES_|DATABASE_)" .env | xargs -I{} echo {})
fi

log() { printf "\033[1;34m[backup]\033[0m %s\n" "$*"; }

log "Dump vers $FILE"
docker compose exec -T shielddb \
    pg_dump -U "${POSTGRES_USER:-kaydan_user}" \
             "${POSTGRES_DB:-kaydan_shield}" \
    | gzip > "$FILE"

SIZE=$(du -h "$FILE" | cut -f1)
log "Backup créé : $FILE ($SIZE)"

# Rotation — garde 30 fichiers
COUNT=$(find "$BACKUP_DIR" -maxdepth 1 -name "kshield-*.sql.gz" | wc -l)
if [ "$COUNT" -gt 30 ]; then
    log "Rotation : suppression des backups > 30"
    find "$BACKUP_DIR" -maxdepth 1 -name "kshield-*.sql.gz" \
        -printf '%T@ %p\n' | sort -n | head -n $((COUNT - 30)) \
        | cut -d' ' -f2- | xargs rm -f
fi

# Upload S3 optionnel si AWS_S3_ENDPOINT_URL configuré
if [ -n "${AWS_S3_ENDPOINT_URL:-}" ] && [ -n "${AWS_STORAGE_BUCKET_NAME:-}" ]; then
    log "Upload S3/MinIO vers $AWS_STORAGE_BUCKET_NAME/backups/"
    docker run --rm --env-file .env \
        -v "$(realpath "$FILE"):/backup.sql.gz:ro" \
        amazon/aws-cli s3 cp \
        --endpoint-url "$AWS_S3_ENDPOINT_URL" \
        /backup.sql.gz \
        "s3://$AWS_STORAGE_BUCKET_NAME/backups/kshield-$TS.sql.gz"
fi

log "\033[1;32m✓ Backup terminé\033[0m"
