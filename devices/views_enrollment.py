"""KAYDAN SHIELD — endpoints REST enrôlement RFID temps réel & commandes device.

Ces vues sont des façades autour de :
  * devices.services.RFIDEnrollmentService
  * devices.services.DeviceCommandQueue

Toute la logique métier vit dans les services — les vues font uniquement :
  1. validation d'entrée
  2. appel service
  3. sérialisation de sortie
"""
from __future__ import annotations

import logging

from django.db.models import Q as models_Q
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import (Device, DeviceCommand, LocalAgent,
                      RFIDEnrollmentEvent, RFIDEnrollmentSession, SystemAlert)
from .utils import resolve_tenant as _resolve_tenant
from .services import (AlertService, DeviceCommandQueue,
                        EquipmentHealthMonitor, EventBus, RFIDEnrollmentService)
from .services.enrollment import EnrollmentError

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════
# Sérialisation minimale (on évite de créer 5 serializers pour Vague 1)
# ═══════════════════════════════════════════════════════════════════
def _serialize_session(s: RFIDEnrollmentSession) -> dict:
    return {
        "id": str(s.uuid),
        "status": s.status,
        "mode": s.mode,
        "site_id": s.site_id,
        "zone_id": s.zone_id,
        "reader_id": s.reader_id,
        "reader_serial": s.reader.serial_number if s.reader_id else None,
        "holder_kind": s.holder_kind,
        "holder_id": s.holder_object_id,
        "scans_count": s.scans_count,
        "valid_count": s.valid_count,
        "duplicate_count": s.duplicate_count,
        "error_count": s.error_count,
        "timeout_seconds": s.timeout_seconds,
        "started_at": s.started_at.isoformat() if s.started_at else None,
        "ended_at": s.ended_at.isoformat() if s.ended_at else None,
        "channel_group": s.channel_group,
    }


def _serialize_command(c: DeviceCommand) -> dict:
    return {
        "id": str(c.pk),
        "device_id": c.device_id,
        "kind": c.kind,
        "status": c.status,
        "payload": c.payload,
        "sent_at": c.sent_at.isoformat() if c.sent_at else None,
        "acked_at": c.acked_at.isoformat() if c.acked_at else None,
        "completed_at": c.completed_at.isoformat() if c.completed_at else None,
        "response": c.response_normalized,
        "error_message": c.error_message,
    }


def _serialize_event(e: RFIDEnrollmentEvent) -> dict:
    return {
        "id": e.pk,
        "event_type": e.event_type,
        "uid": e.uid,
        "device_id": e.device_id,
        "rssi": e.rssi,
        "message": e.message,
        "payload": e.payload,
        "at": e.created_at.isoformat() if e.created_at else None,
        "badge_id": e.resulting_badge_id,
    }


# ═══════════════════════════════════════════════════════════════════
# Sessions d'enrôlement RFID
# ═══════════════════════════════════════════════════════════════════
class EnrollmentStartView(APIView):
    """POST /api/v1/rfid/enrollment/start/

    Body :
        {
          "site_id":   <int|null>,
          "zone_id":   <int|null>,
          "reader_id": <int|null>,          # si null → écoute tous les lecteurs
          "mode":      "single" | "bulk",
          "holder_kind": "worker" | "employee" | "visitor" | "",
          "holder_id":   <int|null>,
          "timeout_seconds": <int>          # défaut 180
        }
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        data = request.data or {}
        tenant = _resolve_tenant(request.user)
        if tenant is None:
            return Response(
                {"error": "Utilisateur sans tenant", "code": "no_tenant"},
                status=400,
            )
        try:
            reader = None
            if data.get("reader_id"):
                reader = Device.objects.get(
                    pk=data["reader_id"],
                    tenant=tenant,
                )
            site = None
            zone = None
            if data.get("site_id"):
                from sites.models import Site

                site = Site.objects.filter(
                    pk=data["site_id"],
                    tenant=tenant,
                ).first()
                if site is None:
                    return Response({"error": "Site introuvable"}, status=404)
            if data.get("zone_id"):
                from sites.models import Zone

                zone = Zone.objects.filter(
                    pk=data["zone_id"],
                    site__tenant=tenant,
                ).first()
                if zone is None:
                    return Response({"error": "Zone introuvable"}, status=404)
                if site is not None and zone.site_id != site.pk:
                    return Response(
                        {"error": "Cette zone n'appartient pas au site sélectionné"},
                        status=400,
                    )

            session = RFIDEnrollmentService.start_session(
                user=request.user,
                site=site, zone=zone, reader=reader,
                mode=(data.get("mode") or "single"),
                holder_kind=data.get("holder_kind") or "",
                holder_id=data.get("holder_id"),
                timeout_seconds=int(data.get("timeout_seconds") or 180),
            )
        except EnrollmentError as exc:
            return Response({"error": exc.message, "code": exc.code}, status=400)
        except Device.DoesNotExist:
            return Response({"error": "Lecteur introuvable"}, status=404)

        return Response(_serialize_session(session), status=201)


class EnrollmentStopView(APIView):
    """POST /api/v1/rfid/enrollment/<session_id>/stop/"""
    permission_classes = [IsAuthenticated]

    def post(self, request, session_id):
        try:
            session = RFIDEnrollmentSession.objects.get(uuid=session_id)
        except RFIDEnrollmentSession.DoesNotExist:
            return Response({"error": "Session introuvable"}, status=404)

        # RBAC minimal — l'opérateur ou un admin de son tenant
        tenant = _resolve_tenant(request.user)
        if tenant is None or session.tenant_id != tenant.pk:
            return Response({"error": "Session hors tenant"}, status=403)

        reason = request.data.get("reason") or ""
        session = RFIDEnrollmentService.stop_session(
            session, user=request.user, reason=reason,
        )
        return Response(_serialize_session(session))


class EnrollmentConfirmView(APIView):
    """POST /api/v1/rfid/enrollment/<session_id>/confirm/

    Confirme un scan → crée le Badge.
    Body :
        {
          "uid":         "AABBCC01",
          "tech":        "nfc" | "uhf" | "uhf_xerafy" | "qr",
          "category":    "worker_rfid" | "employee_rfid" | "visitor_qr",
          "holder_kind": "worker" | "employee" | "visitor" | null,   # override
          "holder_id":   <int|null>,
          "valid_until": "YYYY-MM-DD" | null
        }
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, session_id):
        try:
            session = RFIDEnrollmentSession.objects.get(uuid=session_id)
        except RFIDEnrollmentSession.DoesNotExist:
            return Response({"error": "Session introuvable"}, status=404)

        tenant = _resolve_tenant(request.user)
        if tenant is None or session.tenant_id != tenant.pk:
            return Response({"error": "Session hors tenant"}, status=403)

        data = request.data or {}
        try:
            badge = RFIDEnrollmentService.confirm_enrollment(
                session=session,
                uid=data.get("uid") or "",
                tech=data.get("tech") or "nfc",
                category=data.get("category") or "worker_rfid",
                holder_kind=data.get("holder_kind"),
                holder_id=data.get("holder_id"),
                valid_until=data.get("valid_until"),
                user=request.user,
            )
        except EnrollmentError as exc:
            return Response({"error": exc.message, "code": exc.code}, status=400)

        return Response({
            "badge_id": badge.pk,
            "uid": badge.uid,
            "status": badge.status,
            "type": badge.type,
        }, status=201)


