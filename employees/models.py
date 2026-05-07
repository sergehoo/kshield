"""KAYDAN SHIELD — employees: segment EMPLOYÉS (NFC, bureaux, stockage)."""
from django.db import models

from core.models import TimeStampedModel, UUIDModel


class Department(TimeStampedModel):
    company = models.ForeignKey(
        "core.Company", on_delete=models.CASCADE, related_name="departments",
    )
    name = models.CharField(max_length=180)
    code = models.SlugField(max_length=40)
    parent = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="children",
    )

    class Meta:
        unique_together = ("company", "code")
        ordering = ["name"]

    def __str__(self): return self.name


class JobPosition(TimeStampedModel):
    company = models.ForeignKey(
        "core.Company", on_delete=models.CASCADE, related_name="positions",
    )
    title = models.CharField(max_length=180)
    code = models.SlugField(max_length=60)
    seniority_level = models.PositiveSmallIntegerField(default=1)

    class Meta:
        unique_together = ("company", "code")
        ordering = ["title"]

    def __str__(self): return self.title


class Employee(UUIDModel, TimeStampedModel):
    CONTRACT_CHOICES = [
        ("cdi", "CDI"), ("cdd", "CDD"), ("internship", "Stage"),
        ("freelance", "Indépendant"), ("temp", "Intérim"),
    ]
    STATUS_CHOICES = [
        ("active", "Actif"),
        ("on_leave", "En congé"),
        ("suspended", "Suspendu"),
        ("terminated", "Sorti"),
    ]

    tenant = models.ForeignKey("core.Tenant", on_delete=models.CASCADE, related_name="employees")
    company = models.ForeignKey(
        "core.Company", on_delete=models.PROTECT, related_name="employees",
    )
    user = models.OneToOneField(
        "accounts.User", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="employee_profile",
    )

    matricule = models.CharField(max_length=40, db_index=True)
    first_name = models.CharField(max_length=120)
    last_name = models.CharField(max_length=120)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=32, blank=True)
    photo = models.ImageField(upload_to="employees/photos/", null=True, blank=True)
    id_document = models.FileField(upload_to="employees/id/", null=True, blank=True)

    department = models.ForeignKey(
        Department, null=True, blank=True, on_delete=models.SET_NULL, related_name="employees",
    )
    position = models.ForeignKey(
        JobPosition, null=True, blank=True, on_delete=models.SET_NULL, related_name="employees",
    )
    manager = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="subordinates",
    )

    contract_type = models.CharField(max_length=12, choices=CONTRACT_CHOICES, default="cdi")
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default="active")
    hired_at = models.DateField(null=True, blank=True)
    ended_at = models.DateField(null=True, blank=True)

    # Lieu de travail — détermine si on exige un casque RFID en plus du badge.
    # field    : employé chantier (badge + casque obligatoires)
    # office   : employé bureau (badge seul)
    # both     : employé mobile entre bureau et chantiers (les deux selon le site)
    WORK_LOCATION_CHOICES = [
        ("field",  "Chantier"),
        ("office", "Bureau"),
        ("both",   "Bureau + chantiers"),
    ]
    work_location = models.CharField(
        max_length=8,
        choices=WORK_LOCATION_CHOICES,
        default="office",
        help_text="Détermine si l'employé requiert un couplage badge + casque RFID sur les chantiers.",
    )

    authorized_sites = models.ManyToManyField("sites.Site", blank=True, related_name="authorized_employees")

    class Meta:
        unique_together = ("tenant", "matricule")
        ordering = ["last_name", "first_name"]

    def __str__(self): return f"{self.matricule} — {self.first_name} {self.last_name}"

    @property
    def badge(self):
        """Badge RFID actif associé à cet employé (None si aucun)."""
        from devices.models import Badge
        return Badge.objects.filter(
            category="employee_rfid", holder_kind="employee",
            holder_object_id=self.id, status="active",
        ).first()


class EmployeeContract(TimeStampedModel):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="contracts")
    contract_type = models.CharField(max_length=12, choices=Employee.CONTRACT_CHOICES)
    started_at = models.DateField()
    ended_at = models.DateField(null=True, blank=True)
    annual_salary = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    document = models.FileField(upload_to="employees/contracts/", null=True, blank=True)
    notes = models.TextField(blank=True)


class EmployeeAuthorization(TimeStampedModel):
    """Habilitation spécifique sur une zone (ex: stockage classé)."""

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="authorizations")
    zone = models.ForeignKey("sites.Zone", on_delete=models.CASCADE, related_name="authorizations")
    valid_from = models.DateField()
    valid_until = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)


class EmployeeSchedule(TimeStampedModel):
    SHIFT_CHOICES = [
        ("morning", "Matin"), ("afternoon", "Après-midi"),
        ("night", "Nuit"), ("flexible", "Flexible"), ("remote", "Télétravail"),
    ]

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="schedules")
    day_of_week = models.SmallIntegerField()  # 0..6
    shift = models.CharField(max_length=12, choices=SHIFT_CHOICES, default="morning")
    start_time = models.TimeField(null=True, blank=True)
    end_time = models.TimeField(null=True, blank=True)
    valid_from = models.DateField()
    valid_until = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["employee", "day_of_week"]


# ---------------------------------------------------------------------------
# Reconnaissance faciale (double facteur d'authentification au scan badge)
# ---------------------------------------------------------------------------
class FaceProfile(TimeStampedModel):
    """Profil biométrique facial d'un employé.

    Capturé par la caméra IP du checkpoint au moment de l'enrôlement.
    L'embedding (vecteur 128D ou 512D) est utilisé pour le matching à chaque
    scan badge en double facteur d'authentification.

    RGPD : les profils peuvent être désactivés/effacés sur demande via
    `audit.RGPDService.forget_face_profile(employee)`.
    """

    MODEL_CHOICES = [
        ("facenet_v1",   "FaceNet (TF) — 128D"),
        ("arcface_r100", "ArcFace IResNet100 — 512D"),
        ("insightface",  "InsightFace buffalo_l — 512D"),
    ]

    employee = models.ForeignKey(
        Employee, on_delete=models.CASCADE, related_name="face_profiles",
    )
    is_active = models.BooleanField(default=True, db_index=True)

    embedding_model = models.CharField(max_length=20, choices=MODEL_CHOICES, default="facenet_v1")
    embedding = models.JSONField(
        help_text="Vecteur d'embedding (liste de floats sérialisée). À chiffrer en prod.",
    )
    embedding_dim = models.PositiveSmallIntegerField(default=128)

    quality_score = models.FloatField(
        default=0.0,
        help_text="Score qualité de l'image source (0–1). Seuil minimal recommandé : 0.6.",
    )
    threshold = models.FloatField(
        default=0.6,
        help_text=(
            "Seuil de similarité (0–1) pour valider un match. "
            "0.40 = tolérant. 0.60 = sécurité (défaut KAYDAN). "
            "Plancher dur du service : 0.55."
        ),
    )

    source_image = models.ImageField(
        upload_to="employees/faces/", null=True, blank=True,
        help_text="Image originale chiffrée (S3/MinIO). Référence uniquement.",
    )
    enrolled_at = models.DateTimeField(auto_now_add=True)
    last_matched_at = models.DateTimeField(null=True, blank=True)
    match_count = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-enrolled_at"]
        indexes = [models.Index(fields=["employee", "is_active"])]

    def __str__(self): return f"FaceProfile<{self.employee.matricule}> ({self.embedding_model})"
