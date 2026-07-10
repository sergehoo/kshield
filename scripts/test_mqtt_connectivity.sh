#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════
# Kaydan Shield — Test MQTT end-to-end
# ═══════════════════════════════════════════════════════════════════
#
# Vérifie que tous les acteurs peuvent se connecter à EMQX avec les
# bons credentials et que les topics fonctionnent.
#
# Prérequis :
#   - EMQX déployé et healthy
#   - Users MQTT créés : kshield-backend, kshield-edge-master, kshield-devices
#   - Passer les passwords en variables d'env avant de lancer :
#       export MQTT_PW_BACKEND=xxx
#       export MQTT_PW_EDGE=xxx
#       export MQTT_PW_DEVICES=xxx
#       ./scripts/test_mqtt_connectivity.sh
#
# Se lance :
#   - depuis le VPS         : bash scripts/test_mqtt_connectivity.sh
#   - depuis n'importe où   : ajouter MQTT_HOST=mqtt.kaydanshield.com + MQTT_PORT=8883 + MQTT_TLS=1
# ═══════════════════════════════════════════════════════════════════
set -uo pipefail

# ─── Config ────────────────────────────────────────────────────────
MQTT_HOST="${MQTT_HOST:-shieldmqtt}"       # 'shieldmqtt' si depuis conteneur backend
MQTT_PORT="${MQTT_PORT:-1883}"
MQTT_TLS="${MQTT_TLS:-0}"

: "${MQTT_PW_BACKEND:?Set MQTT_PW_BACKEND=<password de kshield-backend>}"
: "${MQTT_PW_EDGE:?Set MQTT_PW_EDGE=<password de kshield-edge-master>}"
: "${MQTT_PW_DEVICES:?Set MQTT_PW_DEVICES=<password de kshield-devices>}"

# Couleurs
GREEN=$'\033[0;32m'; RED=$'\033[0;31m'; YELLOW=$'\033[0;33m'; RESET=$'\033[0m'
ok()   { printf "%s✓%s %s\n" "$GREEN" "$RESET" "$*"; }
fail() { printf "%s✗%s %s\n" "$RED"   "$RESET" "$*"; }
info() { printf "%s→%s %s\n" "$YELLOW" "$RESET" "$*"; }

# ─── Vérif dépendances ────────────────────────────────────────────
if ! command -v mosquitto_pub >/dev/null || ! command -v mosquitto_sub >/dev/null; then
    fail "mosquitto-clients requis. Installer :"
    echo "    apt install mosquitto-clients   (Ubuntu/Debian)"
    echo "    brew install mosquitto          (macOS)"
    exit 1
fi

TLS_ARGS=()
if [[ "$MQTT_TLS" == "1" ]]; then
    TLS_ARGS=(--capath /etc/ssl/certs -p 8883)
    info "Mode TLS activé sur port 8883"
else
    TLS_ARGS=(-p "$MQTT_PORT")
fi

echo "═══════════════════════════════════════════════════════════════════"
echo "  Test EMQX @ ${MQTT_HOST}:${MQTT_PORT} (TLS=${MQTT_TLS})"
echo "═══════════════════════════════════════════════════════════════════"

# ─── Test 1 : kshield-backend peut publier ─────────────────────────
info "Test 1 — kshield-backend publie sur kshield/backend/test"
if mosquitto_pub -h "$MQTT_HOST" "${TLS_ARGS[@]}" \
     -u kshield-backend -P "$MQTT_PW_BACKEND" \
     -t kshield/backend/test -m "ping-from-backend-$(date +%s)" -q 1; then
    ok "kshield-backend publish OK"
else
    fail "kshield-backend publish échoué (rc=$?) — check password + ACL"
    exit 1
fi

# ─── Test 2 : kshield-edge-master peut s'abonner ───────────────────
info "Test 2 — kshield-edge-master subscribe kshield/cmd/edge/# (5s max)"
if timeout 5 mosquitto_sub -h "$MQTT_HOST" "${TLS_ARGS[@]}" \
     -u kshield-edge-master -P "$MQTT_PW_EDGE" \
     -t 'kshield/cmd/edge/#' -C 0 2>&1 | head -1; then
    ok "kshield-edge-master subscribe OK (aucun message reçu = normal si backend n'a rien publié)"
else
    RC=$?
    if [[ $RC -eq 124 ]]; then
        ok "kshield-edge-master subscribe OK (timeout attendu, connexion établie)"
    else
        fail "kshield-edge-master subscribe échoué (rc=$RC)"
        exit 1
    fi