class EnrollmentSessionDetailView(APIView):
    """GET /api/v1/rfid/enrollment/sessions/<session_id>/

    Retourne l'état complet de la session + les événements (paginés côté client).
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, session_id):
        try:
            session = RFIDEnrollmentSession.objects.select_related("reader").get(
                uuid=session_id,
            )
        except RFIDEnrollmentSession.DoesNotExist:
            return Response({"error": "Session introuvable"}, status=404)

        tenant = _resolve_tenant(request.user)
        if tenant is None or session.tenant_id != tenant.pk:
            return Response({"error": "Session hors tenant"}, status=403)

        limit = min(int(request.query_params.get("limit", 100)), 500)
        events = session.events.order_by("-created_at")[:limit]

        return Response({
            **_serialize_session(session),
            "events": [_serialize_event(e) for e in reversed(events)],
        })


class EnrollmentSessionExportView(APIView):
    """GET /api/v1/rfid/enrollment/sessions/<session_id>/export/?format=csv|pdf

    Retourne un rapport d'enrôlement (CSV par défaut, PDF si reportlab dispo).
    Contient : entête session + tableau des events (UID / statut / device / horodatage).
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, session_id):
        try:
            session = RFIDEnrollmentSession.objects.select_related("reader").get(
                uuid=session_id,
            )
        except RFIDEnrollmentSession.DoesNotExist:
            return Response({"error": "Session introuvable"}, status=404)

        tenant = _resolve_tenant(request.user)
        if tenant is None or session.tenant_id != tenant.pk:
            return Response({"error": "Session hors tenant"}, status=403)

        fmt = (request.query_params.get("format") or "csv").lower()
        events = list(session.events.select_related("device", "resulting_badge")
                              .order_by("created_at"))

        if fmt == "pdf":
            return _export_pdf(session, events)
        return _export_csv(session, events)


def _export_csv(session, events):
    import csv
    from io import StringIO

    from django.http import HttpResponse

    buf = StringIO()
    w = csv.writer(buf)
    w.writerow(["Session", str(session.uuid)])
    w.writerow(["Statut", session.status])
    w.writerow(["Mode", session.mode])
    w.writerow(["Démarrée", session.started_at.isoformat() if session.started_at else ""])
    w.writerow(["Terminée", session.ended_at.isoformat() if session.ended_at else ""])
    w.writerow(["Scans", session.scans_count])
    w.writerow(["Valides", session.valid_count])
    w.writerow(["Doublons", session.duplicate_count])
    w.writerow([])
    w.writerow(["Horodatage", "Type", "UID", "Device", "RSSI", "Badge", "Message"])
    for e in events:
        w.writerow([
            e.created_at.isoformat() if e.created_at else "",
            e.event_type, e.uid,
            e.device.serial_number if e.device_id else "",
            e.rssi if e.rssi is not None else "",
            e.resulting_badge_id if e.resulting_badge_id else "",
            e.message or "",
        ])
    resp = HttpResponse(buf.getvalue(), content_type="text/csv")
    resp["Content-Disposition"] = f'attachment; filename="enrollment_{session.uuid}.csv"'
    return resp


def _export_pdf(session, events):
    """Génère un PDF avec reportlab. Fallback CSV si module absent."""
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.units import cm
        from reportlab.platypus import (Paragraph, SimpleDocTemplate, Spacer,
                                          Table, TableStyle)
    except ImportError:
        return _export_csv(session, events)

    from io import BytesIO

    from django.http import HttpResponse

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=1.2 * cm, bottomMargin=1 * cm)
    styles = getSampleStyleSheet()
    elems = []

    elems.append(Paragraph("<b>KAYDAN SHIELD — Rapport d'enrôlement RFID</b>",
                            styles["Title"]))
    elems.append(Paragraph(f"Session <b>{session.uuid}</b>", styles["Normal"]))
    elems.append(Paragraph(
        f"Statut : {session.status} · Mode : {session.mode} · "
        f"Scans : {session.scans_count} "
        f"(valides {session.valid_count}, doublons {session.duplicate_count})",
        styles["Normal"],
    ))
    if session.started_at:
        elems.append(Paragraph(
            f"Démarrée : {session.started_at.strftime('%d/%m/%Y %H:%M')}"
            + (f" · Terminée : {session.ended_at.strftime('%d/%m/%Y %H:%M')}"
               if session.ended_at else ""),
            styles["Normal"],
        ))
    elems.append(Spacer(1, 0.4 * cm))

    data = [["Horodatage", "Type", "UID", "Device", "RSSI", "Badge"]]
    for e in events:
        data.append([
            e.created_at.strftime("%H:%M:%S") if e.created_at else "",
            e.event_type,
            e.uid or "—",
            e.device.serial_number if e.device_id else "—",
            str(e.rssi) if e.rssi is not None else "—",
            str(e.resulting_badge_id) if e.resulting_badge_id else "—",
        ])

    t = Table(data, colWidths=[2.6*cm, 3*cm, 4*cm, 3.5*cm, 1.4*cm, 2*cm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e293b")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.grey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1),
         [colors.whitesmoke, colors.white]),
    ]))
    elems.append(t)
    doc.build(elems)

    resp = HttpResponse(buf.getvalue(), content_type="application/pdf")
    resp["Content-Disposition"] = f'attachment; filename="enrollment_{session.uuid}.pdf"'
    return resp


