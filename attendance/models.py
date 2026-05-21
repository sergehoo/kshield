"""KAYDAN SHIELD — attendance: pointage, présence, BLE, congés."""
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models

from core.models import TimeStampedModel


class Punch(TimeStampedModel):
    TYPE_CHOICES = [
        ("morning_in", "Pointage matin entrée"),
        ("morning_out", "Pointage matin sortie"),
        ("evening_in", "Pointage soir entrée"),
        ("evening_out", "Pointage soir sortie"),
        ("break_in", "Pause entrée"),
        ("break_out", "Pause sortie"),
    ]
    STATUS_CHOICES = [
        ("on_time", "À l'heure"),
        ("late", "En retard"),
        ("very_late", "Très en retard"),
        ("missing", "Manquant"),
        ("manual", "Saisie manuelle"),
    ]
    HOLDER_KIND_CHOICES = [("employee", "Employé"), ("worker", "Ouvrier"), ("visitor", "Visiteur")]

    tenant = models.ForeignKey("core.Tenant", on_delete=models.CASCADE, related_name="punches")
    site = models.ForeignKey("sites.Site", on_delete=models.PROTECT, related_name="punches")
    holder_kind = models.CharField(max_length=12, choices=HOLDER_KIND_CHOICES)
    holder_content_type = models.ForeignKey(
        ContentType, null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
    )
    holder_object_id = models.PositiveBigIntegerField(null=True, blank=True)
    holder = GenericForeignKey("holder_content_type", "holder_object_id")

    type = models.CharField(max_length=12, choices=TYPE_CHOICES)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default="on_time")
    timestamp = models.DateTimeField(db_index=True)
    delay_minutes = models.IntegerField(default=0)

    source_event = models.ForeignKey(
        "access_control.AccessEvent", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="punches",
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-timestamp"]
        indexes = [
            models.Index(fields=["site", "timestamp"]),
            models.Index(fields=["holder_kind", "holder_object_id", "timestamp"]),
        ]


class AttendanceDay(TimeStampedModel):
    STATUS_CHOICES = [
        ("present", "Présent"),
        ("partial", "Présence partielle"),
        ("absent", "Absent"),
        ("leave", "En congé"),
        ("rest_day", "Jour non travaillé"),
        ("holiday", "Férié"),
    ]
    HOLDER_KIND_CHOICES = [("employee", "Employé"), ("worker", "Ouvrier")]

    tenant = models.ForeignKey("core.Tenant", on_delete=models.CASCADE, related_name="attendance_days")
    site = models.ForeignKey("sites.Site", on_delete=models.PROTECT, related_name="attendance_days")
    holder_kind = models.CharField(max_length=12, choices=HOLDER_KIND_CHOICES)
    holder_object_id = models.PositiveBigIntegerField()
    date = models.DateField(db_index=True)

    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default="absent")
    first_punch_at = models.DateTimeField(null=True, blank=True)
    last_punch_at = models.DateTimeField(null=True, blank=True)
    duration_minutes = models.PositiveIntegerField(default=0)
    delay_total_minutes = models.PositiveIntegerField(default=0)
    helmet_paired = models.BooleanField(default=False)
    incidents_count = models.PositiveSmallIntegerField(default=0)

    class Meta:
        unique_together = ("tenant", "site", "holder_kind", "holder_object_id", "date")
        ordering = ["-date"]
        indexes = [models.Index(fields=["site", "date", "status"])]


class BLEPresencePing(models.Model):
    """Ping BLE individuel (haute fréquence)."""

    helmet = models.ForeignKey("devices.Helmet", on_delete=models.CASCADE, related_name="ble_pings")
    zone = models.ForeignKey("sites.Zone", null=True, blank=True, on_delete=models.SET_NULL, related_name="ble_pings")
    timestamp = models.DateTimeField(db_index=True)
    rssi = models.SmallIntegerField(null=True, blank=True)
    is_immobile = models.BooleanField(default=False)
    accelerometer_payload = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-timestamp"]
        indexes = [models.Index(fields=["helmet", "timestamp"])]


