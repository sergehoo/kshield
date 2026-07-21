#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════
# Kaydan Edge Gateway (Go) — installateur natif
# ═══════════════════════════════════════════════════════════════════
#
# Télécharge le binaire kshield-agent adapté à la plateforme, l'installe
# dans /usr/local/bin/ (ou C:\Program Files sur Windows), configure
# systemd/launchctl, et fait l'appairage cloud.
#
# Aucun venv Python n'est nécessaire — c'est un binaire natif.
#
# Usage :
#     sudo bash install-edge-go.sh
#     # ou avec vars env :
#     KSHIELD_SERVER_URL=https://kaydanshield.com \
#     KSHIELD_ACTIVATION_TOKEN=xxxxx \
#         sudo bash install-edge-go.sh
#
# Le script lit d'abord config/kshield-agent.toml livré dans le zip pour
# récupérer server_url et activation_token, avec fallback sur les env vars.
# ═══════════════════════════════════════════════════════════════════
set -euo pipefail

VERSION="${KSHIELD_AGENT_VERSION:-1.0.0}"
RELEASE_URL="${KSHIELD_RELEASE_URL:-https://github.com/sergehoo/kshield/releases/download/agent-v${VERSION}}"
INSTALL_BIN="/usr/local/bin/kshield-agent"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUNDLED_CONFIG="${SCRIPT_DIR}/config/kshield-agent.toml"

# ─── Helpers ────────────────────────────────────────────────────
log()  { printf '\033[1;34m[install]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[warn]\033[0m %s\n' "$*"; }
err()  { printf '\033[1;31m[error]\033[0m %s\n' "$*" >&2; exit 1; }

# ─── Détection plateforme ──────────────────────────────────────
OS="$(uname -s)"
ARCH="$(uname -m)"

case "$OS" in
    Linux*)  PLATFORM="linux" ;;
    Darwin*) PLATFORM="darwin" ;;
    *) err "Plateforme non supportée : $OS. Utiliser Linux ou macOS." ;;
esac

case "$ARCH" in
    x86_64|amd64) GOARCH="amd64" ;;
    aarch64|arm64) GOARCH="arm64" ;;
    armv7l|armv7) GOARCH="armv7" ;;
    *) err "Architecture non supportée : $ARCH" ;;
esac

BIN_NAME="kshield-agent-${PLATFORM}-${GOARCH}"
BIN_URL="${RELEASE_URL}/${BIN_NAME}"
BUNDLED_BIN="${SCRIPT_DIR}/bin/${BIN_NAME}"
BUNDLED_CHECKSUMS="${SCRIPT_DIR}/bin/SHA256SUMS.txt"

log "Plateforme : $PLATFORM/$GOARCH"
log "Binaire    : $BIN_NAME"

# ─── Read TOML values ──────────────────────────────────────────
read_toml_value() {
    local key="$1" file="$2"
    [ -f "$file" ] || return
    grep -E "^[[:space:]]*${key}[[:space:]]*=" "$file" | head -1 \
        | sed -E "s/^[^=]*=[[:space:]]*\"?([^\"]*)\"?[[:space:]]*$/\1/"
}

if [ -f "$BUNDLED_CONFIG" ]; then
    KSHIELD_SERVER_URL="${KSHIELD_SERVER_URL:-$(read_toml_value 'server_url' "$BUNDLED_CONFIG")}"
    KSHIELD_ACTIVATION_TOKEN="${KSHIELD_ACTIVATION_TOKEN:-$(read_toml_value 'activation_token' "$BUNDLED_CONFIG")}"
    KSHIELD_API_TOKEN="${KSHIELD_API_TOKEN:-$(read_toml_value 'api_token' "$BUNDLED_CONFIG")}"
fi

: "${KSHIELD_SERVER_URL:?Variable KSHIELD_SERVER_URL requise (ou config/kshield-agent.toml présent)}"
if [ -z "${KSHIELD_API_TOKEN:-}" ]; then
    : "${KSHIELD_ACTIVATION_TOKEN:?Variable KSHIELD_ACTIVATION_TOKEN requise}"
