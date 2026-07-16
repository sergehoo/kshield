"""KAYDAN SHIELD — Signals automatiques sur les badges.

- AccessEvent.save → BadgeScanEvent créé + Badge.last_scan_at/scan_count mis à jour
- VisitRequest.save (mode=self_service, status=approved) → auto-attribution d'un
  badge QR depuis le pool + notification email/SMS du QR code.
- Périodiquement (Celery task à brancher) : badges valid_until expirés → status=expired.
"""
from __future__ import annotations

import logging

from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

log = logging.getLogger(__name__)


@receiver(post_save, sender="access_control.AccessEvent")
def link_access_event_to_badge(sender, instance, created, **kwargs):
    """Crée un BadgeScanEvent quand un AccessEvent est sauvegardé."""
    if not created:
        return
    if not instance.badge_uid:
        return

    from .models import Badge, BadgeScanEvent
    badge = Badge.objects.filter(uid=instance.badge_uid).first()
    if not badge:
        return

    BadgeScanEvent.objects.create(
        badge=badge,
        access_event=instance,
        timestamp=instance.timestamp,
        site=instance.site,
        decision=instance.decision,
        method=instance.method or "",
        denial_reason=instance.denial_reason or "",
    )
    # Compteur + dernière utilisation
    badge.last_scan_at = instance.timestamp
    badge.scan_count = (badge.scan_count or 0) + 1
    badge.save(update_fields=["last_scan_at", "scan_count"])


@receiver(post_save, sender="visitors.VisitRequest")
def auto_issue_visitor_badge(sender, instance, created, **kwargs):
    """Auto-attribution d'un badge QR pour les visites self-service approuvées.

    Conditions :
    - Mode = self_service
    - Status = approved
    - Pas encore de badge actif lié à cette visite
    """
    if instance.mode != "self_service" or instance.status != "approved":
        return
    from .models import Badge, BadgeAssignment

    if BadgeAssignment.objects.filter(
        holder_kind="visitor",
        holder_object_id=instance.visitor_id,
        reason=f"Visite {instance.uuid}",
        closed_at__isnull=True,
    ).exists():
        return

    badge = Badge.objects.filter(
        category="visitor_qr", status="available",
    ).order_by("issued_at").first()

    if not badge:
        log.warning("Pas de badge QR disponible dans le pool pour visite %s", instance.uuid)
        return

    try:
        from .services import BadgeWorkflowService
        holder_label = f"{instance.visitor.first_name} {instance.visitor.last_name}"
        BadgeWorkflowService.assign_qr_to_visit(badge, instance, holder_label=holder_label)
        log.info("Badge %s auto-attribué à la visite self-service %s", badge.uid, instance.uuid)
    except Exception:
        log.exception("Échec auto-attribution badge visite %s", instance.uuid)


@receiver(post_save, sender="devices.Badge")
def expire_badges_past_validity(sender, instance, created, **kwargs):
    """Met automatiquement le badge en `expired` si valid_until est dépassé."""
    if instance.valid_until and instance.valid_until < timezone.now().date():
        if instance.status not in ("expired", "revoked", "lost"):
            from .models import Badge
            # Update direct pour ne pas re-déclencher le signal
            Badge.objects.filter(pk=instance.pk).update(status="expired")