class EnrollmentIngestScanView(APIView):
    """POST /api/v1/rfid/enrollment/ingest/

    Endpoint générique appelé par un lecteur IP direct ou par un agent local
    pour pousser un scan RFID. Rejoint la session listening la plus récente.

    Body :
        {
          "uid":       "AABBCC01",
          "device_id": <int|null>,
          "session_id": "<uuid>|null",
          "rssi":      <int|null>,
          "extra":     {...}
        }
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        data = request.data or {}
        uid = (data.get("uid") or "").strip()
        if not uid:
            return Response({"error": "UID manquant"}, status=400)

        tenant = _resolve_tenant(request.user)
        if tenant is None:
            return Response(
                {"error": "Utilisateur sans tenant", "code": "no_tenant"},
                status=400,
            )

        session = None
        device = None
        if data.get("session_id"):
            try:
                session = RFIDEnrollmentSession.objects.get(
                    uuid=data["session_id"],
                    tenant=tenant,
                )
            except RFIDEnrollmentSession.DoesNotExist:
                return Response({"error": "Session introuvable"}, status=404)
        if data.get("device_id"):
            try:
                device = Device.objects.get(
                    pk=data["device_id"],
                    tenant=tenant,
                )
            except Device.DoesNotExist:
                pass  # scan orphelin admis

        try:
            result = RFIDEnrollmentService.ingest_scan(
                session=session,
                tenant=tenant,
                uid=uid,
                device=device,
                rssi=data.get("rssi"),
                extra=data.get("extra") or {},
            )
        except EnrollmentError as exc:
            return Response({"error": exc.message, "code": exc.code}, status=400)

        return Response(result, status=201)


# ═══════════════════════════════════════════════════════════════════
# DeviceCommand — commandes serveur → équipement
# ═══════════════════════════════════════════════════════════════════
class DeviceCommandCreateView(APIView):
    """POST /api/v1/devices/<pk>/commands/

    Body :
        {
          "kind":    "PING_DEVICE" | "SYNC_DEVICE" | ... ,
          "payload": {...},
          "timeout_seconds": <int>
        }
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        try:
            device = Device.objects.get(pk=pk)
        except Device.DoesNotExist:
            return Response({"error": "Équipement introuvable"}, status=404)

        if device.tenant_id != getattr(request.user, "tenant_id", None):
            return Response({"error": "Équipement hors tenant"}, status=403)

        data = request.data or {}
        kind = data.get("kind")
        if not kind:
            return Response({"error": "kind requis"}, status=400)

        try:
            cmd = DeviceCommandQueue.enqueue(
                device=device, kind=kind,
                payload=data.get("payload") or {},
                issued_by=request.user,
                timeout_seconds=int(data.get("timeout_seconds") or 30),
            )
        except Exception as exc:
            logger.exception("Erreur enqueue commande")
            return Response({"error": str(exc)}, status=500)

        return Response(_serialize_command(cmd), status=201)


class DeviceCommandDetailView(APIView):
    """GET /api/v1/devices/commands/<command_id>/ — statut d'une commande."""
    permission_classes = [IsAuthenticated]

    def get(self, request, command_id):
        try:
            cmd = DeviceCommand.objects.get(pk=command_id)
        except DeviceCommand.DoesNotExist:
            return Response({"error": "Commande introuvable"}, status=404)

        if cmd.tenant_id != getattr(request.user, "tenant_id", None):
            return Response({"error": "Commande hors tenant"}, status=403)

        return Response(_serialize_command(cmd))


class DeviceStatusView(APIView):
    """GET /api/v1/devices/<pk>/status/ — snapshot temps réel via probe."""
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        try:
            device = Device.objects.select_related("model").get(pk=pk)
        except Device.DoesNotExist:
            return Response({"error": "Équipement introuvable"}, status=404)

        probe = EquipmentHealthMonitor.probe(device)
        return Response({
            "device_id": device.pk,
            "serial": device.serial_number,
            "status": device.status,
            "last_heartbeat_at": device.last_heartbeat_at.isoformat()
                                 if device.last_heartbeat_at else None,
            "probe": probe,
        })


# ═══════════════════════════════════════════════════════════════════
# Agent local — endpoints HTTP (fallback si WS indisponible)
# ═══════════════════════════════════════════════════════════════════
from .auth_hmac import AgentHmacAuthentication


# ═══════════════════════════════════════════════════════════════════
# Admin — CRUD LocalAgent + provisioning TOML
# ═══════════════════════════════════════════════════════════════════
def _serialize_agent(a: LocalAgent, *, include_secrets: bool = False) -> dict:
    d = {
        "id": str(a.pk),
        "label": a.label,
        "site_id": a.site_id,
        "connected": a.connected,
        "last_seen_at": a.last_seen_at.isoformat() if a.last_seen_at else None,
        "version": a.version,
        "os_info": a.os_info,
        "devices_discovered_count": len(a.devices_discovered or []),
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }
    if include_secrets:
        d["api_token"] = a.api_token
        d["hmac_secret"] = a.hmac_secret or ""
    return d


class LocalAgentListView(APIView):
    """GET / POST /api/v1/devices/local-agents/

    GET → liste des agents du tenant courant.
    POST → provisionne un nouvel agent (retourne token + config TOML).
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        tenant = _resolve_tenant(request.user)
        if tenant is None:
            return Response({"error": "Aucun tenant disponible — créez-en un d'abord"},
                              status=403)
        qs = LocalAgent.objects.filter(tenant=tenant).order_by("-last_seen_at")
        return Response({
            "count": qs.count(),
            "results": [_serialize_agent(a) for a in qs],
        })

    def post(self, request):
        import secrets
        tenant = _resolve_tenant(request.user)
        if tenant is None:
            return Response({"error": "Aucun tenant disponible — créez-en un d'abord"},
                              status=403)

        data = request.data or {}
        label = (data.get("label") or "").strip()
        if not label:
            return Response({"error": "Label requis"}, status=400)

        site = None
        if data.get("site_id"):
            from sites.models import Site
            try:
                site = Site.objects.get(pk=data["site_id"])
            except Site.DoesNotExist:
                return Response({"error": "Site introuvable"}, status=404)

        agent = LocalAgent.objects.create(
            tenant=tenant, label=label, site=site,
            api_token=secrets.token_urlsafe(32),
            hmac_secret=secrets.token_urlsafe(32),
        )
        return Response({
            **_serialize_agent(agent, include_secrets=True),
            "toml": _agent_config_toml(request, agent),
        }, status=201)


class LocalAgentDetailView(APIView):
    """GET / DELETE /api/v1/devices/local-agents/<id>/

    GET → détail (sans secrets).
    DELETE → révoque définitivement (agent ne pourra plus se connecter).
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, agent_id):
        try:
            a = LocalAgent.objects.get(pk=agent_id)
        except LocalAgent.DoesNotExist:
            return Response({"error": "Agent introuvable"}, status=404)
        if a.tenant_id != getattr(request.user, "tenant_id", None):
            return Response({"error": "Agent hors tenant"}, status=403)
        return Response({
            **_serialize_agent(a),
            "devices_discovered": a.devices_discovered or [],
        })

    def delete(self, request, agent_id):
        try:
            a = LocalAgent.objects.get(pk=agent_id)
        except LocalAgent.DoesNotExist:
            return Response({"error": "Agent introuvable"}, status=404)
        if a.tenant_id != getattr(request.user, "tenant_id", None):
            return Response({"error": "Agent hors tenant"}, status=403)
        a.delete()
        return Response({"ok": True})


