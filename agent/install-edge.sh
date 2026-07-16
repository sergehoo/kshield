#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════
# Kaydan Edge Gateway — Script d'installation universel
# ═══════════════════════════════════════════════════════════════════
#
# Usage :
#   sudo KSHIELD_SERVER_URL='https://kaydanshield.com' \
#        KSHIELD_ACTIVATION_TOKEN='<token>' \
#        ./install-edge.sh
#
# Support :
#   - Linux (systemd) : Ubuntu 20.04+ / Debian 11+ / RHEL 8+ / Fedora / Arch
#   - macOS (launchd) : macOS 12+ (Apple Silicon ARM64 + Intel)
#
# Ce que fait le script :
#   1. Vérifie Python 3.10+
#   2. Clone le code de l'agent depuis GitHub
#   3. Crée un venv Python isolé dans /opt/kshield-edge/
#   4. Installe les dépendances
#   5. Écrit la config TOML avec l'URL serveur + token
#   6. Appaire avec le cloud (échange token → api_token permanent)
#   7. Crée un service systemd/launchd pour auto-start
#   8. Démarre l'agent
# ═══════════════════════════════════════════════════════════════════
set -euo pipefail

INSTALL_DIR="${INSTALL_DIR:-/opt/kshield-edge}"
REPO_URL="${REPO_URL:-https://github.com/sergehoo/kshield.git}"
BRANCH="${BRANCH:-main}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUNDLED_CONFIG="${SCRIPT_DIR}/config/kshield-agent.toml"

log()  { printf "\033[1;34m[install]\033[0m %s\n" "$*"; }
warn() { printf "\033[1;33m[warn]\033[0m %s\n" "$*"; }
err()  { printf "\033[1;31m[FAIL]\033[0m %s\n" "$*" >&2; exit 1; }

read_toml_value() {
    local key="$1"
    local file="$2"
    awk -F'=' -v wanted="$key" '
        $1 ~ "^[[:space:]]*" wanted "[[:space:]]*$" {
            value=$2
            sub(/^[[:space:]]+/, "", value)
            sub(/[[:space:]]+$/, "", value)
            gsub(/^"/, "", value)
            gsub(/"$/, "", value)
            print value
            exit
        }
    ' "$file"
}

# ─── Config depuis env ou ZIP personnalisé ───────────────────────
if [ -z "${KSHIELD_SERVER_URL:-}" ] && [ -f "$BUNDLED_CONFIG" ]; then
    KSHIELD_SERVER_URL="$(read_toml_value "server_url" "$BUNDLED_CONFIG")"
fi
if [ -z "${KSHIELD_ACTIVATION_TOKEN:-}" ] && [ -f "$BUNDLED_CONFIG" ]; then
    KSHIELD_ACTIVATION_TOKEN="$(read_toml_value "activation_token" "$BUNDLED_CONFIG")"
fi

: "${KSHIELD_SERVER_URL:?Variable KSHIELD_SERVER_URL requise ou config/kshield-agent.toml manquant}"
: "${KSHIELD_ACTIVATION_TOKEN:?Variable KSHIELD_ACTIVATION_TOKEN requise ou config/kshield-agent.toml manquant}"

# ─── Détection OS ───────────────────────────────────────────────
OS="$(uname -s)"
case "$OS" in
    Linux*)   PLATFORM="linux" ;;
    Darwin*)  PLATFORM="macos" ;;
    *)        err "OS non supporté : $OS" ;;
esac
log "Plateforme détectée : $PLATFORM"

# ─── Vérif Python 3.10+ ─────────────────────────────────────────
if ! command -v python3 >/dev/null 2>&1; then
    err "Python 3 introuvable. Installer : apt/yum/brew install python3"
fi
PY_VER=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
log "Python version : $PY_VER"

# Extract major.minor and compare with 3.10
PY_MAJOR=$(echo "$PY_VER" | cut -d. -f1)
PY_MINOR=$(echo "$PY_VER" | cut -d. -f2)
if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 10 ]; }; then
    err "Python 3.10+ requis (trouvé $PY_VER)"
fi

# ─── Installation git si absent ─────────────────────────────────
if ! command -v git >/dev/null 2>&1; then
    if [ "$PLATFORM" = "linux" ]; then
        log "Installation de git..."
        if command -v apt-get >/dev/null; then
            apt-get update -qq && apt-get install -y -qq git
        elif command -v yum >/dev/null; then
            yum install -y -q git
        elif command -v dnf >/dev/null; then
            dnf install -y -q git
        else
            err "Impossible d'installer git automatiquement"
        fi
    else
        err "git introuvable. Installer via Xcode Command Line Tools : xcode-select --install"
    fi
