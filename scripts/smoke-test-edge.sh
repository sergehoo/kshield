#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════
# Kaydan Edge Gateway — Smoke test intégration bout-en-bout
# ═══════════════════════════════════════════════════════════════════
#
# Vérifie que TOUS les endpoints Edge Gateway répondent correctement.
# Idéal en CI + validation post-deploy prod.
#
# Prérequis :
#   - jq (apt install jq / brew install jq)
#   - curl
#   - Variables env :
#       KSHIELD_URL     (ex: https://kaydanshield.com)
#       KSHIELD_TOKEN   (JWT admin ou API key)
#
# Usage :
#   export KSHIELD_URL=https://kaydanshield.com
#   export KSHIELD_TOKEN=eyJhbGc...
#   ./scripts/smoke-test-edge.sh
# ═══════════════════════════════════════════════════════════════════
set -uo pipefail

: "${KSHIELD_URL:?Variable KSHIELD_URL requise (ex: https://kaydanshield.com)}"
: "${KSHIELD_TOKEN:?Variable KSHIELD_TOKEN requise (JWT admin)}"

URL="${KSHIELD_URL%/}"
TOKEN="$KSHIELD_TOKEN"

# ─── Couleurs ─────────────────────────────────────────────────────
GREEN=$'\033[0;32m'; RED=$'\033[0;31m'; YELLOW=$'\033[0;33m'
CYAN=$'\033[0;36m'; RESET=$'\033[0m'

PASS=0
FAIL=0

ok()   { printf "  %s✓%s %s\n"     "$GREEN"  "$RESET" "$*"; PASS=$((PASS+1)); }
fail() { printf "  %s✗%s %s\n"     "$RED"    "$RESET" "$*"; FAIL=$((FAIL+1)); }
info() { printf "  %s→%s %s\n"     "$YELLOW" "$RESET" "$*"; }
step() { printf "\n%s══ %s ══%s\n" "$CYAN"   "$*" "$RESET"; }

# ─── curl helper : renvoie le status HTTP + body dans /tmp ────────
call() {
    local method="$1"; local path="$2"; local body="${3:-}"
    local url="$URL$path"
    local args=(-s -o /tmp/smoke_body.json -w "%{http_code}" -X "$method"
                -H "Authorization: Bearer $TOKEN"
                -H "Content-Type: application/json")
    if [ -n "$body" ]; then
        args+=(-d "$body")
    fi
    curl "${args[@]}" "$url" 2>/dev/null || echo "000"
}

expect_status() {
    local actual="$1"; local expected="$2"; local test_name="$3"
    if [ "$actual" = "$expected" ]; then
        ok "$test_name (HTTP $actual)"
    else
        fail "$test_name : attendu HTTP $expected, reçu $actual"
        head -c 200 /tmp/smoke_body.json 2>/dev/null && echo
    fi
}

# ═══════════════════════════════════════════════════════════════════
# Section 1 : Endpoints publics
# ═══════════════════════════════════════════════════════════════════
step "1. Endpoints publics"

status=$(curl -s -o /dev/null -w "%{http_code}" "$URL/healthz" 2>/dev/null || echo "000")
expect_status "$status" "200" "/healthz"

status=$(curl -s -o /dev/null -w "%{http_code}" "$URL/readyz" 2>/dev/null || echo "000")
expect_status "$status" "200" "/readyz"

# ═══════════════════════════════════════════════════════════════════
# Section 2 : Auth
# ═══════════════════════════════════════════════════════════════════
step "2. Authentification"

status=$(call GET /api/v1/auth/me/)
expect_status "$status" "200" "/api/v1/auth/me/ (JWT valide)"

USER_INFO=$(cat /tmp/smoke_body.json)
USERNAME=$(echo "$USER_INFO" | jq -r '.email // .username // "?"')
info "Connecté en tant que : $USERNAME"

# ═══════════════════════════════════════════════════════════════════
# Section 3 : Edge Gateway — Catalogue packages
# ═══════════════════════════════════════════════════════════════════
step "3. Edge Gateway — Packages"

status=$(call GET /api/v1/devices/edge-gateway/packages/)
expect_status "$status" "200" "GET /packages/"

# ═══════════════════════════════════════════════════════════════════
# Section 4 : Edge Gateway — Liste gateways
# ═══════════════════════════════════════════════════════════════════
step "4. Edge Gateway — Gateways"

status=$(call GET /api/v1/devices/edge-gateway/)
expect_status "$status" "200" "GET / (liste gateways)"

