"""KAYDAN SHIELD — devices: badges, casques, lecteurs, terminaux IoT."""
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models

from core.fields import EncryptedCharField
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
        ("face_terminal", "Terminal reconnaissance faciale"),
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
    # Cycle de vie complet (12 états — cahier des charges §3.5)
    STATUS_CHOICES = [
        ("available",  "Disponible (en pool)"),
        ("enrolling",  "En cours d'enrôlement"),
        ("assigned",   "Attribué (pas encore utilisé)"),
        ("active",     "Actif"),
        ("suspended",  "Suspendu"),
        ("expired",    "Expiré"),
        ("lost",       "Perdu"),
        ("stolen",     "Volé"),
        ("disabled",   "Désactivé"),
        ("revoked",    "Révoqué (interdit d'usage)"),
        ("destroyed",  "Détruit physiquement"),
        ("archived",   "Archivé (RGPD, conservé pour audit)"),
    ]
    # 7 types de titulaires possibles (cahier des charges §3.4)
    HOLDER_KIND_CHOICES = [
        ("employee",    "Employé"),
        ("worker",      "Ouvrier"),
        ("visitor",     "Visiteur"),
        ("agent",       "Agent sécurité"),
        ("contractor",  "Prestataire externe"),
        ("vehicle",     "Véhicule"),
        ("equipment",   "Équipement / matériel"),
        ("resource",    "Ressource temporaire"),
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


# ---------------------------------------------------------------------------
# Caméras IP — streaming temps réel + pipeline IA optionnel
# ---------------------------------------------------------------------------
class Camera(TimeStampedModel):
    """Caméra IP (RTSP/HTTP) avec streaming + pipeline IA optionnel.

    Le flux RTSP est consommé côté serveur via OpenCV (cv2.VideoCapture),
    re-encodé en JPEG et servi en multipart/x-mixed-replace (MJPEG-over-HTTP)
    pour être affiché dans n'importe quel navigateur via un simple <img src>.

    Pour la prod multi-utilisateurs, voir docs/CAMERAS.md (passage à Channels
    + relay Redis pour éviter d'ouvrir N connexions RTSP).
    """

    STATUS_CHOICES = [
        ("online",   "En ligne"),
        ("offline",  "Hors ligne"),
        ("error",    "Erreur"),
        ("disabled", "Désactivée"),
    ]
    CODEC_CHOICES = [
        ("h264",  "H.264"),
        ("h265",  "H.265 / HEVC"),
        ("mjpeg", "MJPEG"),
    ]
    TRANSPORT_CHOICES = [
        ("tcp", "TCP (fiable)"),
        ("udp", "UDP (faible latence)"),
    ]

    # Identité
    name = models.CharField(max_length=120, help_text="Nom affiché (ex: Portail Nord)")
    site = models.ForeignKey(
        "sites.Site", on_delete=models.CASCADE, related_name="cameras",
        null=True, blank=True,
    )
    zone = models.ForeignKey(
        "sites.Zone", on_delete=models.SET_NULL, related_name="cameras",
        null=True, blank=True,
    )
    location_label = models.CharField(
        max_length=120, blank=True,
        help_text="Description libre de l'emplacement physique (ex: Mât SE, hauteur 4m)",
    )

    # Connexion flux principal
    rtsp_url = models.CharField(
        max_length=500,
        help_text="URL RTSP/HTTP du flux. Ex: rtsp://user:pass@192.168.1.50:554/Streaming/Channels/101",
    )
    transport = models.CharField(max_length=4, choices=TRANSPORT_CHOICES, default="tcp")
    codec = models.CharField(max_length=8, choices=CODEC_CHOICES, default="h264")
    # Credentials séparés (optionnels si déjà dans l'URL)
    username = models.CharField(max_length=120, blank=True)
    password = EncryptedCharField(
        max_length=512, blank=True,
        help_text=("Chiffré Fernet au repos (cf. core/fields.py). En prod, "
                    "définir FIELD_ENCRYPTION_KEY dans .env."),
    )
    # Resolution cible (downscale serveur-side avant MJPEG)
    target_width = models.PositiveIntegerField(default=1280)
    target_height = models.PositiveIntegerField(default=720)
    target_fps = models.PositiveIntegerField(
        default=10,
        help_text="FPS de re-streaming JPEG côté serveur (5-15 conseillé).",
    )
    jpeg_quality = models.PositiveIntegerField(
        default=75,
        help_text="Qualité JPEG 1-100 du re-stream (compromis bande passante/qualité).",
    )

    # ONVIF — pour PTZ et auto-discovery
    onvif_enabled = models.BooleanField(default=False)
    onvif_host = models.CharField(max_length=120, blank=True)
    onvif_port = models.PositiveIntegerField(default=80)

    # Pipeline IA (à brancher progressivement)
    enable_face_recognition = models.BooleanField(
        default=False,
        help_text="Exécute InsightFace sur chaque N-ième frame pour identifier les visages.",
    )
    enable_motion_detection = models.BooleanField(default=False)
    enable_recording = models.BooleanField(
        default=False,
        help_text="Enregistre les segments vidéo (rolling buffer 24h).",
    )

    # État
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="offline")
    is_active = models.BooleanField(default=True, db_index=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)
    last_snapshot = models.ImageField(
        upload_to="cameras/snapshots/", null=True, blank=True,
        help_text="Dernière vignette capturée (régénérée toutes les N minutes).",
    )

    class Meta:
        ordering = ("name",)
        indexes = [
            models.Index(fields=["site", "status"]),
            models.Index(fields=["is_active"]),
        ]

    def __str__(self):
        return self.name

    @property
    def effective_rtsp_url(self) -> str:
        """Reconstruit l'URL avec credentials séparés si fournis."""
        if not self.username:
            return self.rtsp_url
        if "@" in self.rtsp_url and "://" in self.rtsp_url:
            # Credentials déjà dans l'URL
            return self.rtsp_url
        if "://" not in self.rtsp_url:
            return self.rtsp_url
        scheme, rest = self.rtsp_url.split("://", 1)
        from urllib.parse import quote
        creds = f"{quote(self.username, safe='')}:{quote(self.password, safe='')}"
        return f"{scheme}://{creds}@{rest}"


