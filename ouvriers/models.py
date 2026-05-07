"""KAYDAN SHIELD — ouvriers: segment OUVRIERS (chantiers, RFID UHF + casque)."""
from django.db import models

from core.models import TimeStampedModel, UUIDModel


class Trade(TimeStampedModel):
    """Métier / corps de métier (maçon, ferrailleur, conducteur engin...)."""
    name = models.CharField(max_length=120, unique=True)
    code = models.SlugField(max_length=40, unique=True)
    description = models.TextField(blank=True)

    def __str__(self): return self.name


class Subcontractor(TimeStampedModel):
    """Sous-traitant employant des ouvriers sur les chantiers KAYDAN."""
    tenant = models.ForeignKey("core.Tenant", on_delete=models.CASCADE, related_name="subcontractors")
    name = models.CharField(max_length=180)
    code = models.SlugField(max_length=40)
    legal_name = models.CharField(max_length=240, blank=True)
    tax_id = models.CharField(max_length=40, blank=True)
    contact_name = models.CharField(max_length=180, blank=True)
    contact_phone = models.CharField(max_length=32, blank=True)
    contact_email = models.EmailField(blank=True)
    contract_start = models.DateField(null=True, blank=True)
    contract_end = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ("tenant", "code")
        ordering = ["name"]

    def __str__(self): return self.name


class Worker(UUIDModel, TimeStampedModel):
    STATUS_CHOICES = [
        ("active", "Actif"),
        ("suspended", "Suspendu"),
        ("blacklisted", "Liste rouge"),
        ("terminated", "Sorti"),
    ]

    tenant = models.ForeignKey("core.Tenant", on_delete=models.CASCADE, related_name="workers")
    matricule = models.CharField(max_length=40, db_index=True)
    first_name = models.CharField(max_length=120)
    last_name = models.CharField(max_length=120)
    date_of_birth = models.DateField(null=True, blank=True)
    photo = models.ImageField(upload_to="workers/photos/", null=True, blank=True)
    id_document_number = models.CharField(max_length=64, blank=True)
    id_document_file = models.FileField(upload_to="workers/id/", null=True, blank=True)
    phone = models.CharField(max_length=32, blank=True)
    emergency_contact_name = models.CharField(max_length=180, blank=True)
    emergency_contact_phone = models.CharField(max_length=32, blank=True)

    trade = models.ForeignKey(Trade, on_delete=models.SET_NULL, null=True, blank=True, related_name="workers")
    subcontractor = models.ForeignKey(
        Subcontractor, on_delete=models.SET_NULL, null=True, blank=True, related_name="workers",
    )
    helmet_size = models.CharField(max_length=8, blank=True, help_text="S, M, L, XL")
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default="active")

    class Meta:
        unique_together = ("tenant", "matricule")
        ordering = ["last_name", "first_name"]

    def __str__(self): return f"{self.matricule} — {self.first_name} {self.last_name}"

    @property
    def badge(self):
        """Badge RFID UHF actif (avec casque pairé) associé à cet ouvrier."""
        from devices.models import Badge
        return Badge.objects.filter(
            category="worker_rfid", holder_kind="worker",
            holder_object_id=self.id, status="active",
        ).select_related("paired_helmet").first()


class WorkerCertification(TimeStampedModel):
    """Habilitation HSE (CACES, hauteur, électricité...)."""
    worker = models.ForeignKey(Worker, on_delete=models.CASCADE, related_name="certifications")
    code = models.CharField(max_length=40)
    label = models.CharField(max_length=240)
    issued_at = models.DateField()
    valid_until = models.DateField(null=True, blank=True)
    document = models.FileField(upload_to="workers/certs/", null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-valid_until"]


class Crew(TimeStampedModel):
    """Équipe d'ouvriers sous un chef d'équipe sur un chantier."""

    site = models.ForeignKey("sites.Site", on_delete=models.CASCADE, related_name="crews")
    name = models.CharField(max_length=120)
    foreman = models.ForeignKey(
        Worker, null=True, blank=True, on_delete=models.SET_NULL, related_name="crews_led",
    )
    members = models.ManyToManyField(Worker, blank=True, related_name="crews")
    is_active = models.BooleanField(default=True)

    def __str__(self): return f"{self.site.code} / {self.name}"


class WorkerAssignment(TimeStampedModel):
    """Affectation ouvrier × chantier × période."""
    worker = models.ForeignKey(Worker, on_delete=models.CASCADE, related_name="assignments")
    site = models.ForeignKey("sites.Site", on_delete=models.CASCADE, related_name="worker_assignments")
    crew = models.ForeignKey(Crew, null=True, blank=True, on_delete=models.SET_NULL, related_name="assignments")
    started_at = models.DateField()
    ended_at = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-started_at"]
