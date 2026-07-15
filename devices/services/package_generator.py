"""Kaydan Edge Gateway — Générateur de package d'installation personnalisé.

Chaque téléchargement produit un ZIP unique contenant :
  - config/kshield-agent.toml     : config personnalisée (gateway_id, token, urls)
  - certs/kshield-ca.crt           : CA cloud (facultatif, injecté si présent)
  - install-edge.sh / install-edge.ps1 / docker-compose.yml selon plateforme
  - README.txt                     : instructions plateforme
  - VERSION                        : metadata pour l'auto-update

Le fichier est généré en mémoire (BytesIO) — pas de stockage disque.
L'activation_token est régénéré à chaque téléchargement pour éviter la
réutilisation d'un token téléchargé par un tiers.
"""
from __future__ import annotations

import io
import json
import logging
import secrets
import zipfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional

from django.conf import settings
from django.utils import timezone as dj_tz

from devices.models import LocalAgent

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════
# Configuration
# ═══════════════════════════════════════════════════════════════════
DEFAULT_ACTIVATION_TTL_HOURS = 72   # Token valide 3 jours
KSHIELD_AGENT_VERSION = "1.0.0"      # Version du bundle généré


@dataclass
class GeneratedPackage:
    """Résultat d'une génération : ZIP en mémoire + metadata."""
    filename: str
    size_bytes: int
    checksum_sha256: str
    content: bytes  # Le ZIP en mémoire (à streamer via HttpResponse)


# ═══════════════════════════════════════════════════════════════════
# Templates de config
# ═══════════════════════════════════════════════════════════════════
CONFIG_TOML_TEMPLATE = """\
# ═══════════════════════════════════════════════════════════════════
# Kaydan Edge Gateway — Configuration
# ═══════════════════════════════════════════════════════════════════
# GÉNÉRÉ AUTOMATIQUEMENT le {generated_at}
# Gateway  : {label}
# Site     : {site_label}
# Tenant   : {tenant_name}
# Version  : {version}
# ─────────────────────────────────────────────────────────────────

[gateway]
id               = "{gateway_id}"
label            = "{label}"
tenant_id        = "{tenant_id}"
site_id          = "{site_id}"

[cloud]
# URL du backend Kaydan Shield (HTTP + WebSocket)
server_url       = "{server_url}"
# Token d'activation à usage unique — échangé contre api_token permanent
# au premier boot via POST /api/v1/agents/<id>/activate/
activation_token = "{activation_token}"
activation_ttl_hours = {activation_ttl}

[mqtt]
host             = "{mqtt_host}"
port             = {mqtt_port}
use_tls          = {mqtt_use_tls}
username         = "{mqtt_username}"
# Password sera récupéré au premier appairage
verify_cert      = true
ca_file          = "certs/kshield-ca.crt"

[agent]
version          = "{version}"
heartbeat_interval_seconds = 30
offline_queue_max_events   = 10000
scan_network_enabled       = true
scan_network_interval_hours = 6
auto_update_enabled        = true
auto_update_check_interval_hours = 6

[logging]
level            = "INFO"
file             = "logs/kshield-edge.log"
max_size_mb      = 50
backup_count     = 5

# ─── Modules devices activés (auto-détectés au boot) ─────────────
[devices]
enable_zkteco    = true
enable_hikvision = true
enable_suprema   = true
enable_hid       = true
enable_dahua     = true
enable_axis      = true
enable_onvif     = true

# ─── Advanced (ne pas modifier sans raison) ──────────────────────
[advanced]
hmac_signature_enabled = true
websocket_reconnect_delay_seconds = 5
websocket_max_reconnect_attempts  = 999999

# ─── Metrics Prometheus (opt-in, désactivé par défaut) ────────────
# Activer si vous souhaitez scraper les métriques runtime de l'agent.
# Bind sur 127.0.0.1 uniquement — pas d'exposition réseau externe.
[metrics]
enabled     = false
listen_addr = "127.0.0.1:9090"
"""