class LocalAgentRotateTokenView(APIView):
    """POST /api/v1/devices/local-agents/<id>/rotate-token/

    Régénère api_token + hmac_secret. L'ancien token cesse immédiatement de fonctionner.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, agent_id):
        import secrets
        try:
            a = LocalAgent.objects.get(pk=agent_id)
        except LocalAgent.DoesNotExist:
            return Response({"error": "Agent introuvable"}, status=404)
        if a.tenant_id != getattr(request.user, "tenant_id", None):
            return Response({"error": "Agent hors tenant"}, status=403)

        a.api_token = secrets.token_urlsafe(32)
        a.hmac_secret = secrets.token_urlsafe(32)
        a.connected = False
        a.channel_name = ""
        a.save(update_fields=["api_token", "hmac_secret", "connected", "channel_name"])
        return Response({
            **_serialize_agent(a, include_secrets=True),
            "toml": _agent_config_toml(request, a),
        })


def _agent_config_toml(request, agent: LocalAgent) -> str:
    """Génère un TOML prêt à coller dans ~/.kshield-agent.toml sur la machine cliente."""
    scheme = "https" if request.is_secure() else "http"
    host = request.get_host()
    server_url = f"{scheme}://{host}"
    return (
        f'# ~/.kshield-agent.toml — généré le {agent.created_at.strftime("%Y-%m-%d %H:%M")}\n'
        f'server_url  = "{server_url}"\n'
        f'agent_id    = "{agent.pk}"\n'
        f'api_token   = "{agent.api_token}"\n'
        f'hmac_secret = "{agent.hmac_secret}"\n'
        f'log_level   = "INFO"\n'
        f'heartbeat_seconds     = 30\n'
        f'reconnect_max_seconds = 30\n\n'
        f'# Ajoute tes lecteurs ci-dessous :\n'
        f'# [[readers]]\n'
        f'# kind      = "zkteco"\n'
        f'# ip        = "192.168.1.201"\n'
        f'# port      = 4370\n'
        f'# device_id = 6\n'
    )


# ═══════════════════════════════════════════════════════════════════
# Alertes système agrégées (agents offline, devices offline, sessions bloquées)
# ═══════════════════════════════════════════════════════════════════
def _serialize_alert(a: SystemAlert) -> dict:
    return {
        "id": str(a.pk),
        "type": a.kind,
        "severity": a.severity,
        "title": a.title,
        "detail": a.detail,
        "target_url": a.target_url or None,
        "target_id": a.target_id or None,
        "since": a.created_at.isoformat() if a.created_at else None,
        "acknowledged_at": a.acknowledged_at.isoformat() if a.acknowledged_at else None,
        "resolved_at": a.resolved_at.isoformat() if a.resolved_at else None,
    }


class SystemAlertsView(APIView):
    """GET /api/v1/devices/alerts/system/

    Agrège les alertes actives (non résolues) persistées en DB.
    Le sweep Celery ``devices.sweep_system_alerts`` les met à jour toutes les 60s.

    Query params :
        ?include_resolved=true      → inclut les résolues (défaut false)
        ?limit=50                    → limite le nombre de résultats
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from django.utils import timezone

        tenant = _resolve_tenant(request.user)
        if tenant is None:
            return Response({"error": "Aucun tenant disponible — créez-en un d'abord"},
                              status=403)

        include_resolved = request.query_params.get("include_resolved") == "true"
        limit = min(int(request.query_params.get("limit", 100)), 500)

        qs = SystemAlert.objects.filter(tenant=tenant)
        if not include_resolved:
            qs = qs.filter(resolved_at__isnull=True)

        # Tri : critical → warning → info, puis récent d'abord
        from django.db.models import Case, When, Value, IntegerField
        qs = qs.annotate(sev_rank=Case(
            When(severity="critical", then=Value(0)),
            When(severity="warning", then=Value(1)),
            When(severity="info", then=Value(2)),
            default=Value(3),
            output_field=IntegerField(),
        )).order_by("sev_rank", "-created_at")[:limit]

        alerts = list(qs)
        return Response({
            "count": len(alerts),
            "critical": sum(1 for a in alerts if a.severity == "critical"),
            "warning": sum(1 for a in alerts if a.severity == "warning"),
            "info": sum(1 for a in alerts if a.severity == "info"),
            "alerts": [_serialize_alert(a) for a in alerts],
            "at": timezone.now().isoformat(),
        })


class MultiProtocolDiscoveryView(APIView):
    """POST /api/v1/devices/discovery/scan/

    Lance un scan Auto Discovery multi-protocole (ONVIF + mDNS + SSDP + SNMP + ARP).

    Body :
        {
          "protocols": ["onvif", "mdns", "ssdp", "arp", "snmp"],   # optionnel
          "ip_range":  "192.168.1.0/24",                           # optionnel (SNMP+TCP)
          "timeout":   4.0
        }

    Retourne la liste des équipements détectés, mergés par IP.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        from .discovery import DiscoveryOrchestrator
        from .network_scan import _expand_ip_range

        data = request.data or {}
        protocols = data.get("protocols")
        timeout = float(data.get("timeout") or 4.0)
        ip_range = None
        if data.get("ip_range"):
            try:
                ip_range = _expand_ip_range(data["ip_range"])
            except ValueError as exc:
                return Response({"error": str(exc)}, status=400)
            if len(ip_range) > 512:
                return Response({"error": "Plage trop large (max 512 IPs)"}, status=400)

        orch = DiscoveryOrchestrator(protocols=protocols, timeout=timeout)
        try:
            devices = orch.scan(ip_range)
        except Exception as exc:
            return Response({"error": str(exc)}, status=500)

        return Response({
            "count": len(devices),
            "devices": [
                {
                    "ip": d.ip, "mac": d.mac, "hostname": d.hostname,
                    "vendor": d.vendor, "model": d.model, "firmware": d.firmware,
                    "device_type_hint": d.device_type_hint,
                    "protocols_detected": d.protocols_detected,
                    "already_known": d.already_known,
                    "protocols_raw": d.protocols_raw,
                }
                for d in devices
            ],
        })


class DeviceTwinView(APIView):
    """GET /api/v1/devices/<pk>/twin/ — jumeau numérique de l'équipement.

    POST /api/v1/devices/<pk>/twin/refresh/ — force un refresh immédiat via driver.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        from .services import TwinService

        try:
            device = Device.objects.select_related("model").get(pk=pk)
        except Device.DoesNotExist:
            return Response({"error": "Équipement introuvable"}, status=404)
        if device.tenant_id != getattr(request.user, "tenant_id", None):
            return Response({"error": "Équipement hors tenant"}, status=403)

        twin = TwinService.get_or_create(device)
        return Response({
            "device_id": device.pk,
            "serial": device.serial_number,
            "reachable": twin.reachable,
            "health_score": twin.health_score,
            "health_status": twin.health_status,
            "health_reasons": twin.health_reasons,
            "driver_class": twin.driver_class,
            "metrics": {
                "latency_ms": twin.latency_ms,
                "uptime_seconds": twin.uptime_seconds,
                "cpu_percent": twin.cpu_percent,
                "ram_percent": twin.ram_percent,
                "storage_percent": twin.storage_percent,
                "temperature_c": twin.temperature_c,
                "battery_percent": twin.battery_percent,
                "network_quality": twin.network_quality,
            },
            "firmware": twin.firmware,
            "hardware": twin.hardware,
            "recent_errors": twin.recent_errors[-10:],
            "raw_status": twin.raw_status,
            "last_probed_at": twin.last_probed_at.isoformat() if twin.last_probed_at else None,
            "last_seen_at": twin.last_seen_at.isoformat() if twin.last_seen_at else None,
            "updated_at": twin.updated_at.isoformat() if twin.updated_at else None,
        })


