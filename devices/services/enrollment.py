"""KAYDAN SHIELD — orchestration des sessions d'enrôlement RFID temps réel.

Un opérateur ouvre une session (unitaire ou bulk), le service :
  1. Crée le RFIDEnrollmentSession en DB
  2. Émet une commande START_RFID_ENROLLMENT vers le lecteur (ou tous les lecteurs)
  3. À chaque UID reçu (via /scan/inbox POST ou via WS agent), appelle ``ingest_scan``
  4. ``ingest_scan`` détecte duplicatas et émet des événements Channels
  5. L'opérateur confirme via ``confirm_enrollment`` → création du Badge

Le service est indépendant du transport (WS, HTTP polling, ADMS). Il est
uniquement piloté par les vues DRF ou les webhooks.
"""
from __future__ import annotations

import logging
from typing import Optional

from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.utils import timezone

from ..utils import resolve_tenant

logger = logging.getLogger(__name__)


class EnrollmentError(Exception):
    """Erreur métier levée par le service (session invalide, badge en conflit, etc.)."""

    def __init__(self, message: str, code: str = "enrollment_error"):
        super().__init__(message)
        self.code = code
        self.message = message


class RFIDEnrollmentService:
    """Service haut-niveau — appelé uniquement par les vues DRF.

    Toutes les méthodes sont statiques ; l'état vit en DB (RFIDEnrollmentSession)
    et dans le channel layer (broadcast events).
    """

    # ────────────────────────────────────────────────────────────
    # Cycle de vie session
    # ────────────────────────────────────────────────────────────
    @staticmethod
    @transaction.atomic
    def start_session(*, user, site=None, zone=None, reader=None,
                       mode: str = "single",
                       holder_kind: str = "", holder_id: Optional[int] = None,
                       timeout_seconds: int = 180):
        """Ouvre une session et envoie START_RFID_ENROLLMENT au lecteur cible.

        Si ``reader`` est None, la session écoute tous les lecteurs RFID du tenant.
        """
        from devices.models import RFIDEnrollmentSession
        from .command_queue import DeviceCommandQueue

        tenant = resolve_tenant(user)
        if tenant is None:
            raise EnrollmentError("Utilisateur sans tenant — session impossible",
                                    code="no_tenant")

        # Vérification cohérence reader ↔ tenant
        if reader is not None and reader.tenant_id != tenant.id:
            raise EnrollmentError("Ce lecteur n'appartient pas à votre tenant",
                                    code="reader_forbidden")

        holder_ct, holder_obj_id = _resolve_holder_reference(
            tenant,
            holder_kind,
            holder_id,
        )

        session = RFIDEnrollmentSession.objects.create(
            tenant=tenant,
            initiated_by=user,
            site=site, zone=zone, reader=reader,
            mode=mode,
            status="listening",
            holder_kind=holder_kind or "",
            holder_content_type=holder_ct,
            holder_object_id=holder_obj_id,
            timeout_seconds=timeout_seconds,
            started_at=timezone.now(),
        )

        # Push commande START_RFID_ENROLLMENT
        # Si reader précis → une commande. Sinon → broadcast à tous les lecteurs RFID.
        readers_qs = _resolve_readers(tenant, reader)
        for r in readers_qs:
            DeviceCommandQueue.enqueue(
                device=r, kind="START_RFID_ENROLLMENT",
                payload={"session_id": str(session.uuid),
                         "timeout_seconds": timeout_seconds,
                         "mode": mode},
                issued_by=user, session=session,
                timeout_seconds=timeout_seconds,
            )

        _emit_session(session, "listening",
                       message="Session ouverte, en attente des scans")
        try:
            from core.metrics import enrollment_sessions_total
            enrollment_sessions_total.labels(outcome="started").inc()
        except Exception:
            pass
        return session

    @staticmethod
    @transaction.atomic
    def stop_session(session, user=None, reason: str = ""):
        """Ferme la session et envoie STOP_RFID_ENROLLMENT aux lecteurs concernés."""
        from .command_queue import DeviceCommandQueue

        if session.status in ("completed", "cancelled", "timeout", "error"):
            return session

        readers_qs = _resolve_readers(session.tenant, session.reader)
        for r in readers_qs:
            DeviceCommandQueue.enqueue(
                device=r, kind="STOP_RFID_ENROLLMENT",
                payload={"session_id": str(session.uuid)},
                issued_by=user, session=session,
                timeout_seconds=10,
            )

        session.status = "cancelled" if reason == "cancel" else "completed"
        session.ended_at = timezone.now()
        session.save(update_fields=["status", "ended_at"])
        _emit_session(session, session.status,
                       message=reason or "Session fermée")
        try:
            from core.metrics import enrollment_sessions_total
            enrollment_sessions_total.labels(outcome=session.status).inc()
        except Exception:
            pass
        return session

    # ────────────────────────────────────────────────────────────
    # Ingestion d'un scan (appelée par l'endpoint scan/inbox POST ou l'agent)
    # ────────────────────────────────────────────────────────────
    @staticmethod
    def ingest_scan(*, session=None, tenant=None, uid: str, device=None,
                     rssi: Optional[int] = None, extra: Optional[dict] = None):
        """Traite un scan RFID entrant.

        Si ``session`` est fourni → l'événement est rattaché à cette session.
        Sinon on cherche une session en écoute du tenant sur ce lecteur.

        Retourne ``{status, badge_id, is_duplicate}``.
        """
        from devices.models import (Badge, RFIDEnrollmentEvent,
                                     RFIDEnrollmentSession)
        from .event_bus import EventBus

        uid = (uid or "").strip()
        if not uid:
            raise EnrollmentError("UID manquant", code="empty_uid")

        # Session inférée si absente
        if session is None:
            session = RFIDEnrollmentService._find_active_session(tenant, device)

        # Duplicate detection global
        existing_badge = Badge.objects.filter(uid=uid).first()
        is_duplicate = existing_badge is not None

        if session is not None:
            # Enregistrement de l'événement en DB
            event_type = "card.duplicate" if is_duplicate else "card.detected"
            evt = RFIDEnrollmentEvent.objects.create(
                session=session,
                event_type=event_type,
                uid=uid,
                device=device,
                rssi=rssi,
                payload=extra or {},
                resulting_badge=existing_badge if is_duplicate else None,
            )
            # Compteurs
            session.scans_count = (session.scans_count or 0) + 1
            if is_duplicate:
                session.duplicate_count = (session.duplicate_count or 0) + 1
            else:
                session.valid_count = (session.valid_count or 0) + 1
            session.save(update_fields=["scans_count", "duplicate_count", "valid_count"])

            # Métrique Prometheus
            try:
                from core.metrics import rfid_scans_total
                rfid_scans_total.labels(
                    result="duplicate" if is_duplicate else "detected",
                ).inc()
            except Exception:
                pass

            # Broadcast Channels
            if is_duplicate:
                EventBus.emit_card_duplicate(
                    session.uuid, uid,
                    existing_badge={
                        "id": existing_badge.pk,
                        "uid": existing_badge.uid,
                        "status": existing_badge.status,
                        "holder": _serialize_holder(existing_badge),
                    },
                )
            else:
                EventBus.emit_card_detected(
                    session.uuid, uid,
                    device_id=device.pk if device else None,
                    device_serial=device.serial_number if device else "",
                    rssi=rssi, extra=extra,
                )
            return {
                "status": "duplicate" if is_duplicate else "detected",
                "event_id": evt.pk,
                "session_id": str(session.uuid),
                "existing_badge_id": existing_badge.pk if existing_badge else None,
                "is_duplicate": is_duplicate,
            }

        # Pas de session — retour minimal pour le legacy inbox
        return {
            "status": "orphan",
            "session_id": None,
            "is_duplicate": is_duplicate,
            "existing_badge_id": existing_badge.pk if existing_badge else None,
        }

    # ────────────────────────────────────────────────────────────
    # Confirmation → création effective du Badge
    # ────────────────────────────────────────────────────────────
    @staticmethod
    @transaction.atomic
    def confirm_enrollment(*, session, uid: str, tech: str = "nfc",
                            category: str = "worker_rfid",
                            holder_kind: Optional[str] = None,
                            holder_id: Optional[int] = None,
                            valid_until=None, user=None):
        """Crée le Badge à partir d'un scan validé par l'opérateur.

        Bloque si UID déjà présent en base (sauf si status="revoked" et override).
        """
        from devices.models import Badge, RFIDEnrollmentEvent
        from .event_bus import EventBus

        uid = (uid or "").strip()
        if not uid:
            raise EnrollmentError("UID manquant", code="empty_uid")

        existing = Badge.objects.filter(uid=uid).first()
        if existing:
            raise EnrollmentError(
                f"Badge {uid} déjà enrôlé (statut {existing.status})",
                code="badge_duplicate",
            )

        # Résolution du porteur (préfère l'override sur session.holder)
        kind = holder_kind or session.holder_kind
        obj_id = holder_id if holder_id else session.holder_object_id
        holder_content_type = None
        holder_object_id = None
        holder_kind_str = ""
        if kind and obj_id:
            holder_content_type, holder_object_id = _resolve_holder_reference(
                session.tenant,
                kind,
                obj_id,
            )
            holder_kind_str = kind

        badge = Badge.objects.create(
            tenant=session.tenant,
            uid=uid,
            type=tech if tech in ("nfc", "uhf", "uhf_xerafy", "qr") else "nfc",
            category=category,
            status="active" if holder_object_id else "available",
            holder_kind=holder_kind_str,
            holder_content_type=holder_content_type,
            holder_object_id=holder_object_id,
            valid_until=valid_until,
        )

        # Event DB + broadcast
        RFIDEnrollmentEvent.objects.create(
            session=session, event_type="card.enrolled",
            uid=uid, resulting_badge=badge,
            message=f"Badge {badge.pk} créé",
        )

        EventBus.emit_card_enrolled(
            session.uuid, uid,
            badge={
                "id": badge.pk,
                "uid": badge.uid,
                "type": badge.type,
                "category": badge.category,
                "status": badge.status,
            },
        )
        try:
            from core.metrics import rfid_scans_total
            rfid_scans_total.labels(result="enrolled").inc()
        except Exception:
            pass
        logger.info(
            "Enrolled badge %s (uid=%s) via session %s",
            badge.pk,
            uid,
            session.uuid,
        )
        return badge