# ═══════════════════════════════════════════════════════════════════
# Communication temps réel — commandes envoyées aux équipements
# ═══════════════════════════════════════════════════════════════════
class DeviceCommand(UUIDModel, TimeStampedModel):
    """Commande unitaire envoyée à un équipement (lecteur RFID, terminal, gateway).

    Cycle de vie :
        pending  → sent → acknowledged → completed
                                       ↘ failed
                                       ↘ timeout

    Persistée pour audit + rejouable ; la "vraie" queue temps réel est en Redis
    (via ``devices.services.command_queue``) pour un pickup en <1s côté Agent.
    """

    KIND_CHOICES = [
        ("PING_DEVICE",             "Ping"),
        ("SYNC_DEVICE",             "Synchronisation"),
        ("RESTART_DEVICE",          "Redémarrage"),
        ("GET_DEVICE_INFO",         "Info équipement"),
        ("GET_DEVICE_STATUS",       "Statut équipement"),
        ("GET_DEVICE_LOGS",         "Logs équipement"),
        ("START_RFID_ENROLLMENT",   "Démarrer écoute RFID"),
        ("STOP_RFID_ENROLLMENT",    "Arrêter écoute RFID"),
        ("READ_RFID_CARD",          "Lire carte RFID"),
        ("PUSH_USER",               "Push utilisateur (biométrie)"),
        ("CUSTOM",                  "Commande custom"),
    ]

    STATUS_CHOICES = [
        ("pending",       "En attente"),
        ("sent",          "Envoyée"),
        ("acknowledged",  "Acquittée"),
        ("completed",     "Terminée"),
        ("failed",        "Échec"),
        ("timeout",       "Timeout"),
    ]

    tenant = models.ForeignKey("core.Tenant", on_delete=models.CASCADE,
                                related_name="device_commands")
    device = models.ForeignKey("devices.Device", on_delete=models.CASCADE,
                                related_name="commands")
    session = models.ForeignKey("devices.RFIDEnrollmentSession", null=True, blank=True,
                                 on_delete=models.SET_NULL, related_name="commands",
                                 help_text="Session d'enrôlement qui a émis cette commande.")
    kind = models.CharField(max_length=32, choices=KIND_CHOICES, db_index=True)
    payload = models.JSONField(default=dict, blank=True,
                                help_text="Paramètres additionnels (ex. timeout, session_id).")
    status = models.CharField(max_length=16, choices=STATUS_CHOICES,
                               default="pending", db_index=True)
    issued_by = models.ForeignKey("accounts.User", null=True, blank=True,
                                   on_delete=models.SET_NULL,
                                   related_name="issued_device_commands")
    sent_at = models.DateTimeField(null=True, blank=True)
    acked_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    timeout_at = models.DateTimeField(null=True, blank=True,
                                       help_text="Deadline avant passage en statut timeout.")
    response_raw = models.JSONField(default=dict, blank=True,
                                     help_text="Réponse brute du device.")
    response_normalized = models.JSONField(default=dict, blank=True,
                                            help_text="Version normalisée pour le front.")
    error_message = models.CharField(max_length=500, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["tenant", "device", "status"]),
            models.Index(fields=["kind", "status"]),
        ]

    def __str__(self):
        return f"{self.kind} → {self.device.serial_number} [{self.status}]"


