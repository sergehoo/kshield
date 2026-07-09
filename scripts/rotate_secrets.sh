#!/usr/bin/env bash
# KAYDAN SHIELD — Rotation trimestrielle des secrets.
#
# Génère un template .env.rotated avec de nouvelles valeurs aléatoires pour :
#   - SECRET_KEY
#   - FIELD_ENCRYPTION_KEY (Fernet)
#   - EMQX_NODE_COOKIE
#   - POSTGRES_PASSWORD (si prod HA)
#
# ATTENTION : ne remplace PAS .env automatiquement. Toi seul décides quand
# basculer (nécessite migration DB pour FIELD_ENCRYPTION_KEY si des données
# chiffrées existent).
set -euo pipefail

cd "$(dirname "$0")/.."

OUT=".env.rotated-$(date +%Y%m%d)"
log() { printf "\033[1;34m[rotate]\033[0m %s\n" "$*"; }

if [ ! -f .env ]; then
    echo "ERROR: .env manquant" >&2
    exit 1
fi

log "Génération nouvelles valeurs → $OUT"
cp .env "$OUT"

# ─── SECRET_KEY : 64 chars aléatoires ────────────────────────────
NEW_SK=$(python -c "import secrets; print(secrets.token_urlsafe(64))")
sed -i.bak "s|^SECRET_KEY=.*|SECRET_KEY=$NEW_SK|" "$OUT"

# ─── FIELD_ENCRYPTION_KEY : Fernet valide ────────────────────────
NEW_FE=$(python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
sed -i.bak "s|^FIELD_ENCRYPTION_KEY=.*|FIELD_ENCRYPTION_KEY=$NEW_FE|" "$OUT"

# ─── EMQX_NODE_COOKIE : 64 chars ────────────────────────────────
NEW_EMQX=$(python -c "import secrets; print(secrets.token_hex(32))")
sed -i.bak "s|^EMQX_NODE_COOKIE=.*|EMQX_NODE_COOKIE=$NEW_EMQX|" "$OUT"

# ─── POSTGRES_PASSWORD ─────────────────────────────────────────
NEW_PG=$(python -c "import secrets; print(secrets.token_urlsafe(24))")
sed -i.bak "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=$NEW_PG|" "$OUT"

rm -f "$OUT.bak"
chmod 600 "$OUT"

log "\033[1;32m✓ Nouveau template : $OUT\033[0m"
log ""
log "Étapes suivantes MANUELLES :"
log "  1. Comparer avec l'ancien .env : diff .env $OUT"
log "  2. Si FIELD_ENCRYPTION_KEY change, prévoir migration des champs"
log "     chiffrés en base (Camera.password, LocalAgent.hmac_secret…)"
log "  3. Sauvegarder l'ancien .env : cp .env .env.old-$(date +%Y%m%d)"
log "  4. Basculer : mv $OUT .env"
log "  5. Redémarrer tous les services : docker compose restart"