class DeviceTwinRefreshView(APIView):
    """POST /api/v1/devices/<pk>/twin/refresh/ — refresh synchrone via driver."""
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        from .services import TwinService

        try:
            device = Device.objects.select_related("model").get(pk=pk)
        except Device.DoesNotExist:
            return Response({"error": "Équipement introuvable"}, status=404)
        if device.tenant_id != getattr(request.user, "tenant_id", None):
            return Response({"error": "Équipement hors tenant"}, status=403)

        try:
            twin = TwinService.refresh(device, use_driver=True)
        except Exception as exc:
            return Response({"error": str(exc)}, status=500)

        return Response({
            "device_id": device.pk,
            "reachable": twin.reachable,
            "health_score": twin.health_score,
            "health_reasons": twin.health_reasons,
            "refreshed_at": twin.last_probed_at.isoformat() if twin.last_probed_at else None,
        })


class PluginCatalogView(APIView):
    """GET /api/v1/devices/marketplace/plugins/

    Retourne le catalogue officiel des plugins vendor disponibles + statut
    d'installation (chargé = présent dans le registre en cours).

    Le catalogue est statique pour l'instant (Vague 8) — sera enrichi par un
    registry externe dans une itération future.
    """
    permission_classes = [IsAuthenticated]

    CATALOG = [
        {"vendor": "zkteco",    "name": "ZKTeco / AiFace",     "protocols": ["ADMS", "pyzk"],       "verified": True},
        {"vendor": "hikvision", "name": "Hikvision",            "protocols": ["ISAPI"],              "verified": True},
        {"vendor": "suprema",   "name": "Suprema BioStar",      "protocols": ["REST", "WebSocket"],  "verified": True},
        {"vendor": "hid",       "name": "HID Global",           "protocols": ["Origo", "OSDP"],      "verified": False},
        {"vendor": "dahua",     "name": "Dahua",                "protocols": ["CGI"],                "verified": True},
        {"vendor": "axis",      "name": "Axis Communications",  "protocols": ["VAPIX"],              "verified": True},
        {"vendor": "onvif",     "name": "ONVIF Universal",      "protocols": ["ONVIF Profile S/T/D"],"verified": True},
        {"vendor": "bosch",     "name": "Bosch Security",       "protocols": ["ONVIF", "CGI"],       "verified": False, "coming_soon": True},
        {"vendor": "invixium",  "name": "Invixium",             "protocols": ["REST"],               "coming_soon": True},
        {"vendor": "honeywell", "name": "Honeywell",            "protocols": ["ProWatch"],           "coming_soon": True},
        {"vendor": "gallagher", "name": "Gallagher",            "protocols": ["Command Centre API"], "coming_soon": True},
        {"vendor": "stid",      "name": "STid",                 "protocols": ["OSDP", "BLE"],        "coming_soon": True},
        {"vendor": "identiv",   "name": "Identiv",              "protocols": ["Hirsch Velocity"],    "coming_soon": True},
    ]

    def get(self, request):
        from .drivers import DriverManager
        installed = {d["vendor"] for d in DriverManager.list_drivers()}
        catalog = []
        for item in self.CATALOG:
            catalog.append({
                **item,
                "installed": item["vendor"] in installed,
            })
        return Response({"count": len(catalog), "plugins": catalog})


class PluginUploadView(APIView):
    """POST /api/v1/devices/marketplace/plugins/upload/

    Upload d'un plugin ZIP (extension .kshield-driver) : validation basique
    + décompression dans un dossier de staging. Le rechargement effectif
    nécessite un restart Django (autoload au boot).

    Body : multipart/form-data avec champ ``file``.

    NB : cette route est intentionnellement basique — un vrai marketplace
    exigerait signature GPG + review Anthropic-like. À enrichir en Vague 9.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        from django.conf import settings
        from pathlib import Path
        import zipfile

        # RBAC : seulement les superusers pour installer un plugin
        if not getattr(request.user, "is_superuser", False):
            return Response({"error": "Réservé aux superadmins"}, status=403)

        f = request.FILES.get("file")
        if not f:
            return Response({"error": "Fichier manquant (champ 'file')"}, status=400)
        if f.size > 5 * 1024 * 1024:
            return Response({"error": "Plugin > 5 MB refusé"}, status=413)
        if not f.name.endswith((".zip", ".kshield-driver")):
            return Response({"error": "Extension attendue .zip ou .kshield-driver"},
                              status=400)

        # Staging directory (non chargé automatiquement — audit manuel requis)
        staging = Path(getattr(settings, "PLUGIN_STAGING_DIR",
                                 "/var/lib/kshield/plugin-staging"))
        staging.mkdir(parents=True, exist_ok=True)
        dest = staging / f.name
        with dest.open("wb") as out:
            for chunk in f.chunks():
                out.write(chunk)

        # Validation minimale : ZIP valide + présence d'un fichier driver.py
        try:
            with zipfile.ZipFile(dest) as z:
                names = z.namelist()
                has_driver = any(n.endswith("/driver.py") or n == "driver.py"
                                  for n in names)
                if not has_driver:
                    dest.unlink(missing_ok=True)
                    return Response({"error": "ZIP invalide — driver.py manquant"},
                                      status=400)
        except zipfile.BadZipFile:
            dest.unlink(missing_ok=True)
            return Response({"error": "ZIP corrompu"}, status=400)

        return Response({
            "ok": True,
            "staged_at": str(dest),
            "message": "Plugin stocké en staging. Redémarre Django et le driver "
                        "sera chargé si placé dans devices/drivers/.",
        })


class NetworkTopologyView(APIView):
    """GET /api/v1/devices/topology/

    Retourne un graphe hiérarchique : tenant → sites → zones → devices + agents
    avec statut live + health score. Utilisé par la page /topology (SVG D3).
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from sites.models import Site, Zone
        from .models import Device, DeviceTwin, LocalAgent

        tenant = _resolve_tenant(request.user)
        if tenant is None:
            return Response({"error": "Aucun tenant disponible — créez-en un d'abord"},
                              status=403)

        # Preload
        sites = list(Site.objects.filter(company__tenant=tenant)
                      .select_related("company"))
        site_ids = [s.id for s in sites]
        zones = list(Zone.objects.filter(site_id__in=site_ids))
        devices = list(
            Device.objects.filter(tenant=tenant)
                            .select_related("model", "site", "zone", "twin")
        )
        agents = list(LocalAgent.objects.filter(tenant=tenant))

        # Aggregate stats par site/zone
        site_stats: dict = {s.id: {"total": 0, "online": 0, "critical_alerts": 0}
                             for s in sites}
        zone_stats: dict = {z.id: {"total": 0, "online": 0} for z in zones}
        heartbeat_cutoff = timezone_now() - _delta(seconds=90)

        for d in devices:
            reachable = False
            score = None
            try:
                if d.twin:
                    reachable = d.twin.reachable
                    score = d.twin.health_score
            except DeviceTwin.DoesNotExist:
                pass
            if not reachable and d.last_heartbeat_at:
                reachable = d.last_heartbeat_at > heartbeat_cutoff
            if d.site_id and d.site_id in site_stats:
                site_stats[d.site_id]["total"] += 1
                if reachable:
                    site_stats[d.site_id]["online"] += 1
            if d.zone_id and d.zone_id in zone_stats:
                zone_stats[d.zone_id]["total"] += 1
                if reachable:
                    zone_stats[d.zone_id]["online"] += 1

        return Response({
            "tenant": {
                "id": tenant.id,
                "name": getattr(tenant, "name", str(tenant)),
                "devices_total": len(devices),
                "agents_total": len(agents),
            },
            "sites": [
                {
                    "id": s.id, "name": s.name, "code": s.code,
                    "company": {"id": s.company_id,
                                 "name": getattr(s.company, "name", "")} if s.company_id else None,
                    "devices_total": site_stats[s.id]["total"],
                    "devices_online": site_stats[s.id]["online"],
                    "zones": [
                        {
                            "id": z.id, "name": z.name,
                            "devices_total": zone_stats.get(z.id, {}).get("total", 0),
                            "devices_online": zone_stats.get(z.id, {}).get("online", 0),
                        }
                        for z in zones if z.site_id == s.id
                    ],
                }
                for s in sites
            ],
            "devices": [
                _topo_device(d) for d in devices
            ],
            "agents": [
                {
                    "id": str(a.pk), "label": a.label,
                    "site_id": a.site_id, "connected": a.connected,
                    "last_seen_at": a.last_seen_at.isoformat() if a.last_seen_at else None,
                }
                for a in agents
            ],
        })


