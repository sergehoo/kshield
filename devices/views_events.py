"""KAYDAN SHIELD — API Événements techniques (Phase 1 refonte).

Endpoints exposés :

    GET  /api/v1/devices/events/                Liste filtrée + pagination
    GET  /api/v1/devices/events/live/           Idem + WS URL + stats
    GET  /api/v1/devices/events/<id>/           Détail complet + acks
    POST /api/v1/devices/events/<id>/acknowledge/
    POST /api/v1/devices/events/<id>/resolve/
    POST /api/v1/devices/events/<id>/comment/
    GET  /api/v1/devices/events/types/          Catalogue nomenclature
    GET  /api/v1/devices/events/export.csv      Export CSV filtré

Filtres URL supportés (cahier des charges section 1.2) :
    ?period=today|last_hour|last_24h|custom
    ?date_from=ISO&date_to=ISO
    ?site=X&zone=Y&checkpoint=Z
    ?gateway=uuid&agent=uuid
    ?device=X&device_type=camera
    ?type=ACCESS_GRANTED (peut être répété)
    ?category=access|attendance|...
    ?severity=info|warning|critical|emergency
    ?result=granted|denied|pending|anomaly|alert
    ?holder=uid
    ?badge=uid
    ?has_helmet=true|false
    ?transmission=realtime_cloud|gateway_local|deferred_sync|offline
    ?is_offline=true|false
    ?is_synced=true|false
    ?q=texte libre (search sur message + payload)
"""
from __future__ import annotations

import csv
from datetime import timedelta

from django.db.models import Q
from django.http import StreamingHttpResponse
from django.utils import timezone
from rest_framework import status as http_status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models_events import DeviceEvent, EventType
from .services.events import EventService
from .utils import resolve_tenant as _resolve_tenant


# ═══════════════════════════════════════════════════════════════════
# Helpers filtres (partagés entre views)
# ═══════════════════════════════════════════════════════════════════
def _apply_filters(qs, params):
    """Applique tous les filtres du cahier des charges §1.2 à un queryset."""
    # Période
    period = (params.get("period") or "").strip().lower()
    now = timezone.now()
    if period == "today":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        qs = qs.filter(occurred_at__gte=start)
    elif period == "last_hour":
        qs = qs.filter(occurred_at__gte=now - timedelta(hours=1))
    elif period == "last_24h":
        qs = qs.filter(occurred_at__gte=now - timedelta(hours=24))
    elif period == "last_7d":
        qs = qs.filter(occurred_at__gte=now - timedelta(days=7))
    else:
        # Custom range
        date_from = params.get("date_from")
        date_to = params.get("date_to")
        if date_from:
            qs = qs.filter(occurred_at__gte=date_from)
        if date_to:
            qs = qs.filter(occurred_at__lte=date_to)

    # Localisation
    if site := params.get("site"):
        qs = qs.filter(site_id=site)
    if zone := params.get("zone"):
        qs = qs.filter(zone_id=zone)
    if checkpoint := params.get("checkpoint"):
        qs = qs.filter(checkpoint_id=checkpoint)

    # Sources techniques
    if gateway := params.get("gateway"):
        qs = qs.filter(gateway_id=gateway)
    if agent := params.get("agent"):
        qs = qs.filter(agent_id=agent)
    if device := params.get("device"):
        qs = qs.filter(device_id=device)

    # Types + catégorie
    types = params.getlist("type") if hasattr(params, "getlist") else \
            [params.get("type")] if params.get("type") else []
    if types:
        qs = qs.filter(event_type__code__in=types)
    if category := params.get("category"):
        qs = qs.filter(event_type__category=category)

    # Sévérité + résultat
    if severity := params.get("severity"):
        qs = qs.filter(severity=severity)
    if result := params.get("result"):
        qs = qs.filter(result=result)

    # Personnes + badges
    if holder := params.get("holder"):
        qs = qs.filter(holder_ref=holder)
    if badge := params.get("badge"):
        qs = qs.filter(badge_uid=badge)
    has_helmet = params.get("has_helmet")
    if has_helmet in ("true", "1"):
        qs = qs.exclude(helmet_uid="")
    elif has_helmet in ("false", "0"):
        qs = qs.filter(helmet_uid="")

    # Transmission
    if tx := params.get("transmission"):
        qs = qs.filter(transmission_mode=tx)
    is_offline = params.get("is_offline")
    if is_offline in ("true", "1"):
        qs = qs.filter(is_offline=True)
    elif is_offline in ("false", "0"):
        qs = qs.filter(is_offline=False)
    is_synced = params.get("is_synced")
    if is_synced in ("true", "1"):
        qs = qs.filter(is_synced=True)
    elif is_synced in ("false", "0"):
        qs = qs.filter(is_synced=False)

    # Texte libre
    if q := params.get("q"):
        qs = qs.filter(
            Q(message__icontains=q)
            | Q(badge_uid__icontains=q)
            | Q(helmet_uid__icontains=q)
            | Q(holder_ref__icontains=q)
            | Q(event_type__code__icontains=q)
        )

    return qs


