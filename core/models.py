"""KAYDAN SHIELD — core: Tenant, Company, abstracts, FeatureFlag."""
from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


# ---------------------------------------------------------------------------
# Abstract bases
# ---------------------------------------------------------------------------
class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="+",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="+",
    )

    class Meta:
        abstract = True


class SoftDeleteQuerySet(models.QuerySet):
    """QuerySet helper avec `.alive()` pour filtrer les enregistrements vivants."""
    def alive(self):
        return self.filter(is_deleted=False)


class SoftDeleteModel(models.Model):
    """Mixin abstrait pour les modèles RGPD-sensibles.

    À appliquer sur Visitor, Employee, Worker, Helmet quand on a besoin de
    conserver l'historique sans exposer les données — le `soft_delete()`
    bascule juste un flag, ce qui préserve les ForeignKey existantes
    (AccessEvent, BadgeAssignment, etc.) sans CASCADE destructive.

    Pas encore appliqué : déclencher une migration coordonnée par modèle
    qui ajoute les 3 champs + remplace `objects` par `SoftDeleteQuerySet`.
    Voir docs/SOFT_DELETE_PLAN.md (à rédiger) avant adoption.
    """
    is_deleted = models.BooleanField(default=False, db_index=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    deleted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="+",
    )

    objects = SoftDeleteQuerySet.as_manager()

    class Meta:
        abstract = True

    def soft_delete(self, user=None):
        from django.utils import timezone
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.deleted_by = user
        self.save(update_fields=["is_deleted", "deleted_at", "deleted_by"])

    def restore(self):
        self.is_deleted = False
        self.deleted_at = None
        self.deleted_by = None
        self.save(update_fields=["is_deleted", "deleted_at", "deleted_by"])


class UUIDModel(models.Model):
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, db_index=True)

    class Meta:
        abstract = True


# ---------------------------------------------------------------------------
# Tenant / Company
# ---------------------------------------------------------------------------
class Tenant(UUIDModel, TimeStampedModel):
    name = models.CharField(max_length=180)
    code = models.SlugField(max_length=40, unique=True)
    logo = models.ImageField(upload_to="tenants/logos/", null=True, blank=True)
    timezone = models.CharField(max_length=64, default="Africa/Abidjan")
    currency = models.CharField(max_length=8, default="XOF")
    is_active = models.BooleanField(default=True)
    settings = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self): return self.name


class Company(UUIDModel, TimeStampedModel):
    SECTOR_CHOICES = [
        ("btp", "BTP / Construction"), ("logistics", "Logistique"),
        ("industry", "Industrie"), ("services", "Services"),
        ("trading", "Commerce"), ("other", "Autre"),
    ]
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="companies")
    name = models.CharField(max_length=180)
    code = models.SlugField(max_length=40)
    legal_name = models.CharField(max_length=240, blank=True)
    tax_id = models.CharField("IFU / N° fiscal", max_length=40, blank=True)
    sector = models.CharField(max_length=24, choices=SECTOR_CHOICES, default="services")
    contact_name = models.CharField(max_length=180, blank=True)
    contact_email = models.EmailField(blank=True)
    contact_phone = models.CharField(max_length=32, blank=True)
    is_active = models.BooleanField(default=True)
    logo = models.ImageField(
        upload_to="companies/logos/", null=True, blank=True,
        help_text="Logo de la filiale (imprimé sur les badges employés).",
    )

    class Meta:
        unique_together = ("tenant", "code")
        ordering = ["name"]

    def __str__(self): return self.name


class Address(TimeStampedModel):
    line1 = models.CharField(max_length=240)
    line2 = models.CharField(max_length=240, blank=True)
    city = models.CharField(max_length=120, blank=True)
    region = models.CharField(max_length=120, blank=True)
    country = models.CharField(max_length=64, default="Côte d'Ivoire")
    postal_code = models.CharField(max_length=20, blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)

    def __str__(self): return f"{self.line1}, {self.city}"


class FeatureFlag(TimeStampedModel):
    tenant = models.ForeignKey(
        Tenant, on_delete=models.CASCADE, related_name="feature_flags",
        null=True, blank=True, help_text="null = flag global",
    )
    code = models.SlugField(max_length=80)
    is_enabled = models.BooleanField(default=False)
    description = models.TextField(blank=True)
    payload = models.JSONField(default=dict, blank=True)

    class Meta:
        unique_together = ("tenant", "code")
        ordering = ["code"]

    def __str__(self):
        scope = self.tenant.code if self.tenant_id else "global"
        return f"{self.code} ({scope}) → {'ON' if self.is_enabled else 'OFF'}"


# ---------------------------------------------------------------------------
# Edge / SiteGateway — mini-serveur Django local sur chaque chantier
# ---------------------------------------------------------------------------
class SiteGateway(UUIDModel, TimeStampedModel):
    """Passerelle locale (Mini-PC / Raspberry Pi / NUC) installée sur un site.

    Sert l'API LAN aux terminaux RFID/NFC en mode offline puis synchronise
    avec le serveur central dès le retour de connexion.
    """

    HARDWARE_CHOICES = [
        ("rpi", "Raspberry Pi"),
        ("nuc", "Intel NUC"),
        ("mini_pc", "Mini-PC"),
        ("edge_box", "Edge Box (industriel)"),
        ("vm", "Machine virtuelle"),
    ]
    STATUS_CHOICES = [
        ("active", "Actif"),
        ("offline", "Hors ligne"),
        ("syncing", "Synchronisation"),
        ("error", "Erreur"),
        ("decommissioned", "Mis hors service"),
    ]

    tenant = models.ForeignKey(
        Tenant, on_delete=models.CASCADE, related_name="gateways",
    )
    site = models.OneToOneField(
        "sites.Site", on_delete=models.CASCADE, related_name="gateway",
    )
    name = models.CharField(max_length=180)
    code = models.SlugField(max_length=40)
    hardware = models.CharField(max_length=16, choices=HARDWARE_CHOICES, default="mini_pc")
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="active")

    # Réseau
    lan_ip = models.GenericIPAddressField(null=True, blank=True)
    public_ip = models.GenericIPAddressField(null=True, blank=True)
    vpn_endpoint = models.CharField(max_length=240, blank=True)
    api_port = models.PositiveSmallIntegerField(default=8080)

    # Identification
    serial_number = models.CharField(max_length=120, blank=True, db_index=True)
    mac_address = models.CharField(max_length=20, blank=True)
    os_version = models.CharField(max_length=80, blank=True)
    kshield_version = models.CharField(max_length=40, blank=True)

    # Synchronisation
    last_sync_at = models.DateTimeField(null=True, blank=True)
    last_heartbeat_at = models.DateTimeField(null=True, blank=True)
    sync_pending_count = models.PositiveIntegerField(default=0)

    # Sécurité
    api_secret_hash = models.CharField(max_length=128, blank=True)
    is_active = models.BooleanField(default=True)

    notes = models.TextField(blank=True)

    class Meta:
        unique_together = ("tenant", "code")
        ordering = ["name"]
        verbose_name = "Gateway locale"
        verbose_name_plural = "Gateways locales"

    def __str__(self): return f"Gateway {self.code} @ {self.site.name}"
