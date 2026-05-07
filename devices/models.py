"""KAYDAN SHIELD — devices: badges, casques, lecteurs, terminaux IoT."""
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models

from core.models import TimeStampedModel, UUIDModel


class DeviceModel(TimeStampedModel):
    TYPE_CHOICES = [
        ("reader_uhf_fixed", "Lecteur UHF fixe"),
        ("reader_uhf_mobile", "Lecteur UHF mobile"),
        ("reader_nfc_fixed", "Lecteur NFC fixe"),
        ("reader_nfc_mobile", "Lecteur NFC mobile"),
        ("tag_uhf", "Tag RFID UHF"),
        ("beacon_ble", "Beacon BLE"),
        ("tablet", "Tablette"),
        ("smartphone", "Smartphone"),
        ("id_scanner", "Scanner pièce d'identité"),
        ("door_lock", "Gâche électrique"),
        ("camera", "Caméra"),
        ("portique", "Portique RFID"),
    ]

    brand = models.CharField(max_length=120)
    model = models.CharField(max_length=180)
    type = models.CharField(max_length=24, choices=TYPE_CHOICES)
    spec = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ("brand", "model")
        ordering = ["brand", "model"]

    def __str__(self): return f"{self.brand} {self.model}"


class Device(UUIDModel, TimeStampedModel):
    STATUS_CHOICES = [
        ("active", "Actif"),
        ("inactive", "Inactif"),
        ("maintenance", "Maintenance"),
        ("lost", "Perdu / volé"),
    ]

    tenant = models.ForeignKey("core.Tenant", on_delete=models.CASCADE, related_name="devices")
    model = models.ForeignKey(DeviceModel, on_delete=models.PROTECT, related_name="devices")
    serial_number = models.CharField(max_length=120, unique=True, db_index=True)
    site = models.ForeignKey(
        "sites.Site", null=True, blank=True, on_delete=models.SET_NULL, related_name="devices",
    )
    zone = models.ForeignKey(
        "sites.Zone", null=True, blank=True, on_delete=models.SET_NULL, related_name="devices",
    )
    checkpoint = models.ForeignKey(
        "sites.Checkpoint", null=True, blank=True, on_delete=models.SET_NULL, related_name="devices",
    )
    api_key = models.ForeignKey(
        "accounts.APIKey", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="devices",
    )
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default="active")
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    mac_address = models.CharField(max_length=20, blank=True)
    firmware_version = models.CharField(max_length=40, blank=True)
    battery_level = models.PositiveSmallIntegerField(null=True, blank=True)
    commissioned_at = models.DateTimeField(null=True, blank=True)
    last_heartbeat_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["serial_number"]
        indexes = [models.Index(fields=["tenant", "status"])]

    def __str__(self): return f"{self.model} #{self.serial_number}"