fi

# ─── Root check ────────────────────────────────────────────────
if [ "$(id -u)" -ne 0 ]; then
    err "Doit être lancé avec sudo (installe dans /usr/local/bin/)."
fi

TARGET_USER="${SUDO_USER:-$(whoami)}"
TARGET_UID=$(id -u "$TARGET_USER")
TARGET_HOME=$(eval echo "~${TARGET_USER}")

# ─── Installation du binaire ────────────────────────────────────
TMP_BIN="$(mktemp)"
if [ -f "$BUNDLED_BIN" ]; then
    log "Installation du binaire embarqué $BIN_NAME..."
    cp "$BUNDLED_BIN" "$TMP_BIN"

    if [ -f "$BUNDLED_CHECKSUMS" ]; then
        EXPECTED="$(awk -v name="$BIN_NAME" '$2 == name {print $1}' "$BUNDLED_CHECKSUMS")"
        if command -v sha256sum >/dev/null 2>&1; then
            ACTUAL="$(sha256sum "$TMP_BIN" | awk '{print $1}')"
        else
            ACTUAL="$(shasum -a 256 "$TMP_BIN" | awk '{print $1}')"
        fi
        [ -n "$EXPECTED" ] && [ "$ACTUAL" = "$EXPECTED" ] \
            || err "Checksum SHA-256 invalide pour $BIN_NAME."
    fi
else
    warn "Binaire absent du package; téléchargement de secours depuis $BIN_URL"
    if command -v curl >/dev/null 2>&1; then
        curl -fL --progress-bar -o "$TMP_BIN" "$BIN_URL" \
            || err "Échec du téléchargement de la release ${VERSION}."
    elif command -v wget >/dev/null 2>&1; then
        wget -q --show-progress -O "$TMP_BIN" "$BIN_URL" || err "Échec du téléchargement."
    else
        err "Binaire absent du package et ni curl ni wget disponibles."
    fi
fi

chmod +x "$TMP_BIN"
mv "$TMP_BIN" "$INSTALL_BIN"
log "Binaire installé : $INSTALL_BIN ($(du -h "$INSTALL_BIN" | cut -f1))"

# ─── Copie du TOML bundled ──────────────────────────────────────
CFG_PATH="$TARGET_HOME/.kshield-agent.toml"
if [ -f "$BUNDLED_CONFIG" ]; then
    # Ne pas écraser un TOML déjà activé
    if [ -f "$CFG_PATH" ] && grep -q "api_token" "$CFG_PATH" 2>/dev/null; then
        log "TOML déjà présent : $CFG_PATH (préservé)"
    else
        cp "$BUNDLED_CONFIG" "$CFG_PATH"
        chown "$TARGET_USER" "$CFG_PATH"
        chmod 600 "$CFG_PATH"
        log "TOML installé : $CFG_PATH"
    fi
fi
if [ -d "${SCRIPT_DIR}/certs" ]; then
    cp -R "${SCRIPT_DIR}/certs" "$TARGET_HOME/certs"
    chown -R "$TARGET_USER" "$TARGET_HOME/certs"
fi

# ─── Appairage cloud (activate) ────────────────────────────────
log "Appairage avec le cloud..."
if [ "$TARGET_USER" != "root" ]; then
    sudo -u "$TARGET_USER" -H "$INSTALL_BIN" activate \
        --config "$CFG_PATH" \
        --server-url "$KSHIELD_SERVER_URL" \
        --token     "$KSHIELD_ACTIVATION_TOKEN" \
        || err "Activation échouée. Vérifier le token et l'URL serveur."
else
    "$INSTALL_BIN" activate \
        --config "$CFG_PATH" \
        --server-url "$KSHIELD_SERVER_URL" \
        --token     "$KSHIELD_ACTIVATION_TOKEN" \
        || err "Activation échouée."
fi

# Le TOML final peut avoir été écrit dans le home du user ou de root
if [ ! -f "$CFG_PATH" ] && [ -f "/var/root/.kshield-agent.toml" ]; then
    cp /var/root/.kshield-agent.toml "$CFG_PATH"