class BLEPresenceWindow(TimeStampedModel):
    """Fenêtre agrégée (5 min) — utilisée par les règles anti-fraude BLE."""

    helmet = models.ForeignKey("devices.Helmet", on_delete=models.CASCADE, related_name="ble_windows")
    zone = models.ForeignKey("sites.Zone", null=True, blank=True, on_delete=models.SET_NULL, related_name="ble_windows")
    started_at = models.DateTimeField(db_index=True)
    ended_at = models.DateTimeField()
    pings_count = models.PositiveIntegerField(default=0)
    immobile_minutes = models.PositiveIntegerField(default=0)


class LeaveRequest(TimeStampedModel):
    TYPE_CHOICES = [
        ("paid", "Congé payé"),
        ("sick", "Maladie"),
        ("unpaid", "Sans solde"),
        ("mission", "Mission externe"),
        ("training", "Formation"),
        ("other", "Autre"),
    ]
    STATUS_CHOICES = [
        ("pending", "En attente"),
        ("approved", "Approuvé"),
        ("rejected", "Refusé"),
        ("cancelled", "Annulé"),
    ]

    employee = models.ForeignKey(
        "employees.Employee", null=True, blank=True,
        on_delete=models.CASCADE, related_name="leave_requests",
    )
    worker = models.ForeignKey(
        "ouvriers.Worker", null=True, blank=True,
        on_delete=models.CASCADE, related_name="leave_requests",
    )
    type = models.CharField(max_length=12, choices=TYPE_CHOICES, default="paid")
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default="pending")
    start_date = models.DateField()
    end_date = models.DateField()
    reason = models.TextField(blank=True)
    document = models.FileField(upload_to="leave/", null=True, blank=True)
    approved_by = models.ForeignKey(
        "accounts.User", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="approved_leaves",
    )
    approved_at = models.DateTimeField(null=True, blank=True)


class Roster(TimeStampedModel):
    """Planning prévisionnel d'une personne pour une journée."""

    HOLDER_KIND_CHOICES = [("employee", "Employé"), ("worker", "Ouvrier")]

    tenant = models.ForeignKey("core.Tenant", on_delete=models.CASCADE, related_name="rosters")
    site = models.ForeignKey("sites.Site", on_delete=models.CASCADE, related_name="rosters")
    holder_kind = models.CharField(max_length=12, choices=HOLDER_KIND_CHOICES)
    holder_object_id = models.PositiveBigIntegerField()
    date = models.DateField(db_index=True)
    expected_start = models.TimeField(null=True, blank=True)
    expected_end = models.TimeField(null=True, blank=True)
    is_present_expected = models.BooleanField(default=True)

    class Meta:
        unique_together = ("tenant", "site", "holder_kind", "holder_object_id", "date")


class OvertimeRule(TimeStampedModel):
    company = models.ForeignKey("core.Company", on_delete=models.CASCADE, related_name="overtime_rules")
    name = models.CharField(max_length=120)
    weekly_threshold_hours = models.DecimalField(max_digits=5, decimal_places=2, default=40)
    rate_125 = models.DecimalField(max_digits=4, decimal_places=2, default=1.25)
    rate_150 = models.DecimalField(max_digits=4, decimal_places=2, default=1.50)
    night_rate = models.DecimalField(max_digits=4, decimal_places=2, default=1.50)
    is_active = models.BooleanField(default=True)


class OvertimeCalculation(TimeStampedModel):
    employee = models.ForeignKey(
        "employees.Employee", null=True, blank=True,
        on_delete=models.CASCADE, related_name="overtime_calculations",
    )
    worker = models.ForeignKey(
        "ouvriers.Worker", null=True, blank=True,
        on_delete=models.CASCADE, related_name="overtime_calculations",
    )
    week_start = models.DateField()
    base_minutes = models.PositiveIntegerField(default=0)
    overtime_125_minutes = models.PositiveIntegerField(default=0)
    overtime_150_minutes = models.PositiveIntegerField(default=0)
    night_minutes = models.PositiveIntegerField(default=0)
    payload = models.JSONField(default=dict, blank=True)


