"""KAYDAN SHIELD — visitors: gestion visiteurs (OCR CNI + self-service QR)."""
import secrets
import uuid

from django.db import models

from core.models import TimeStampedModel, UUIDModel


class VisitPurpose(TimeStampedModel):
    """Motifs de visite proposés à l'enregistrement."""

    code = models.SlugField(max_length=40, unique=True)
    label = models.CharField(max_length=180)
    requires_approval = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["label"]

    def __str__(self): return self.label


class Visitor(UUIDModel, TimeStampedModel):
    """Visiteur (identité issue OCR ou pré-saisie)."""

    ID_TYPE_CHOICES = [
        ("cni", "CNI"), ("passport", "Passeport"),
        ("driver_license", "Permis de conduire"), ("residence", "Carte de séjour"),
    ]

    tenant = models.ForeignKey("core.Tenant", on_delete=models.CASCADE, related_name="visitors")
    first_name = models.CharField(max_length=120)
    last_name = models.CharField(max_length=120)
    date_of_birth = models.DateField(null=True, blank=True)
    nationality = models.CharField(max_length=80, blank=True)
    id_type = models.CharField(max_length=16, choices=ID_TYPE_CHOICES, default="cni")
    id_number = models.CharField(max_length=64, blank=True, db_index=True)
    phone = models.CharField(max_length=32, blank=True)
    email = models.EmailField(blank=True)
    company = models.CharField("Entreprise/Organisation", max_length=180, blank=True)
    photo = models.ImageField(upload_to="visitors/photos/", null=True, blank=True)
    notes = models.TextField(blank=True)

    # RGPD
    pseudonymized_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["tenant", "id_number"])]

    def __str__(self): return f"{self.first_name} {self.last_name}"


class VisitorIDDocument(TimeStampedModel):
    """Image et résultat OCR de la pièce d'identité (chiffrée S3 en prod)."""

    visitor = models.ForeignKey(Visitor, on_delete=models.CASCADE, related_name="id_documents")
    front_image = models.ImageField(upload_to="visitors/id/front/", null=True, blank=True)
    back_image = models.ImageField(upload_to="visitors/id/back/", null=True, blank=True)
    ocr_payload = models.JSONField(default=dict, blank=True)
    ocr_confidence = models.FloatField(default=0.0)


class VisitRequest(UUIDModel, TimeStampedModel):
    """Demande de visite (planifiée ou inopinée)."""

    STATUS_CHOICES = [
        ("pending", "En attente"),
        ("approved", "Approuvée"),
        ("rejected", "Refusée"),
        ("cancelled", "Annulée"),
        ("checked_in", "Arrivée enregistrée"),
        ("completed", "Terminée"),
    ]
    MODE_CHOICES = [
        ("walk_in", "Inopinée"),
        ("self_service", "Self-service"),
    ]

    tenant = models.ForeignKey("core.Tenant", on_delete=models.CASCADE, related_name="visit_requests")
    visitor = models.ForeignKey(Visitor, on_delete=models.CASCADE, related_name="visit_requests")
    site = models.ForeignKey("sites.Site", on_delete=models.CASCADE, related_name="visit_requests")
    host_employee = models.ForeignKey(
        "employees.Employee", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="hosted_visits",
    )
    purpose = models.ForeignKey(
        VisitPurpose, null=True, blank=True, on_delete=models.SET_NULL, related_name="visit_requests",
    )
    purpose_other = models.CharField(max_length=240, blank=True)
    mode = models.CharField(max_length=16, choices=MODE_CHOICES, default="walk_in")
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="pending")
    scheduled_at = models.DateTimeField(null=True, blank=True)
    expected_duration_minutes = models.PositiveIntegerField(default=60)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]


class VisitorInvitation(TimeStampedModel):
    """Lien envoyé au visiteur pour le pré-enregistrement self-service."""

    visit_request = models.ForeignKey(VisitRequest, on_delete=models.CASCADE, related_name="invitations")
    token = models.CharField(max_length=64, unique=True, default=secrets.token_urlsafe)
    sent_to_email = models.EmailField(blank=True)
    sent_to_phone = models.CharField(max_length=32, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)


class VisitorPass(TimeStampedModel):
    """Badge visiteur émis (PVC marche-arrière ou QR self-service)."""

    TYPE_CHOICES = [
        ("self_service_qr", "QR self-service"),
        ("walk_in_pvc", "Badge PVC inopiné"),
        ("digital", "Badge numérique"),
    ]

    visit_request = models.OneToOneField(VisitRequest, on_delete=models.CASCADE, related_name="pass_card")
    type = models.CharField(max_length=20, choices=TYPE_CHOICES, default="walk_in_pvc")
    qr_token = models.CharField(max_length=80, unique=True, default=uuid.uuid4)
    serial_number = models.CharField(max_length=40, blank=True)
    valid_from = models.DateTimeField()
    valid_until = models.DateTimeField()
    allowed_zones = models.ManyToManyField("sites.Zone", blank=True, related_name="visitor_passes")
    revoked_at = models.DateTimeField(null=True, blank=True)


class VisitLog(TimeStampedModel):
    """Entrée et sortie effectives du visiteur."""

    visit_request = models.ForeignKey(VisitRequest, on_delete=models.CASCADE, related_name="logs")
    checked_in_at = models.DateTimeField()
    checked_out_at = models.DateTimeField(null=True, blank=True)
    checkin_user = models.ForeignKey(
        "accounts.User", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="visit_checkins",
    )
    escort_employee = models.ForeignKey(
        "employees.Employee", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="visitor_escorts",
    )
    signature = models.ImageField(upload_to="visitors/signatures/", null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-checked_in_at"]


class Watchlist(TimeStampedModel):
    """Liste rouge — visiteur banni d'un site/tenant."""

    tenant = models.ForeignKey("core.Tenant", on_delete=models.CASCADE, related_name="watchlist")
    visitor = models.ForeignKey(
        Visitor, null=True, blank=True, on_delete=models.SET_NULL, related_name="watchlist_entries",
    )
    full_name = models.CharField(max_length=240, blank=True)
    id_number = models.CharField(max_length=64, blank=True)
    site = models.ForeignKey(
        "sites.Site", null=True, blank=True, on_delete=models.CASCADE, related_name="watchlist",
    )
    reason = models.TextField()
    is_active = models.BooleanField(default=True)
    expires_at = models.DateTimeField(null=True, blank=True)