fi

# ─── Test 3 : Aller-retour backend → edge ──────────────────────────
info "Test 3 — Aller-retour : backend publie, edge reçoit"
# Sub en background
(mosquitto_sub -h "$MQTT_HOST" "${TLS_ARGS[@]}" \
     -u kshield-edge-master -P "$MQTT_PW_EDGE" \
     -t "kshield/cmd/edge/test-gateway-42/#" -C 1 -W 8 > /tmp/mqtt_edge_recv.txt 2>&1) &
SUB_PID=$!
sleep 1

# Pub depuis backend
PAYLOAD="{\"cmd\":\"restart\",\"ts\":$(date +%s)}"
mosquitto_pub -h "$MQTT_HOST" "${TLS_ARGS[@]}" \
     -u kshield-backend -P "$MQTT_PW_BACKEND" \
     -t "kshield/cmd/edge/test-gateway-42/action" -m "$PAYLOAD" -q 1

# Attend le sub
wait "$SUB_PID" 2>/dev/null || true

if grep -q "restart" /tmp/mqtt_edge_recv.txt 2>/dev/null; then
    ok "Aller-retour backend → edge OK (payload reçu: $(cat /tmp/mqtt_edge_recv.txt))"
else
    fail "Edge n'a rien reçu — check ACL topic (kshield-edge-master doit être autorisé sur kshield/cmd/edge/#)"
    echo "  Contenu recv : $(cat /tmp/mqtt_edge_recv.txt 2>/dev/null || echo '(vide)')"
fi

# ─── Test 4 : Device publie un event ───────────────────────────────
info "Test 4 — kshield-devices publie un event"
if mosquitto_pub -h "$MQTT_HOST" "${TLS_ARGS[@]}" \
     -u kshield-devices -P "$MQTT_PW_DEVICES" \
     -t "kshield/devices/reader-01/events" \
     -m "{\"type\":\"badge_scan\",\"card\":\"1234567\",\"ts\":$(date +%s)}" -q 1; then
    ok "kshield-devices publish OK"
else
    fail "kshield-devices publish échoué"
fi

# ─── Test 5 : Anonymous refusé ─────────────────────────────────────
info "Test 5 — vérif que l'anonyme est bien REFUSÉ"
if timeout 3 mosquitto_pub -h "$MQTT_HOST" "${TLS_ARGS[@]}" \
     -t "test/anon" -m "should_fail" -q 0 2>&1 | grep -qi "denied\|not authorized\|refused"; then
    ok "Anonyme correctement REFUSÉ"
elif timeout 3 mosquitto_pub -h "$MQTT_HOST" "${TLS_ARGS[@]}" \
     -t "test/anon" -m "should_fail" -q 0 2>/dev/null; then
    fail "⚠️  ATTENTION : connexion anonyme ACCEPTÉE — EMQX_ALLOW_ANONYMOUS doit être 'false'"
else
    ok "Anonyme rejeté (rc≠0)"
fi

# ─── Test 6 : Mauvais mot de passe refusé ──────────────────────────
info "Test 6 — vérif que credentials incorrects sont REFUSÉS"
if timeout 3 mosquitto_pub -h "$MQTT_HOST" "${TLS_ARGS[@]}" \
     -u kshield-backend -P "wrong-password-xyz" \
     -t "test/wrong-pass" -m "should_fail" 2>&1 | grep -qi "denied\|not authorized"; then
    ok "Mauvais password rejeté"
elif timeout 3 mosquitto_pub -h "$MQTT_HOST" "${TLS_ARGS[@]}" \
     -u kshield-backend -P "wrong-password-xyz" \
     -t "test/wrong-pass" -m "should_fail" 2>/dev/null; then
    fail "⚠️  ATTENTION : mauvais password ACCEPTÉ — auth cassée"
else
    ok "Mauvais password rejeté (rc≠0)"
fi

echo ""
echo "═══════════════════════════════════════════════════════════════════"
ok "Tests MQTT terminés"
echo "═══════════════════════════════════════════════════════════════════"
echo ""
echo "Prochaine étape : vérifier dans le Dashboard EMQX"
echo "  → https://mqtt.kaydanshield.com"
echo "  → Monitoring → Clients : tu dois voir kshield-backend, kshield-edge-master,"
echo "    kshield-devices dans la liste des clients récemment connectés"
echo "  → Monitoring → Metrics : bytes/messages entrants doivent avoir bougé"