def _serialize_event(event: DeviceEvent, full: bool = False) -> dict:
    """Serialize un DeviceEvent pour l'API.

    ``full=False`` (défaut) → forme compacte pour la liste.
    ``full=True``  → forme complète avec payload + acks pour la modale détail.
    """
    d = EventService.serialize_for_ws(event)
    # Enrichit avec labels lisibles
    if event.site_id:
        d["site_label"] = str(event.site) if event.site else ""
    if event.device_id:
        d["device_label"] = event.device.name if event.device else ""
        d["device_type"] = (
            event.device.type if event.device and hasattr(event.device, "type") else ""
        )
    if event.gateway_id and event.gateway:
        d["gateway_label"] = event.gateway.label

    if full:
        d["payload"] = event.payload
        d["acknowledgements"] = [
            {
                "id":           str(a.pk),
                "action":       a.action,
                "user":         str(a.user),
                "user_id":      a.user_id,
                "notes":        a.notes,
                "evidence_url": a.evidence_url,
                "created_at":   a.created_at.isoformat(),
            }
            for a in event.acknowledgements.order_by("-created_at")
        ]
        d["ack_count"] = event.acknowledgements.count()
        d["is_acknowledged"] = event.acknowledgements.filter(
            action="acknowledge",
        ).exists()
        d["is_resolved"] = event.acknowledgements.filter(
            action="resolve",
        ).exists()

    return d


def _base_queryset(request):
    """QuerySet de base scopé au tenant."""
    tenant = _resolve_tenant(request.user)
    if tenant is None:
        return DeviceEvent.objects.none(), None
    return (
        DeviceEvent.objects
            .filter(tenant=tenant)
            .select_related("event_type", "site", "zone", "device",
                             "gateway", "agent")
    ), tenant


