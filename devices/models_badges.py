"""KAYDAN SHIELD — Modèles cycle de vie badges (Phase 3 refonte).

Cahier des charges §3 :
  - BadgeAssignment : historique append-only des affectations de badges
  - BadgeLifecycleEvent : trace immutable des changements d'état

Un Badge peut avoir plusieurs BadgeAssignment successifs dans son cycle
de vie (ex: attribué à Alice puis Bob après démission d'Alice). Chaque
assignation est immutable une fois créée (audit RGPD).

Le badge lui-même (models.Badge) conserve un pointeur vers l'assignation
active courante via une propriété calculée ``current_assignment``.
"""
from __future__ import annotations

import uuid

from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models

from core.mixins import TimeStampedModel


# ═══════════════════════════════════════════════════════════════════
# BadgeAssignment — historique immutable des attributions
# ═══════════════════════════════════════════════════════════════════
class BadgeAssignment(models.Model):
    """Représente une période d'attribution d'un badge à un titulaire.

    Cahier des charges §3.4 :
      - Types de titulaires : employé/ouvrier/visiteur/agent/prestataire/
        véhicule/équipement/ressource
      - Champs : dates, sites, zones, horaires, jours, niveau, motif,
        attribution permanente ou temporaire, responsable de validation

    Cahier des charges §3.5 :
      - Historique complet et non modifiable

    Convention :
      - ``closed_at`` NULL      → assignation active
      - ``closed_at`` != NULL   → assignation fermée (badge rendu, expiré,
                                  révoqué, etc.)
      - Un badge ne peut avoir qu'UNE seule assignation active à la fois.
    """
    # Types alignés sur Badge.HOLDER_KIND_CHOICES
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

    # Motifs de clôture — pour audit + reporting
    CLOSE_REASON_CHOICES = [
        ("unassigned",   "Désaffecté volontairement"),
        ("expired",      "Expiré (fin de validité)"),
        ("lost",         "Perdu"),
        ("stolen",       "Volé"),
        ("suspended",    "Suspendu (temporaire)"),
        ("revoked",      "Révoqué (sanction)"),
        ("holder_left",  "Titulaire parti (démission/fin visite)"),
        ("destroyed",    "Badge détruit"),
        ("replaced",     "Remplacé par un nouveau badge"),
        ("archived",     "Archivé (RGPD)"),
    ]

    ACCESS_LEVEL_CHOICES = [
        ("none",       "Aucun (badge visiteur simple)"),
        ("basic",      "Basique"),
        ("standard",   "Standard"),
        ("elevated",   "Élevé (superviseur)"),
        ("critical",   "Critique (direction/sécurité)"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    badge = models.ForeignKey(
        "devices.Badge", on_delete=models.CASCADE, related_name="assignments",
    )
    tenant = models.ForeignKey(
        "core.Tenant", on_delete=models.CASCADE, related_name="badge_assignments",
    )

    # ─── Titulaire (GenericFK — 8 types possibles) ─────────────
    holder_kind = models.CharField(max_length=16, choices=HOLDER_KIND_CHOICES)
    holder_content_type = models.ForeignKey(
        ContentType, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="+",
    )
    holder_object_id = models.PositiveBigIntegerField(null=True, blank=True)
    holder = GenericForeignKey("holder_content_type", "holder_object_id")
    # Version textuelle du titulaire — pour affichage historique même si
    # l'objet référencé est supprimé.
    holder_label = models.CharField(
        max_length=200,
        help_text="Nom complet du titulaire au moment de l'attribution.",
    )

    # ─── Portée d'accès ────────────────────────────────────────
    site = models.ForeignKey(
        "sites.Site", null=True, blank=True, on_delete=models.PROTECT,
        related_name="badge_assignments",
        help_text="Site principal — le badge n'est actif que sur ce site.",
    )
    zones = models.ManyToManyField(
        "sites.Zone", blank=True, related_name="badge_assignments",
        help_text="Zones autorisées (vide = toutes les zones du site).",
    )
    access_level = models.CharField(
        max_length=16, choices=ACCESS_LEVEL_CHOICES, default="basic",
    )

    # ─── Restrictions temporelles ──────────────────────────────
    assigned_at = models.DateTimeField(
        auto_now_add=True, db_index=True,
        help_text="Date d'attribution (immuable).",
    )
    activated_at = models.DateTimeField(
        null=True, blank=True,
        help_text="Date à partir de laquelle le badge peut être utilisé.",
    )
    expires_at = models.DateTimeField(
        null=True, blank=True, db_index=True,
        help_text="Fin de validité — le badge passe auto en state expired.",
    )
    time_window_start = models.TimeField(
        null=True, blank=True,
        help_text="Heure de début autorisée dans la journée (ex: 06:00).",
    )
    time_window_end = models.TimeField(
        null=True, blank=True,
        help_text="Heure de fin autorisée dans la journée (ex: 22:00).",
    )
    allowed_weekdays = models.CharField(
        max_length=20, blank=True,
        help_text='Jours autorisés séparés par virgule (ex: "0,1,2,3,4" = '
                    "lun-ven, 0=lundi, 6=dimanche). Vide = tous les jours.",
    )

    # ─── Attribution ───────────────────────────────────────────
    is_permanent = models.BooleanField(
        default=False,
        help_text="True : attribution permanente sans expires_at. "
                    "False : attribution temporaire (dates obligatoires).",
    )
    reason = models.CharField(
        max_length=240, blank=True,
        help_text='Motif d\'attribution : "Mission chantier Riviera 2026-Q3", '
                    '"Visiteur ENT-CI", etc.',
    )
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="+",
        help_text="Utilisateur qui a créé l'attribution.",
    )
    validated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="+",
        help_text="Responsable qui a validé cette attribution (workflow "
                    "d'approbation pour niveaux élevés).",
    )

    # ─── Clôture ───────────────────────────────────────────────
    closed_at = models.DateTimeField(
        null=True, blank=True, db_index=True,
        help_text="NULL = active. Non-NULL = fermée.",
    )
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="+",
    )
    close_reason = models.CharField(
        max_length=16, choices=CLOSE_REASON_CHOICES, blank=True,
    )
    close_notes = models.TextField(blank=True)

    # ─── Métadonnées ───────────────────────────────────────────
    notes = models.TextField(blank=True)
    metadata = models.JSONField(
        default=dict, blank=True,
        help_text="Champs additionnels (n° véhicule, catégorie ressource, etc.)",
    )

    class Meta:
        ordering = ["-assigned_at"]
        verbose_name = "Attribution de badge"
        verbose_name_plural = "Attributions de badges"
        indexes = [
            models.Index(fields=["badge", "-assigned_at"]),
            models.Index(fields=["tenant", "-assigned_at"]),
            models.Index(fields=["holder_kind", "closed_at"]),
            models.Index(fields=["site", "closed_at"]),
            models.Index(fields=["expires_at"]),
        ]
        constraints = [
            # Un badge ne peut avoir qu'UNE assignation active (closed_at IS NULL)
            models.UniqueConstraint(
                fields=["badge"],
                condition=models.Q(closed_at__isnull=True),
                name="badge_one_active_assignment",
            ),
        ]

    def __str__(self) -> str:
        status = "active" if self.closed_at is None else "fermée"
        return f"{self.badge.uid} → {self.holder_label} ({status})"

    @property
    def is_active(self) -> bool:
        return self.closed_at is None

    def allowed_weekday_list(self) -> list[int]:
        """Parse allowed_weekdays en liste d'entiers 0-6."""
        if not self.allowed_weekdays:
            return list(range(7))   # tous les jours
        return [int(x) for x in self.allowed_weekdays.split(",") if x.strip().isdigit()]


# ═══════════════════════════════════════════════════════════════════
# BadgeLifecycleEvent — trace immutable des changements d'état
# ═══════════════════════════════════════════════════════════════════
class BadgeLifecycleEvent(models.Model):
    """Historique complet des transitions d'état d'un badge.

    Chaque changement de status (enrolling → assigned → active → suspended
    → active → lost → …) crée un événement immuable dans cette table pour
    audit RGPD + reporting.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    badge = models.ForeignKey(
        "devices.Badge", on_delete=models.CASCADE, related_name="lifecycle_events",
    )
    from_status = models.CharField(max_length=16, blank=True)
    to_status = models.CharField(max_length=16)
    reason = models.CharField(max_length=240, blank=True)
    performed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="+",
    )
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Événement cycle de vie badge"
        indexes = [
            models.Index(fields=["badge", "-created_at"]),
            models.Index(fields=["to_status", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.badge.uid} : {self.from_status} → {self.to_status}"
