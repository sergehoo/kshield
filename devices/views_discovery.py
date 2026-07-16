"""KAYDAN SHIELD — API Discovery équipements (Phase 5 refonte §2).

Endpoints agent (HMAC) — register par la gateway après scan LAN :

    POST /api/v1/devices/discovery/register/           (batch)
    POST /api/v1/devices/discovery/scan/complete/      (marque scan terminé)

Endpoints admin (JWT) :

    GET  /api/v1/devices/discovery/                    (liste pending)
    GET  /api/v1/devices/discovery/<id>/               (détail)
    POST /api/v1/devices/discovery/<id>/test/          (test connexion)
    POST /api/v1/devices/discovery/<id>/adopt/         (crée Device)
    POST /api/v1/devices/discovery/<id>/reject/
    POST /api/v1/devices/discovery/<id>/reactivate/
    GET  /api/v1/devices/discovery/scans/              (historique scans)
"""
from __future__ import annotations

from rest_framework import status as http_status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .auth_hmac import AgentHmacAuthentication
from .models_discovery import (
    DeviceDiscovery, DeviceDiscoveryScan,
)
from .services.discovery import DeviceDiscoveryService
from .utils import resolve_tenant as _resolve_tenant


# ═══════════════════════════════════════════════════════════════════
# Endpoints AGENT (HMAC)
# ═══════════════════════════════════════════════════════════════════
class AgentDiscoveryRegisterView(APIView):
    """POST /discovery/register/

    L'agent Go push les résultats d'un scan LAN.
    Body :
      {
        "scan_id": "uuid",              // optionnel, pour grouper
        "protocols_used": ["arp", "onvif"],
        "devices": [
          {
            "mac_address": "aa:bb:cc:dd:ee:ff",
            "ip_address":  "192.168.1.42",
            "hostname":    "cam-01",
            "vendor":      "Hikvision",
            "model":       "DS-2CD",
            "device_type": "ip_camera",
            "firmware_version": "5.6.1",
            "protocols":   ["onvif", "rtsp"],
            "ports":       [80, 554, 8080],
            "detected_via": "onvif",
            "latency_ms":  25
          },
          ...
        ]
      }
    """
    permission_classes = []
    authentication_classes = [AgentHmacAuthentication]

    def post(self, request):
        agent = getattr(request, "agent", None)
        if agent is None or agent.revoked_at:
            return Response({"error": "unauthorized"},
                              status=http_status.HTTP_403_FORBIDDEN)

        data = request.data or {}
        devices = data.get("devices") or []
        if not isinstance(devices, list):
            return Response({"error": "devices_must_be_list"},
                              status=http_status.HTTP_400_BAD_REQUEST)

        # Crée ou reprend un scan
        scan_id = data.get("scan_id")
        scan = None
        if scan_id:
            scan = DeviceDiscoveryScan.objects.filter(
                pk=scan_id, tenant=agent.tenant, gateway=agent,
            ).first()
        if scan is None:
            scan = DeviceDiscoveryScan.objects.create(
                tenant=agent.tenant, gateway=agent,
                site=agent.site,
                protocols_used=data.get("protocols_used") or [],
                status="running",
            )

        new_count = 0
        updated_count = 0
        errors = 0

        for dev in devices:
            if not isinstance(dev, dict):
                errors += 1
                continue
            result = DeviceDiscoveryService.register_discovered(
                tenant=agent.tenant,
                mac_address=dev.get("mac_address", ""),
                ip_address=dev.get("ip_address", ""),
                hostname=dev.get("hostname", ""),
                serial_number=dev.get("serial_number", ""),
                vendor=dev.get("vendor", ""),
                model=dev.get("model", ""),
                device_type=dev.get("device_type", ""),
                firmware_version=dev.get("firmware_version", ""),
                detected_via=dev.get("detected_via", "unknown"),
                protocols_supported=dev.get("protocols") or [],
                ports_open=dev.get("ports") or [],
                latency_ms=int(dev.get("latency_ms") or 0),
                signal_strength=dev.get("signal_strength"),
                gateway=agent,
                site=agent.site,
                scan=scan,
                raw_payload=dev.get("raw") or {},
            )
            if not result.ok:
                errors += 1
                continue
            if result.created:
                new_count += 1
            else:
                updated_count += 1

        # Update scan counters
        scan.devices_detected = new_count + updated_count
        scan.devices_new = new_count
        scan.devices_updated = updated_count
        scan.save(update_fields=[
            "devices_detected", "devices_new", "devices_updated",
        ])

        return Response({
            "ok": True,
            "scan_id": str(scan.pk),
            "new": new_count,
            "updated": updated_count,
            "errors": errors,
        })


