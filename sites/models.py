"""KAYDAN SHIELD — sites: Site, Zone, Checkpoint, OpeningHours, SitePolicy."""
from django.db import models

from core.models import TimeStampedModel, UUIDModel


class Site(UUIDModel, TimeStampedModel):
    TYPE_CHOICES = [
        ("office", "Bureau"),
        ("warehouse", "Entrepôt / Stockage"),
        ("construction", "Chantier"),
        ("mixed", "Mixte"),
    ]
    STATUS_CHOICES = [
        ("active", "Actif"),
        ("inactive", "Inactif"),
        ("archived", "Archivé"),
    ]

    tenant = models.ForeignKey("core.Tenant", on_delete=models.CASCADE, related_name="sites")
    company = models.ForeignKey(
        "core.Company", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="sites",
    )
    name = models.CharField(max_length=180)
    code = models.SlugField(max_length=40)
    type = models.CharField(max_length=16, choices=TYPE_CHOICES, default="office")
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default="active")

    address = models.ForeignKey(
        "core.Address", on_delete=models.SET_NULL, null=True, blank=True, related_name="sites",
    )
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    geofence = models.JSONField(default=dict, blank=True, help_text="Polygone GeoJSON optionnel")

    timezone = models.CharField(max_length=64, default="Africa/Abidjan")

    # Spécifique chantier
    project_manager_name = models.CharField(max_length=180, blank=True)
    site_supervisor_name = models.CharField(max_length=180, blank=True)
    risk_level = models.CharField(
        max_length=10, blank=True,
        choices=[("low", "Faible"), ("medium", "Moyen"), ("high", "Élevé"), ("extreme", "Critique")],
    )
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)

    class Meta:
        unique_together = ("tenant", "code")
        ordering = ["name"]

    def __str__(self): return self.name


class Zone(TimeStampedModel):
    """Sous-zone hiérarchique d'un site (Bâtiment A, Hall, R+5...)."""

    site = models.ForeignKey(Site, on_delete=models.CASCADE, related_name="zones")
    parent = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.CASCADE, related_name="children",
    )
    name = models.CharField(max_length=180)
    code = models.SlugField(max_length=40)
    description = models.TextField(blank=True)
    is_restricted = models.BooleanField(default=False)

    class Meta:
        unique_together = ("site", "code")
        ordering = ["site", "name"]

    def __str__(self): return f"{self.site.code} / {self.name}"


class Checkpoint(TimeStampedModel):
    """Point de contrôle physique (entrée, sortie, scan inopiné)."""

    TYPE_CHOICES = [
        ("entry", "Entrée"),
        ("exit", "Sortie"),
        ("bidirectional", "Bidirectionnel"),
        ("inopine", "Contrôle inopiné"),
        ("internal", "Contrôle interne"),
    ]
    MODE_CHOICES = [
        ("fixed", "Fixe (Option A)"),
        ("mobile", "Mobile (Option B)"),
    ]
    METHOD_CHOICES = [
        ("nfc", "NFC"),
        ("uhf", "RFID UHF"),
        ("ble", "BLE"),
        ("qr", "QR code"),
        ("manual", "Manuel"),
        ("hybrid", "Hybride"),
    ]

    site = models.ForeignKey(Site, on_delete=models.CASCADE, related_name="checkpoints")
    zone = models.ForeignKey(
        Zone, on_delete=models.SET_NULL, null=True, blank=True, related_name="checkpoints",
    )
    name = models.CharField(max_length=180)
    code = models.SlugField(max_length=40)
    type = models.CharField(max_length=16, choices=TYPE_CHOICES, default="entry")
    mode = models.CharField(max_length=12, choices=MODE_CHOICES, default="fixed")
    method = models.CharField(max_length=12, choices=METHOD_CHOICES, default="hybrid")
    is_active = models.BooleanField(default=True)
    description = models.TextField(blank=True)

    class Meta:
        unique_together = ("site", "code")
        ordering = ["site", "name"]

    def __str__(self): return f"{self.site.code} / {self.name}"


class OpeningHours(TimeStampedModel):
    """Horaires d'ouverture d'un site/zone, par jour."""

    DAYS = [
        (0, "Lundi"), (1, "Mardi"), (2, "Mercredi"), (3, "Jeudi"),
        (4, "Vendredi"), (5, "Samedi"), (6, "Dimanche"),
    ]

    site = models.ForeignKey(Site, on_delete=models.CASCADE, related_name="opening_hours")
    zone = models.ForeignKey(
        Zone, null=True, blank=True, on_delete=models.CASCADE, related_name="opening_hours",
    )
    day_of_week = models.SmallIntegerField(choices=DAYS)
    open_time = models.TimeField()
    close_time = models.TimeField()
    is_closed = models.BooleanField(default=False)

    class Meta:
        ordering = ["site", "day_of_week"]


class SitePolicy(TimeStampedModel):
    """Règles applicables à un site (tolérance, casque obligatoire, etc.)."""

    site = models.OneToOneField(Site, on_delete=models.CASCADE, related_name="policy")
    late_tolerance_minutes = models.PositiveSmallIntegerField(default=10)
    very_late_threshold_minutes = models.PositiveSmallIntegerField(default=30)
    morning_punch_open = models.TimeField(default="06:00")
    morning_punch_close = models.TimeField(default="09:30")
    evening_punch_open = models.TimeField(default="16:30")
    evening_punch_close = models.TimeField(default="20:00")
    helmet_required = models.BooleanField(default=False)
    badge_helmet_pairing_required = models.BooleanField(default=False)
    visitor_escort_required = models.BooleanField(default=True)
    auto_unlock_door = models.BooleanField(default=False)

    def __str__(self): return f"Politique — {self.site}"