DOCKER_COMPOSE_TEMPLATE = """\
# ═══════════════════════════════════════════════════════════════════
# Kaydan Edge Gateway — docker-compose.yml
# ═══════════════════════════════════════════════════════════════════
# GÉNÉRÉ le {generated_at} pour la gateway "{label}"
# Utilisation : docker compose up -d
# ═══════════════════════════════════════════════════════════════════
services:
  kshield-edge:
    image: kaydangroupe/kshield-edge:{version}
    container_name: kshield-edge-{gateway_short_id}
    restart: unless-stopped
    network_mode: host   # accès LAN pour scan réseau et devices locaux
    volumes:
      - ./config:/etc/kshield-edge:ro
      - ./logs:/var/log/kshield-edge
      - ./data:/var/lib/kshield-edge
      - ./certs:/etc/kshield-edge/certs:ro
    environment:
      KSHIELD_CONFIG_FILE: /etc/kshield-edge/kshield-agent.toml
      KSHIELD_SERVER_URL:  "{server_url}"
      KSHIELD_GATEWAY_ID:  "{gateway_id}"
    healthcheck:
      test: ["CMD-SHELL", "kshield-agent status || exit 1"]
      interval: 30s
      timeout:  10s
      retries:  5
      start_period: 60s
    labels:
      com.kaydangroupe.gateway.id:     "{gateway_id}"
      com.kaydangroupe.gateway.label:  "{label}"
      com.kaydangroupe.gateway.tenant: "{tenant_id}"
"""


README_TEMPLATE = """\
═══════════════════════════════════════════════════════════════════
                    KAYDAN EDGE GATEWAY
                Installation — {label}
═══════════════════════════════════════════════════════════════════

Bienvenue. Ce package contient tout ce qu'il faut pour connecter
ce site au Cloud Kaydan Shield.

Gateway ID         : {gateway_id}
Site               : {site_label}
Organisation       : {tenant_name}
URL Cloud          : {server_url}
Version bundle     : {version}
Généré le          : {generated_at}
Token expire le    : {activation_expires}

───────────────────────────────────────────────────────────────────
INSTALLATION — {platform_label}
───────────────────────────────────────────────────────────────────

{install_instructions}

───────────────────────────────────────────────────────────────────
APRÈS L'INSTALLATION
───────────────────────────────────────────────────────────────────

1. Le service Kaydan Edge Gateway se lance automatiquement au boot.
2. Vérifiez la connexion depuis :
     {server_url}/edge-gateway
3. Le voyant doit passer au vert dans les 60 secondes.

───────────────────────────────────────────────────────────────────
SUPPORT
───────────────────────────────────────────────────────────────────

  Docs        : {server_url}/docs/edge-gateway
  Support     : support@kaydangroupe.com
  Téléphone   : +225 xxxx-xxxx-xx

Ne partagez PAS le fichier config/kshield-agent.toml — il contient
un token d'activation qui donne accès à votre organisation.
"""


INSTALL_INSTRUCTIONS = {
    "linux_deb": (
        "  1. Ouvrir un terminal dans ce dossier\n"
        "  2. Lancer : sudo bash install-edge.sh\n"
        "  3. Le service systemd 'kshield-edge' sera créé et démarré.\n"
        "  4. Vérifier : sudo systemctl status kshield-edge"
    ),
    "linux_rpm": (
        "  1. Ouvrir un terminal dans ce dossier\n"
        "  2. Lancer : sudo bash install-edge.sh\n"
        "  3. Le service systemd 'kshield-edge' sera créé et démarré.\n"
        "  4. Vérifier : sudo systemctl status kshield-edge"
    ),
    "linux_sh": (
        "  1. Ouvrir un terminal dans ce dossier\n"
        "  2. Rendre exécutable : chmod +x install-edge.sh\n"
        "  3. Lancer : sudo bash install-edge.sh\n"
        "  4. Le service tourne. Logs : journalctl -u kshield-edge -f"
    ),
    "windows_exe": (
        "  1. Clic droit sur install-edge.ps1 → Exécuter avec PowerShell\n"
        "     (si bloqué : Set-ExecutionPolicy -Scope Process Bypass)\n"
        "  2. Suivre l'assistant (~2 minutes).\n"
        "  3. Le service Windows 'KaydanEdgeGateway' se lance au boot."
    ),
    "windows_portable": (
        "  1. Extraire le contenu dans C:\\Program Files\\KaydanEdge\\\n"
        "  2. Ouvrir PowerShell en administrateur\n"
        "  3. cd C:\\Program Files\\KaydanEdge\n"
        "  4. .\\install-edge.ps1"
    ),
    "macos_pkg": (
        "  1. Ouvrir un terminal dans ce dossier\n"
        "  2. Lancer : sudo bash install-edge.sh\n"
        "  3. Approuver l'ajout à LaunchDaemons si demandé.\n"
        "  4. Vérifier : sudo launchctl list | grep kaydan"
    ),
    "docker": (
        "  1. Docker & Docker Compose installés requis\n"
        "  2. Ouvrir un terminal dans ce dossier\n"
        "  3. Lancer : docker compose up -d\n"
        "  4. Voir les logs : docker compose logs -f"
    ),
    "raspberry_pi": (
        "  1. Raspberry Pi OS 64-bit recommandé (Bullseye+)\n"
        "  2. Ouvrir un terminal dans ce dossier\n"
        "  3. Lancer : sudo bash install-edge.sh\n"
        "  4. Vérifier : sudo systemctl status kshield-edge"
    ),
    "mini_pc": (
        "  1. Mini PC industriel avec Debian/Ubuntu\n"
        "  2. Ouvrir un terminal dans ce dossier\n"
        "  3. Lancer : sudo bash install-edge.sh"
    ),
    "windows": (
        "  1. Clic droit sur install-edge.ps1 → Exécuter avec PowerShell\n"
        "  2. Suivre l'assistant."
    ),
}