COUNT=$(cat /tmp/smoke_body.json | jq -r '.count // 0')
info "$COUNT gateway(s) enregistrée(s)"

# Récupère l'ID de la première gateway pour tests suivants
GID=$(cat /tmp/smoke_body.json | jq -r '.gateways[0].id // empty')
if [ -z "$GID" ]; then
    info "Aucune gateway — création d'une gateway test"
    status=$(call POST /api/v1/devices/edge-gateway/ '{"label":"smoke-test-gateway"}')
    if [ "$status" = "201" ] || [ "$status" = "200" ]; then
        GID=$(cat /tmp/smoke_body.json | jq -r '.id')
        ok "Gateway test créée : $GID"
    else
        fail "Impossible de créer une gateway test (HTTP $status)"
        GID=""
    fi
fi

# ═══════════════════════════════════════════════════════════════════
# Section 5 : Gateway detail + targets
# ═══════════════════════════════════════════════════════════════════
if [ -n "$GID" ]; then
    step "5. Gateway detail — $GID"

    status=$(call GET "/api/v1/devices/edge-gateway/$GID/")
    expect_status "$status" "200" "GET /<gid>/ (detail)"

    status=$(call GET "/api/v1/devices/edge-gateway/$GID/targets/")
    expect_status "$status" "200" "GET /<gid>/targets/"

    status=$(call GET "/api/v1/devices/edge-gateway/$GID/logs/")
    expect_status "$status" "200" "GET /<gid>/logs/"

    status=$(call GET "/api/v1/devices/edge-gateway/$GID/devices/")
    expect_status "$status" "200" "GET /<gid>/devices/"

    # ═══════════════════════════════════════════════════════════════
    # Section 6 : Download package personnalisé
    # ═══════════════════════════════════════════════════════════════
    step "6. Download package personnalisé"

    status=$(curl -s -o /tmp/smoke_zip.bin \
        -w "%{http_code}" \
        -H "Authorization: Bearer $TOKEN" \
        "$URL/api/v1/devices/edge-gateway/$GID/download/?platform=linux_deb" \
        2>/dev/null || echo "000")

    if [ "$status" = "200" ]; then
        SIZE=$(stat -c%s /tmp/smoke_zip.bin 2>/dev/null \
            || stat -f%z /tmp/smoke_zip.bin 2>/dev/null || echo "?")
        # Vérifie que c'est bien un ZIP (signature PK\x03\x04)
        HEAD=$(head -c 2 /tmp/smoke_zip.bin | od -An -c | tr -d ' ')
        if [ "$HEAD" = "PK" ]; then
            ok "Download package (HTTP 200, $SIZE bytes, signature ZIP OK)"
        else
            fail "Download retourne 200 mais pas un ZIP (head=$HEAD)"
        fi
    else
        fail "Download package (HTTP $status)"
    fi

    # Test platform invalide
    status=$(call GET "/api/v1/devices/edge-gateway/$GID/download/?platform=bad_platform")
    expect_status "$status" "400" "Download platform invalide → 400"

    # ═══════════════════════════════════════════════════════════════
    # Section 7 : Fleet view
    # ═══════════════════════════════════════════════════════════════
    step "7. Fleet view (tenant-wide)"

    status=$(call GET /api/v1/devices/edge-gateway/fleet/targets/)
    expect_status "$status" "200" "GET /fleet/targets/"

    # Filtres
    status=$(call GET "/api/v1/devices/edge-gateway/fleet/targets/?vendor=hikvision")
    expect_status "$status" "200" "GET /fleet/targets/?vendor=hikvision"
fi

# ═══════════════════════════════════════════════════════════════════
# Section 8 : Stats + Realtime
# ═══════════════════════════════════════════════════════════════════
step "8. Stats + Realtime"

status=$(call GET /api/v1/devices/stats/realtime/)
expect_status "$status" "200" "GET /devices/stats/realtime/"

status=$(call GET /api/v1/devices/drivers/)
expect_status "$status" "200" "GET /devices/drivers/"

# ═══════════════════════════════════════════════════════════════════
# Bilan
# ═══════════════════════════════════════════════════════════════════
echo ""
echo "═══════════════════════════════════════════════════════════════════"
if [ "$FAIL" -eq 0 ]; then
    printf "%sTous les tests passent : %d/%d%s\n" \
        "$GREEN" "$PASS" "$((PASS+FAIL))" "$RESET"
    exit 0
else
    printf "%s%d test(s) échoué(s) — %d/%d OK%s\n" \
        "$RED" "$FAIL" "$PASS" "$((PASS+FAIL))" "$RESET"
    exit 1
fi
