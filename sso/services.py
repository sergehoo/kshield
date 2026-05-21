"""Services SSO — provisioning user, role mapping, sync edge."""
from __future__ import annotations

import logging
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils import timezone

logger = logging.getLogger(__name__)
User = get_user_model()


def get_or_create_user_from_claims(claims: dict) -> tuple:
    """Crée ou met à jour un User local KAYDAN à partir des claims OIDC.

    Stratégie de matching :
    1. SSOIdentity.subject (claim 'sub') — match prioritaire car immuable
    2. User.email (case-insensitive) — fallback pour les users créés avant SSO
    3. Création nouvelle si SSO_AUTO_CREATE_USER=True

    Retourne (user, created, identity).
    """
    from sso.models import SSOIdentity
    from sso.utils import extract_user_claims

    data = extract_user_claims(claims) if "sub" in claims else claims
    subject = data.get("subject")
    email = (data.get("email") or "").lower()

    if not subject:
        raise ValueError("Claim 'sub' manquant dans le token OIDC")

    # 1. Lookup par subject
    identity = SSOIdentity.objects.filter(subject=subject).select_related("user").first()
    if identity:
        user = identity.user
    elif email:
        # 2. Match par email — pour les users créés avant l'activation SSO
        user = User.objects.filter(email__iexact=email).first()
    else:
        user = None

    created = False
    if user is None:
        if not getattr(settings, "SSO_AUTO_CREATE_USER", True):
            raise PermissionError(
                f"Utilisateur {email or subject} inconnu et auto-création désactivée."
            )
        user = User.objects.create(
            email=email or f"{subject}@sso.kaydan.local",
            first_name=data.get("first_name", ""),
            last_name=data.get("last_name", ""),
            is_active=True,
        )
        # Pas de mot de passe local — login obligatoire via SSO
        user.set_unusable_password()
        user.save()
        created = True

    if not user.is_active:
        raise PermissionError(f"Utilisateur {user.email} désactivé.")

    # Met à jour les attributs depuis Keycloak (sauf si user superuser local)
    changed = False
    if not user.is_superuser:
        for attr, val in (
            ("first_name", data.get("first_name", "")),
            ("last_name", data.get("last_name", "")),
        ):
            if val and getattr(user, attr) != val:
                setattr(user, attr, val)
                changed = True
    if changed:
        user.save(update_fields=["first_name", "last_name"])

    # Lien permanent SSOIdentity
    if identity is None:
        identity, _ = SSOIdentity.objects.update_or_create(
            user=user,
            defaults={
                "subject": subject,
                "issuer": data.get("issuer", ""),
                "preferred_username": data.get("preferred_username", ""),
                "email_verified": data.get("email_verified", False),
                "federation_provider": data.get("federation", ""),
                "last_synced_at": timezone.now(),
            },
        )
    else:
        SSOIdentity.objects.filter(pk=identity.pk).update(
            preferred_username=data.get("preferred_username", ""),
            email_verified=data.get("email_verified", False),
            last_synced_at=timezone.now(),
        )

    # Synchro des rôles globaux Keycloak → RoleAssignment locaux
    if getattr(settings, "SSO_SYNC_ROLES", True):
        sync_user_roles(user, data.get("realm_roles", []) + data.get("client_roles", []))

    # Invalide le cache RBAC
    try:
        from accounts.rbac import invalidate_user_perms
        invalidate_user_perms(user.pk)
    except Exception:
        logger.warning("Invalidation cache RBAC échouée pour user=%s", user.pk, exc_info=True)

    return user, created, identity


def sync_user_roles(user, keycloak_roles: list[str]) -> int:
    """Applique les SSORoleMapping pour aligner les rôles locaux."""
    from accounts.models import RoleAssignment
    from sso.models import SSORoleMapping

    target_role_ids = set(SSORoleMapping.objects.filter(
        keycloak_role__in=keycloak_roles, auto_assign_on_login=True,
    ).values_list("local_role_id", flat=True))

    current = set(RoleAssignment.objects.filter(
        user=user, granted_by_sso=True if hasattr(RoleAssignment, "granted_by_sso") else None,
    ).values_list("role_id", flat=True)) if False else set(
        RoleAssignment.objects.filter(user=user).values_list("role_id", flat=True)
    )

    # Ajoute les nouveaux
    added = 0
    for rid in target_role_ids - current:
        try:
            RoleAssignment.objects.get_or_create(user=user, role_id=rid, site=None)
            added += 1
        except Exception:
            logger.exception("RoleAssignment failed for user=%s role=%s", user.pk, rid)
    return added


def revoke_session(session_state: str, reason: str = "logout"):
    """Marque la session SSO comme révoquée (back-channel logout Keycloak)."""
    from sso.models import SSOSession
    SSOSession.objects.filter(
        session_state=session_state, status="active",
    ).update(status="logged_out", revoked_at=timezone.now())


# ─── Synchronisation edge / offline ─────────────────────────────────────
def sync_users_to_edge(site, ttl_hours: int | None = None) -> dict:
    """Pousse vers le cache offline d'un site les users autorisés à y accéder.

    Sont éligibles : tous les User actifs ayant une RoleAssignment soit
    globale (site=None) soit ciblant ce site précis.
    """
    from accounts.models import RoleAssignment
    from accounts.rbac import user_permissions
    from sso.models import EdgeSSOSyncLog, OfflineUserCredentialCache

    ttl = ttl_hours or int(getattr(settings, "KAYDAN_SHIELD", {}).get(
        "SSO_OFFLINE_CACHE_TTL_HOURS", 24))
    expires_at = timezone.now() + timedelta(hours=ttl)

    log = EdgeSSOSyncLog.objects.create(site=site)
    pushed, revoked = 0, 0
    try:
        eligible_user_ids = set(
            RoleAssignment.objects.filter(
                user__is_active=True,
            ).filter(
                models_Q := __import__("django.db.models", fromlist=["Q"]).Q(site=site)
                | __import__("django.db.models", fromlist=["Q"]).Q(site__isnull=True),
            ).values_list("user_id", flat=True).distinct()
        )

        # Pour chaque user éligible, met à jour ou crée le cache
        from django.contrib.auth import get_user_model as _gu
        for user in _gu().objects.filter(id__in=eligible_user_ids):
            perms = list(user_permissions(user) or [])
            OfflineUserCredentialCache.objects.update_or_create(
                user=user, site=site,
                defaults={
                    "is_active": True,
                    "permissions_snapshot": perms,
                    "expires_at": expires_at,
                    "password_hash": user.password,  # hash bcrypt déjà
                },
            )
            pushed += 1

        # Désactive les caches des users qui n'ont plus de droit
        revoked = OfflineUserCredentialCache.objects.filter(
            site=site, is_active=True,
        ).exclude(user_id__in=eligible_user_ids).update(is_active=False)

        log.users_pushed = pushed
        log.users_revoked = revoked
        log.finished_at = timezone.now()
        log.save(update_fields=["users_pushed", "users_revoked", "finished_at"])
    except Exception as exc:
        log.ok = False
        log.error_message = str(exc)[:400]
        log.finished_at = timezone.now()
        log.save(update_fields=["ok", "error_message", "finished_at"])
        raise

    return {"pushed": pushed, "revoked": revoked, "expires_at": expires_at}
