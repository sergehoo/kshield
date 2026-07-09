"""KAYDAN SHIELD — Kaydan Edge Gateway bootstrap.

Au premier démarrage :
  1. Lit KSHIELD_SERVER_URL + KSHIELD_ACTIVATION_TOKEN depuis env ou config
  2. Appelle POST /devices/edge-gateway/activate/ avec le token
  3. Reçoit api_token permanent + hmac_secret
  4. Sauvegarde la config finale dans ~/.kshield-agent.toml
  5. L'agent démarre en mode normal

L'activation_token n'est utilisable qu'une seule fois. Une fois activé,
l'agent utilise l'api_token permanent pour toutes les communications.
"""
from __future__ import annotations

import logging
import os
import platform
import socket
from pathlib import Path
from typing import Optional

import httpx

from .config import AgentConfig

logger = logging.getLogger(__name__)


def needs_activation(cfg_path: Optional[str] = None) -> bool:
    """Retourne True si la config existante est vide OU si un activation_token env est fourni."""
    if os.environ.get("KSHIELD_ACTIVATION_TOKEN"):
        return True
    path = Path(cfg_path or os.path.expanduser("~/.kshield-agent.toml"))
    if not path.exists():
        return True
    text = path.read_text()
    return "api_token" not in text or 'api_token = ""' in text


def activate(
    server_url: Optional[str] = None,
    activation_token: Optional[str] = None,
    cfg_path: Optional[str] = None,
) -> AgentConfig:
    """Effectue l'appairage avec le cloud.

    Args:
        server_url: URL du serveur Kaydan Shield (défaut env KSHIELD_SERVER_URL).
        activation_token: Token à usage unique (défaut env KSHIELD_ACTIVATION_TOKEN).
        cfg_path: Chemin où écrire la config finale.

    Returns:
        AgentConfig prête à l'usage.

    Raises:
        RuntimeError en cas d'échec (token invalide, expiré, réseau).
    """
    server_url = server_url or os.environ.get("KSHIELD_SERVER_URL")
    activation_token = activation_token or os.environ.get("KSHIELD_ACTIVATION_TOKEN")

    if not server_url or not activation_token:
        raise RuntimeError(
            "KSHIELD_SERVER_URL et KSHIELD_ACTIVATION_TOKEN requis pour l'activation"
        )

    payload = {
        "activation_token": activation_token,
        "hostname": socket.gethostname()[:64],
        "os_info": f"{platform.system()} {platform.release()}"[:120],
        "version": "0.1.0",
        "ip_local": _detect_local_ip(),
    }
    url = f"{server_url.rstrip('/')}/api/v1/devices/edge-gateway/activate/"

    try:
        r = httpx.post(url, json=payload, timeout=15)
    except Exception as exc:
        raise RuntimeError(f"Impossible de contacter le serveur : {exc}") from exc

    if r.status_code >= 400:
        raise RuntimeError(f"Activation refusée ({r.status_code}) : {r.text[:200]}")
    data = r.json()

    cfg = AgentConfig(
        server_url=server_url,
        agent_id=data["gateway_id"],
        api_token=data["api_token"],
        hmac_secret=data.get("hmac_secret", ""),
        readers=[],
    )
    _write_config(cfg, cfg_path)
    logger.info("Activation réussie — gateway_id=%s label=%s",
                 cfg.agent_id, data.get("label"))
    return cfg


def _write_config(cfg: AgentConfig, cfg_path: Optional[str] = None):
    path = Path(cfg_path or os.path.expanduser("~/.kshield-agent.toml"))
    path.parent.mkdir(parents=True, exist_ok=True)
    body = (
        f'# Kaydan Edge Gateway — config générée automatiquement par l\'activation.\n'
        f'server_url  = "{cfg.server_url}"\n'
        f'agent_id    = "{cfg.agent_id}"\n'
        f'api_token   = "{cfg.api_token}"\n'
        f'hmac_secret = "{cfg.hmac_secret}"\n'
        f'log_level   = "INFO"\n'
        f'heartbeat_seconds     = 30\n'
        f'reconnect_max_seconds = 30\n\n'
        f'# Déclare tes lecteurs sous [[readers]] — voir config.example.toml.\n'
    )
    path.write_text(body)
    try:
        path.chmod(0o600)
    except OSError:
        pass


def _detect_local_ip() -> Optional[str]:
    """Best-effort — retourne l'IP locale utilisée pour sortir vers Internet."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return None
