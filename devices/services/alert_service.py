"""KAYDAN SHIELD — Service de gestion des alertes système.

Encapsule la persistance en DB (``SystemAlert``), la déduplication (une alerte
par ``(kind, target_id)`` non résolue), l'auto-résolution et le routing vers
les notifications email/slack pour les critiques.

Utilisation :

    AlertService.raise_alert(
        tenant=tenant, kind="agent_offline", severity="critical",
        title="Agent hors ligne", detail="...",
        target_url="/local-agents", target_id=str(agent.pk),
    )

    AlertService.resolve_alerts(
        tenant=tenant, kind="agent_offline", target_id=str(agent.pk),
    )
"""
from __future__ import annotations

import logging
from typing import Optional

from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)


class AlertService:
    """Façade pour lever, résoudre, router les alertes système."""

    # ────────────────────────────────────────────────────────────
    # Émission
    # ────────────────────────────────────────────────────────────
    @staticmethod
    @transaction.atomic
    def raise_alert(*, tenant, kind: str, severity: str,
                     title: str, detail: str = "",
                     target_url: str = "", target_id: str = "",
                     payload: Optional[dict] = None,
                     route_notifications: bool = True):
        """Crée une alerte OU update une alerte existante non résolue.

        Idempotent : appeler plusieurs fois avec la même ``(kind, target_id)``
        met à jour l'alerte existante plutôt que d'en créer une nouvelle.

        Retourne le tuple ``(alert, created)``.
        """
        from devices.models import SystemAlert

        alert, created = SystemAlert.objects.get_or_create(
            tenant=tenant, kind=kind, target_id=target_id or "",
            resolved_at__isnull=True,
            defaults={
                "severity": severity,
                "title": title[:240],
                "detail": detail[:500],
                "target_url": target_url,
                "payload": payload or {},
            },
        )
        if not created:
            # Update les champs mutables (le detail/severity peut évoluer)
            changed = False
            if alert.severity != severity:
                alert.severity = severity; changed = True
            if alert.title != title[:240]:
                alert.title = title[:240]; changed = True
            if alert.detail != detail[:500]:
                alert.detail = detail[:500]; changed = True
            if changed:
                alert.save(update_fields=["severity", "title", "detail"])

        # Routing notifications (une seule fois — cf. routed_at)
        if created and route_notifications and severity == "critical":
            try:
                AlertService._route_notification(alert)
                alert.routed_at = timezone.now()
                alert.save(update_fields=["routed_at"])
            except Exception as exc:
                logger.exception("Routing alerte %s KO : %s", alert.pk, exc)

        return alert, created

    # ────────────────────────────────────────────────────────────
    # Résolution auto
    # ────────────────────────────────────────────────────────────
    @staticmethod
    def resolve_alerts(*, tenant, kind: str, target_id: str = ""):
        """Marque comme résolues toutes les alertes matchant (kind, target_id)."""
        from devices.models import SystemAlert

        qs = SystemAlert.objects.filter(
            tenant=tenant, kind=kind, resolved_at__isnull=True,
        )
        if target_id:
            qs = qs.filter(target_id=target_id)
        count = qs.update(resolved_at=timezone.now())
        if count:
            logger.info("Résolu %d alerte(s) : %s / %s", count, kind, target_id or "*")
        return count

    @staticmethod
    def acknowledge(alert_id, user):
        """L'utilisateur reconnaît avoir vu l'alerte (ne la résout pas pour autant)."""
        from devices.models import SystemAlert
        try:
            a = SystemAlert.objects.get(pk=alert_id)
        except SystemAlert.DoesNotExist:
            return None
        a.acknowledged_at = timezone.now()
        a.acknowledged_by = user
        a.save(update_fields=["acknowledged_at", "acknowledged_by"])
        return a

    # ────────────────────────────────────────────────────────────
    # Routing notifications — email/slack via app notifications
    # ────────────────────────────────────────────────────────────
    @staticmethod
    def _route_notification(alert):
        """Émet une Notification pour les admins du tenant → email/slack via workers."""
        try:
            from notifications.services import create_notification
        except ImportError:
            # Service de notifications non exposé — utilise create() direct
            create_notification = None

        try:
            from accounts.models import User
        except Exception:
            User = None

        # Cible : tous les admins/staff du tenant
        recipients = []
        if User is not None:
            recipients = list(
                User.objects.filter(
                    tenant=alert.tenant, is_active=True,
                ).filter(
                    is_staff=True,
                )[:20],
            )
        if not recipients:
            logger.info("Aucun destinataire pour alerte critique %s", alert.pk)
            return

        title = f"[ALERTE {alert.get_severity_display().upper()}] {alert.title}"
        body = (
            f"{alert.detail}\n\n"
            f"Type : {alert.get_kind_display()}\n"
            f"Créée : {alert.created_at.strftime('%d/%m/%Y %H:%M')}\n"
            f"→ Voir : {alert.target_url or '—'}"
        )

        # Utilise la couche notifications existante si dispo, sinon fallback simple
        for user in recipients:
            try:
                if create_notification:
                    create_notification(
                        user=user, title=title, body=body,
                        category="system_alert",
                        link=alert.target_url or "",
                    )
                else:
                    _fallback_notification(user, title, body, alert)
            except Exception as exc:
                logger.warning("Notif KO pour user=%s : %s", user.pk, exc)


def _fallback_notification(user, title, body, alert):
    """Fallback si notifications.services n'expose pas create_notification.

    On utilise le modèle Notification directement s'il existe.
    """
    try:
        from notifications.models import Notification
        Notification.objects.create(
            user=user, tenant=alert.tenant,
            title=title, body=body,
            category="system_alert",
            link=alert.target_url or "",
        )
    except Exception:
        pass
