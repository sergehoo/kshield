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
    GENDER_CHOICES = [
        ("male", "Homme"),
        ("female", "Femme"),
        ("other", "Autre"),
    ]
    MARITAL_STATUS_CHOICES = [
        ("single", "Célibataire"),
        ("married", "Marié(e)"),
        ("divorced", "Divorcé(e)"),
        ("widowed", "Veuf/veuve"),
    ]
    ID_TYPE_CHOICES = [
        ("cni",       "CNI"),
        ("passport",  "Passeport"),
        ("driver",    "Permis de conduire"),
        ("cedeao",    "CEDEAO"),
        ("other",     "Autre"),
    ]

    tenant = models.ForeignKey("core.Tenant", on_delete=models.CASCADE, related_name="workers")
    matricule = models.CharField(max_length=40, db_index=True)
    first_name = models.CharField(max_length=120)
    last_name = models.CharField(max_length=120)
    date_of_birth = models.DateField(null=True, blank=True)
    gender = models.CharField(max_length=8, choices=GENDER_CHOICES, blank=True)
    marital_status = models.CharField(max_length=12, choices=MARITAL_STATUS_CHOICES, blank=True)
    photo = models.ImageField(upload_to="workers/photos/", null=True, blank=True)

    # KYC — pièce d'identité
    id_type = models.CharField(max_length=12, choices=ID_TYPE_CHOICES, blank=True)
    id_document_number = models.CharField(max_length=64, blank=True)
    id_document_file = models.FileField(upload_to="workers/id/", null=True, blank=True)
    id_issue_date = models.DateField(null=True, blank=True)
    id_expiry_date = models.DateField(null=True, blank=True)

    # Contact
    phone = models.CharField(max_length=32, blank=True)
    email = models.EmailField(blank=True)
    emergency_contact_name = models.CharField(max_length=180, blank=True)
    emergency_contact_phone = models.CharField(max_length=32, blank=True)
    emergency_contact_relation = models.CharField(max_length=80, blank=True)

    # Origine & résidence
    nationality = models.CharField(max_length=64, blank=True, help_text="Ex: Ivoirien, Malien…")
    country_of_residence = models.CharField(max_length=64, blank=True, default="Côte d'Ivoire")
    city = models.CharField(max_length=120, blank=True)
    neighborhood = models.CharField(max_length=120, blank=True, help_text="Quartier / commune")
    address = models.CharField(max_length=240, blank=True)

    # Métier & rattachement
    trade = models.ForeignKey(Trade, on_delete=models.SET_NULL, null=True, blank=True, related_name="workers")
    subcontractor = models.ForeignKey(
        Subcontractor, on_delete=models.SET_NULL, null=True, blank=True, related_name="workers",
    )
    helmet_size = models.CharField(max_length=8, blank=True, help_text="S, M, L, XL")

    # Emploi
    hired_at = models.DateField(null=True, blank=True, help_text="Date de première affectation")
    ended_at = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default="active")

    class Meta:
        unique_together = ("tenant", "matricule")
        ordering = ["last_name", "first_name"]

    @property
    def age(self):
        if not self.date_of_birth:
            return None
        from datetime import date
        today = date.today()
        return today.year - self.date_of_birth.year - (
            (today.month, today.day) < (self.date_of_birth.month, self.date_of_birth.day)
        )

    @property
    def seniority_days(self):
        """Ancienneté en jours depuis hired_at (ou created_at fallback)."""
        from datetime import date
        start = self.hired_at or (self.created_at.date() if self.created_at else None)
        if not start:
            return 0
        return (date.today() - start).days

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