class Badge(UUIDModel, TimeStampedModel):
    """Badge NFC, RFID UHF ou QR visiteur — physique ou virtuel (PDF)."""

    TYPE_CHOICES = [
        ("nfc", "NFC"),
        ("uhf", "RFID UHF"),
        ("uhf_xerafy", "Xerafy UHF (casque)"),
        ("qr",  "QR Code"),
    ]
    # Catégorie métier — pilote les workflows et la génération PDF.
    CATEGORY_CHOICES = [
        ("visitor_qr",     "Badge visiteur QR"),
        ("employee_rfid",  "Badge employé RFID"),
        ("worker_rfid",    "Badge ouvrier RFID (avec casque)"),
    ]
    STATUS_CHOICES = [
        ("available",  "Disponible (en pool)"),
        ("assigned",   "Attribué"),
        ("active",     "Actif"),
        ("suspended",  "Suspendu"),
        ("expired",    "Expiré"),
        ("lost",       "Perdu"),
        ("revoked",    "Révoqué"),
        ("disabled",   "Désactivé"),
    ]
    HOLDER_KIND_CHOICES = [
        ("employee", "Employé"),
        ("worker", "Ouvrier"),
        ("visitor", "Visiteur"),
    ]

    tenant = models.ForeignKey("core.Tenant", on_delete=models.CASCADE, related_name="badges")
    uid = models.CharField(max_length=64, unique=True, db_index=True)
    type = models.CharField(max_length=16, choices=TYPE_CHOICES, default="nfc")
    category = models.CharField(
        max_length=20, choices=CATEGORY_CHOICES, default="employee_rfid",
        help_text="Workflow métier auquel appartient le badge.",
    )
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default="active")

    # Casque RFID associé (utilisé pour worker_rfid + employee_rfid si chantier)
    paired_helmet = models.ForeignKey(
        "devices.Helmet", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="paired_badges",
        help_text="Casque associé pour le couplage badge+casque (chantier).",
    )

    holder_kind = models.CharField(max_length=12, choices=HOLDER_KIND_CHOICES, blank=True)
    holder_content_type = models.ForeignKey(
        ContentType, null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
    )
    holder_object_id = models.PositiveBigIntegerField(null=True, blank=True)
    holder = GenericForeignKey("holder_content_type", "holder_object_id")

    # Fichier PDF + miniature
    pdf_file = models.FileField(
        upload_to="badges/pdf/", null=True, blank=True,
        help_text="Badge imprimable au format PDF avec QR code.",
    )
    thumbnail = models.ImageField(
        upload_to="badges/thumbnails/", null=True, blank=True,
        help_text="Miniature PNG du badge (générée automatiquement avec le PDF).",
    )
    qr_payload = models.CharField(
        max_length=240, blank=True,
        help_text="Données encodées dans le QR code (visit ID, RFID UID, etc.)",
    )

    issued_at = models.DateTimeField(auto_now_add=True)
    valid_from = models.DateField(null=True, blank=True,
        help_text="Début de validité — le badge est refusé avant cette date.")
    valid_until = models.DateField(null=True, blank=True,
        help_text="Fin de validité — le badge passe automatiquement en `expired`.")
    expires_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    revoked_reason = models.CharField(max_length=240, blank=True)
    suspended_at = models.DateTimeField(null=True, blank=True)
    suspended_reason = models.CharField(max_length=240, blank=True)

    last_scan_at = models.DateTimeField(
        null=True, blank=True, db_index=True,
        help_text="Mis à jour automatiquement par signal sur AccessEvent.",
    )
    scan_count = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-issued_at"]
        indexes = [
            models.Index(fields=["tenant", "status", "type"]),
            models.Index(fields=["category", "status"]),
        ]

    def __str__(self):
        return f"{self.get_category_display()} · {self.uid}"

    @property
    def is_assigned(self):
        return bool(self.holder_object_id)

    @property
    def is_available_for_visitor(self):
        """Un badge visiteur QR libre, prêt à être attribué à une nouvelle visite."""
        return self.category == "visitor_qr" and self.status == "available"

    @property
    def is_currently_valid(self):
        """True si valid_from <= today <= valid_until (ou si pas de bornes)."""
        from datetime import date
        today = date.today()
        if self.valid_from and today < self.valid_from: return False
        if self.valid_until and today > self.valid_until: return False
        return self.status in ("active", "assigned", "available")

    @property
    def can_be_used(self):
        """Conditions cumulées pour qu'un scan soit accepté."""
        return self.status == "active" and self.is_currently_valid


class BadgeAssignment(TimeStampedModel):
    """Historique des attributions d'un badge à des porteurs successifs.

    Particulièrement utile pour les badges visiteurs QR qui sont réutilisés
    pour plusieurs visites — chaque attribution garde sa trace pour
    l'audit et la conformité RGPD.
    """

    HOLDER_KIND_CHOICES = Badge.HOLDER_KIND_CHOICES

    badge = models.ForeignKey(Badge, on_delete=models.CASCADE, related_name="assignments")
    holder_kind = models.CharField(max_length=12, choices=HOLDER_KIND_CHOICES)
    holder_object_id = models.PositiveBigIntegerField()
    holder_label = models.CharField(
        max_length=240,
        help_text="Snapshot du nom du porteur (au cas où l'objet est supprimé).",
    )

    visit_request = models.ForeignKey(
        "visitors.VisitRequest", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="badge_assignments",
    )
    assigned_at = models.DateTimeField(auto_now_add=True)
    released_at = models.DateTimeField(
        null=True, blank=True,
        help_text="Date à laquelle le badge a été rendu / désassigné.",
    )
    assigned_by = models.ForeignKey(
        "accounts.User", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="badge_assignments_made",
        help_text="Agent ayant effectué l'attribution.",
    )
    released_by = models.ForeignKey(
        "accounts.User", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="badge_assignments_released",
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-assigned_at"]
        indexes = [
            models.Index(fields=["badge", "-assigned_at"]),
            models.Index(fields=["holder_kind", "holder_object_id"]),
        ]

    def __str__(self):
        return f"{self.badge.uid} → {self.holder_label} ({self.assigned_at:%d/%m/%y})"

    @property
    def is_active(self):
        return self.released_at is None

    @property
    def duration(self):
        """Durée d'utilisation (released_at - assigned_at) ou en cours."""
        from django.utils import timezone
        end = self.released_at or timezone.now()
        return end - self.assigned_at


class BadgeScanEvent(models.Model):
    """Trace de chaque scan d'un badge — alimenté par signal sur AccessEvent.

    Permet d'afficher l'historique des scans d'un badge en O(1) sans
    requêter AccessEvent par badge_uid à chaque fois.
    """

    DECISION_CHOICES = [
        ("granted", "Autorisé"), ("denied", "Refusé"), ("review", "À vérifier"),
    ]

    badge = models.ForeignKey(Badge, on_delete=models.CASCADE, related_name="scan_events")
    access_event = models.ForeignKey(
        "access_control.AccessEvent", on_delete=models.CASCADE,
        related_name="badge_scan_events",
    )
    timestamp = models.DateTimeField(db_index=True)
    site = models.ForeignKey(
        "sites.Site", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="badge_scans",
    )
    decision = models.CharField(max_length=8, choices=DECISION_CHOICES)
    method = models.CharField(max_length=8, blank=True)
    denial_reason = models.CharField(max_length=240, blank=True)

    class Meta:
        ordering = ["-timestamp"]
        indexes = [
            models.Index(fields=["badge", "-timestamp"]),
        ]

    def __str__(self):
        return f"{self.badge.uid} @ {self.timestamp:%d/%m %H:%M} → {self.decision}"


class Helmet(UUIDModel, TimeStampedModel):
    """Casque connecté (tag UHF + beacon BLE)."""

    STATUS_CHOICES = [
        ("active", "Actif"),
        ("inactive", "Inactif"),
        ("maintenance", "Maintenance"),
        ("retired", "Hors service"),
        ("lost", "Perdu"),
    ]

    tenant = models.ForeignKey("core.Tenant", on_delete=models.CASCADE, related_name="helmets")
    serial_number = models.CharField(max_length=64, unique=True, db_index=True)
    uhf_tag_uid = models.CharField(max_length=64, unique=True)
    ble_beacon_uid = models.CharField(max_length=64, unique=True)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="active")
    size = models.CharField(max_length=8, blank=True)
    commissioned_at = models.DateField(null=True, blank=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)
    last_battery_level = models.PositiveSmallIntegerField(null=True, blank=True)

    current_worker = models.ForeignKey(
        "ouvriers.Worker", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="current_helmets",
    )

    def __str__(self): return f"Casque {self.serial_number}"


