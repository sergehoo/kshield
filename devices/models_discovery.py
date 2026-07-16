"""KAYDAN SHIELD — Modèles Discovery équipements (Phase 5 refonte §2).

Objectif : formaliser le workflow de découverte + enregistrement des
équipements avant qu'ils deviennent des Device officiels.

Modèles :
  - DeviceDiscovery : équipement détecté (avant adoption/rejet)
  - DeviceDiscoveryScan : session de scan lancée (par un agent ou admin)

Un DeviceDiscovery peut passer par 4 états :
  detected → tested → adopted (crée un Device officiel)
                    → rejected (ignoré définitivement)

Aucun matériel ne peut apparaître comme Device officiel sans avoir été
adopté explicitement — même les scans automatiques par gateway.
"""
from __future__ import annotations

import uuid

from django.db import models

from core.mixins import TimeStampedModel


# ═══════════════════════════════════════════════════════════════════
# Enums
# ═══════════════════════════════════════════════════════════════════
class DiscoveryStatus(models.TextChoices):
    """État d'une découverte."""
    DETECTED   = "detected",   "Détecté (info brute uniquement)"
    TESTED     = "tested",     "Testé (connexion validée)"
    ADOPTED    = "adopted",    "Adopté (Device créé)"
    REJECTED   = "rejected",   "Rejeté (ignoré définitivement)"
    STALE      = "stale",      "Périmé (plus vu récemment)"


class DeviceState(models.TextChoices):
    """États explicites d'un Device (cahier §2.4 — 11 valeurs)."""
    DISCOVERED             = "discovered",             "Découvert"
    PENDING_CONFIGURATION  = "pending_configuration",  "En attente config"
    CONNECTING             = "connecting",             "Connexion en cours"
    ONLINE                 = "online",                 "En ligne"
    DEGRADED               = "degraded",               "Dégradé"
    OFFLINE                = "offline",                "Hors ligne"
    AUTHENTICATION_FAILED  = "authentication_failed",  "Auth échouée"
    UNREACHABLE            = "unreachable",            "Injoignable"
    DISABLED               = "disabled",               "Désactivé"
    MAINTENANCE            = "maintenance",            "Maintenance"
    INCOMPATIBLE           = "incompatible",           "Incompatible"


class DiscoveryProtocol(models.TextChoices):
    """Protocole ayant détecté l'équipement."""
    ARP     = "arp",     "ARP"
    MDNS    = "mdns",    "mDNS / Bonjour"
    SSDP    = "ssdp",    "SSDP / UPnP"
    ONVIF   = "onvif",   "ONVIF"
    SNMP    = "snmp",    "SNMP"
    NMAP    = "nmap",    "Nmap"
    BLE     = "ble",     "Bluetooth LE"
    USB     = "usb",     "USB / Série"
    MANUAL  = "manual",  "Saisie manuelle"
    QR      = "qr",      "QR code d'activation"
    TOKEN   = "token",   "Token enrôlement"
    UNKNOWN = "unknown", "Inconnu"


class DeviceCompatibility(models.TextChoices):
    """Compatibilité avec Kaydan Shield."""
    COMPATIBLE       = "compatible",       "Compatible officiel"
    EXPERIMENTAL     = "experimental",     "Compatible (expérimental)"
    UNSUPPORTED      = "unsupported",      "Non supporté (générique)"
    INCOMPATIBLE     = "incompatible",     "Incompatible (protocole inconnu)"
    UNKNOWN          = "unknown",          "Inconnu (test requis)"