def _topo_device(d) -> dict:
    twin = None
    try:
        if d.twin:
            twin = {
                "reachable": d.twin.reachable,
                "health_score": d.twin.health_score,
                "health_status": d.twin.health_status,
            }
    except Exception:
        pass
    return {
        "id": d.pk, "serial": d.serial_number,
        "brand": d.model.brand, "model": d.model.model, "type": d.model.type,
        "site_id": d.site_id, "zone_id": d.zone_id,
        "ip": d.ip_address, "status": d.status,
        "twin": twin,
    }


def timezone_now():
    from django.utils import timezone
    return timezone.now()


def _delta(**kwargs):
    from datetime import timedelta
    return timedelta(**kwargs)


class MaintenanceTicketListView(APIView):
    """GET /api/v1/devices/maintenance/tickets/

    Query params :
      ?status=open,in_progress    # défaut : open + in_progress
      ?severity=critical
      ?device_id=<uuid>
      ?limit=100
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from .models import MaintenanceTicket

        tenant = _resolve_tenant(request.user)
        if tenant is None:
            return Response({"error": "Aucun tenant disponible — créez-en un d'abord"},
                              status=403)

        qs = MaintenanceTicket.objects.filter(tenant=tenant).select_related("device")

        status_p = request.query_params.get("status")
        if status_p:
            qs = qs.filter(status__in=status_p.split(","))
        else:
            qs = qs.filter(status__in=["open", "in_progress"])

        sev = request.query_params.get("severity")
        if sev:
            qs = qs.filter(severity=sev)

        device_id = request.query_params.get("device_id")
        if device_id:
            qs = qs.filter(device_id=device_id)

        limit = min(int(request.query_params.get("limit", 100)), 500)

        # Tri : critical → warning → info, puis récent
        from django.db.models import Case, IntegerField, Value, When
        qs = qs.annotate(sev_rank=Case(
            When(severity="critical", then=Value(0)),
            When(severity="warning", then=Value(1)),
            When(severity="info", then=Value(2)),
            default=Value(3),
            output_field=IntegerField(),
        )).order_by("sev_rank", "-created_at")[:limit]

        return Response({
            "count": qs.count() if hasattr(qs, "count") else len(list(qs)),
            "tickets": [_serialize_ticket(t) for t in qs],
        })

    def post(self, request):
        """Création manuelle d'un ticket."""
        from .models import Device, MaintenanceTicket

        tenant = _resolve_tenant(request.user)
        if tenant is None:
            return Response({"error": "Aucun tenant disponible — créez-en un d'abord"},
                              status=403)

        data = request.data or {}
        device_id = data.get("device_id")
        if not device_id:
            return Response({"error": "device_id requis"}, status=400)
        try:
            device = Device.objects.get(pk=device_id, tenant=tenant)
        except Device.DoesNotExist:
            return Response({"error": "Device introuvable"}, status=404)

        t = MaintenanceTicket.objects.create(
            tenant=tenant, device=device,
            kind=data.get("kind", "manual"),
            severity=data.get("severity", "warning"),
            title=(data.get("title") or "Ticket manuel")[:240],
            description=data.get("description") or "",
            scheduled_for=data.get("scheduled_for"),
            created_by_engine=False,
        )
        return Response(_serialize_ticket(t), status=201)


class MaintenanceTicketDetailView(APIView):
    """GET/PATCH/DELETE /api/v1/devices/maintenance/tickets/<uuid>/"""
    permission_classes = [IsAuthenticated]

    def _get(self, request, ticket_id):
        from .models import MaintenanceTicket
        try:
            t = MaintenanceTicket.objects.select_related("device").get(pk=ticket_id)
        except MaintenanceTicket.DoesNotExist:
            return None
        if t.tenant_id != getattr(request.user, "tenant_id", None):
            return None
        return t

    def get(self, request, ticket_id):
        t = self._get(request, ticket_id)
        if t is None:
            return Response({"error": "Ticket introuvable"}, status=404)
        return Response(_serialize_ticket(t))

    def patch(self, request, ticket_id):
        from django.utils import timezone
        t = self._get(request, ticket_id)
        if t is None:
            return Response({"error": "Ticket introuvable"}, status=404)
        data = request.data or {}

        for f in ("status", "severity", "assigned_to", "resolution_notes",
                   "description"):
            if f in data:
                setattr(t, f, data[f])
        if t.status == "resolved" and not t.resolved_at:
            t.resolved_at = timezone.now()
        t.save()
        return Response(_serialize_ticket(t))

    def delete(self, request, ticket_id):
        t = self._get(request, ticket_id)
        if t is None:
            return Response({"error": "Ticket introuvable"}, status=404)
        t.delete()
        return Response({"ok": True})