fi

# ─── Clone / update du repo ─────────────────────────────────────
mkdir -p "$INSTALL_DIR"
if [ ! -d "$INSTALL_DIR/.git" ]; then
    log "Clone du repo dans $INSTALL_DIR..."
    git clone --depth 1 --branch "$BRANCH" "$REPO_URL" "$INSTALL_DIR"
else
    log "Mise à jour du repo existant..."
    cd "$INSTALL_DIR" && git fetch --depth 1 origin "$BRANCH" && git reset --hard "origin/$BRANCH"
fi

cd "$INSTALL_DIR/agent"

# ─── Création du venv ──────────────────────────────────────────
if [ ! -d ".venv" ]; then
    log "Création du venv Python..."
    python3 -m venv .venv
fi
# shellcheck source=/dev/null
source .venv/bin/activate

log "Installation des dépendances..."
pip install --quiet --upgrade pip
pip install --quiet -e .

# ─── Activation (échange token) ────────────────────────────────
log "Appairage avec le cloud (activation token)..."
kshield-agent activate \
    --server-url "$KSHIELD_SERVER_URL" \
    --token "$KSHIELD_ACTIVATION_TOKEN" \
    || err "Activation échouée. Vérifier le token et l'URL serveur."

log "Activation réussie ✓"

# ─── Service systemd (Linux) ───────────────────────────────────
if [ "$PLATFORM" = "linux" ]; then
    log "Installation du service systemd..."
    SERVICE_USER="${SUDO_USER:-$(id -u -n 1000 2>/dev/null || echo root)}"
    CONFIG_PATH="/home/$SERVICE_USER/.kshield-agent.toml"
    [ -f "$CONFIG_PATH" ] || CONFIG_PATH="/root/.kshield-agent.toml"

    cat > /etc/systemd/system/kshield-edge.service << UNIT
[Unit]
Description=Kaydan Shield Edge Gateway
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$SERVICE_USER
Environment=HOME=/home/$SERVICE_USER
WorkingDirectory=$INSTALL_DIR/agent
ExecStart=$INSTALL_DIR/agent/.venv/bin/kshield-agent run
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
UNIT

    systemctl daemon-reload
    systemctl enable --now kshield-edge
    sleep 3
    if systemctl is-active --quiet kshield-edge; then
        log "Service systemd actif ✓"
    else
        warn "Service démarré mais pas encore actif. Voir : journalctl -u kshield-edge -n 20"
    fi

# ─── Service launchd (macOS) ───────────────────────────────────
elif [ "$PLATFORM" = "macos" ]; then
    log "Installation du LaunchAgent macOS..."
    PLIST_PATH="$HOME/Library/LaunchAgents/com.kaydangroupe.kshield-edge.plist"
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
        <string>$INSTALL_DIR/agent/.venv/bin/kshield-agent</string>
        <string>run</string>
    </array>
    <key>WorkingDirectory</key>
    <string>$INSTALL_DIR/agent</string>
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

    launchctl unload "$PLIST_PATH" 2>/dev/null || true
    launchctl load "$PLIST_PATH"
    sleep 3
    if launchctl list | grep -q com.kaydangroupe.kshield-edge; then
        log "LaunchAgent actif ✓"
    else
        warn "LaunchAgent chargé mais pas actif. Voir : cat /tmp/kshield-edge.err"
    fi
fi

# ─── Fin ────────────────────────────────────────────────────────
log ""
log "\033[1;32m✓ Kaydan Edge Gateway installé et démarré\033[0m"
log ""
log "Commandes utiles :"
if [ "$PLATFORM" = "linux" ]; then
    log "  Logs        : journalctl -u kshield-edge -f"
    log "  Statut      : systemctl status kshield-edge"
    log "  Redémarrer  : sudo systemctl restart kshield-edge"
    log "  Arrêter     : sudo systemctl stop kshield-edge"
else
    log "  Logs        : tail -f /tmp/kshield-edge.log"
    log "  Erreurs     : tail -f /tmp/kshield-edge.err"
    log "  Redémarrer  : launchctl kickstart -k gui/\$(id -u)/com.kaydangroupe.kshield-edge"
    log "  Arrêter     : launchctl unload $PLIST_PATH"
fi
log ""
log "Vérifier sur : $KSHIELD_SERVER_URL/edge-gateway"
