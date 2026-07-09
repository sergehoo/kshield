"""KAYDAN SHIELD — Driver Framework, base abstraite.

Chaque constructeur d'équipement est isolé dans un plugin qui implémente
l'interface ``BaseDriver`` ci-dessous. Le reste de la plateforme ne dépend
JAMAIS d'un module vendor-specific — tout passe par ce contrat commun.

Le ``DriverManager`` (voir ``devices.drivers.manager``) sélectionne le bon
driver pour un ``Device`` donné en fonction de ``DeviceModel.brand/model``.

Cycle de vie :
    driver = DriverManager.for_device(device)
    with driver:                   # connect() / disconnect() automatique
        info = driver.get_info()
        driver.start_enrollment(session_id="abc")
        events = driver.read_events()
"""
from __future__ import annotations

import abc
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, ContextManager, Iterable, Optional

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════
# Data classes de retour (normalisées, indépendantes du vendor)
# ═══════════════════════════════════════════════════════════════════
@dataclass
class DeviceInfo:
    """Snapshot d'identification d'un équipement — même shape pour tous."""
    serial: str = ""
    brand: str = ""
    model: str = ""
    firmware: str = ""
    hardware: str = ""
    mac: str = ""
    ip: str = ""
    capabilities: list[str] = field(default_factory=list)
    raw: dict = field(default_factory=dict)


@dataclass
class DeviceStatus:
    """État runtime — alimente le Digital Twin."""
    reachable: bool = False
    latency_ms: Optional[int] = None
    uptime_seconds: Optional[int] = None
    cpu_percent: Optional[float] = None
    ram_percent: Optional[float] = None
    storage_percent: Optional[float] = None
    temperature_c: Optional[float] = None
    battery_percent: Optional[int] = None
    network_quality: Optional[int] = None      # 0-100 (RSSI normalisé)
    firmware: str = ""
    errors: list[str] = field(default_factory=list)
    raw: dict = field(default_factory=dict)
    at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class DeviceEvent:
    """Événement générique — badge présenté, porte ouverte, etc.

    Publié sur l'Event Bus (Redis pub/sub + EMQX) après normalisation.
    """
    event_type: str            # "rfid.detected", "door.opened", "tamper", …
    at: datetime
    uid: str = ""
    door: str = ""
    granted: Optional[bool] = None
    payload: dict = field(default_factory=dict)


@dataclass
class DriverResult:
    """Retour standard pour toute commande exécutée par un driver."""
    ok: bool
    detail: str = ""
    data: dict = field(default_factory=dict)
    raw: Any = None


# ═══════════════════════════════════════════════════════════════════
# Capabilities — chaque driver déclare ce qu'il sait faire
# ═══════════════════════════════════════════════════════════════════
class Capability:
    PING              = "ping"
    DISCOVER          = "discover"
    GET_INFO          = "get_info"
    GET_STATUS        = "get_status"
    READ_EVENTS       = "read_events"
    ENROLL_RFID       = "enroll_rfid"
    ENROLL_FACE       = "enroll_face"
    ENROLL_FINGERPRINT = "enroll_fingerprint"
    PUSH_USER         = "push_user"
    SYNC_ATTENDANCES  = "sync_attendances"
    RESTART           = "restart"
    UPDATE_FIRMWARE   = "update_firmware"
    DOOR_UNLOCK       = "door_unlock"


