"""Pipeline de traitement d'un scan — AccessGatewayService.process_scan."""
from __future__ import annotations

import logging
from datetime import date

from django.db import transaction
from django.utils import timezone

from devices.models import Badge, BadgeHelmetPairing, Device, Helmet
from employees.models import Employee
from ouvriers.models import Worker
from visitors.models import Visitor

from .models import AccessDecision, AccessEvent

logger = logging.getLogger(__name__)


class AccessGatewayService:
    """Point d'entrée unique pour les scans des terminaux."""

    @classmethod
    def process_scan(cls, payload: dict, operator=None) -> AccessEvent:
        device = Device.objects.filter(serial_number=payload["device_serial"]).first()
        site = device.site if device else None
        zone = device.zone if device else None
        checkpoint = device.checkpoint if device else None

        badge = Badge.objects.filter(uid=payload.get("badge_uid", "")).first() if payload.get("badge_uid") else None
        helmet = Helmet.objects.filter(uhf_tag_uid=payload.get("helmet_uid", "")).first() if payload.get("helmet_uid") else None

        holder = badge.holder if badge else None
        holder_kind = "unknown"
        if isinstance(holder, Employee): holder_kind = "employee"
        elif isinstance(holder, Worker): holder_kind = "worker"
        elif isinstance(holder, Visitor): holder_kind = "visitor"

        decision, reason = cls._evaluate(badge, helmet, site, holder)

        # ─── Prometheus business metric ────────────────────────
        try:
            from core.metrics import scans_total
            scans_total.labels(
                decision=decision or "unknown",
                method=payload.get("method", "nfc"),
                site=site.code if site else "unknown",
            ).inc()
        except Exception:
            pass

        event = AccessEvent.objects.create(
            timestamp=payload.get("timestamp") or timezone.now(),
            tenant_id=device.tenant_id if device else None,
            site=site,
            zone=zone,
            checkpoint=checkpoint,
            device=device,
            operator=operator,
            badge_uid=payload.get("badge_uid", ""),
            helmet_uid=payload.get("helmet_uid", ""),
            holder_kind=holder_kind,
            holder_object_id=getattr(holder, "id", None),
            direction=payload.get("direction", "in"),
            method=payload.get("method", "nfc"),
            decision=decision,
            denial_reason=reason,
            raw_payload=payload.get("raw_payload", {}),
            latitude=payload.get("latitude"),
            longitude=payload.get("longitude"),
        )
        AccessDecision.objects.create(event=event, deciding_rule_code=reason or "OK")

        # Appairage si ouvrier
        if isinstance(holder, Worker) and badge and helmet and site:
            cls._track_pairing(holder, badge, helmet, site, event.timestamp)

        # Dispatch async (anti-fraude + notifications + WS broadcast).
        # Utilise transaction.on_commit pour s'assurer que l'event est bien
        # persisté avant que le worker Celery ne le lise.
        try:
            from access_control.tasks import dispatch_access_event
            transaction.on_commit(
                lambda: dispatch_access_event.delay(event.id),
            )
        except Exception:
            logger.exception("Échec du dispatch async pour event=%s", event.id)
        return event

    @staticmethod
    def _evaluate(badge, helmet, site, holder):
        if not badge:
            return "denied", "BADGE_INCONNU"
        if badge.status != "active":
            return "denied", f"BADGE_{badge.status.upper()}"
        if isinstance(holder, Worker) and not helmet:
            return "review", "CASQUE_MANQUANT"

        # Évalue les AccessRule configurables (P0 #3)
        try:
            decision, reason = AccessGatewayService._eval_access_rules(
                badge, helmet, site, holder)
            if decision != "granted":
                return decision, reason
        except Exception:
            logger.exception("AccessRule evaluation failed")

        return "granted", ""

    @staticmethod
    def _eval_access_rules(badge, helmet, site, holder) -> tuple[str, str]:
        """Applique les règles AccessRule actives. La 1re règle violée gagne."""
        from datetime import datetime
        from django.utils import timezone

        from access_control.models import AccessRule
        if not site:
            return "granted", ""

        rules = AccessRule.objects.filter(is_active=True).filter(
            # Règle attachée au site OU règle globale (site=None)
        ).order_by("-severity")
        rules = list(rules.filter(site=site)) + list(rules.filter(site__isnull=True))

        now = timezone.localtime()
        holder_kind = "employee" if isinstance(holder, Employee) else (
            "worker" if isinstance(holder, Worker) else (
                "visitor" if isinstance(holder, Visitor) else "unknown"))

        for rule in rules:
            cond = rule.conditions or {}
            try:
                if rule.type == "time_restriction":
                    start = cond.get("start_time")
                    end = cond.get("end_time")
                    days = cond.get("days")  # liste 1-7 (lundi-dimanche), optionnel
                    if start and end:
                        s = datetime.strptime(start, "%H:%M").time()
                        e = datetime.strptime(end, "%H:%M").time()
                        cur = now.time()
                        if not (s <= cur <= e):
                            return "denied", f"OUT_OF_HOURS_{rule.code}"
                    if days and now.isoweekday() not in days:
                        return "denied", f"OUT_OF_DAYS_{rule.code}"

                elif rule.type == "zone_restriction":
                    blocked = cond.get("blocked_holder_kinds", [])
                    if holder_kind in blocked:
                        return "denied", f"ZONE_RESTRICTED_{rule.code}"

                elif rule.type == "blacklist":
                    if cond.get("badge_uids") and badge.uid in cond["badge_uids"]:
                        return "denied", f"BLACKLISTED_{rule.code}"

                elif rule.type == "certification_required":
                    if isinstance(holder, Worker):
                        required = set(cond.get("codes", []))
                        try:
                            owned = set(holder.certifications.filter(
                                expires_at__gte=timezone.now()
                            ).values_list("code", flat=True))
                        except Exception:
                            owned = set()
                        if required and not (required & owned):
                            return "denied", f"CERTIFICATION_MISSING_{rule.code}"

                elif rule.type == "capacity_limit":
                    max_inside = cond.get("max", 0)
                    if max_inside:
                        from access_control.models import AccessEvent
                        from datetime import timedelta
                        since = timezone.now() - timedelta(hours=12)
                        count_in = AccessEvent.objects.filter(
                            site=site, direction="in", decision="granted",
                            timestamp__gte=since,
                        ).count()
                        if count_in >= max_inside:
                            return "review", f"CAPACITY_REACHED_{rule.code}"
            except Exception:
                logger.exception("AccessRule %s eval failed", rule.code)
                continue

        return "granted", ""

    @staticmethod
    def _track_pairing(worker, badge, helmet, site, timestamp):
        today = (timestamp or timezone.now()).date()
        pairing, created = BadgeHelmetPairing.objects.get_or_create(
            worker=worker, pairing_date=today, site=site,
            defaults={
                "badge": badge,
                "helmet": helmet,
                "first_scan_at": timestamp,
                "last_verified_at": timestamp,
                "verifications_count": 1,
            },
        )
        if not created:
            mismatch = pairing.badge_id != badge.id or pairing.helmet_id != helmet.id
            if mismatch:
                pairing.is_broken = True
                pairing.broken_reason = "Appairage soir ≠ matin"
            pairing.last_verified_at = timestamp
            pairing.verifications_count += 1
            pairing.save()
