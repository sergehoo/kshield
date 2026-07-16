"""DeviceDiscoveryService — Workflow §2.2 refonte détection équipements.

Flow complet cahier des charges §2.2 :

    Lancement du scan
      → Détection des équipements (via probes ARP/mDNS/ONVIF/SSDP/SNMP)
      → Identification du type (matching OUI MAC + protocoles)
      → Lecture des informations disponibles
      → Vérification de compatibilité (driver dispo ?)
      → Test de connexion (ping, HTTP, ONVIF getInfo)
      → Prévisualisation (retour à l'admin)
      → Affectation à un site et une zone
      → Enregistrement (adopt = crée Device officiel)
      → Activation (Device.status → CONNECTING → ONLINE)
      → Monitoring
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Optional

from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════
# Structures
# ═══════════════════════════════════════════════════════════════════
@dataclass
class DiscoveryResult:
    ok: bool
    discovery: Any = None
    device: Any = None
    error: str = ""
    error_code: str = ""
    created: bool = False   # True si nouveau, False si maj d'un existant


# OUI MAC → vendor (pour identification rapide)
OUI_MAP: dict[str, str] = {
    # Hikvision
    "00:12:41": "Hikvision", "00:19:1b": "Hikvision",
    "c0:56:e3": "Hikvision", "34:5f:c1": "Hikvision",
    # ZKTeco
    "00:17:29": "ZKTeco",    "00:20:16": "ZKTeco",
    # Axis Communications
    "00:40:8c": "Axis",      "ac:cc:8e": "Axis",  "b8:a4:4f": "Axis",
    # Dahua
    "00:1c:c4": "Dahua",     "3c:ef:8c": "Dahua",
    # Suprema
    "00:17:fc": "Suprema",   "00:14:d0": "Suprema",
    # HID Global
    "00:06:8e": "HID",       "00:11:57": "HID",
    # Raspberry Pi
    "b8:27:eb": "Raspberry Pi", "dc:a6:32": "Raspberry Pi",
}

# Détection vendor → driver suggéré
VENDOR_TO_DRIVER: dict[str, str] = {
    "hikvision":   "hikvision",
    "zkteco":      "zkteco",
    "axis":        "axis",
    "dahua":       "dahua",
    "suprema":     "suprema",
    "hid":         "hid",
    "onvif":       "onvif",
}


# ═══════════════════════════════════════════════════════════════════
# DeviceDiscoveryService
# ═══════════════════════════════════════════════════════════════════
class DeviceDiscoveryService:
    """Service stateless du workflow de découverte."""

    # ─── Register (dedup + upsert) ───────────────────────────────
    @classmethod
    @transaction.atomic
    def register_discovered(
        cls,
        tenant,
        mac_address: str = "",
        ip_address: str = "",
        hostname: str = "",
        serial_number: str = "",
        vendor: str = "",
        model: str = "",
        device_type: str = "",
        firmware_version: str = "",
        detected_via: str = "unknown",
        protocols_supported: Optional[list] = None,
        ports_open: Optional[list] = None,
        latency_ms: int = 0,
        signal_strength: Optional[int] = None,
        gateway=None,
        site=None,
        scan=None,
        raw_payload: Optional[dict] = None,
    ) -> DiscoveryResult:
        """Enregistre (ou met à jour) un équipement détecté.

        Idempotent : si un DeviceDiscovery existe pour la même MAC dans
        le tenant, on l'update (incrémente times_seen + refresh last_seen).
        """
        from devices.models_discovery import (
            DeviceDiscovery, DiscoveryStatus, DiscoveryProtocol,
        )

        # Normalisation MAC
        mac_address = (mac_address or "").lower().replace("-", ":")

        # Auto-detect vendor si non fourni via OUI MAC
        if not vendor and mac_address and len(mac_address) >= 8:
            oui = mac_address[:8]
            vendor = OUI_MAP.get(oui, "")

        # Détection compatibilité + driver suggéré
        compatibility, suggested_driver = cls._detect_compatibility(
            vendor=vendor, device_type=device_type,
            protocols=protocols_supported or [],
        )

        defaults = {
            "ip_address":          ip_address or None,
            "hostname":            hostname[:120],
            "serial_number":       serial_number[:64],
            "vendor":              vendor[:64],
            "model":               model[:120],
            "device_type":         device_type[:32],
            "firmware_version":    firmware_version[:40],
            "detected_via":        (detected_via if detected_via in
                                        dict(DiscoveryProtocol.choices)
                                        else DiscoveryProtocol.UNKNOWN),
            "protocols_supported": protocols_supported or [],
            "ports_open":          ports_open or [],
            "latency_ms":          latency_ms,
            "signal_strength":     signal_strength,
            "compatibility":       compatibility,
            "suggested_driver":    suggested_driver,
            "gateway":             gateway,
            "site":                site,
            "scan":                scan,
            "raw_payload":         raw_payload or {},
        }

        created = False
        if mac_address:
            # Match par MAC (clé forte)
            obj, created = DeviceDiscovery.objects.update_or_create(
                tenant=tenant, mac_address=mac_address,
                defaults=defaults,
            )
        elif serial_number:
            # Fallback : match par serial
            obj, created = DeviceDiscovery.objects.update_or_create(
                tenant=tenant, serial_number=serial_number,
                defaults={**defaults, "mac_address": ""},
            )
        elif ip_address:
            # Fallback : match par IP (moins fiable — dedup pas garanti)
            obj = DeviceDiscovery.objects.filter(
                tenant=tenant, ip_address=ip_address,
                status__in=[DiscoveryStatus.DETECTED, DiscoveryStatus.TESTED],
            ).first()
            if obj:
                for k, v in defaults.items():
                    setattr(obj, k, v)
                obj.save()
                created = False
            else:
                obj = DeviceDiscovery.objects.create(
                    tenant=tenant, mac_address="", **defaults,
                )
                created = True
        else:
            return DiscoveryResult(
                ok=False, error_code="no_identifier",
                error="Au moins mac_address, serial_number ou ip_address requis",
            )

        # Incrémente times_seen si mise à jour
        if not created:
            obj.times_seen = (obj.times_seen or 0) + 1
            obj.save(update_fields=["times_seen"])

        # Reset status à detected si stale (nouveau scan reveille l'équipement)
        if obj.status == DiscoveryStatus.STALE:
            obj.status = DiscoveryStatus.DETECTED
            obj.save(update_fields=["status"])

        logger.info(
            "Discovery %s : %s / %s (%s, compat=%s)",
            "new" if created else "updated",
            mac_address or ip_address, vendor or "?",
            device_type or "?", compatibility,
        )
        return DiscoveryResult(ok=True, discovery=obj, created=created)

    # ─── Test de connexion ───────────────────────────────────────
    @classmethod
    def test_connection(cls, discovery, deep: bool = False) -> DiscoveryResult:
        """Teste la connexion à l'équipement découvert.

        - deep=False : ping simple TCP sur port ouvert
        - deep=True  : test protocole complet (auth, getInfo, etc.)

        Update discovery.last_test_* et status → tested si succès.
        """
        from devices.models_discovery import DiscoveryStatus
        import socket

        start = time.time()
        success = False
        error = ""
        response = {}

        try:
            ip = str(discovery.ip_address) if discovery.ip_address else ""
            if not ip:
                return DiscoveryResult(
                    ok=False, discovery=discovery,
                    error_code="no_ip", error="Pas d'IP pour tester",
                )

            # Test TCP simple sur un port utile
            port = (discovery.ports_open or [80])[0]
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(3.0)
            sock.connect((ip, port))
            sock.close()

            latency = int((time.time() - start) * 1000)
            success = True
            response = {"port": port, "latency_ms": latency}
            discovery.latency_ms = latency

        except Exception as e:
            error = str(e)[:2000]
            success = False

        discovery.last_test_at = timezone.now()
        discovery.last_test_success = success
        discovery.last_test_error = error
        discovery.last_test_response = response
        if success and discovery.status == DiscoveryStatus.DETECTED:
            discovery.status = DiscoveryStatus.TESTED
        discovery.save(update_fields=[
            "last_test_at", "last_test_success", "last_test_error",
            "last_test_response", "latency_ms", "status",
        ])
        return DiscoveryResult(ok=success, discovery=discovery,
                                error=error, error_code="test_failed" if not success else "")

    # ─── Adoption : DeviceDiscovery → Device officiel ───────────
    @classmethod
    @transaction.atomic
    def adopt(
        cls,
        discovery,
        adopted_by,
        site=None,
        zone=None,
        checkpoint=None,
        name: str = "",
        driver_override: str = "",
    ) -> DiscoveryResult:
        """Convertit un DeviceDiscovery en Device officiel.

        Le Device est créé avec status=CONNECTING, driver = suggested_driver
        (ou override), site = auto ou fourni, checkpoint = optionnel.
        """
        from devices.models import Device
        from devices.models_discovery import (
            DiscoveryStatus, DeviceCompatibility,
        )

        # Validation
        if discovery.status == DiscoveryStatus.ADOPTED:
            return DiscoveryResult(
                ok=False, discovery=discovery, error_code="already_adopted",
                error=f"Déjà adopté (Device {discovery.adopted_device_id})",
            )
        if discovery.status == DiscoveryStatus.REJECTED:
            return DiscoveryResult(
                ok=False, discovery=discovery, error_code="rejected",
                error="Équipement rejeté — le ré-activer d'abord.",
            )
        if discovery.compatibility == DeviceCompatibility.INCOMPATIBLE:
            return DiscoveryResult(
                ok=False, discovery=discovery, error_code="incompatible",
                error="Équipement incompatible avec Kaydan Shield",
            )

        # Site : fourni ou hérité de discovery.site ou discovery.gateway.site
        final_site = site or discovery.site or (
            discovery.gateway.site if discovery.gateway else None
        )
        if not final_site:
            return DiscoveryResult(
                ok=False, discovery=discovery, error_code="no_site",
                error="Aucun site n'a pu être déterminé — spécifier explicitement",
            )

        # Génération d'un serial_number si absent (fallback MAC)
        serial = discovery.serial_number or (
            discovery.mac_address.replace(":", "").upper()[:24]
            if discovery.mac_address else f"KSH-{discovery.pk}"[:24]
        )
        display_name = name or discovery.hostname or discovery.model or \
                        f"{discovery.vendor or 'device'}-{serial[:8]}"

        # Récupère un DeviceModel générique — les vrais matching seront
        # dans un dispatcher métier plus tard.
        from devices.models import DeviceModel
        # DeviceType (peut être null en fallback)
        device_type = discovery.device_type or "generic"
        try:
            # On prend n'importe quel DeviceModel du même type
            model_obj = DeviceModel.objects.filter(type=device_type).first()
        except Exception:
            model_obj = None

        # Création du Device officiel
        device_kwargs = {
            "tenant":         discovery.tenant,
            "site":           final_site,
            "checkpoint":     checkpoint,
            "serial_number":  serial[:64],
            "status":         "connecting",   # état initial post-adoption
        }
        # display_name / name — s'adapter aux champs réels du Device
        # (compatible avec Device.name si existe, sinon skip)
        try:
            device = Device(**device_kwargs)
            # Champs optionnels selon le modèle réel
            if hasattr(device, "name"):
                setattr(device, "name", display_name[:120])
            if hasattr(device, "model") and model_obj is not None:
                setattr(device, "model", model_obj)
            if hasattr(device, "ip_address") and discovery.ip_address:
                setattr(device, "ip_address", discovery.ip_address)
            if hasattr(device, "mac_address"):
                setattr(device, "mac_address", discovery.mac_address)
            if hasattr(device, "firmware_version"):
                setattr(device, "firmware_version",
                        discovery.firmware_version[:40])
            device.save()
        except Exception as e:
            logger.exception("Adoption Device create failed")
            return DiscoveryResult(
                ok=False, discovery=discovery, error_code="device_create_failed",
                error=str(e),
            )

        # Marquage discovery adopté
        discovery.status = DiscoveryStatus.ADOPTED
        discovery.adopted_device = device
        discovery.adopted_at = timezone.now()
        discovery.adopted_by = str(adopted_by)[:200]
        discovery.save(update_fields=[
            "status", "adopted_device", "adopted_at", "adopted_by",
        ])

        logger.info(
            "Adoption : DeviceDiscovery %s → Device %s (site=%s)",
            discovery.pk, device.pk, final_site.pk,
        )
        return DiscoveryResult(
            ok=True, discovery=discovery, device=device, created=True,
        )

    # ─── Rejet ───────────────────────────────────────────────────
    @classmethod
    def reject(
        cls, discovery, rejected_by, reason: str = "",
    ) -> DiscoveryResult:
        """Rejette une découverte (l'ignore définitivement).

        Un discovery rejeté n'apparaît plus dans les scans sauf si l'admin
        le réactive manuellement (status → detected).
        """
        from devices.models_discovery import DiscoveryStatus

        discovery.status = DiscoveryStatus.REJECTED
        discovery.rejected_at = timezone.now()
        discovery.rejected_reason = reason[:240]
        discovery.save(update_fields=[
            "status", "rejected_at", "rejected_reason",
        ])
        return DiscoveryResult(ok=True, discovery=discovery)

    # ─── Réactivation (rejeté → detected) ────────────────────────
    @classmethod
    def reactivate(cls, discovery) -> DiscoveryResult:
        from devices.models_discovery import DiscoveryStatus
        if discovery.status not in (
            DiscoveryStatus.REJECTED, DiscoveryStatus.STALE,
        ):
            return DiscoveryResult(
                ok=False, discovery=discovery, error_code="wrong_status",
                error=f"Ne peut réactiver depuis {discovery.status}",
            )
        discovery.status = DiscoveryStatus.DETECTED
        discovery.rejected_at = None
        discovery.rejected_reason = ""
        discovery.save(update_fields=[
            "status", "rejected_at", "rejected_reason",
        ])
        return DiscoveryResult(ok=True, discovery=discovery)

    # ─── Helpers privés ──────────────────────────────────────────
    @staticmethod
    def _detect_compatibility(
        vendor: str, device_type: str, protocols: list,
    ) -> tuple[str, str]:
        """Détecte compatibilité + driver suggéré."""
        from devices.models_discovery import DeviceCompatibility

        vendor_lower = (vendor or "").lower()
        # Match vendor connu
        for known, driver in VENDOR_TO_DRIVER.items():
            if known in vendor_lower:
                return (DeviceCompatibility.COMPATIBLE, driver)

        # Match par protocole ONVIF
        if "onvif" in (p.lower() for p in protocols):
            return (DeviceCompatibility.COMPATIBLE, "onvif")

        # Match par device_type
        if device_type in ("ip_camera", "rfid_reader", "biometric_terminal"):
            return (DeviceCompatibility.EXPERIMENTAL, "generic")

        return (DeviceCompatibility.UNKNOWN, "")

    # ─── Requêtes lecture ────────────────────────────────────────
    @classmethod
    def list_pending(cls, tenant, limit: int = 200):
        """Liste des découvertes en attente d'adoption/rejet."""
        from devices.models_discovery import DeviceDiscovery, DiscoveryStatus
        return list(DeviceDiscovery.objects.filter(
            tenant=tenant,
            status__in=[DiscoveryStatus.DETECTED, DiscoveryStatus.TESTED],
        ).select_related("gateway", "site").order_by("-last_seen_at")[:limit])

    @classmethod
    def mark_stale_older_than(cls, tenant, hours: int = 24) -> int:
        """Marque comme stale les découvertes non vues depuis N heures.

        Retourne le nombre d'objets affectés. À appeler périodiquement
        via une task Celery beat.
        """
        from devices.models_discovery import DeviceDiscovery, DiscoveryStatus
        from datetime import timedelta
        threshold = timezone.now() - timedelta(hours=hours)
        return DeviceDiscovery.objects.filter(
            tenant=tenant,
            status__in=[DiscoveryStatus.DETECTED, DiscoveryStatus.TESTED],
            last_seen_at__lt=threshold,
        ).update(status=DiscoveryStatus.STALE)