# ═══════════════════════════════════════════════════════════════════
# DeviceDiscoveryScan — session de scan
# ═══════════════════════════════════════════════════════════════════
class DeviceDiscoveryScan(TimeStampedModel):
    """Session de scan réseau (par agent ou admin).

    Chaque scan génère plusieurs DeviceDiscovery.
    Historisé pour audit + comparaison entre scans.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "core.Tenant", on_delete=models.CASCADE, related_name="discovery_scans",
    )
    gateway = models.ForeignKey(
        "devices.LocalAgent", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="discovery_scans",
        help_text="Gateway ayant lancé le scan (null = scan cloud/admin).",
    )
    site = models.ForeignKey(
        "sites.Site", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="discovery_scans",
    )

    protocols_used = models.JSONField(
        default=list, blank=True,
        help_text='Liste des protocoles activés (ex: ["arp", "onvif"]).',
    )
    duration_ms = models.PositiveIntegerField(default=0)
    devices_detected = models.PositiveIntegerField(default=0)
    devices_new = models.PositiveIntegerField(default=0)
    devices_updated = models.PositiveIntegerField(default=0)

    STATUS_CHOICES = [
        ("running",  "En cours"),
        ("succeeded", "Terminé"),
        ("failed",   "Échec"),
    ]
    status = models.CharField(
        max_length=12, choices=STATUS_CHOICES, default="running", db_index=True,
    )
    error = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Session de scan discovery"
        indexes = [
            models.Index(fields=["tenant", "-created_at"]),
            models.Index(fields=["gateway", "-created_at"]),
        ]


# ═══════════════════════════════════════════════════════════════════
# DeviceDiscovery — équipement détecté (avant adoption)
# ═══════════════════════════════════════════════════════════════════
class DeviceDiscovery(TimeStampedModel):
    """Un équipement détecté par scan mais pas encore enregistré comme Device.

    Cahier §2.2 — Informations à afficher pour chaque équipement détecté :
    IP, MAC, serial, vendor, model, type, firmware, protocoles disponibles,
    ports ouverts utiles, état de connexion, temps de réponse, gateway de
    rattachement, site détecté, compatibilité Kaydan Shield.

    Un DeviceDiscovery unique = combinaison (tenant, mac_address) OU
    (tenant, ip, serial_number). Un même équipement scanné 10 fois n'a
    qu'un seul enregistrement — les métadonnées sont mises à jour à
    chaque vue.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "core.Tenant", on_delete=models.CASCADE, related_name="discoveries",
    )
    scan = models.ForeignKey(
        DeviceDiscoveryScan, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="discoveries",
        help_text="Session de scan qui a détecté cet équipement en premier.",
    )
    gateway = models.ForeignKey(
        "devices.LocalAgent", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="discoveries",
        help_text="Gateway locale ayant détecté l'équipement.",
    )
    site = models.ForeignKey(
        "sites.Site", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="discoveries",
        help_text="Site auto-détecté (via gateway rattachée).",
    )

    # ─── Identification matérielle ────────────────────────────
    mac_address = models.CharField(
        max_length=17, blank=True, db_index=True,
        help_text='Format "AA:BB:CC:DD:EE:FF" — clé principale de dédup.',
    )
    ip_address = models.GenericIPAddressField(null=True, blank=True, db_index=True)
    hostname = models.CharField(max_length=120, blank=True)
    serial_number = models.CharField(max_length=64, blank=True, db_index=True)

    # ─── Métadonnées vendor ────────────────────────────────────
    vendor = models.CharField(
        max_length=64, blank=True, db_index=True,
        help_text="Ex: Hikvision, ZKTeco, Axis. Déduit du OUI MAC ou du protocole.",
    )
    model = models.CharField(max_length=120, blank=True)
    device_type = models.CharField(
        max_length=32, blank=True,
        help_text='Ex: "ip_camera", "rfid_reader", "biometric_terminal", "controller"',
    )
    firmware_version = models.CharField(max_length=40, blank=True)

    # ─── Connectivité ──────────────────────────────────────────
    protocols_supported = models.JSONField(
        default=list, blank=True,
        help_text='Ex: ["onvif", "rtsp", "http"] — détectés au scan.',
    )
    ports_open = models.JSONField(
        default=list, blank=True,
        help_text='Ports utiles ouverts détectés (ex: [80, 443, 554, 8080]).',
    )
    latency_ms = models.PositiveIntegerField(
        default=0,
        help_text="Latence moyenne du dernier ping (ms).",
    )
    signal_strength = models.IntegerField(
        null=True, blank=True,
        help_text="Force du signal en dBm (pour BLE/WiFi uniquement).",
    )

    # ─── État & compatibilité ──────────────────────────────────
    status = models.CharField(
        max_length=12, choices=DiscoveryStatus.choices,
        default=DiscoveryStatus.DETECTED, db_index=True,
    )
    detected_via = models.CharField(
        max_length=12, choices=DiscoveryProtocol.choices,
        default=DiscoveryProtocol.UNKNOWN,
        help_text="Protocole qui a détecté l'équipement en premier.",
    )
    compatibility = models.CharField(
        max_length=16, choices=DeviceCompatibility.choices,
        default=DeviceCompatibility.UNKNOWN,
    )
    suggested_driver = models.CharField(
        max_length=40, blank=True,
        help_text='Ex: "hikvision", "zkteco", "onvif_generic".',
    )

    # ─── Test de connexion ────────────────────────────────────
    last_test_at = models.DateTimeField(null=True, blank=True)
    last_test_success = models.BooleanField(default=False)
    last_test_error = models.TextField(blank=True)
    last_test_response = models.JSONField(default=dict, blank=True)

    # ─── Adoption / Rejet ──────────────────────────────────────
    adopted_device = models.OneToOneField(
        "devices.Device", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="discovery_origin",
        help_text="Device officiel créé après adoption.",
    )
    adopted_at = models.DateTimeField(null=True, blank=True)
    adopted_by = models.CharField(
        max_length=200, blank=True,
        help_text="User qui a adopté (email). Textuel pour survivre à la suppression.",
    )
    rejected_at = models.DateTimeField(null=True, blank=True)
    rejected_reason = models.CharField(max_length=240, blank=True)

    # ─── Compteurs et métadonnées ──────────────────────────────
    times_seen = models.PositiveIntegerField(
        default=1,
        help_text="Nombre de fois où l'équipement a été détecté.",
    )
    first_seen_at = models.DateTimeField(auto_now_add=True, db_index=True)
    last_seen_at = models.DateTimeField(auto_now=True, db_index=True)
    raw_payload = models.JSONField(
        default=dict, blank=True,
        help_text="Payload brut du scan (pour debug + réplay).",
    )

    class Meta:
        ordering = ["-last_seen_at"]
        verbose_name = "Équipement découvert"
        verbose_name_plural = "Équipements découverts"
        indexes = [
            models.Index(fields=["tenant", "status", "-last_seen_at"]),
            models.Index(fields=["gateway", "status"]),
            models.Index(fields=["compatibility", "status"]),
            models.Index(fields=["vendor", "device_type"]),
            models.Index(fields=["mac_address"]),
        ]
        constraints = [
            # Une combinaison (tenant, mac_address) est unique quand mac fournie
            models.UniqueConstraint(
                fields=["tenant", "mac_address"],
                condition=~models.Q(mac_address=""),
                name="discovery_unique_mac_per_tenant",
            ),
        ]

    def __str__(self) -> str:
        label = self.hostname or self.model or self.mac_address or str(self.ip_address) or "?"
        return f"{label} · {self.vendor or 'unknown'} · {self.status}"

    @property
    def is_active(self) -> bool:
        return self.status in (DiscoveryStatus.DETECTED, DiscoveryStatus.TESTED)

    def as_display_dict(self) -> dict:
        """Résumé pour l'UI liste — évite un serializer complet."""
        return {
            "id":                str(self.pk),
            "mac_address":       self.mac_address,
            "ip_address":        str(self.ip_address) if self.ip_address else None,
            "hostname":          self.hostname,
            "vendor":            self.vendor,
            "model":             self.model,
            "device_type":       self.device_type,
            "firmware_version":  self.firmware_version,
            "status":            self.status,
            "compatibility":     self.compatibility,
            "suggested_driver":  self.suggested_driver,
            "detected_via":      self.detected_via,
            "latency_ms":        self.latency_ms,
            "protocols_supported": self.protocols_supported,
            "ports_open":        self.ports_open,
            "gateway_id":        str(self.gateway_id) if self.gateway_id else None,
            "site_id":           self.site_id,
            "times_seen":        self.times_seen,
            "first_seen_at":     self.first_seen_at.isoformat(),
            "last_seen_at":      self.last_seen_at.isoformat(),
            "adopted_device_id": str(self.adopted_device_id) if self.adopted_device_id else None,
        }