class AgentScanCompleteView(APIView):
    """POST /discovery/scan/<scan_id>/complete/

    Marque un scan comme terminé (l'agent a fini toutes les probes).
    Body : {"duration_ms": 1234, "error": ""}
    """
    permission_classes = []
    authentication_classes = [AgentHmacAuthentication]

    def post(self, request, scan_id):
        agent = getattr(request, "agent", None)
        if agent is None:
            return Response({"error": "unauthorized"},
                              status=http_status.HTTP_403_FORBIDDEN)
        try:
            scan = DeviceDiscoveryScan.objects.get(
                pk=scan_id, tenant=agent.tenant, gateway=agent,
            )
        except DeviceDiscoveryScan.DoesNotExist:
            return Response({"error": "scan_not_found"},
                              status=http_status.HTTP_404_NOT_FOUND)

        data = request.data or {}
        scan.duration_ms = int(data.get("duration_ms") or 0)
        error = data.get("error", "")
        if error:
            scan.status = "failed"
            scan.error = error[:2000]
        else:
            scan.status = "succeeded"
        scan.save(update_fields=["status", "duration_ms", "error"])

        return Response({
            "ok": True,
            "scan_id": str(scan.pk),
            "status": scan.status,
            "devices_detected": scan.devices_detected,
        })