# ═══════════════════════════════════════════════════════════════════
# Session d'enrôlement RFID temps réel
# ═══════════════════════════════════════════════════════════════════
class RFIDEnrollmentSession(UUIDModel, TimeStampedModel):
    """Session d'enrôlement RFID — un opérateur, un lecteur, plusieurs scans possibles.

    Cycle de vie :
        pending  → listening → completed | cancelled | timeout | error

    Chaque scan reçu génère un ``RFIDEnrollmentEvent`` associé.
    """

    STATUS_CHOICES = [
        ("pending",   "En préparation"),
        ("listening", "En écoute"),
        ("completed", "Terminée"),
        ("cancelled", "Annulée"),
        ("timeout",   "Timeout"),
        ("error",     "Erreur"),
    ]

    MODE_CHOICES = [
        ("single", "Unitaire"),
        ("bulk",   "En masse"),
    ]

    HOLDER_KIND_CHOICES = [
        ("worker",   "Ouvrier"),
        ("employee", "Employé"),
        ("visitor",  "Visiteur"),
        ("",         "Aucun (pool)"),
    ]

    tenant = models.ForeignKey("core.Tenant", on_delete=models.CASCADE,
                                related_name="rfid_enrollment_sessions")
    initiated_by = models.ForeignKey("accounts.User", null=True, blank=True,
                                      on_delete=models.SET_NULL,
                                      related_name="rfid_enrollment_sessions")
    site = models.ForeignKey("sites.Site", null=True, blank=True,
                              on_delete=models.SET_NULL, related_name="+")
    zone = models.ForeignKey("sites.Zone", null=True, blank=True,
                              on_delete=models.SET_NULL, related_name="+")
    reader = models.ForeignKey("devices.Device", null=True, blank=True,
                                on_delete=models.SET_NULL, related_name="rfid_sessions",
                                help_text="Lecteur cible ; null = tous lecteurs du tenant.")
    mode = models.CharField(max_length=8, choices=MODE_CHOICES, default="single")
    status = models.CharField(max_length=12, choices=STATUS_CHOICES,
                               default="pending", db_index=True)

    # Porteur préchoisi (unitaire) — si non défini, l'opérateur associera manuellement
    holder_kind = models.CharField(max_length=12, choices=HOLDER_KIND_CHOICES, blank=True)
    holder_content_type = models.ForeignKey(ContentType, null=True, blank=True,
                                             on_delete=models.SET_NULL, related_name="+")
    holder_object_id = models.PositiveBigIntegerField(null=True, blank=True)
    holder = GenericForeignKey("holder_content_type", "holder_object_id")

    # Paramètres de session
    timeout_seconds = models.PositiveIntegerField(default=180,
                                                    help_text="Auto-annulation si inactivité.")
    started_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)

    # Compteurs (dénormalisés pour le dashboard)
    scans_count = models.PositiveIntegerField(default=0)
    valid_count = models.PositiveIntegerField(default=0)
    duplicate_count = models.PositiveIntegerField(default=0)
    error_count = models.PositiveIntegerField(default=0)

    error_message = models.CharField(max_length=500, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["tenant", "status"]),
            models.Index(fields=["initiated_by", "status"]),
        ]

    def __str__(self):
        return f"Session {self.pk} [{self.status}] × {self.scans_count} scans"

    @property
    def channel_group(self) -> str:
        """Nom du groupe Channels pour broadcaster les events de cette session."""
        return f"enrollment.{self.pk}"