class BadgeHelmetPairing(TimeStampedModel):
    """Appairage Badge_X <-> Casque_X pour la journée."""

    worker = models.ForeignKey("ouvriers.Worker", on_delete=models.CASCADE, related_name="pairings")
    badge = models.ForeignKey(Badge, on_delete=models.CASCADE, related_name="pairings")
    helmet = models.ForeignKey(Helmet, on_delete=models.CASCADE, related_name="pairings")
    site = models.ForeignKey("sites.Site", on_delete=models.CASCADE, related_name="pairings")
    pairing_date = models.DateField(db_index=True)
    first_scan_at = models.DateTimeField()
    last_verified_at = models.DateTimeField()
    verifications_count = models.PositiveIntegerField(default=1)
    is_broken = models.BooleanField(default=False)
    broken_reason = models.CharField(max_length=240, blank=True)

    class Meta:
        unique_together = ("worker", "pairing_date", "site")
        ordering = ["-pairing_date"]
        indexes = [models.Index(fields=["badge", "helmet", "pairing_date"])]

    def __str__(self):
        return f"{self.worker} : {self.badge.uid} ↔ {self.helmet.serial_number} ({self.pairing_date})"


class DeviceHeartbeat(models.Model):
    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name="heartbeats")
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    is_online = models.BooleanField(default=True)
    battery_level = models.PositiveSmallIntegerField(null=True, blank=True)
    signal_strength = models.SmallIntegerField(null=True, blank=True)
    cpu_usage = models.FloatField(null=True, blank=True)
    ram_usage = models.FloatField(null=True, blank=True)
    payload = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-timestamp"]


class DeviceMaintenance(TimeStampedModel):
    KIND_CHOICES = [
        ("preventive", "Préventive"),
        ("corrective", "Corrective"),
        ("replacement", "Remplacement"),
    ]
    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name="maintenances")
    kind = models.CharField(max_length=16, choices=KIND_CHOICES, default="corrective")
    technician_name = models.CharField(max_length=180, blank=True)
    started_at = models.DateTimeField()
    ended_at = models.DateTimeField(null=True, blank=True)
    description = models.TextField(blank=True)
    cost = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)


class FirmwareVersion(TimeStampedModel):
    device_model = models.ForeignKey(DeviceModel, on_delete=models.CASCADE, related_name="firmwares")
    version = models.CharField(max_length=40)
    release_notes = models.TextField(blank=True)
    file = models.FileField(upload_to="firmwares/", null=True, blank=True)
    is_published = models.BooleanField(default=False)

    class Meta:
        unique_together = ("device_model", "version")


class OTAUpdate(TimeStampedModel):
    STATUS_CHOICES = [
        ("scheduled", "Programmée"),
        ("in_progress", "En cours"),
        ("succeeded", "Réussie"),
        ("failed", "Échec"),
        ("cancelled", "Annulée"),
    ]
    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name="ota_updates")
    firmware = models.ForeignKey(FirmwareVersion, on_delete=models.CASCADE, related_name="deployments")
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="scheduled")
    scheduled_for = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True)