# ═══════════════════════════════════════════════════════════════════
# Contrat de base — TOUS les drivers en héritent
# ═══════════════════════════════════════════════════════════════════
class BaseDriver(abc.ABC):
    """Interface unique parlée par toute la plateforme.

    L'implémentation vendor-specific vit dans un sous-module dédié
    (``devices/drivers/hikvision/driver.py``, etc.).

    Contract-first : les méthodes RETOURNENT toujours un ``DriverResult``
    ou une dataclass normalisée. Ne lève JAMAIS une exception vendor-specific
    au-dessus de cette couche — attraper et wrapper dans un ``DriverResult(ok=False)``.
    """

    # Identifiants — remplis par la sous-classe
    vendor: str = "unknown"
    supported_models: tuple[str, ...] = ()
    capabilities: tuple[str, ...] = ()

    def __init__(self, device):
        """
        Args:
            device: instance ``devices.models.Device`` (accès à ip, port, model.spec…)
        """
        self.device = device
        self._connected = False

    # ────────────────────────────────────────────────────────────
    # Lifecycle — context manager friendly
    # ────────────────────────────────────────────────────────────
    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            self.disconnect()
        except Exception as exc:
            logger.debug("Driver %s disconnect KO : %s", self.vendor, exc)
        return False

    @abc.abstractmethod
    def connect(self) -> DriverResult:
        """Ouvre la session vers l'équipement."""

    @abc.abstractmethod
    def disconnect(self) -> DriverResult:
        """Ferme proprement la session."""

    # ────────────────────────────────────────────────────────────
    # Info + statut (obligatoires)
    # ────────────────────────────────────────────────────────────
    @abc.abstractmethod
    def ping(self) -> DriverResult:
        """Test de vie rapide (TCP ou heartbeat vendor)."""

    def get_info(self) -> DeviceInfo:
        """Snapshot d'identification — par défaut, retourne ce qu'on connaît via le modèle."""
        m = self.device.model
        return DeviceInfo(
            serial=self.device.serial_number, brand=m.brand, model=m.model,
            firmware=self.device.firmware_version, mac=self.device.mac_address or "",
            ip=self.device.ip_address or "",
        )

    def get_status(self) -> DeviceStatus:
        """État runtime détaillé — par défaut, ping + heartbeat récent."""
        r = self.ping()
        s = DeviceStatus(reachable=r.ok, latency_ms=r.data.get("latency_ms"))
        s.firmware = self.device.firmware_version
        return s

    # ────────────────────────────────────────────────────────────
    # Actions optionnelles (surcharger si supporté)
    # ────────────────────────────────────────────────────────────
    def read_events(self, since: Optional[datetime] = None) -> Iterable[DeviceEvent]:
        """Pull les événements depuis un timestamp donné.

        Le driver DOIT être idempotent — retourner uniquement les nouveaux.
        """
        return []

    def start_enrollment(self, session_id: str,
                          mode: str = "rfid", timeout_seconds: int = 120) -> DriverResult:
        """Passe le lecteur en mode enrôlement (bloque les scans normaux)."""
        return DriverResult(ok=False, detail=f"{self.vendor} ne supporte pas l'enrôlement")

    def stop_enrollment(self, session_id: str) -> DriverResult:
        """Sort du mode enrôlement, revient en mode contrôle d'accès."""
        return DriverResult(ok=True)

    def sync(self) -> DriverResult:
        """Synchronisation générique (push users + pull events)."""
        return DriverResult(ok=False, detail=f"{self.vendor} ne supporte pas sync()")

    def restart(self) -> DriverResult:
        return DriverResult(ok=False, detail=f"{self.vendor} ne supporte pas restart()")

    def update_firmware(self, firmware_url: str, checksum: str = "") -> DriverResult:
        return DriverResult(ok=False, detail=f"{self.vendor} ne supporte pas update_firmware()")

    def door_unlock(self, door_id: str = "", duration_seconds: int = 5) -> DriverResult:
        return DriverResult(ok=False, detail=f"{self.vendor} ne supporte pas door_unlock()")

    def push_user(self, user_data: dict) -> DriverResult:
        return DriverResult(ok=False, detail=f"{self.vendor} ne supporte pas push_user()")

    # ────────────────────────────────────────────────────────────
    # Introspection
    # ────────────────────────────────────────────────────────────
    def has_capability(self, cap: str) -> bool:
        return cap in self.capabilities

    def __repr__(self):
        return f"<{self.__class__.__name__} {self.vendor} device={self.device.pk}>"


# ═══════════════════════════════════════════════════════════════════
# Décorateur de registration — chaque plugin fait :
#     @register_driver
#     class HikvisionDriver(BaseDriver): ...
# ═══════════════════════════════════════════════════════════════════
_DRIVER_REGISTRY: dict[str, type[BaseDriver]] = {}


def register_driver(cls: type[BaseDriver]) -> type[BaseDriver]:
    """Enregistre un driver dans le registre global.

    Appelé au moment de l'import du module — les drivers sont autodétectés
    par ``DriverManager.autoload()``.
    """
    key = cls.vendor.lower()
    if key in _DRIVER_REGISTRY:
        logger.warning("Driver %s déjà enregistré, écrasement", key)
    _DRIVER_REGISTRY[key] = cls
    return cls


def get_registered_drivers() -> dict[str, type[BaseDriver]]:
    return dict(_DRIVER_REGISTRY)