# ═══════════════════════════════════════════════════════════════════
# Helpers privés
# ═══════════════════════════════════════════════════════════════════
def _resolve_readers(tenant, reader=None):
    """Renvoie le queryset des lecteurs à activer pour la session."""
    from devices.models import Device
    if reader is not None:
        return [reader]
    return Device.objects.filter(
        tenant=tenant, status="active",
        model__type__in=[
            "reader_uhf_fixed", "reader_uhf_mobile",
            "reader_nfc_fixed", "reader_nfc_mobile",
            "portique", "face_terminal",
        ],
    )


def _resolve_holder_reference(tenant, holder_kind, holder_id):
    if not holder_kind or not holder_id:
        return None, None

    model_map = {
        "worker": ("ouvriers", "worker"),
        "employee": ("employees", "employee"),
        "visitor": ("visitors", "visitor"),
    }
    if holder_kind not in model_map:
        raise EnrollmentError(
            f"Type de porteur invalide : {holder_kind}",
            code="invalid_holder_kind",
        )

    app_label, model_name = model_map[holder_kind]
    try:
        holder_pk = int(holder_id)
        holder_ct = ContentType.objects.get(
            app_label=app_label,
            model=model_name,
        )
    except (TypeError, ValueError):
        raise EnrollmentError(
            "Identifiant de porteur invalide",
            code="invalid_holder_id",
        )
    except ContentType.DoesNotExist:
        raise EnrollmentError(
            f"Modèle {app_label}.{model_name} introuvable",
            code="content_type_missing",
        )

    holder_model = holder_ct.model_class()
    holder = holder_model.objects.filter(
        pk=holder_pk,
        tenant=tenant,
    ).first()
    if holder is None:
        raise EnrollmentError(
            "Porteur introuvable dans ce tenant",
            code="holder_not_found",
        )
    return holder_ct, holder.pk


def _find_active_session(tenant, device):
    """Cherche une session listening pour ce tenant + device."""
    from devices.models import RFIDEnrollmentSession

    qs = RFIDEnrollmentSession.objects.filter(status="listening", tenant=tenant)
    if device is not None:
        # Session ciblée sur ce device OU session sans device (broadcast)
        from django.db.models import Q
        qs = qs.filter(Q(reader=device) | Q(reader__isnull=True))
    return qs.order_by("-started_at").first()


# Expose helper statiquement pour clarté
RFIDEnrollmentService._find_active_session = staticmethod(_find_active_session)


def _emit_session(session, status: str, message: str = ""):
    from .event_bus import EventBus
    EventBus.emit_session_status(session.uuid, status, message)


def _serialize_holder(badge):
    """Retourne une repr minimale du porteur pour affichage front."""
    try:
        h = badge.holder
        if h is None:
            return None
        return {
            "id": getattr(h, "id", None),
            "kind": badge.holder_kind,
            "label": getattr(h, "full_name", None) or str(h),
        }
    except Exception:
        return None