class RFIDEnrollmentEvent(TimeStampedModel):
    """Événement émis pendant une session d'enrôlement.

    Un event = un UID scanné, ou une transition d'état, ou une erreur.
    """

    EVENT_TYPE_CHOICES = [
        ("card.detected",   "Carte détectée"),
        ("card.duplicate",  "Carte déjà enrôlée"),
        ("card.enrolled",   "Carte enrôlée"),
        ("card.error",      "Erreur carte"),
        ("session.start",   "Session démarrée"),
        ("session.stop",    "Session arrêtée"),
        ("session.timeout", "Session timeout"),
        ("device.error",    "Erreur équipement"),
    ]

    session = models.ForeignKey(RFIDEnrollmentSession, on_delete=models.CASCADE,
                                 related_name="events")
    event_type = models.CharField(max_length=24, choices=EVENT_TYPE_CHOICES, db_index=True)
    uid = models.CharField(max_length=64, blank=True, db_index=True)
    device = models.ForeignKey("devices.Device", null=True, blank=True,
                                on_delete=models.SET_NULL, related_name="+")
    rssi = models.SmallIntegerField(null=True, blank=True)
    payload = models.JSONField(default=dict, blank=True)
    message = models.CharField(max_length=240, blank=True)
    resulting_badge = models.ForeignKey("devices.Badge", null=True, blank=True,
                                         on_delete=models.SET_NULL, related_name="+")

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["session", "event_type"]),
            models.Index(fields=["uid"]),
        ]

    def __str__(self):
        return f"{self.event_type} · {self.uid or '—'}"


# ═══════════════════════════════════════════════════════════════════
# Agent local — Kaydan Shield Local Agent
# ═══════════════════════════════════════════════════════════════════
class LocalAgent(UUIDModel, TimeStampedModel):
    """Agent local installé sur le LAN client — relaye lectures & commandes.

    Un LocalAgent maintient une WebSocket persistante vers ``/ws/agents/<id>/``.
    Le serveur push les commandes via cette WS ; l'agent push les events RFID
    via HTTP ``/api/v1/agent/events/`` (ou via la même WS quand messages entrants).
    """

    tenant = models.ForeignKey("core.Tenant", on_delete=models.CASCADE,
                                related_name="local_agents")
    label = models.CharField(max_length=120,
                              help_text="Nom donné à l'agent, ex. « Chantier Riviera-01 ».")
    api_token = models.CharField(max_length=64, unique=True, db_index=True,
                                  help_text="Secret partagé pour authentifier l'agent (HMAC).")
    # NB : Fernet encrypt un token de 43 chars → payload chiffré ~130-180 chars.
    # On garde une marge très large (512) pour éviter tout StringDataRightTruncation.
    hmac_secret = EncryptedCharField(max_length=512, blank=True,
                                      help_text="Secret HMAC pour signer les messages (stocké chiffré).")

    site = models.ForeignKey("sites.Site", null=True, blank=True,
                              on_delete=models.SET_NULL, related_name="local_agents")
    last_seen_at = models.DateTimeField(null=True, blank=True)
    connected = models.BooleanField(default=False,
                                     help_text="True si une WS est actuellement ouverte.")
    channel_name = models.CharField(max_length=200, blank=True,
                                     help_text="Nom Channels du canal WS actif.")

    version = models.CharField(max_length=32, blank=True)
    os_info = models.CharField(max_length=120, blank=True)
    devices_discovered = models.JSONField(default=list, blank=True,
                                           help_text="Snapshot des équipements vus par l'agent.")

    # ── Vague 9 : provisioning & supervision Edge Gateway ────────
    activation_token = models.CharField(max_length=64, unique=True, blank=True,
                                          null=True, db_index=True,
        help_text="Token à usage unique pour l'enrôlement initial du Gateway "
                    "(échangé contre api_token permanent au premier boot).")
    activation_expires_at = models.DateTimeField(null=True, blank=True,
        help_text="Expiration du activation_token — après quoi il faut regénérer.")
    activated_at = models.DateTimeField(null=True, blank=True,
        help_text="Date du premier appairage réussi.")
    revoked_at = models.DateTimeField(null=True, blank=True,
        help_text="Date de révocation — l'agent ne peut plus se connecter.")

    ip_local = models.GenericIPAddressField(null=True, blank=True,
        help_text="IP locale de la machine hôte, poussée par l'agent au heartbeat.")
    ip_public = models.GenericIPAddressField(null=True, blank=True,
        help_text="IP publique vue par le serveur cloud.")
    uptime_seconds = models.BigIntegerField(null=True, blank=True)
    events_pending = models.PositiveIntegerField(default=0,
        help_text="Nombre d'événements dans l'offline queue de l'agent.")

    # Statuts détaillés (poussés par l'agent au heartbeat)
    STATUS_CHOICES = [
        ("unknown", "Inconnu"),
        ("ok", "OK"),
        ("degraded", "Dégradé"),
        ("down", "Hors service"),
    ]
    mqtt_status = models.CharField(max_length=12, choices=STATUS_CHOICES,
                                     default="unknown")
    ws_status = models.CharField(max_length=12, choices=STATUS_CHOICES,
                                   default="unknown")
    cloud_status = models.CharField(max_length=12, choices=STATUS_CHOICES,
                                      default="unknown")

    class Meta:
        ordering = ["-last_seen_at"]

    def __str__(self):
        return f"{self.label} ({'en ligne' if self.connected else 'hors ligne'})"