fi
chown "$TARGET_USER" "$CFG_PATH" 2>/dev/null || true
chmod 600 "$CFG_PATH" 2>/dev/null || true

log "Activation réussie ✓"

# ─── Service — Linux (systemd) ─────────────────────────────────
if [ "$PLATFORM" = "linux" ]; then
    log "Installation du service systemd..."
    cat > /etc/systemd/system/kshield-edge.service << UNIT
[Unit]
Description=Kaydan Edge Gateway (Go agent)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$TARGET_USER
Environment=HOME=$TARGET_HOME
WorkingDirectory=$TARGET_HOME
ExecStart=$INSTALL_BIN run --config $CFG_PATH
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
UNIT

    systemctl daemon-reload
    systemctl enable kshield-edge.service
    systemctl restart kshield-edge.service
    sleep 2
    if systemctl is-active --quiet kshield-edge; then
        log "Service systemd actif ✓"
    else
        warn "Service pas encore actif — journalctl -u kshield-edge -n 20"
    fi

# ─── Service — macOS (LaunchAgent) ─────────────────────────────
elif [ "$PLATFORM" = "darwin" ]; then
    log "Installation du LaunchAgent macOS..."
    PLIST_PATH="$TARGET_HOME/Library/LaunchAgents/com.kaydangroupe.kshield-edge.plist"
    mkdir -p "$(dirname "$PLIST_PATH")"

    cat > "$PLIST_PATH" << PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.kaydangroupe.kshield-edge</string>
    <key>ProgramArguments</key>
    <array>
        <string>$INSTALL_BIN</string>
        <string>run</string>
        <string>--config</string>
        <string>$CFG_PATH</string>
    </array>
    <key>WorkingDirectory</key>
    <string>$TARGET_HOME</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/tmp/kshield-edge.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/kshield-edge.err</string>
</dict>
</plist>
PLIST

    chown "$TARGET_USER" "$PLIST_PATH"

    # Bootstrap dans la session GUI de l'user (nécessaire quand on est en sudo)
    if [ "$TARGET_USER" != "root" ]; then
        sudo -u "$TARGET_USER" launchctl bootout "gui/$TARGET_UID/com.kaydangroupe.kshield-edge" 2>/dev/null || true
        sudo -u "$TARGET_USER" launchctl bootstrap "gui/$TARGET_UID" "$PLIST_PATH" \
            || sudo -u "$TARGET_USER" launchctl load "$PLIST_PATH"
    else
        launchctl load "$PLIST_PATH"
    fi

    sleep 2
    if sudo -u "$TARGET_USER" launchctl list 2>/dev/null | grep -q com.kaydangroupe.kshield-edge; then
        log "LaunchAgent actif ✓"
    else
        warn "LaunchAgent chargé mais peut-être pas encore actif."
        warn "  Logs : tail -f /tmp/kshield-edge.log /tmp/kshield-edge.err"
        warn "  Kick : launchctl kickstart -k gui/$TARGET_UID/com.kaydangroupe.kshield-edge"
    fi
fi

# ─── Fin ───────────────────────────────────────────────────────
log ""
log "\033[1;32m✓ Kaydan Edge Gateway (Go) installé et démarré\033[0m"
log ""
log "Commandes utiles :"
if [ "$PLATFORM" = "linux" ]; then
    log "  Logs        : journalctl -u kshield-edge -f"
    log "  Redémarrer  : systemctl restart kshield-edge"
    log "  Arrêter     : systemctl stop kshield-edge"
else
    log "  Logs        : tail -f /tmp/kshield-edge.log"
    log "  Erreurs     : tail -f /tmp/kshield-edge.err"
    log "  Redémarrer  : launchctl kickstart -k gui/$TARGET_UID/com.kaydangroupe.kshield-edge"
fi
log "  Vérifier    : $INSTALL_BIN status"
log ""
log "UI cloud : ${KSHIELD_SERVER_URL}/edge-gateway"