# ═══════════════════════════════════════════════════════════════════
# Endpoints ADMIN (JWT)
# ═══════════════════════════════════════════════════════════════════
class DiscoveryListView(APIView):
    """GET /discovery/  — liste des découvertes filtrable."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        tenant = _resolve_tenant(request.user)
        if tenant is None:
            return Response({"count": 0, "results": []})

        qs = DeviceDiscovery.objects.filter(tenant=tenant)

        # Filtres
        status_f = request.query_params.get("status")
        if status_f:
            qs = qs.filter(status=status_f)
        else:
            # Par défaut : detected + tested (attente adoption)
            qs = qs.filter(status__in=["detected", "tested"])

        vendor = request.query_params.get("vendor")
        if vendor:
            qs = qs.filter(vendor__icontains=vendor)

        gateway = request.query_params.get("gateway")
        if gateway:
            qs = qs.filter(gateway_id=gateway)

        compat = request.query_params.get("compatibility")
        if compat:
            qs = qs.filter(compatibility=compat)

        limit = min(int(request.query_params.get("limit", 100)), 500)
        total = qs.count()
        results = qs.select_related("gateway", "site")\
                    .order_by("-last_seen_at")[:limit]

        return Response({
            "count":   total,
            "results": [d.as_display_dict() for d in results],
        })


class DiscoveryDetailView(APIView):
    """GET /discovery/<id>/ — détail complet."""
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        tenant = _resolve_tenant(request.user)
        if tenant is None:
            return Response({"error": "no_tenant"},
                              status=http_status.HTTP_403_FORBIDDEN)
        try:
            d = DeviceDiscovery.objects.select_related(
                "gateway", "site", "scan", "adopted_device",
            ).get(pk=pk, tenant=tenant)
        except DeviceDiscovery.DoesNotExist:
            return Response({"error": "not_found"},
                              status=http_status.HTTP_404_NOT_FOUND)

        base = d.as_display_dict()
        base.update({
            "last_test_at":     d.last_test_at.isoformat() if d.last_test_at else None,
            "last_test_success": d.last_test_success,
            "last_test_error":   d.last_test_error,
            "last_test_response": d.last_test_response,
            "adopted_at":       d.adopted_at.isoformat() if d.adopted_at else None,
            "adopted_by":       d.adopted_by,
            "rejected_at":      d.rejected_at.isoformat() if d.rejected_at else None,
            "rejected_reason":  d.rejected_reason,
            "raw_payload":      d.raw_payload,
        })
        return Response(base)


class DiscoveryActionView(APIView):
    """POST /discovery/<id>/{test|adopt|reject|reactivate}/"""
    permission_classes = [IsAuthenticated]

    ACTIONS = {"test", "adopt", "reject", "reactivate"}

    def post(self, request, pk, action):
        if action not in self.ACTIONS:
            return Response(
                {"error": "action_invalide", "allowed": sorted(self.ACTIONS)},
                status=http_status.HTTP_400_BAD_REQUEST,
            )
        tenant = _resolve_tenant(request.user)
        if tenant is None:
            return Response({"error": "no_tenant"},
                              status=http_status.HTTP_403_FORBIDDEN)
        try:
            d = DeviceDiscovery.objects.get(pk=pk, tenant=tenant)
        except DeviceDiscovery.DoesNotExist:
            return Response({"error": "not_found"},
                              status=http_status.HTTP_404_NOT_FOUND)

        data = request.data or {}

        if action == "test":
            result = DeviceDiscoveryService.test_connection(d, deep=False)
        elif action == "adopt":
            # Site optionnel — si non fourni, on utilise discovery.site
            site = None
            if data.get("site_id"):
                from sites.models import Site
                site = Site.objects.filter(
                    pk=data["site_id"], tenant=tenant,
                ).first()
            checkpoint = None
            if data.get("checkpoint_id"):
                from sites.models import Checkpoint
                checkpoint = Checkpoint.objects.filter(
                    pk=data["checkpoint_id"],
                ).first()
            result = DeviceDiscoveryService.adopt(
                d, adopted_by=request.user, site=site, checkpoint=checkpoint,
                name=data.get("name", ""),
                driver_override=data.get("driver", ""),
            )
        elif action == "reject":
            result = DeviceDiscoveryService.reject(
                d, rejected_by=request.user, reason=data.get("reason", ""),
            )
        else:  # reactivate
            result = DeviceDiscoveryService.reactivate(d)

        if not result.ok:
            return Response(
                {"error": result.error, "code": result.error_code},
                status=http_status.HTTP_400_BAD_REQUEST,
            )

        response = {"ok": True, "action": action}
        if result.discovery:
            response["discovery"] = result.discovery.as_display_dict()
        if result.device:
            response["device_id"] = str(result.device.pk)
        return Response(response)


class DiscoveryScansListView(APIView):
    """GET /discovery/scans/ — historique des sessions de scan."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        tenant = _resolve_tenant(request.user)
        if tenant is None:
            return Response({"count": 0, "results": []})

        qs = DeviceDiscoveryScan.objects.filter(tenant=tenant)
        gateway = request.query_params.get("gateway")
        if gateway:
            qs = qs.filter(gateway_id=gateway)

        limit = min(int(request.query_params.get("limit", 50)), 200)
        total = qs.count()
        scans = qs.select_related("gateway", "site").order_by("-created_at")[:limit]

        results = [{
            "id":               str(s.pk),
            "gateway_id":       str(s.gateway_id) if s.gateway_id else None,
            "gateway_label":    s.gateway.label if s.gateway else "",
            "site_id":          s.site_id,
            "site_label":       str(s.site) if s.site else "",
            "protocols_used":   s.protocols_used,
            "duration_ms":      s.duration_ms,
            "devices_detected": s.devices_detected,
            "devices_new":      s.devices_new,
            "devices_updated":  s.devices_updated,
            "status":           s.status,
            "error":            s.error,
            "created_at":       s.created_at.isoformat(),
        } for s in scans]

        return Response({"count": total, "results": results})