def _serialize_ticket(t) -> dict:
    return {
        "id": str(t.pk),
        "device_id": t.device_id,
        "device_serial": t.device.serial_number if t.device_id else None,
        "kind": t.kind,
        "severity": t.severity,
        "status": t.status,
        "title": t.title,
        "description": t.description,
        "prediction": t.prediction,
        "confidence": t.confidence,
        "created_by_engine": t.created_by_engine,
        "assigned_to": t.assigned_to_id,
        "scheduled_for": t.scheduled_for.isoformat() if t.scheduled_for else None,
        "resolved_at": t.resolved_at.isoformat() if t.resolved_at else None,
        "resolution_notes": t.resolution_notes,
        "created_at": t.created_at.isoformat() if t.created_at else None,
    }


class DriversListView(APIView):
    """GET /api/v1/devices/drivers/ — liste des drivers vendor enregistrés."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from .drivers import DriverManager
        return Response({
            "count": len(DriverManager.list_drivers()),
            "drivers": DriverManager.list_drivers(),
        })


class DriverTestView(APIView):
    """POST /api/v1/devices/<pk>/driver-test/ — teste le driver assigné.

    Retourne le résultat de ``driver.ping()`` + ``driver.get_info()`` pour vérifier
    que le bon plugin s'active et qu'il communique bien avec l'équipement.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        from .drivers import DriverManager

        try:
            device = Device.objects.select_related("model").get(pk=pk)
        except Device.DoesNotExist:
            return Response({"error": "Équipement introuvable"}, status=404)

        if device.tenant_id != getattr(request.user, "tenant_id", None):
            return Response({"error": "Équipement hors tenant"}, status=403)

        driver = DriverManager.for_device(device)
        result = {"driver": driver.__class__.__name__, "vendor": driver.vendor}
        try:
            with driver:
                ping = driver.ping()
                info = driver.get_info()
                result.update({
                    "ping": {"ok": ping.ok, "detail": ping.detail, "data": ping.data},
                    "info": {
                        "serial": info.serial, "brand": info.brand, "model": info.model,
                        "firmware": info.firmware, "mac": info.mac, "ip": info.ip,
                        "capabilities": info.capabilities,
                    },
                    "capabilities": list(driver.capabilities),
                })
        except Exception as exc:
            result["error"] = str(exc)
        return Response(result)


