"""Kaydan Shield Local Agent — configuration.

Charge le fichier ``~/.kshield-agent.toml`` (ou un chemin donné via CLI/env).
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover
    import tomli as tomllib


@dataclass
class ReaderConfig:
    """Configuration d'un lecteur RFID/BLE à sonder localement."""
    kind: str                       # "zkteco", "http_webhook", "llrp"
    ip: str
    port: int = 4370
    device_id: Optional[int] = None  # ID Device côté Kaydan Shield (facultatif)
    serial: str = ""
    poll_seconds: int = 3
    extra: dict = field(default_factory=dict)


@dataclass
class AgentConfig:
    """Configuration globale de l'agent."""
    server_url: str                  # ex. "https://api.kaydanshield.com"
    agent_id: str                    # UUID renvoyé par la plateforme
    api_token: str                   # LocalAgent.api_token
    hmac_secret: str = ""            # secret partagé pour signer les messages
    reconnect_max_seconds: int = 30
    heartbeat_seconds: int = 30
    readers: list[ReaderConfig] = field(default_factory=list)
    log_level: str = "INFO"

    @classmethod
    def load(cls, path: Optional[str] = None) -> "AgentConfig":
        """Charge la config depuis un fichier TOML.

        Priorité : path CLI > env KSHIELD_AGENT_CONFIG > ~/.kshield-agent.toml
        """
        candidates = []
        if path:
            candidates.append(Path(path))
        env_path = os.environ.get("KSHIELD_AGENT_CONFIG")
        if env_path:
            candidates.append(Path(env_path))
        candidates.append(Path.home() / ".kshield-agent.toml")

        for p in candidates:
            if p.exists():
                with p.open("rb") as f:
                    data = tomllib.load(f)
                readers = [
                    ReaderConfig(**r) for r in data.pop("readers", [])
                ]
                return cls(readers=readers, **data)

        raise FileNotFoundError(
            "Aucun fichier de config trouvé. Créez ~/.kshield-agent.toml ou "
            "passez --config /chemin.toml"
        )

    # WebSocket URL déduite du server_url
    @property
    def ws_url(self) -> str:
        base = self.server_url.rstrip("/")
        if base.startswith("https://"):
            proto = "wss://"
            host = base.removeprefix("https://")
        elif base.startswith("http://"):
            proto = "ws://"
            host = base.removeprefix("http://")
        else:
            proto = "wss://"
            host = base
        return f"{proto}{host}/ws/agents/{self.agent_id}/?token={self.api_token}"

    @property
    def http_base(self) -> str:
        return self.server_url.rstrip("/") + "/api/v1"
