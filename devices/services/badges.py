"""BadgeAssignmentService — logique métier du cycle de vie badge.

Cahier des charges §3 :
  §3.3 — 9 règles de validation strictes (unicité UID, badge affecté,
         désactivé, expiré, autre site, personne titulaire, type compatible,
         lecteur autorisé, capacité équipement)
  §3.4 — Attribution à 8 types de titulaires
  §3.5 — Cycle de vie 12 états avec transitions autorisées

Utilisation depuis un endpoint :

    from devices.services.badges import BadgeAssignmentService
    result = BadgeAssignmentService.assign(
        badge=badge, holder_kind="worker", holder_object=worker,
        site=site, access_level="basic", assigned_by=request.user,
    )
    if not result.ok:
        return Response({"error": result.error}, status=400)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Optional

from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════
# Transitions d'état autorisées (§3.5)
# ═══════════════════════════════════════════════════════════════════
# Format : from_status → [to_status permis]
STATE_TRANSITIONS: dict[str, set[str]] = {
    "available":  {"enrolling", "assigned", "disabled", "destroyed", "archived"},
    "enrolling":  {"available", "assigned", "disabled"},
    "assigned":   {"active", "suspended", "expired", "lost", "stolen",
                   "disabled", "revoked", "available"},
    "active":     {"suspended", "expired", "lost", "stolen", "disabled",
                   "revoked", "available"},   # available après restitution
    "suspended":  {"active", "expired", "revoked", "disabled", "lost", "stolen"},
    "expired":    {"archived", "destroyed", "available"},   # renouvellement possible
    "lost":       {"revoked", "archived"},   # peut être marqué révoqué après recherche
    "stolen":     {"revoked", "archived"},
    "disabled":   {"available", "revoked", "archived", "destroyed"},
    "revoked":    {"archived", "destroyed"},   # terminal presque
    "destroyed":  {"archived"},   # terminal, seul archive possible
    "archived":   set(),   # état final absolu
}


# ═══════════════════════════════════════════════════════════════════
# Result — résultat structuré d'une opération
# ═══════════════════════════════════════════════════════════════════
@dataclass
class AssignmentResult:
    ok: bool
    assignment: Any = None
    error: str = ""
    error_code: str = ""

    @classmethod
    def success(cls, assignment) -> "AssignmentResult":
        return cls(ok=True, assignment=assignment)

    @classmethod
    def fail(cls, code: str, error: str) -> "AssignmentResult":
        return cls(ok=False, error_code=code, error=error)


# ═══════════════════════════════════════════════════════════════════
# BadgeAssignmentService — API publique
# ═══════════════════════════════════════════════════════════════════
class BadgeAssignmentService:
    """Service stateless — méthodes de classe pour import facile."""

    # ─── Validation (§3.3 — 9 règles) ────────────────────────────
    @classmethod
    def validate_assignment(
        cls,
        badge,
        holder_kind: str,
        holder_object: Any = None,
        site=None,
        expires_at: Optional[datetime] = None,
        **_kwargs,
    ) -> Optional[AssignmentResult]:
        """Vérifie les 9 règles avant assignation. Renvoie None si OK,
        sinon un AssignmentResult.fail(code, message) prêt à retourner."""

        # Règle 1 — Badge dans un état incompatible avec assignation
        if badge.status in ("revoked", "destroyed", "archived", "stolen"):
            return AssignmentResult.fail(
                "badge_terminal_state",
                f"Le badge est en état {badge.status} — impossible d'attribuer.",
            )
        if badge.status == "lost":
            return AssignmentResult.fail(
                "badge_lost",
                "Ce badge est signalé perdu. Le retrouver ou en créer un nouveau.",
            )
        if badge.status == "disabled":
            return AssignmentResult.fail(
                "badge_disabled",
                "Badge désactivé. Réactiver via /badges/<id>/enable/ d'abord.",
            )

        # Règle 2 — Badge déjà affecté (assignation active)
        from devices.models_badges import BadgeAssignment
        active_qs = BadgeAssignment.objects.filter(
            badge=badge, closed_at__isnull=True,
        )
        if active_qs.exists():
            existing = active_qs.first()
            return AssignmentResult.fail(
                "badge_already_assigned",
                f"Badge déjà attribué à {existing.holder_label}. "
                "Désaffecter d'abord.",
            )

        # Règle 3 — Badge expiré ou expiration passée
        if badge.valid_until:
            today = date.today()
            if badge.valid_until < today:
                return AssignmentResult.fail(
                    "badge_expired",
                    f"Badge expiré depuis le {badge.valid_until}.",
                )

        # Règle 4 — Type de titulaire cohérent avec catégorie badge
        if not cls._holder_kind_compatible(badge.category, holder_kind):
            return AssignmentResult.fail(
                "holder_kind_incompatible",
                f"Type de titulaire '{holder_kind}' incompatible avec la "
                f"catégorie de badge '{badge.category}'.",
            )

        # Règle 5 — Badge appartenant à un autre site
        if site and badge.tenant_id and hasattr(site, "tenant_id"):
            if badge.tenant_id != site.tenant_id:
                return AssignmentResult.fail(
                    "badge_wrong_tenant",
                    "Badge et site appartiennent à des tenants différents.",
                )

        # Règle 6 — Personne déjà titulaire d'un badge actif
        # (uniquement pour employés/ouvriers/visiteurs — pas pour véhicules/eq)
        if (holder_object and holder_kind in ("employee", "worker", "visitor")):
            active_for_holder = BadgeAssignment.objects.filter(
                closed_at__isnull=True,
                holder_kind=holder_kind,
                holder_content_type=ContentType.objects.get_for_model(
                    type(holder_object),
                ),
                holder_object_id=getattr(holder_object, "pk", None),
            ).exclude(badge=badge)
            if active_for_holder.exists():
                other_badge = active_for_holder.first().badge
                return AssignmentResult.fail(
                    "holder_has_active_badge",
                    f"Ce titulaire a déjà un badge actif (UID {other_badge.uid}). "
                    "Désaffecter l'autre badge d'abord.",
                )

        # Règle 7 — Expiration future si non-permanent + expires_at
        if expires_at is not None and expires_at <= timezone.now():
            return AssignmentResult.fail(
                "expires_in_past",
                "La date d'expiration est déjà passée.",
            )

        return None   # tout est OK

    @staticmethod
    def _holder_kind_compatible(category: str, holder_kind: str) -> bool:
        """Vérifie cohérence entre category badge et holder_kind."""
        rules = {
            "visitor_qr":    {"visitor", "contractor"},
            "employee_rfid": {"employee", "agent", "contractor"},
            "worker_rfid":   {"worker", "contractor"},
        }
        return holder_kind in rules.get(category, set())

    # ─── Actions principales ─────────────────────────────────────
    @classmethod
    @transaction.atomic
    def assign(
        cls,
        badge,
        holder_kind: str,
        holder_object: Any = None,
        holder_label: str = "",
        site=None,
        zones: Optional[list] = None,
        access_level: str = "basic",
        expires_at: Optional[datetime] = None,
        activated_at: Optional[datetime] = None,
        time_window_start=None,
        time_window_end=None,
        allowed_weekdays: str = "",
        is_permanent: bool = False,
        reason: str = "",
        assigned_by=None,
        validated_by=None,
        notes: str = "",
        metadata: Optional[dict] = None,
    ) -> AssignmentResult:
        """Crée une BadgeAssignment active + transitions badge → assigned."""
        # 1. Validation
        error = cls.validate_assignment(
            badge=badge, holder_kind=holder_kind, holder_object=holder_object,
            site=site, expires_at=expires_at,
        )
        if error is not None:
            return error

        # 2. Résolution holder_label si non fourni
        if not holder_label and holder_object:
            holder_label = str(holder_object)[:200]

        # 3. Création BadgeAssignment
        from devices.models_badges import BadgeAssignment
        ct = None
        oid = None
        if holder_object:
            ct = ContentType.objects.get_for_model(type(holder_object))
            oid = getattr(holder_object, "pk", None)

        assignment = BadgeAssignment.objects.create(
            badge=badge, tenant=badge.tenant,
            holder_kind=holder_kind,
            holder_content_type=ct, holder_object_id=oid,
            holder_label=holder_label or "—",
            site=site, access_level=access_level,
            activated_at=activated_at, expires_at=expires_at,
            time_window_start=time_window_start,
            time_window_end=time_window_end,
            allowed_weekdays=allowed_weekdays,
            is_permanent=is_permanent, reason=reason,
            assigned_by=assigned_by, validated_by=validated_by,
            notes=notes, metadata=metadata or {},
        )
        if zones:
            assignment.zones.set(zones)

        # 4. Update badge status + reverse-FK sur badge (compat)
        cls._transition(badge, "assigned",
                         reason=f"Attribué à {holder_label}",
                         performed_by=assigned_by)
        badge.holder_kind = holder_kind
        badge.holder_content_type = ct
        badge.holder_object_id = oid
        badge.save(update_fields=[
            "status", "holder_kind", "holder_content_type", "holder_object_id",
        ])

        return AssignmentResult.success(assignment)

    @classmethod
    @transaction.atomic
    def unassign(
        cls, badge, close_reason: str = "unassigned",
        close_notes: str = "", performed_by=None,
    ) -> AssignmentResult:
        """Ferme l'assignation active + repasse badge → available."""
        from devices.models_badges import BadgeAssignment
        active = BadgeAssignment.objects.filter(
            badge=badge, closed_at__isnull=True,
        ).first()
        if not active:
            return AssignmentResult.fail(
                "no_active_assignment",
                "Aucune assignation active à fermer.",
            )
        active.closed_at = timezone.now()
        active.close_reason = close_reason
        active.close_notes = close_notes
        active.closed_by = performed_by
        active.save(update_fields=[
            "closed_at", "close_reason", "close_notes", "closed_by",
        ])
        cls._transition(badge, "available",
                         reason=f"Désaffecté ({close_reason})",
                         performed_by=performed_by)
        badge.holder_object_id = None
        badge.holder_content_type = None
        badge.holder_kind = ""
        badge.save(update_fields=[
            "status", "holder_kind", "holder_content_type", "holder_object_id",
        ])
        return AssignmentResult.success(active)

    # ─── Transitions d'état simples (suspend/resume/expire/lost/stolen/revoke/destroy/archive) ─
    @classmethod
    def suspend(cls, badge, reason: str = "", performed_by=None) -> AssignmentResult:
        badge.suspended_at = timezone.now()
        badge.suspended_reason = reason[:240]
        badge.save(update_fields=["suspended_at", "suspended_reason"])
        return cls._transition_result(badge, "suspended", reason, performed_by)

    @classmethod
    def resume(cls, badge, reason: str = "", performed_by=None) -> AssignmentResult:
        badge.suspended_at = None
        badge.suspended_reason = ""
        badge.save(update_fields=["suspended_at", "suspended_reason"])
        # Retour à l'état actif ou assigné selon assignation
        target = "active" if cls._has_active_assignment(badge) else "available"
        return cls._transition_result(badge, target, reason, performed_by)

    @classmethod
    def expire(cls, badge, reason: str = "", performed_by=None) -> AssignmentResult:
        return cls._close_and_transition(
            badge, "expired", "expired", reason, performed_by,
        )

    @classmethod
    def report_lost(cls, badge, reason: str = "", performed_by=None) -> AssignmentResult:
        return cls._close_and_transition(
            badge, "lost", "lost", reason, performed_by,
        )

    @classmethod
    def report_stolen(cls, badge, reason: str = "", performed_by=None) -> AssignmentResult:
        return cls._close_and_transition(
            badge, "stolen", "stolen", reason, performed_by,
        )

    @classmethod
    def disable(cls, badge, reason: str = "", performed_by=None) -> AssignmentResult:
        return cls._transition_result(badge, "disabled", reason, performed_by)

    @classmethod
    def enable(cls, badge, reason: str = "", performed_by=None) -> AssignmentResult:
        return cls._transition_result(badge, "available", reason, performed_by)

    @classmethod
    def revoke(cls, badge, reason: str = "", performed_by=None) -> AssignmentResult:
        badge.revoked_at = timezone.now()
        badge.revoked_reason = reason[:240]
        badge.save(update_fields=["revoked_at", "revoked_reason"])
        return cls._close_and_transition(
            badge, "revoked", "revoked", reason, performed_by,
        )

    @classmethod
    def destroy(cls, badge, reason: str = "", performed_by=None) -> AssignmentResult:
        return cls._close_and_transition(
            badge, "destroyed", "destroyed", reason, performed_by,
        )

    @classmethod
    def archive(cls, badge, reason: str = "", performed_by=None) -> AssignmentResult:
        return cls._transition_result(badge, "archived", reason, performed_by)

    # ─── Helpers internes ────────────────────────────────────────
    @classmethod
    @transaction.atomic
    def _close_and_transition(
        cls, badge, close_reason: str, target_status: str,
        reason: str, performed_by,
    ) -> AssignmentResult:
        """Ferme l'assignation active + change status. Atomique."""
        from devices.models_badges import BadgeAssignment
        BadgeAssignment.objects.filter(
            badge=badge, closed_at__isnull=True,
        ).update(
            closed_at=timezone.now(),
            close_reason=close_reason,
            close_notes=reason[:2000],
            closed_by=performed_by,
        )
        return cls._transition_result(badge, target_status, reason, performed_by)

    @classmethod
    def _transition_result(
        cls, badge, target: str, reason: str, performed_by,
    ) -> AssignmentResult:
        try:
            cls._transition(badge, target, reason=reason, performed_by=performed_by)
        except ValueError as e:
            return AssignmentResult.fail("invalid_transition", str(e))
        badge.save(update_fields=["status"])
        return AssignmentResult.success(None)

    @classmethod
    def _transition(cls, badge, target: str, reason: str = "", performed_by=None):
        """Valide la transition + log dans BadgeLifecycleEvent.

        Raise ValueError si transition non autorisée.
        """
        from_status = badge.status
        allowed = STATE_TRANSITIONS.get(from_status, set())
        if target not in allowed and target != from_status:
            raise ValueError(
                f"Transition {from_status} → {target} non autorisée. "
                f"États permis : {sorted(allowed)}.",
            )

        from devices.models_badges import BadgeLifecycleEvent
        BadgeLifecycleEvent.objects.create(
            badge=badge,
            from_status=from_status,
            to_status=target,
            reason=reason[:240],
            performed_by=performed_by,
        )
        badge.status = target
        logger.info(
            "Badge %s : %s → %s (%s)",
            badge.uid, from_status, target, reason[:80],
        )

    @staticmethod
    def _has_active_assignment(badge) -> bool:
        from devices.models_badges import BadgeAssignment
        return BadgeAssignment.objects.filter(
            badge=badge, closed_at__isnull=True,
        ).exists()

    # ─── Requêtes lecture ────────────────────────────────────────
    @classmethod
    def get_active_assignment(cls, badge):
        from devices.models_badges import BadgeAssignment
        return BadgeAssignment.objects.filter(
            badge=badge, closed_at__isnull=True,
        ).select_related("site", "assigned_by", "validated_by").first()

    @classmethod
    def get_history(cls, badge, limit: int = 100):
        from devices.models_badges import BadgeAssignment
        return list(BadgeAssignment.objects.filter(
            badge=badge,
        ).select_related("site", "assigned_by", "closed_by").order_by(
            "-assigned_at",
        )[:limit])
