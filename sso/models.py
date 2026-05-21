"""KAYDAN SHIELD — Modèles SSO Keycloak.

Principe : on NE remplace PAS le User local KAYDAN. On le LIE à son identité
Keycloak via `SSOIdentity.subject` (claim `sub` du JWT). Toutes les
permissions métier locales (sites, zones, RoleAssignment) restent dans
KAYDAN SHIELD — Keycloak ne fournit que l'identité globale + groupes.
"""
from __future__ import annotations

from django.conf import settings
from django.db import models


class SSOIdentity(models.Model):
    """Lien permanent entre un User local KAYDAN et son identité Keycloak.

    Une seule identité par user (unicité sur user_id ET sur subject).
    Le subject Keycloak est immuable — il identifie l'utilisateur même si
    l'email change.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="sso_identity",
    )
    subject = models.CharField(
        max_length=128, unique=True, db_index=True,
        help_text="Claim 'sub' OIDC — identifiant immuable Keycloak.",
    )
    issuer = models.CharField(
        max_length=255, default="",
        help_text="URL du realm Keycloak (claim 'iss').",
    )
    preferred_username = models.CharField(max_length=180, blank=True)
    email_verified = models.BooleanField(default=False)

    # Provenance fédération (LDAP / Entra ID / local Keycloak)
    federation_provider = models.CharField(
        max_length=80, blank=True,
        help_text="Ex: 'ldap-kaydan', 'entra-kaydan', 'local'.",
    )
    last_login_ip = models.GenericIPAddressField(null=True, blank=True)
    last_synced_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Identité SSO"
        verbose_name_plural = "Identités SSO"
        indexes = [models.Index(fields=["subject"])]

    def __str__(self):
        return f"{self.user} ↔ {self.subject[:8]}…"


class SSOSession(models.Model):
    """Trace une session OIDC active. Permet le logout global SSO."""

    STATUS = [
        ("active", "Active"),
        ("expired", "Expirée"),
        ("revoked", "Révoquée"),
        ("logged_out", "Déconnectée"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="sso_sessions",
    )
    session_state = models.CharField(
        max_length=128, db_index=True,
        help_text="Claim 'session_state' Keycloak — utilisé pour le back-channel logout.",
    )
    access_token_jti = models.CharField(max_length=128, blank=True, db_index=True)
    refresh_token_jti = models.CharField(max_length=128, blank=True)
    issued_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS, default="active")
    user_agent = models.CharField(max_length=500, blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        ordering = ["-issued_at"]
        indexes = [models.Index(fields=["session_state", "status"])]

    def __str__(self):
        return f"{self.user} · {self.status}"


class SSORoleMapping(models.Model):
    """Mappe un nom de rôle Keycloak vers un Role local KAYDAN.

    Permet à l'admin de dire : "tous les users qui ont le rôle realm
    'kaydan-supervisor' → reçoivent automatiquement le Role local 'supervisor'
    avec scope=site". Les permissions métier fines restent dans KAYDAN.
    """

    keycloak_role = models.CharField(
        max_length=120, unique=True, db_index=True,
        help_text="Nom du rôle realm ou client dans Keycloak.",
    )
    local_role = models.ForeignKey(
        "accounts.Role", on_delete=models.CASCADE,
        related_name="sso_mappings",
    )
    auto_assign_on_login = models.BooleanField(default=True)
    description = models.CharField(max_length=300, blank=True)

    class Meta:
        verbose_name = "Mapping rôle SSO"
        verbose_name_plural = "Mappings rôles SSO"

    def __str__(self):
        return f"{self.keycloak_role} → {self.local_role.code}"


class SSOLoginAudit(models.Model):
    """Audit complet de chaque login SSO (succès ou échec)."""

    EVENT_KIND = [
        ("login_success", "Login OK"),
        ("login_failure", "Login échec"),
        ("token_refresh", "Refresh token"),
        ("logout", "Logout"),
        ("token_invalid", "Token invalide"),
        ("user_disabled", "Utilisateur désactivé"),
        ("offline_login", "Login offline"),
    ]

    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="sso_audit",
    )
    subject = models.CharField(max_length=128, blank=True, db_index=True)
    email = models.EmailField(blank=True)
    kind = models.CharField(max_length=24, choices=EVENT_KIND)
    success = models.BooleanField(default=True)
    reason = models.CharField(max_length=300, blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=500, blank=True)
    site = models.ForeignKey(
        "sites.Site", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="sso_audit",
        help_text="Renseigné pour les login offline depuis une gateway.",
    )

    class Meta:
        ordering = ["-timestamp"]
        indexes = [
            models.Index(fields=["subject", "kind"]),
            models.Index(fields=["-timestamp", "kind"]),
        ]


class OfflineUserCredentialCache(models.Model):
    """Cache des utilisateurs autorisés sur une gateway, valable hors-ligne.

    Permet à une borne KAYDAN-EDGE de continuer à authentifier des agents
    de sécurité quand le serveur central est injoignable.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="offline_caches",
    )
    site = models.ForeignKey(
        "sites.Site", on_delete=models.CASCADE,
        related_name="offline_caches",
    )
    # Hash PBKDF2 d'un PIN court + salt (pour login d'urgence)
    pin_hash = models.CharField(max_length=200, blank=True)
    badge_uid = models.CharField(max_length=80, blank=True, db_index=True)
    # Hash du dernier mot de passe (cas exceptionnel, pour migration)
    password_hash = models.CharField(max_length=200, blank=True)
    permissions_snapshot = models.JSONField(
        default=list, blank=True,
        help_text="Codes de permissions valides au moment de la sync.",
    )
    is_active = models.BooleanField(default=True)
    cached_at = models.DateTimeField(auto_now=True)
    expires_at = models.DateTimeField()

    class Meta:
        verbose_name = "Cache user offline"
        verbose_name_plural = "Caches users offline"
        unique_together = ("user", "site")
        indexes = [
            models.Index(fields=["site", "is_active", "expires_at"]),
            models.Index(fields=["badge_uid", "site"]),
        ]


class EdgeSSOSyncLog(models.Model):
    """Trace les synchronisations effectuées par chaque gateway edge."""

    site = models.ForeignKey(
        "sites.Site", on_delete=models.CASCADE,
        related_name="sso_syncs",
    )
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    users_pushed = models.PositiveIntegerField(default=0)
    users_revoked = models.PositiveIntegerField(default=0)
    error_message = models.CharField(max_length=400, blank=True)
    ok = models.BooleanField(default=True)

    class Meta:
        ordering = ["-started_at"]
