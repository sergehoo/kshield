#!/usr/bin/env bash
# KAYDAN SHIELD — Script de déploiement prod (Docker Compose).
#
# Usage :
#   ./scripts/deploy.sh              # deploy standard (rolling restart Django)
#   ./scripts/deploy.sh --full       # incl. pull images + migrations + collectstatic
#   ./scripts/deploy.sh --check-only # dry-run : vérifie sans rien déployer
#
# Prérequis :
#   - Fichier .env rempli
#   - docker + docker compose v2
#   - Cluster prod running (postgres, redis, emqx, minio)
set -euo pipefail

cd "$(dirname "$0")/.."

FULL=0
CHECK_ONLY=0
for arg in "$@"; do
    case "$arg" in
        --full)       FULL=1 ;;
        --check-only) CHECK_ONLY=1 ;;
        *) echo "Usage: $0 [--full] [--check-only]"; exit 1 ;;
    esac
done

log() { printf "\033[1;34m[deploy]\033[0m %s\n" "$*"; }
err() { printf "\033[1;31m[FAIL]\033[0m %s\n" "$*"; exit 1; }

# ─── 1. Vérifs préalables ───────────────────────────────────────────
log "Vérification .env"
[ -f .env ] || err ".env manquant — copier depuis .env.example et remplir"

log "Vérification docker"
command -v docker >/dev/null 2>&1 || err "docker introuvable"
docker compose version >/dev/null 2>&1 || err "docker compose v2 requis"

# ─── 2. Production readiness check ──────────────────────────────────
log "Check production readiness"
docker compose exec -T shieldback \
    python manage.py check_production_readiness \
    || err "Production check a échoué — corriger avant deploy"

if [ "$CHECK_ONLY" = "1" ]; then
    log "Mode --check-only, rien de déployé."
    exit 0
fi

# ─── 3. Pull + build ────────────────────────────────────────────────
if [ "$FULL" = "1" ]; then
    log "Pull des images prod"
    docker compose pull

    log "Build local (si nécessaire)"
    docker compose build --pull
fi

# ─── 4. Migrations + collectstatic ──────────────────────────────────
log "Migrations DB"
docker compose run --rm shieldback python manage.py migrate --noinput

log "Collectstatic"
docker compose run --rm shieldback python manage.py collectstatic --noinput

# ─── 5. Rolling restart Django + Celery ─────────────────────────────
log "Rolling restart shieldback + celery_worker + celery_beat"
docker compose up -d --no-deps --wait shieldback
docker compose up -d --no-deps --wait celery_worker
docker compose up -d --no-deps --wait celery_beat

# ─── 6. Healthchecks post-deploy ────────────────────────────────────
log "Attendre les healthchecks (30s max)"
for i in {1..30}; do
    if docker compose ps --status running | grep -q shieldback; then
        HEALTH=$(docker inspect --format='{{.State.Health.Status}}' \
                   $(docker compose ps -q shieldback) 2>/dev/null || echo "n/a")
        if [ "$HEALTH" = "healthy" ] || [ "$HEALTH" = "n/a" ]; then
            log "shieldback healthy ✓"
            break
        fi
    fi
    sleep 1
done

# ─── 7. Smoke test /healthz ─────────────────────────────────────────
log "Smoke test /healthz"
if docker compose exec -T shieldback \
       curl -fsS http://localhost:8000/healthz >/dev/null 2>&1; then
    log "healthz OK"
else
    err "healthz KO — inspecter les logs : docker compose logs shieldback --tail 100"
fi

log "\033[1;32m✓ Deploy terminé\033[0m"