class RealtimeStatsView(APIView):
    """GET /api/v1/devices/stats/realtime/

    Snapshot instantané des compteurs temps réel pour le dashboard.
    Alimenté par les modèles DB (pas par Prometheus — pour rester simple).
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from datetime import timedelta

        from django.db.models import Count
        from django.utils import timezone

        now = timezone.now()

        tenant = _resolve_tenant(request.user)
        if tenant is None:
            # Retourne un shape complet même sans tenant : le widget front
            # affichera des zéros au lieu de crasher avec "undefined.online".
            return Response({
                "at": now.isoformat(),
                "warning": "Aucun tenant — connectez votre compte à un tenant",
                "devices":    {"total": 0, "online": 0, "offline": 0, "online_ratio": 0},
                "agents":     {"total": 0, "connected": 0, "disconnected": 0},
                "enrollment": {"sessions_active": 0, "scans_last_hour": 0,
                               "enrolled_last_24h": 0},
                "commands":   {"total_last_hour": 0, "completed_last_hour": 0,
                               "failed_last_hour": 0, "success_ratio": 100},
                "alerts":     {"critical": 0, "warning": 0, "total": 0},
            })

        last_hour = now - timedelta(hours=1)
        last_24h = now - timedelta(hours=24)
        heartbeat_cutoff = now - timedelta(seconds=90)

        # Compteurs devices
        devices_qs = Device.objects.filter(tenant=tenant)
        devices_total = devices_qs.count()
        devices_online = devices_qs.filter(
            status="active", last_heartbeat_at__gte=heartbeat_cutoff,
        ).count()

        # Agents
        agents_qs = LocalAgent.objects.filter(tenant=tenant)
        agents_total = agents_qs.count()
        agents_connected = agents_qs.filter(connected=True).count()

        # Sessions d'enrôlement
        sessions_active = RFIDEnrollmentSession.objects.filter(
            tenant=tenant, status="listening",
        ).count()
        scans_last_hour = RFIDEnrollmentEvent.objects.filter(
            session__tenant=tenant,
            event_type__in=["card.detected", "card.duplicate", "card.enrolled"],
            created_at__gte=last_hour,
        ).count()
        enrolled_last_24h = RFIDEnrollmentEvent.objects.filter(
            session__tenant=tenant,
            event_type="card.enrolled",
            created_at__gte=last_24h,
        ).count()

        # Commandes
        commands_last_hour = DeviceCommand.objects.filter(
            tenant=tenant, created_at__gte=last_hour,
        ).aggregate(
            total=Count("id"),
            completed=Count("id", filter=models_Q(status="completed")),
            failed=Count("id", filter=models_Q(status__in=["failed", "timeout"])),
        )

        # Alertes actives
        alerts_qs = SystemAlert.objects.filter(tenant=tenant, resolved_at__isnull=True)
        alerts_critical = alerts_qs.filter(severity="critical").count()
        alerts_warning = alerts_qs.filter(severity="warning").count()

        return Response({
            "at": now.isoformat(),
            "devices": {
                "total": devices_total,
                "online": devices_online,
                "offline": devices_total - devices_online,
                "online_ratio": (
                    round(devices_online * 100 / devices_total, 1)
                    if devices_total > 0 else 0
                ),
            },
            "agents": {
                "total": agents_total,
                "connected": agents_connected,
                "disconnected": agents_total - agents_connected,
            },
            "enrollment": {
                "sessions_active": sessions_active,
                "scans_last_hour": scans_last_hour,
                "enrolled_last_24h": enrolled_last_24h,
            },
            "commands": {
                "total_last_hour":     commands_last_hour["total"] or 0,
                "completed_last_hour": commands_last_hour["completed"] or 0,
                "failed_last_hour":    commands_last_hour["failed"] or 0,
                "success_ratio": (
                    round((commands_last_hour["completed"] or 0) * 100
                          / (commands_last_hour["total"] or 1), 1)
                    if commands_last_hour["total"] else 100
                ),
            },
            "alerts": {
                "critical": alerts_critical,
                "warning": alerts_warning,
                "total": alerts_qs.count(),
            },
        })


class SystemAlertAcknowledgeView(APIView):
    """POST /api/v1/devices/alerts/<alert_id>/acknowledge/"""
    permission_classes = [IsAuthenticated]

    def post(self, request, alert_id):
        try:
            a = SystemAlert.objects.get(pk=alert_id)
        except SystemAlert.DoesNotExist:
            return Response({"error": "Alerte introuvable"}, status=404)
        if a.tenant_id != getattr(request.user, "tenant_id", None):
            return Response({"error": "Alerte hors tenant"}, status=403)
        AlertService.acknowledge(a.pk, request.user)
        a.refresh_from_db()
        return Response(_serialize_alert(a))


class AgentPullCommandsView(APIView):
    """GET /api/v1/agent/<agent_id>/commands/ — l'agent récupère ses commandes.

    Auth : ``AgentHmacAuthentication`` (Bearer token + signature HMAC si configurée).
    """
    permission_classes = []
    authentication_classes = [AgentHmacAuthentication]

    def get(self, request, agent_id):
        agent = getattr(request, "agent", None)
        if agent is None or str(agent.pk) != str(agent_id):
            return Response({"error": "Agent hors scope"}, status=403)

        # Update heartbeat
        from django.utils import timezone
        agent.last_seen_at = timezone.now()
        agent.save(update_fields=["last_seen_at"])

        # Dépile toutes les commandes pour les devices de cet agent
        from devices.models import Device
        devices = Device.objects.filter(tenant=agent.tenant, site=agent.site)
        commands = []
        for d in devices:
            commands.extend(DeviceCommandQueue.drain_for_device(d.pk))
        return Response({"commands": commands, "at": timezone.now().isoformat()})


class AgentEventView(APIView):
    """POST /api/v1/agent/<agent_id>/events/ — l'agent push un event (singleton).

    Auth : ``AgentHmacAuthentication`` (Bearer token + signature HMAC si configurée).

    Pour un batch de plusieurs events, préférer AgentEventBatchView.
    """
    permission_classes = []
    authentication_classes = [AgentHmacAuthentication]

    def post(self, request, agent_id):
        agent = getattr(request, "agent", None)
        if agent is None or str(agent.pk) != str(agent_id):
            return Response({"error": "Agent hors scope"}, status=403)

        data = request.data or {}
        event = data.get("event")
        if event == "rfid.card.detected":
            uid = data.get("uid")
            device_id = data.get("device_id")
            device = None
            if device_id:
                try:
                    device = Device.objects.get(pk=device_id)
                except Device.DoesNotExist:
                    pass
            try:
                result = RFIDEnrollmentService.ingest_scan(
                    tenant=agent.tenant, uid=uid, device=device,
                    rssi=data.get("rssi"), extra=data.get("extra") or {},
                )
                return Response(result)
            except EnrollmentError as exc:
                return Response({"error": exc.message, "code": exc.code}, status=400)

        if event == "device.command.ack":
            DeviceCommandQueue.acknowledge(data.get("command_id"))
        elif event == "device.command.completed":
            DeviceCommandQueue.complete(
                data.get("command_id"),
                response_raw=data.get("response_raw") or {},
                response_normalized=data.get("response_normalized") or {},
            )
        elif event == "device.command.failed":
            DeviceCommandQueue.fail(
                data.get("command_id"), data.get("error") or "unknown",
            )
        elif event == "scan_network.result":
            # L'agent a scanné son LAN — on persiste les résultats sur LocalAgent
            devs = data.get("devices_discovered") or data.get("devices") or []
            if isinstance(devs, list) and agent is not None:
                agent.devices_discovered = devs[:500]
                agent.save(update_fields=["devices_discovered"])
                logger.info("Agent %s scan → %d devices", agent.pk, len(devs))
        else:
            logger.warning("Event agent inconnu : %s", event)
            return Response({"error": f"event inconnu: {event}"}, status=400)

        return Response({"ok": True})


class AgentEventBatchView(APIView):
    """POST /api/v1/agent/events/  — endpoint batch pour l'agent Go.

    Shape attendu :
        {
          "gateway_id": "uuid",
          "events": [
            {"type": "...", "occurred_at": "ISO8601", "payload": {...},
             "source_ip": "...", "source_mac": "...", "signature": "..."}
          ]
        }

    L'agent est identifié via le Bearer token (HMAC auth), le gateway_id
    dans le body sert juste de sanity check.

    Chaque event du batch est traité indépendamment via AgentEventView.
    Un échec sur un event ne bloque pas les autres.
    """
    permission_classes = []
    authentication_classes = [AgentHmacAuthentication]

    def post(self, request):
        agent = getattr(request, "agent", None)
        if agent is None or agent.revoked_at:
            return Response({"error": "Non autorisé"}, status=403)

        data = request.data or {}
        gateway_id = data.get("gateway_id")
        if gateway_id and str(gateway_id) != str(agent.pk):
            return Response({"error": "gateway_id mismatch avec token"}, status=403)

        events = data.get("events") or []
        if not isinstance(events, list):
            return Response({"error": "events doit être une liste"}, status=400)

        processed = 0
        rejected = 0
        errors = []

        for i, ev in enumerate(events):
            try:
                self._process_one(agent, ev)
                processed += 1
            except Exception as exc:  # noqa: BLE001
                rejected += 1
                errors.append({"index": i, "error": str(exc)[:200],
                                "type": ev.get("type") if isinstance(ev, dict) else "?"})

        logger.info(
            "Agent %s batch: %d processed, %d rejected",
            agent.pk, processed, rejected,
        )
        return Response({
            "ok": rejected == 0,
            "processed": processed,
            "rejected": rejected,
            "errors": errors[:20],   # capped pour éviter payload énorme
        })

    def _process_one(self, agent, ev):
        """Route un event unique vers le bon service métier.

        Le shape event Go a la clé ``type`` (pas ``event``). On normalise ici.
        """
        if not isinstance(ev, dict):
            raise ValueError("event doit être un dict")

        event_type = ev.get("type") or ev.get("event") or ""
        payload = ev.get("payload") or {}

        if event_type == "access.granted" or event_type == "access.denied":
            # TODO: hook access_control app
            logger.debug("Agent event: %s payload=%s", event_type, payload)
            return

        if event_type == "rfid.card.detected":
            uid = payload.get("uid") or payload.get("card")
            device_id = payload.get("device_id")
            device = None
            if device_id:
                try:
                    device = Device.objects.get(pk=device_id)
                except Device.DoesNotExist:
                    pass
            RFIDEnrollmentService.ingest_scan(
                tenant=agent.tenant, uid=uid, device=device,
                rssi=payload.get("rssi"), extra=payload.get("extra") or {},
            )
            return

        if event_type == "device.tamper":
            logger.warning("Device tamper: agent=%s payload=%s", agent.pk, payload)
            # TODO: hook antifraud
            return

        if event_type == "device.command.completed":
            DeviceCommandQueue.complete(
                payload.get("command_id"),
                response_raw=payload.get("response_raw") or {},
                response_normalized=payload.get("response_normalized") or {},
            )
            return

        if event_type == "device.command.failed":
            DeviceCommandQueue.fail(
                payload.get("command_id"),
                payload.get("error") or "unknown",
            )
            return

        if event_type == "scan_network.result":
            devs = payload.get("devices_discovered") or payload.get("devices") or []
            if isinstance(devs, list):
                agent.devices_discovered = devs[:500]
                agent.save(update_fields=["devices_discovered"])
            return

        # Event inconnu — on le log mais on ne rejette pas le batch entier
        logger.debug("Event agent type inconnu (skip): %s", event_type)