# ═══════════════════════════════════════════════════════════════════
# GatewayTarget (Phase 3 — équipements vendors pilotés par une gateway)
# ═══════════════════════════════════════════════════════════════════
class GatewayTarget(UUIDModel, TimeStampedModel):
    """Équipement vendor géré par un Kaydan Edge Gateway.

    Chaque LocalAgent (gateway) peut piloter plusieurs équipements vendors
    (ZKTeco, Hikvision, Suprema, HID, Dahua, Axis). Cette table stocke
    la config de connexion pour chacun.

    L'agent Go lit cette liste depuis son fichier TOML (section [[targets]]
    générée dynamiquement lors du download du package) et démarre un driver
    par target via ``drivers.Manager.Start()``.
    """
    VENDOR_CHOICES = [
        ("zkteco",    "ZKTeco (Push HTTP)"),
        ("hikvision", "Hikvision (ISAPI)"),
        ("suprema",   "Suprema (BioStar 2 REST)"),
        ("hid",       "HID Global (VertX)"),
        ("dahua",     "Dahua (CGI)"),
        ("axis",      "Axis (VAPIX)"),
        ("onvif",     "ONVIF générique"),
        ("generic",   "Générique (custom)"),
    ]

    gateway = models.ForeignKey(
        LocalAgent, on_delete=models.CASCADE, related_name="targets",
        help_text="Kaydan Edge Gateway qui pilote cet équipement.",
    )
    label = models.CharField(max_length=120,
        help_text='Nom convivial, ex. "Portail entrée principale".')
    vendor = models.CharField(max_length=24, choices=VENDOR_CHOICES, db_index=True)
    ip = models.GenericIPAddressField()
    port = models.PositiveIntegerField(default=0,
        help_text="0 = port par défaut du vendor (ex: 80 pour Hikvision).")

    # Credentials chiffrés (identifiants d'accès au device vendor)
    username = models.CharField(max_length=120, blank=True)
    password = EncryptedCharField(max_length=512, blank=True,
        help_text="Password vendor (stocké chiffré Fernet).")

    # Métadonnées matérielles
    mac = models.CharField(max_length=17, blank=True)
    model = models.CharField(max_length=80, blank=True)
    firmware = models.CharField(max_length=40, blank=True)
    serial_number = models.CharField(max_length=64, blank=True, db_index=True)

    # État runtime (poussé par la gateway)
    connected = models.BooleanField(default=False)
    last_seen_at = models.DateTimeField(null=True, blank=True)
    events_count = models.PositiveIntegerField(default=0)
    last_error = models.TextField(blank=True)

    # Extra JSON pour config vendor-spécifique (chemins door_id, etc.)
    extra = models.JSONField(default=dict, blank=True)

    enabled = models.BooleanField(default=True,
        help_text="False = target désactivé (l'agent ne le connectera pas).")

    class Meta:
        ordering = ["gateway", "vendor", "label"]
        indexes = [
            models.Index(fields=["gateway", "enabled"]),
            models.Index(fields=["vendor", "enabled"]),
        ]
        unique_together = [("gateway", "ip", "port")]

    def __str__(self):
        return f"{self.label} ({self.vendor} @ {self.ip})"

    def to_toml_dict(self) -> dict:
        """Serialize pour injection dans le TOML de l'agent."""
        return {
            "id":       str(self.pk),
            "vendor":   self.vendor,
            "ip":       self.ip,
            "port":     int(self.port or 0),
            "username": self.username or "",
            "password": self.password or "",
            "extra":    self.extra or {},
        }


