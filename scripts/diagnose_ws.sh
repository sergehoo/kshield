#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
# KAYDAN SHIELD — Diagnostic WebSocket (handshake 200 = Traefik
# fait retomber /ws/ sur le front au lieu du service ASGI).
#
# À lancer sur le serveur en SSH :
#   bash scripts/diagnose_ws.sh
# ─────────────────────────────────────────────────────────────
set -euo pipefail

DOMAIN="${BASE_DOMAIN:-kaydanshield.com}"

echo "═══ 1. Container shieldws (uvicorn ASGI) — statut + healthcheck ═══"
docker ps --filter "name=kshield_ws" --format \
  "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
echo

echo "═══ 2. Derniers logs shieldws (50 lignes) ═══"
docker logs --tail 50 kshield_ws 2>&1 || echo "(container introuvable)"
echo

echo "═══ 3. Réseau Traefik — service kshield-ws-svc visible ? ═══"
docker inspect kshield_ws --format \
  '{{range $net, $conf := .NetworkSettings.Networks}}{{$net}} → {{$conf.IPAddress}}{{"\n"}}{{end}}' \
  2>/dev/null || echo "(container introuvable)"
echo

echo "═══ 4. Traefik voit-il le routeur kshield-ws-main ? ═══"
docker exec traefik curl -fsS \
  http://127.0.0.1:8080/api/http/routers 2>/dev/null \
  | grep -A2 '"kshield-ws' || echo "(pas d'accès à l'API Traefik ou routeur absent)"
echo

echo "═══ 5. Test handshake WS local (depuis l'hôte, sans Traefik) ═══"
if command -v websocat >/dev/null 2>&1; then
  timeout 5 websocat -1 "ws://$(docker inspect kshield_ws --format \
    '{{(index .NetworkSettings.Networks "kshield_network").IPAddress}}'):8001/ws/devices/status/" \
    <<< "ping" && echo "→ handshake OK côté uvicorn" || echo "→ échec côté uvicorn"
else
  echo "(websocat non installé — sudo apt install websocat)"
fi
echo

echo "═══ 6. Test handshake WS public via Traefik ═══"
curl -isS -o /tmp/wshead -w "%{http_code}\n" \
  -H "Connection: Upgrade" -H "Upgrade: websocket" \
  -H "Sec-WebSocket-Version: 13" \
  -H "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==" \
  "https://$DOMAIN/ws/devices/status/" || true
echo "── headers ──"
head -8 /tmp/wshead 2>/dev/null || true
echo
echo "→ Attendu : HTTP/1.1 101 Switching Protocols"
echo "→ Reçu 200 : Traefik n'a pas de service healthy → il retombe sur le front."
echo "→ Reçu 404 : uvicorn ne connait pas cette URL → problème routing.py."
echo "→ Reçu 403 : middleware rejette → normal si token JWT absent."