# ═══════════════════════════════════════════════════════════════════
# GET /api/v1/devices/events/  — Liste + filtres + pagination
# ═══════════════════════════════════════════════════════════════════
class DeviceEventListView(APIView):
    """GET liste paginée d'événements avec les filtres complets §1.2."""
    permission_classes = [IsAuthenticated]

    DEFAULT_PAGE_SIZE = 50
    MAX_PAGE_SIZE = 500

    def get(self, request):
        qs, tenant = _base_queryset(request)
        if tenant is None:
            return Response({"count": 0, "results": [], "warning": "no_tenant"})

        qs = _apply_filters(qs, request.query_params)

        # Pagination
        try:
            page_size = min(
                int(request.query_params.get("page_size") or self.DEFAULT_PAGE_SIZE),
                self.MAX_PAGE_SIZE,
            )
            page = max(int(request.query_params.get("page") or 1), 1)
        except ValueError:
            page_size, page = self.DEFAULT_PAGE_SIZE, 1

        total = qs.count()
        start = (page - 1) * page_size
        events = qs[start:start + page_size]

        return Response({
            "count":      total,
            "page":       page,
            "page_size":  page_size,
            "num_pages":  max(1, -(-total // page_size)),  # ceil
            "results":    [_serialize_event(e) for e in events],
        })


# ═══════════════════════════════════════════════════════════════════
# GET /api/v1/devices/events/live/  — Liste + WS URL + stats live
# ═══════════════════════════════════════════════════════════════════
class DeviceEventLiveView(APIView):
    """Complète DeviceEventListView avec les infos temps réel :
       - URL WebSocket pour souscrire au flux
       - Stats live (compteurs par catégorie / sévérité)
       - Timestamp serveur pour clock skew display
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs, tenant = _base_queryset(request)
        if tenant is None:
            return Response({"count": 0, "results": [], "warning": "no_tenant"})

        qs = _apply_filters(qs, request.query_params)

        # Limite basse pour affichage initial (le reste vient via WS)
        limit = min(int(request.query_params.get("limit") or 100), 500)
        events = qs[:limit]

        # Stats compactes des dernières 24h
        now = timezone.now()
        last_24h = qs.filter(occurred_at__gte=now - timedelta(hours=24))

        stats_by_severity = {
            "info":       last_24h.filter(severity="info").count(),
            "warning":    last_24h.filter(severity="warning").count(),
            "critical":   last_24h.filter(severity="critical").count(),
            "emergency":  last_24h.filter(severity="emergency").count(),
        }
        stats_by_result = {
            "granted": last_24h.filter(result="granted").count(),
            "denied":  last_24h.filter(result="denied").count(),
            "anomaly": last_24h.filter(result="anomaly").count(),
            "alert":   last_24h.filter(result="alert").count(),
        }

        return Response({
            "server_time":  now.isoformat(),
            "count":        qs.count(),
            "returned":     len(events),
            "ws_url":       f"/ws/events/{tenant.pk}/",
            "stats_24h":    {
                "by_severity": stats_by_severity,
                "by_result":   stats_by_result,
                "total":       last_24h.count(),
            },
            "results":      [_serialize_event(e) for e in events],
        })


# ═══════════════════════════════════════════════════════════════════
# GET /api/v1/devices/events/<uuid>/  — Détail complet
# ═══════════════════════════════════════════════════════════════════
class DeviceEventDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, event_id):
        qs, tenant = _base_queryset(request)
        if tenant is None:
            return Response({"error": "no_tenant"}, status=http_status.HTTP_403_FORBIDDEN)
        try:
            event = qs.get(pk=event_id)
        except DeviceEvent.DoesNotExist:
            return Response({"error": "not_found"}, status=http_status.HTTP_404_NOT_FOUND)
        return Response(_serialize_event(event, full=True))


# ═══════════════════════════════════════════════════════════════════
# POST /api/v1/devices/events/<uuid>/{acknowledge|resolve|comment}/
# ═══════════════════════════════════════════════════════════════════
class DeviceEventActionView(APIView):
    permission_classes = [IsAuthenticated]

    ACTIONS = {"acknowledge", "resolve", "comment"}

    def post(self, request, event_id, action):
        if action not in self.ACTIONS:
            return Response(
                {"error": "action_invalide", "allowed": sorted(self.ACTIONS)},
                status=http_status.HTTP_400_BAD_REQUEST,
            )
        qs, tenant = _base_queryset(request)
        if tenant is None:
            return Response({"error": "no_tenant"}, status=http_status.HTTP_403_FORBIDDEN)
        try:
            event = qs.get(pk=event_id)
        except DeviceEvent.DoesNotExist:
            return Response({"error": "not_found"}, status=http_status.HTTP_404_NOT_FOUND)

        data = request.data or {}
        notes = (data.get("notes") or "")[:2000]
        evidence_url = data.get("evidence_url") or ""

        if action == "acknowledge":
            ack = EventService.acknowledge(event, request.user, notes=notes)
        elif action == "resolve":
            ack = EventService.resolve(event, request.user, notes=notes,
                                          evidence_url=evidence_url)
        else:
            if not notes:
                return Response({"error": "notes_requises"},
                                status=http_status.HTTP_400_BAD_REQUEST)
            ack = EventService.comment(event, request.user, notes=notes)

        return Response({
            "ok":    True,
            "action": action,
            "ack": {
                "id":         str(ack.pk),
                "created_at": ack.created_at.isoformat(),
                "user":       str(ack.user),
            },
        })


# ═══════════════════════════════════════════════════════════════════
# GET /api/v1/devices/events/types/  — Catalogue nomenclature
# ═══════════════════════════════════════════════════════════════════
class EventTypeCatalogView(APIView):
    """Retourne la nomenclature complète des EventType pour les selects UI."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = EventType.objects.filter(is_active=True).order_by("category", "code")
        by_category: dict = {}
        for et in qs:
            by_category.setdefault(et.category, []).append({
                "code":             et.code,
                "label":            et.label,
                "severity_default": et.severity_default,
                "result_default":   et.result_default,
                "icon":             et.icon,
                "color":            et.color,
                "triggers_alert":   et.triggers_alert,
                "requires_ack":     et.requires_ack,
            })
        return Response({
            "count":      qs.count(),
            "categories": by_category,
        })


# ═══════════════════════════════════════════════════════════════════
# GET /api/v1/devices/events/export.csv  — Export filtré
# ═══════════════════════════════════════════════════════════════════
class DeviceEventExportView(APIView):
    """Export CSV streamé des événements filtrés.

    Utilise StreamingHttpResponse pour supporter les gros exports
    (100k+ events) sans exploser la RAM.
    """
    permission_classes = [IsAuthenticated]

    HEADERS = [
        "occurred_at", "received_at", "code", "category", "severity",
        "result", "site", "zone", "device_id", "gateway_id", "agent_id",
        "badge_uid", "helmet_uid", "holder_kind", "holder_ref",
        "transmission_mode", "is_offline", "message",
    ]
    MAX_ROWS = 100_000

    def get(self, request):
        qs, tenant = _base_queryset(request)
        if tenant is None:
            return Response({"error": "no_tenant"},
                              status=http_status.HTTP_403_FORBIDDEN)
        qs = _apply_filters(qs, request.query_params)[:self.MAX_ROWS]

        def _iter():
            # Écrire headers puis chaque row via csv.writer avec buffer
            import io
            buf = io.StringIO()
            writer = csv.writer(buf)
            writer.writerow(self.HEADERS)
            yield buf.getvalue()
            buf.seek(0); buf.truncate()

            for e in qs.iterator(chunk_size=1000):
                writer.writerow([
                    e.occurred_at.isoformat(),
                    e.received_at.isoformat(),
                    e.event_type.code,
                    e.event_type.category,
                    e.severity,
                    e.result,
                    str(e.site) if e.site else "",
                    str(e.zone) if e.zone else "",
                    e.device_id or "",
                    str(e.gateway_id) if e.gateway_id else "",
                    str(e.agent_id) if e.agent_id else "",
                    e.badge_uid,
                    e.helmet_uid,
                    e.holder_kind,
                    e.holder_ref,
                    e.transmission_mode,
                    "1" if e.is_offline else "0",
                    e.message[:200],
                ])
                yield buf.getvalue()
                buf.seek(0); buf.truncate()

        response = StreamingHttpResponse(_iter(), content_type="text/csv")
        response["Content-Disposition"] = \
            f'attachment; filename="kshield-events-{timezone.now():%Y%m%d-%H%M}.csv"'
        return response