# ═══════════════════════════════════════════════════════════════════
# Packages Kaydan Edge Gateway (Vague 9 — téléchargement multi-plateforme)
# ═══════════════════════════════════════════════════════════════════
class EdgeGatewayPackage(TimeStampedModel):
    """Package installateur Kaydan Edge Gateway par plateforme.

    L'administrateur upload les binaires officiels ici (via admin Django)
    puis les utilisateurs les téléchargent depuis /admin/edge-gateway/.

    Le fichier est stocké dans MEDIA_ROOT/gateway_packages/.
    """
    PLATFORM_CHOICES = [
        # Windows
        ("windows_exe",       "Windows (Installateur .exe)"),
        ("windows_portable",  "Windows (Portable ZIP)"),
        # Linux
        ("linux_deb",         "Linux (.deb)"),
        ("linux_rpm",         "Linux (.rpm)"),
        ("linux_sh",          "Linux (script universel)"),
        # macOS
        ("macos_pkg",         "macOS (.pkg)"),
        # Container
        ("docker",            "Docker Compose"),
        # Embedded / IoT
        ("raspberry_pi",      "Raspberry Pi"),
        ("mini_pc",           "Mini PC industriel"),
        # Legacy fallback (rétrocompat : ancien "windows" tout court)
        ("windows",           "Windows (legacy)"),
    ]

    name = models.CharField(max_length=120,
        help_text='Nom convivial, ex. "kshield-edge-1.2.0-windows-x64".')
    platform = models.CharField(max_length=24, choices=PLATFORM_CHOICES, db_index=True)
    version = models.CharField(max_length=32,
        help_text='Semver, ex. "1.2.0".')
    file = models.FileField(upload_to="gateway_packages/", null=True, blank=True,
        help_text="Binaire installateur ou tarball. Null pour Docker (image seule).")
    docker_image = models.CharField(max_length=200, blank=True,
        help_text='Ex. "kaydangroupe/kshield-edge:1.2.0" pour la plateforme "docker".')
    docker_compose_snippet = models.TextField(blank=True,
        help_text="Extrait docker-compose.yml prêt à coller.")
    size_bytes = models.BigIntegerField(default=0)
    checksum_sha256 = models.CharField(max_length=64, blank=True, db_index=True)
    release_notes = models.TextField(blank=True)
    published_at = models.DateTimeField(null=True, blank=True, db_index=True)
    is_latest = models.BooleanField(default=False, db_index=True,
        help_text="Marque la version courante pour chaque plateforme.")
    min_os_version = models.CharField(max_length=64, blank=True,
        help_text='Ex. "Windows 10 20H2" ou "Ubuntu 20.04".')

    class Meta:
        ordering = ["-published_at", "platform"]
        indexes = [models.Index(fields=["platform", "is_latest"])]

    def __str__(self):
        return f"{self.name} ({self.version})"

    def save(self, *args, **kwargs):
        # Auto-calcul checksum SHA256 + taille dès qu'un fichier est uploadé.
        if self.file and hasattr(self.file, "path"):
            try:
                import hashlib, os
                path = self.file.path
                if os.path.exists(path):
                    self.size_bytes = os.path.getsize(path)
                    if not self.checksum_sha256:
                        h = hashlib.sha256()
                        with open(path, "rb") as f:
                            for chunk in iter(lambda: f.read(65536), b""):
                                h.update(chunk)
                        self.checksum_sha256 = h.hexdigest()
            except Exception:
                pass
        super().save(*args, **kwargs)


