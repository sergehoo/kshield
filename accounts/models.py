"""KAYDAN SHIELD — accounts: User, Role, RBAC, APIKey."""
from __future__ import annotations

import secrets
import uuid

from django.conf import settings
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models


# ---------------------------------------------------------------------------
# User
# ---------------------------------------------------------------------------
class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError("L'email est obligatoire")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        return self._create_user(email, password, **extra_fields)


class User(AbstractUser):
    """Utilisateur KAYDAN — email comme identifiant principal."""

    username = None  # remplacé par email
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    email = models.EmailField(unique=True, db_index=True)
    phone = models.CharField(max_length=32, blank=True)
    photo = models.ImageField(upload_to="users/", null=True, blank=True)

    tenant = models.ForeignKey(
        "core.Tenant", on_delete=models.PROTECT,
        related_name="users", null=True, blank=True,
    )
    company = models.ForeignKey(
        "core.Company", on_delete=models.SET_NULL,
        related_name="users", null=True, blank=True,
    )

    # MFA
    mfa_enabled = models.BooleanField(default=False)
    mfa_secret = models.CharField(max_length=64, blank=True)

    # Sécurité
    last_ip = models.GenericIPAddressField(null=True, blank=True)
    failed_login_count = models.PositiveSmallIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = UserManager()

    class Meta:
        ordering = ["last_name", "first_name"]

    def __str__(self): return self.email


# ---------------------------------------------------------------------------
# Roles & permissions
# ---------------------------------------------------------------------------
class Role(models.Model):
    """Rôle métier (distinct des Groups Django)."""

    SCOPE_CHOICES = [
        ("global", "Global"),
        ("tenant", "Tenant"),
        ("site", "Site"),
    ]

    code = models.SlugField(max_length=64, unique=True)
    name = models.CharField(max_length=120)
    scope = models.CharField(max_length=16, choices=SCOPE_CHOICES, default="tenant")
    description = models.TextField(blank=True)
    is_system = models.BooleanField(default=False, help_text="Rôle livré par défaut, non supprimable")

    class Meta:
        ordering = ["name"]

    def __str__(self): return self.name


class RolePermission(models.Model):
    """Permission granulaire portée par un rôle (ex: 'antifraud.acknowledge_alert')."""

    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name="permissions")
    code = models.SlugField(max_length=120)

    class Meta:
        unique_together = ("role", "code")

    def __str__(self): return f"{self.role.code}:{self.code}"


class RoleAssignment(models.Model):
    """Affectation d'un rôle à un utilisateur (avec scope optionnel sur un site)."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="role_assignments")
    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name="assignments")
    site = models.ForeignKey(
        "sites.Site", null=True, blank=True,
        on_delete=models.CASCADE, related_name="role_assignments",
    )
    granted_at = models.DateTimeField(auto_now_add=True)
    granted_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
    )

    class Meta:
        unique_together = ("user", "role", "site")

    def __str__(self):
        scope = f"@{self.site}" if self.site_id else ""
        return f"{self.user} → {self.role}{scope}"


# ---------------------------------------------------------------------------
# Sécurité
# ---------------------------------------------------------------------------
class UserSession(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="sessions")
    session_key = models.CharField(max_length=64, unique=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=512, blank=True)
    device_fingerprint = models.CharField(max_length=128, blank=True)
    started_at = models.DateTimeField(auto_now_add=True)
    last_activity_at = models.DateTimeField(auto_now=True)
    revoked_at = models.DateTimeField(null=True, blank=True)


class LoginAttempt(models.Model):
    email = models.EmailField()
    ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=512, blank=True)
    success = models.BooleanField(default=False)
    reason = models.CharField(max_length=120, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]


class APIKey(models.Model):
    """Clé API pour les terminaux fixes / passerelles IoT (HMAC)."""

    SCOPE_CHOICES = [
        ("device_terminal", "Terminal IoT"),
        ("mobile_pda", "PDA mobile"),
        ("integration", "Intégration tierce"),
    ]

    name = models.CharField(max_length=120)
    scope = models.CharField(max_length=24, choices=SCOPE_CHOICES, default="device_terminal")
    tenant = models.ForeignKey(
        "core.Tenant", on_delete=models.CASCADE, related_name="api_keys",
        null=True, blank=True,
    )
    site = models.ForeignKey(
        "sites.Site", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="api_keys",
    )
    public_id = models.CharField(max_length=32, unique=True, db_index=True)
    secret_hash = models.CharField(max_length=128)
    is_active = models.BooleanField(default=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    @staticmethod
    def generate_secret() -> str:
        return secrets.token_urlsafe(48)

    def __str__(self): return f"{self.name} ({self.public_id})"