VERSION_MANIFEST_TEMPLATE = """\
{{
    "version": "{version}",
    "generated_at": "{generated_at}",
    "gateway_id": "{gateway_id}",
    "gateway_label": "{label}",
    "server_url": "{server_url}",
    "platform": "{platform}",
    "update_check_url": "{server_url}/api/v1/edge-gateway/updates/check/",
    "min_python_version": "3.10"
}}
"""


# ═══════════════════════════════════════════════════════════════════
# Service principal
# ═══════════════════════════════════════════════════════════════════
class PackageGenerator:
    """Génère un ZIP d'installation personnalisé par gateway + plateforme."""

    def __init__(self, agent: LocalAgent, platform: str):
        if platform not in dict(self._platform_choices()):
            raise ValueError(f"Platform inconnue : {platform}")
        self.agent = agent
        self.platform = platform

    @staticmethod
    def _platform_choices():
        from devices.models import EdgeGatewayPackage
        return EdgeGatewayPackage.PLATFORM_CHOICES

    # ──────────────────────────────────────────────────────────
    # Génération
    # ──────────────────────────────────────────────────────────
    def generate(self) -> GeneratedPackage:
        """Crée le ZIP en mémoire et retourne un GeneratedPackage."""
        # 1. Regénère un activation_token frais à chaque téléchargement
        self._rotate_activation_token()

        # 2. Assemble le contexte de rendu
        ctx = self._build_context()

        # 3. Construit le ZIP en mémoire
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED,
                              compresslevel=6) as zf:
            self._write_zip(zf, ctx)

        content = buffer.getvalue()
        buffer.close()

        # 4. Metadata
        import hashlib
        checksum = hashlib.sha256(content).hexdigest()
        filename = self._filename(ctx)

        logger.info(
            "PackageGenerator: gateway=%s platform=%s size=%s sha256=%s",
            self.agent.id, self.platform, len(content), checksum[:16],
        )

        return GeneratedPackage(
            filename=filename,
            size_bytes=len(content),
            checksum_sha256=checksum,
            content=content,
        )

    # ──────────────────────────────────────────────────────────
    # Rotation du activation_token à chaque download
    # ──────────────────────────────────────────────────────────
    def _rotate_activation_token(self):
        """Regénère un token à usage unique valide {TTL} heures."""
        if self.agent.activated_at:
            # Gateway déjà activée — on ne regénère pas le token, on rend
            # celui existant (si présent) ou vide (l'agent utilise api_token).
            return

        new_token = secrets.token_urlsafe(48)
        ttl = timedelta(hours=DEFAULT_ACTIVATION_TTL_HOURS)
        self.agent.activation_token = new_token
        self.agent.activation_expires_at = dj_tz.now() + ttl
        self.agent.save(update_fields=["activation_token", "activation_expires_at"])

    # ──────────────────────────────────────────────────────────
    # Contexte de rendu
    # ──────────────────────────────────────────────────────────
    def _build_context(self) -> Dict[str, str]:
        agent = self.agent
        tenant = agent.tenant
        site = agent.site
        now_iso = dj_tz.now().strftime("%Y-%m-%d %H:%M:%S %Z")

        server_url = getattr(settings, "PUBLIC_BASE_URL", None) \
            or self._infer_server_url()
        mqtt_host = getattr(settings, "MQTT_PUBLIC_HOST", None) \
            or getattr(settings, "MQTT_HOST", "shieldmqtt")
        mqtt_port = int(getattr(settings, "MQTT_PORT", 1883))
        mqtt_tls = bool(getattr(settings, "MQTT_TLS", False))

        # En prod, MQTT_HOST=shieldmqtt (nom Docker interne) est inutile pour
        # un client externe. On expose le hostname public ou l'IP publique.
        if mqtt_host == "shieldmqtt":
            # Fallback : dérive depuis PUBLIC_BASE_URL
            from urllib.parse import urlparse
            parsed = urlparse(server_url)
            mqtt_host = parsed.hostname or "mqtt.kaydanshield.com"

        expires = agent.activation_expires_at
        expires_str = expires.strftime("%Y-%m-%d %H:%M %Z") if expires else "n/a"

        return {
            "gateway_id":        str(agent.id),
            "gateway_short_id":  str(agent.id)[:8],
            "label":             agent.label,
            "tenant_id":         str(tenant.id) if tenant else "",
            "tenant_name":       str(tenant) if tenant else "N/A",
            "site_id":           str(site.id) if site else "",
            "site_label":        str(site) if site else "N/A",
            "server_url":        server_url.rstrip("/"),
            "mqtt_host":         mqtt_host,
            "mqtt_port":         str(mqtt_port),
            "mqtt_use_tls":      "true" if mqtt_tls else "false",
            "mqtt_username":     f"kshield-edge-{str(agent.id)[:8]}",
            "activation_token":  agent.activation_token or "",
            "activation_ttl":    str(DEFAULT_ACTIVATION_TTL_HOURS),
            "activation_expires": expires_str,
            "generated_at":      now_iso,
            "version":           KSHIELD_AGENT_VERSION,
            "platform":          self.platform,
            "platform_label":    self._platform_label(),
            "install_instructions": INSTALL_INSTRUCTIONS.get(
                self.platform, INSTALL_INSTRUCTIONS["linux_sh"]),
        }

    def _infer_server_url(self) -> str:
        """Fallback pour PUBLIC_BASE_URL — dérive depuis ALLOWED_HOSTS."""
        allowed = getattr(settings, "ALLOWED_HOSTS", [])
        for h in allowed:
            if h and h not in ("*", "localhost", "127.0.0.1"):
                return f"https://{h}"
        return "https://kaydanshield.com"

    def _platform_label(self) -> str:
        return dict(self._platform_choices()).get(self.platform, self.platform)

    def _filename(self, ctx: Dict[str, str]) -> str:
        safe_label = "".join(c if c.isalnum() or c in "-_" else "-"
                              for c in ctx["label"])[:40] or "gateway"
        return (f"KaydanEdgeGateway-{safe_label}-"
                  f"{ctx['version']}-{self.platform}.zip")

    # ──────────────────────────────────────────────────────────
    # Contenu du ZIP
    # ──────────────────────────────────────────────────────────
    def _write_zip(self, zf: zipfile.ZipFile, ctx: Dict[str, str]):
        # 1. Config TOML personnalisée + section [[targets]] par équipement
        toml_content = CONFIG_TOML_TEMPLATE.format(**ctx)
        toml_content += self._render_targets_toml()
        zf.writestr("config/kshield-agent.toml", toml_content)

        # 2. Certificat CA si présent
        ca_path = getattr(settings, "KSHIELD_CA_CERT_PATH", None)
        if ca_path:
            try:
                with open(ca_path, "rb") as f:
                    zf.writestr("certs/kshield-ca.crt", f.read())
            except FileNotFoundError:
                logger.warning("KSHIELD_CA_CERT_PATH=%s introuvable", ca_path)

        # 3. Script d'installation selon plateforme
        install_script, install_name = self._get_install_script(ctx)
        if install_script:
            info = zipfile.ZipInfo(install_name)
            info.external_attr = 0o755 << 16  # rendre exécutable
            zf.writestr(info, install_script)

        # 4. docker-compose.yml (uniquement pour la plateforme docker)
        if self.platform == "docker":
            zf.writestr("docker-compose.yml",
                        DOCKER_COMPOSE_TEMPLATE.format(**ctx))

        # 5. README plateforme-spécifique
        zf.writestr("README.txt", README_TEMPLATE.format(**ctx))

        # 6. Manifest de version pour l'auto-update
        zf.writestr("VERSION.json", VERSION_MANIFEST_TEMPLATE.format(**ctx))

    def _render_targets_toml(self) -> str:
        """Génère les sections [[targets]] TOML pour tous les équipements
        actifs de cette gateway.

        Format attendu par l'agent Go (config.TargetSection) :
            [[targets]]
            id = "uuid"
            vendor = "hikvision"
            ip = "192.168.1.20"
            port = 80
            username = "admin"
            password = "***"

            [targets.extra]
            key = "value"
        """
        try:
            from devices.models import GatewayTarget
        except Exception:
            return ""

        targets = GatewayTarget.objects.filter(
            gateway=self.agent, enabled=True,
        ).order_by("vendor", "label")

        if not targets.exists():
            return "\n# Aucun équipement vendor configuré pour cette gateway.\n"

        lines = ["\n\n# ═══ Targets vendors — générés depuis Kaydan Shield admin ═══"]
        for t in targets:
            lines.append("")
            lines.append("[[targets]]")
            lines.append(f'id       = "{t.pk}"')
            lines.append(f'vendor   = "{t.vendor}"')
            lines.append(f'ip       = "{t.ip}"')
            lines.append(f'port     = {int(t.port or 0)}')
            lines.append(f'username = "{_toml_escape(t.username or "")}"')
            lines.append(f'password = "{_toml_escape(t.password or "")}"')
            if t.extra:
                lines.append("")
                lines.append("[targets.extra]")
                for k, v in t.extra.items():
                    lines.append(f'{k} = "{_toml_escape(str(v))}"')
        return "\n".join(lines) + "\n"

    def _get_install_script(self, ctx: Dict[str, str]) -> tuple[Optional[str], str]:
        """Retourne (contenu_script, nom_fichier) selon la plateforme."""
        # Windows → PowerShell
        if self.platform in ("windows", "windows_exe", "windows_portable"):
            return self._load_script_asset("install-edge.ps1"), "install-edge.ps1"

        # Docker → pas de script, docker-compose suffit
        if self.platform == "docker":
            return None, ""

        # Linux/macOS/RPI → bash
        return self._load_script_asset("install-edge.sh"), "install-edge.sh"

    def _load_script_asset(self, filename: str) -> str:
        """Lit un asset du dossier agent/ et l'injecte tel quel dans le ZIP.

        Les scripts prennent leur config depuis les variables d'env passées
        au run (KSHIELD_SERVER_URL, KSHIELD_ACTIVATION_TOKEN). Ils lisent
        aussi config/kshield-agent.toml qu'on vient d'écrire dans le ZIP.
        """
        import os
        agent_dir = os.path.join(settings.BASE_DIR, "agent")
        script_path = os.path.join(agent_dir, filename)
        if not os.path.exists(script_path):
            logger.warning("Script %s introuvable dans %s", filename, agent_dir)
            return (f"#!/bin/sh\n"
                    f"echo 'Script {filename} manquant — contactez le support.'\n"
                    f"exit 1\n")
        with open(script_path, "r", encoding="utf-8") as f:
            return f.read()


def _toml_escape(s: str) -> str:
    """Échappe une string pour un TOML value double-quoted.

    Selon TOML spec 1.0 : escape \\ et " et les control chars.
    """
    return (
        s.replace("\\", "\\\\")
         .replace('"', '\\"')
         .replace("\n", "\\n")
         .replace("\r", "\\r")
         .replace("\t", "\\t")
    )