# ═══════════════════════════════════════════════════════════════════
# Historique des alertes système (Vague 5)
# ═══════════════════════════════════════════════════════════════════
class SystemAlert(UUIDModel, TimeStampedModel):
    """Alerte matérialisée en DB pour historique + routing notifications.

    Auto-résolue quand la condition disparaît (le sweep Celery met ``resolved_at``).
    """

    TYPE_CHOICES = [
        ("agent_offline",   "Agent hors ligne"),
        ("agent_stale",     "Agent stale"),
        ("device_offline",  "Équipement hors ligne"),
        ("session_stalled", "Session bloquée"),
        ("command_timeout", "Commande timeout"),
    ]
    SEVERITY_CHOICES = [
        ("critical", "Critique"),
        ("warning",  "Avertissement"),
        ("info",     "Info"),
    ]

    tenant = models.ForeignKey("core.Tenant", on_delete=models.CASCADE,
                                related_name="system_alerts")
    kind = models.CharField(max_length=32, choices=TYPE_CHOICES, db_index=True)
    severity = models.CharField(max_length=12, choices=SEVERITY_CHOICES,
                                 default="warning", db_index=True)
    title = models.CharField(max_length=240)
    detail = models.CharField(max_length=500, blank=True)

    # Cible : URL front + ID de l'objet concerné (device, agent, session…)
    target_url = models.CharField(max_length=240, blank=True)
    target_id = models.CharField(max_length=64, blank=True, db_index=True)

    # Cycle de vie
    resolved_at = models.DateTimeField(null=True, blank=True, db_index=True)
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    acknowledged_by = models.ForeignKey("accounts.User", null=True, blank=True,
                                         on_delete=models.SET_NULL, related_name="+")

    # Routing notifications (une seule fois par alerte)
    routed_at = models.DateTimeField(null=True, blank=True)

    payload = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["tenant", "kind", "resolved_at"]),
            models.Index(fields=["severity", "resolved_at"]),
        ]

    def __str__(self):
        return f"{self.severity}: {self.title}"

    @property
    def dedup_key(self) -> str:
        """Clef d'idempotence pour éviter les doublons."""
        return f"{self.kind}:{self.target_id}"


# ═══════════════════════════════════════════════════════════════════
# Digital Twin — jumeau numérique de chaque Device (Vague 7)
# ═══════════════════════════════════════════════════════════════════
class DeviceTwin(TimeStampedModel):
    """Jumeau numérique — cache runtime de l'état d'un équipement.

    Le front ne dialogue JAMAIS directement avec l'équipement — il lit le twin,
    qui est rafraîchi périodiquement par la tâche Celery ``refresh_device_twins``
    ou immédiatement quand un driver retourne un ``DeviceStatus``.
    """

    device = models.OneToOneField(
        "devices.Device", on_delete=models.CASCADE, related_name="twin",
        primary_key=True,
    )

    # État global
    reachable = models.BooleanField(default=False, db_index=True)
    health_score = models.PositiveSmallIntegerField(
        default=100, db_index=True,
        help_text="Score 0-100 recalculé à chaque refresh (0=KO, 100=OK).",
    )
    health_reasons = models.JSONField(default=list, blank=True,
        help_text="Liste des raisons ayant fait baisser le score.")

    # Runtime metrics
    latency_ms = models.PositiveIntegerField(null=True, blank=True)
    uptime_seconds = models.BigIntegerField(null=True, blank=True)
    cpu_percent = models.FloatField(null=True, blank=True)
    ram_percent = models.FloatField(null=True, blank=True)
    storage_percent = models.FloatField(null=True, blank=True)
    temperature_c = models.FloatField(null=True, blank=True)
    battery_percent = models.PositiveSmallIntegerField(null=True, blank=True)
    network_quality = models.PositiveSmallIntegerField(null=True, blank=True,
        help_text="0-100 (RSSI ou latence normalisée).")

    # Identification (miroir des champs Device pour éviter les jointures fréquentes)
    firmware = models.CharField(max_length=64, blank=True)
    hardware = models.CharField(max_length=64, blank=True)

    # Historique compact — dernières erreurs / événements notables
    recent_errors = models.JSONField(default=list, blank=True,
        help_text="Max 20 dernières erreurs (ring buffer).")
    driver_class = models.CharField(max_length=120, blank=True,
        help_text="Nom du driver qui alimente ce twin.")

    # Snapshot complet dernière lecture
    raw_status = models.JSONField(default=dict, blank=True)

    last_probed_at = models.DateTimeField(null=True, blank=True, db_index=True)
    last_seen_at = models.DateTimeField(null=True, blank=True,
        help_text="Dernier moment où l'équipement a répondu à un ping.")

    class Meta:
        indexes = [
            models.Index(fields=["reachable", "health_score"]),
        ]

    def __str__(self):
        return f"Twin[{self.device_id}] score={self.health_score} reach={self.reachable}"

    @property
    def health_status(self) -> str:
        """Bucket textuel du score."""
        if self.health_score >= 90: return "excellent"
        if self.health_score >= 70: return "good"
        if self.health_score >= 40: return "degraded"
        return "critical"