class AttendanceCorrection(TimeStampedModel):
    """Correction manuelle d'un AttendanceDay par RH/manager (auditée)."""

    attendance_day = models.ForeignKey(AttendanceDay, on_delete=models.CASCADE, related_name="corrections")
    field_name = models.CharField(max_length=64)
    previous_value = models.JSONField(null=True, blank=True)
    new_value = models.JSONField(null=True, blank=True)
    reason = models.TextField()
    performed_by = models.ForeignKey(
        "accounts.User", on_delete=models.PROTECT, related_name="attendance_corrections",
    )


# ---------------------------------------------------------------------------
# Reconnaissance faciale → confirmation présence
# (ENRICHIT le pointage RFID existant, ne le remplace pas)
# ---------------------------------------------------------------------------
class FaceSightingEvent(TimeStampedModel):
    """Détection visage sur un flux caméra — trace brute (matched ou non).

    Chaque détection est enregistrée. Si ``matched=True``, l'employee est lié.
    Sinon c'est un visage inconnu (visiteur ? intrus ? employé non enrôlé ?).
    """

    camera = models.ForeignKey(
        "devices.Camera", on_delete=models.CASCADE, related_name="sightings",
    )
    site = models.ForeignKey(
        "sites.Site", on_delete=models.SET_NULL, related_name="face_sightings",
        null=True, blank=True,
    )
    employee = models.ForeignKey(
        "employees.Employee", on_delete=models.SET_NULL,
        related_name="face_sightings", null=True, blank=True, db_index=True,
    )

    timestamp = models.DateTimeField(db_index=True)
    face_score = models.FloatField(default=0.0, help_text="Similarité cosine 0-1")
    liveness_score = models.FloatField(null=True, blank=True,
        help_text="Score anti-spoof real_score 0-1 (null si liveness off)")
    bbox = models.JSONField(default=list, blank=True,
        help_text="[x1, y1, x2, y2] dans le repère image")
    snapshot = models.ImageField(
        upload_to="face_sightings/%Y/%m/%d/", null=True, blank=True,
        help_text="Crop ou frame complète au moment du sighting",
    )
    matched = models.BooleanField(default=False, db_index=True)

    class Meta:
        ordering = ("-timestamp",)
        indexes = [
            models.Index(fields=["employee", "timestamp"]),
            models.Index(fields=["camera", "timestamp"]),
            models.Index(fields=["matched", "timestamp"]),
        ]


class FaceCheckinConfirmation(TimeStampedModel):
    """Lie un sighting visage à un Punch RFID (ou pas) pour 1 employé/jour/type.

    Le pointage RFID reste la source de vérité. Cette table sert à :
      - confirmer qu'un employé a bien été VU à son arrivée/départ
      - alerter si un visage est vu sans badge correspondant (et inversement)
      - dédupliquer : 2 entrées max par employé par jour (arrival + departure)
    """

    KIND_CHOICES = [
        ("arrival",   "Arrivée bureau"),
        ("departure", "Départ bureau"),
    ]
    STATUS_CHOICES = [
        ("confirmed",      "Confirmé (badge + face matchent)"),
        ("face_only",      "Visage seul (pas de badge)"),
        ("badge_only",     "Badge seul (pas de visage)"),
        ("out_of_window",  "Hors fenêtre temporelle"),
    ]

    employee = models.ForeignKey(
        "employees.Employee", on_delete=models.CASCADE,
        related_name="checkin_confirmations",
    )
    date = models.DateField(db_index=True)
    kind = models.CharField(max_length=10, choices=KIND_CHOICES)

    sighting = models.OneToOneField(
        FaceSightingEvent, on_delete=models.SET_NULL,
        related_name="confirmation", null=True, blank=True,
    )
    punch = models.ForeignKey(
        Punch, on_delete=models.SET_NULL, related_name="face_confirmations",
        null=True, blank=True,
    )

    delta_seconds = models.IntegerField(
        null=True, blank=True,
        help_text="Écart temporel face↔badge (positif = badge après face)",
    )
    status = models.CharField(max_length=16, choices=STATUS_CHOICES,
                                default="confirmed", db_index=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ("-date", "kind")
        unique_together = ("employee", "date", "kind")
        indexes = [
            models.Index(fields=["date", "kind"]),
            models.Index(fields=["status"]),
        ]