# ═══════════════════════════════════════════════════════════════════
# Maintenance prédictive — tickets générés automatiquement (Vague 8)
# ═══════════════════════════════════════════════════════════════════
class MaintenanceTicket(UUIDModel, TimeStampedModel):
    """Ticket de maintenance créé automatiquement par le moteur prédictif
    ou manuellement par un opérateur.

    Cycle : open → in_progress → resolved | cancelled
    """
    KIND_CHOICES = [
        ("battery_low",         "Batterie faible"),
        ("battery_critical",    "Batterie critique"),
        ("storage_low",         "Stockage faible"),
        ("storage_critical",    "Stockage critique"),
        ("temperature_high",    "Température élevée"),
        ("temperature_critical","Température critique"),
        ("firmware_outdated",   "Firmware obsolète"),
        ("connectivity_loss",   "Perte de connectivité"),
        ("high_error_rate",     "Taux d'erreurs élevé"),
        ("performance_drop",    "Baisse de performance"),
        ("scheduled",           "Maintenance programmée"),
        ("manual",              "Ticket manuel"),
    ]
    SEVERITY_CHOICES = [
        ("info", "Info"), ("warning", "Avertissement"),
        ("critical", "Critique"),
    ]
    STATUS_CHOICES = [
        ("open",         "Ouvert"),
        ("in_progress",  "En cours"),
        ("resolved",     "Résolu"),
        ("cancelled",    "Annulé"),
    ]

    tenant = models.ForeignKey("core.Tenant", on_delete=models.CASCADE,
                                related_name="maintenance_tickets")
    device = models.ForeignKey("devices.Device", on_delete=models.CASCADE,
                                related_name="maintenance_tickets")
    kind = models.CharField(max_length=32, choices=KIND_CHOICES, db_index=True)
    severity = models.CharField(max_length=12, choices=SEVERITY_CHOICES,
                                 default="warning", db_index=True)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES,
                               default="open", db_index=True)

    title = models.CharField(max_length=240)
    description = models.TextField(blank=True)
    prediction = models.JSONField(default=dict, blank=True,
        help_text="Données prédictives : trend, ETA, seuils.")
    confidence = models.FloatField(default=1.0,
        help_text="0.0-1.0 — confiance du moteur pour les tickets auto.")

    created_by_engine = models.BooleanField(default=False, db_index=True)
    assigned_to = models.ForeignKey("accounts.User", null=True, blank=True,
                                     on_delete=models.SET_NULL, related_name="+")
    scheduled_for = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolution_notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["tenant", "status", "severity"]),
            models.Index(fields=["device", "status"]),
        ]

    def __str__(self):
        return f"[{self.severity}] {self.title}"


# ═══════════════════════════════════════════════════════════════════
# Ré-export des modèles d'événements (Phase 1 — cahier des charges)
# ═══════════════════════════════════════════════════════════════════
# Ces modèles vivent dans models_events.py pour ne pas alourdir ce fichier
# déjà volumineux, mais sont exposés ici pour permettre les imports
# standards :
#     from devices.models import EventType, DeviceEvent
from .models_events import (  # noqa: E402, F401
    EventType,
    DeviceEvent,
    EventAcknowledgement,
    EventCategory,
    EventSeverity,
    EventResult,
    TransmissionMode,
)
from .models_badges import (  # noqa: E402, F401
    BadgeAssignment,
    BadgeLifecycleEvent,
)
from .models_sync import (  # noqa: E402, F401
    EdgeSyncBatch,
    EdgeSyncItem,
    EdgeSyncConflict,
    SyncDirection,
    SyncStatus,
    SyncPriority,
    SyncEntityType,
    ConflictResolution,
)
from .models_discovery import (  # noqa: E402, F401
    DeviceDiscovery,
    DeviceDiscoveryScan,
    DiscoveryStatus,
    DeviceState,
    DiscoveryProtocol,
    DeviceCompatibility,
)
from .models_agents import (  # noqa: E402, F401
    LocalAgentType,
    LocalAgentHeartbeat,
    LocalAgentConfiguration,
    LocalAgentLog,
    AgentState,
    LogLevel,
)
