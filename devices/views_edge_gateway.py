"""KAYDAN SHIELD — Endpoints Edge Gateway (Vague 9).

Provisioning enrichi + supervision + actions administrateur + registration
au premier boot du Gateway.

Vues :
    Catalogue packages : GET  /devices/edge-gateway/packages/
                         GET  /devices/edge-gateway/packages/<id>/install-command/?platform=…
                         GET  /devices/edge-gateway/packages/<id>/download/  (redirige vers le .file)
    Provisioning       : POST /devices/edge-gateway/          → nouveau Gateway + activation_token
                         POST /devices/edge-gateway/<id>/rotate-activation/
                         POST /devices/edge-gateway/<id>/revoke/
                         POST /devices/edge-gateway/<id>/reactivate/
    Actions            : POST /devices/edge-gateway/<id>/restart/
                         POST /devices/edge-gateway/<id>/force-sync/
                         POST /devices/edge-gateway/<id>/scan-network/
                         POST /devices/edge-gateway/<id>/update/
    Supervision        : GET  /devices/edge-gateway/<id>/     → détail temps réel
                         GET  /devices/edge-gateway/<id>/logs/
                         GET  /devices/edge-gateway/<id>/devices/
    Registration       : POST /devices/edge-gateway/activate/ → appairage boot Gateway
"""
from __future__ import annotations

import logging
import secrets
from datetime import timedelta
from typing import Optional

from django.db import transaction
from django.http import HttpResponse, HttpResponseRedirect
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .auth_hmac import AgentHmacAuthentication
from .models import EdgeGatewayPackage, LocalAgent

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════
# Helpers communs
# ═══════════════════════════════════════════════════════════════════
from .utils import resolve_tenant as _resolve_tenant  # noqa: E402


# ═══════════════════════════════════════════════════════════════════
# Serializers manuels (léger — évite de créer une classe DRF par vue)
# ═══════════════════════════════════════════════════════════════════
def _serialize_package(p: EdgeGatewayPackage, request=None) -> dict:
    file_url = None
    if p.file:
        try:
            file_url = request.build_absolute_uri(p.file.url) if request else p.file.url
        except Exception:
            file_url = None
    return {
        "id": p.pk,
        "name": p.name,
        "platform": p.platform,
        "platform_label": p.get_platform_display(),
        "version": p.version,
        "size_bytes": p.size_bytes,
        "checksum_sha256": p.checksum_sha256,
        "release_notes": p.release_notes,
        "published_at": p.published_at.isoformat() if p.published_at else None,
        "is_latest": p.is_latest,
        "min_os_version": p.min_os_version,
        "file_url": file_url,
        "docker_image": p.docker_image,
        "has_file": bool(p.file),
    }


def _serialize_gateway(a: LocalAgent, *, include_secrets: bool = False) -> dict:
    now = timezone.now()
    d = {
        "id": str(a.pk),
        "label": a.label,
        "site_id": a.site_id,
        "connected": a.connected,
        "last_seen_at": a.last_seen_at.isoformat() if a.last_seen_at else None,
        "activated_at": a.activated_at.isoformat() if a.activated_at else None,
        "revoked_at": a.revoked_at.isoformat() if a.revoked_at else None,
        "activation_expires_at": (
            a.activation_expires_at.isoformat() if a.activation_expires_at else None
        ),
        "ip_local": a.ip_local,
        "ip_public": a.ip_public,
        "os_info": a.os_info,
        "version": a.version,
        "uptime_seconds": a.uptime_seconds,
        "events_pending": a.events_pending,
        "devices_discovered_count": len(a.devices_discovered or []),
        "mqtt_status": a.mqtt_status,
        "ws_status": a.ws_status,
        "cloud_status": a.cloud_status,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }
    # Compute status global : activated ? revoked ? connected ?
    if a.revoked_at:
        d["status"] = "revoked"
    elif not a.activated_at:
        expired = (a.activation_expires_at and a.activation_expires_at < now)
        d["status"] = "activation_expired" if expired else "pending_activation"
    elif a.connected:
        d["status"] = "connected"
    else:
        d["status"] = "disconnected"

    if include_secrets:
        d["api_token"] = a.api_token
        d["hmac_secret"] = a.hmac_secret or ""
        d["activation_token"] = a.activation_token
    return d


# ═══════════════════════════════════════════════════════════════════
# Catalogue packages
# ═══════════════════════════════════════════════════════════════════
class PackageListView(APIView):
    """GET /api/v1/devices/edge-gateway/packages/?platform=…&latest=true"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = EdgeGatewayPackage.objects.all()
        platform = request.query_params.get("platform")
        if platform:
            qs = qs.filter(platform=platform)
        if request.query_params.get("latest") == "true":
            qs = qs.filter(is_latest=True)
        packages = [_serialize_package(p, request) for p in qs]
        # Groupé par plateforme si pas de filtre
        by_platform: dict[str, list] = {}
        for p in packages:
            by_platform.setdefault(p["platform"], []).append(p)
        return Response({"count": len(packages),
                          "packages": packages,
                          "by_platform": by_platform})


class PackageInstallCommandView(APIView):
    """GET /api/v1/devices/edge-gateway/packages/<id>/install-command/

    Retourne une commande shell copier-collable pour installer le package sur
    la plateforme cible. Le token du gateway est injecté si ``gateway_id`` fourni.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, pkg_id):
        try:
            p = EdgeGatewayPackage.objects.get(pk=pkg_id)
        except EdgeGatewayPackage.DoesNotExist:
            return Response({"error": "Package introuvable"}, status=404)

        gateway_id = request.query_params.get("gateway_id")
        activation_token = None
        if gateway_id:
            try:
                a = LocalAgent.objects.get(
                    pk=gateway_id,
                    tenant_id=getattr(request.user, "tenant_id", None),
                )
                activation_token = a.activation_token or ""
            except LocalAgent.DoesNotExist:
                pass

        cmd = _build_install_command(p, request, activation_token)
        return Response({
            "package_id": p.pk,
            "platform": p.platform,
            "command": cmd,
            "requires_token": bool(gateway_id),
        })


def _build_install_command(p: EdgeGatewayPackage, request, activation_token: Optional[str]) -> str:
    """Génère la commande shell selon la plateforme.

    Injecte le server_url + activation_token pour que l'installation crée
    directement le fichier de config prêt à l'usage.
    """
    scheme = "https" if request.is_secure() else "http"
    host = request.get_host()
    server_url = f"{scheme}://{host}"
    token_line = f"KSHIELD_ACTIVATION_TOKEN={activation_token}" if activation_token else "KSHIELD_ACTIVATION_TOKEN=<PASTE_TOKEN_HERE>"

    file_url = ""
    if p.file:
        try:
            file_url = request.build_absolute_uri(p.file.url)
        except Exception:
            pass

    if p.platform == "windows":
        return (
            f"# PowerShell (admin)\n"
            f"$env:KSHIELD_SERVER_URL='{server_url}'\n"
            f"$env:{token_line}\n"
            f"Invoke-WebRequest -Uri '{file_url}' -OutFile kshield-edge.msi\n"
            f"Get-FileHash kshield-edge.msi -Algorithm SHA256\n"
            f"# Attendu: {p.checksum_sha256}\n"
            f"msiexec /i kshield-edge.msi /quiet"
        )
    if p.platform in ("linux_deb",):
        return (
            f"# Debian/Ubuntu\n"
            f"curl -fsSL '{file_url}' -o kshield-edge.deb\n"
            f"echo '{p.checksum_sha256}  kshield-edge.deb' | sha256sum -c -\n"
            f"sudo dpkg -i kshield-edge.deb\n"
            f"sudo tee /etc/kshield-edge/environment << EOF\n"
            f"KSHIELD_SERVER_URL={server_url}\n"
            f"{token_line}\n"
            f"EOF\n"
            f"sudo systemctl enable --now kshield-edge"
        )
    if p.platform in ("linux_rpm",):
        return (
            f"# CentOS/Fedora/RHEL\n"
            f"curl -fsSL '{file_url}' -o kshield-edge.rpm\n"
            f"echo '{p.checksum_sha256}  kshield-edge.rpm' | sha256sum -c -\n"
            f"sudo rpm -i kshield-edge.rpm\n"
            f"sudo tee /etc/kshield-edge/environment << EOF\n"
            f"KSHIELD_SERVER_URL={server_url}\n"
            f"{token_line}\n"
            f"EOF\n"
            f"sudo systemctl enable --now kshield-edge"
        )
    if p.platform in ("linux_sh", "raspberry_pi", "mini_pc"):
        return (
            f"# Script d'installation universel\n"
            f"curl -fsSL '{file_url}' -o install-edge.sh\n"
            f"echo '{p.checksum_sha256}  install-edge.sh' | sha256sum -c -\n"
            f"chmod +x install-edge.sh\n"
            f"sudo KSHIELD_SERVER_URL='{server_url}' {token_line} ./install-edge.sh"
        )
    if p.platform == "docker":
        img = p.docker_image or "kaydangroupe/kshield-edge:latest"
        return (
            f"# Docker\n"
            f"docker pull {img}\n"
            f"docker run -d --name kshield-edge \\\n"
            f"  --restart unless-stopped \\\n"
            f"  --network host \\\n"
            f"  -e KSHIELD_SERVER_URL='{server_url}' \\\n"
            f"  -e {token_line} \\\n"
            f"  -v /var/lib/kshield-edge:/data \\\n"
            f"  {img}"
        )
    return f"# Plateforme non gérée : {p.platform}"


class PackageDownloadView(APIView):
    """GET /api/v1/devices/edge-gateway/packages/<id>/download/

    Log l'accès puis redirige vers l'URL du fichier (backend média ou MinIO).
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, pkg_id):
        try:
            p = EdgeGatewayPackage.objects.get(pk=pkg_id)
        except EdgeGatewayPackage.DoesNotExist:
            return Response({"error": "Package introuvable"}, status=404)
        if not p.file:
            return Response({"error": "Fichier non disponible (image Docker only)"},
                            status=404)
        logger.info("Package %s downloaded by user=%s", p.pk, request.user.pk)
        return HttpResponseRedirect(p.file.url)


# ═══════════════════════════════════════════════════════════════════
# Provisioning Gateway
# ═══════════════════════════════════════════════════════════════════
ACTIVATION_TOKEN_TTL_HOURS = 24


class GatewayListCreateView(APIView):
    """GET / POST /api/v1/devices/edge-gateway/

    GET → liste des gateways du tenant + supervision temps réel.
    POST → provisionne un nouveau Gateway avec token d'activation à usage unique.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        tenant = _resolve_tenant(request.user)
        if tenant is None:
            return Response({"count": 0, "gateways": []})
        qs = LocalAgent.objects.filter(tenant=tenant).order_by("-last_seen_at")
        return Response({
            "count": qs.count(),
            "gateways": [_serialize_gateway(a) for a in qs],
        })

    def post(self, request):
        tenant = _resolve_tenant(request.user)
        if tenant is None:
            return Response(
                {"error": "Impossible de résoudre un tenant pour cet utilisateur. "
                          "Assigner le user à une filiale ou créer un tenant par défaut."},
                status=403,
            )

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

        with transaction.atomic():
            agent = LocalAgent.objects.create(
                tenant=tenant, label=label, site=site,
                api_token=secrets.token_urlsafe(32),
                hmac_secret=secrets.token_urlsafe(32),
                activation_token=secrets.token_urlsafe(24),
                activation_expires_at=(
                    timezone.now() + timedelta(hours=ACTIVATION_TOKEN_TTL_HOURS)
                ),
            )
        return Response({
            **_serialize_gateway(agent, include_secrets=True),
            "activation_ttl_hours": ACTIVATION_TOKEN_TTL_HOURS,
            "activation_pairing_url": _build_pairing_url(request, agent),
        }, status=201)


def _build_pairing_url(request, agent: LocalAgent) -> str:
    """URL de pairing courte pour le QR code (l'agent la scanne pour bootstrap)."""
    scheme = "https" if request.is_secure() else "http"
    host = request.get_host()
    return (
        f"{scheme}://{host}/api/v1/devices/edge-gateway/activate/"
        f"?token={agent.activation_token or ''}"
    )


class GatewayPairingQrView(APIView):
    """GET /api/v1/devices/edge-gateway/<id>/pairing-qr.png

    Retourne un QR code PNG contenant l'activation_pairing_url du Gateway.
    L'admin scanne depuis la machine hôte pour bootstrap l'agent sans copier
    manuellement le token.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, gid):
        try:
            a = LocalAgent.objects.get(pk=gid,
                                         tenant_id=getattr(request.user, "tenant_id", None))
        except LocalAgent.DoesNotExist:
            return Response({"error": "Gateway introuvable"}, status=404)
        if not a.activation_token:
            return Response({"error": "Aucun token d'activation actif"}, status=400)

        try:
            import io
            import qrcode

            pairing_url = _build_pairing_url(request, a)
            img = qrcode.make(pairing_url)
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            resp = HttpResponse(buf.getvalue(), content_type="image/png")
            resp["Cache-Control"] = "no-store"
            return resp
        except Exception as exc:
            return Response({"error": str(exc)}, status=500)


class GatewayDetailView(APIView):
    """GET / PATCH / DELETE /api/v1/devices/edge-gateway/<id>/"""
    permission_classes = [IsAuthenticated]

    def _get(self, request, gid):
        try:
            a = LocalAgent.objects.get(pk=gid)
        except LocalAgent.DoesNotExist:
            return None
        if a.tenant_id != getattr(request.user, "tenant_id", None):
            return None
        return a

    def get(self, request, gid):
        a = self._get(request, gid)
        if a is None:
            return Response({"error": "Gateway introuvable"}, status=404)
        # Enrichit avec logs récents
        return Response({
            **_serialize_gateway(a),
            "devices_discovered": (a.devices_discovered or [])[-50:],
        })

    def patch(self, request, gid):
        a = self._get(request, gid)
        if a is None:
            return Response({"error": "Gateway introuvable"}, status=404)
        data = request.data or {}
        if "label" in data:
            a.label = data["label"][:120]
        if "site_id" in data:
            if data["site_id"]:
                from sites.models import Site
                try:
                    a.site = Site.objects.get(pk=data["site_id"])
                except Site.DoesNotExist:
                    return Response({"error": "Site introuvable"}, status=404)
            else:
                a.site = None
        a.save()
        return Response(_serialize_gateway(a))

    def delete(self, request, gid):
        a = self._get(request, gid)
        if a is None:
            return Response({"error": "Gateway introuvable"}, status=404)
        a.delete()
        return Response({"ok": True})


class GatewayRotateActivationView(APIView):
    """POST /api/v1/devices/edge-gateway/<id>/rotate-activation/

    Régénère un activation_token (utile si l'admin doit ré-appairer un Gateway).
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, gid):
        try:
            a = LocalAgent.objects.get(pk=gid,
                                         tenant_id=getattr(request.user, "tenant_id", None))
        except LocalAgent.DoesNotExist:
            return Response({"error": "Gateway introuvable"}, status=404)
        a.activation_token = secrets.token_urlsafe(24)
        a.activation_expires_at = timezone.now() + timedelta(hours=ACTIVATION_TOKEN_TTL_HOURS)
        a.save(update_fields=["activation_token", "activation_expires_at"])
        return Response({
            **_serialize_gateway(a, include_secrets=True),
            "activation_pairing_url": _build_pairing_url(request, a),
        })


class GatewayRevokeView(APIView):
    """POST /api/v1/devices/edge-gateway/<id>/revoke/"""
    permission_classes = [IsAuthenticated]

    def post(self, request, gid):
        try:
            a = LocalAgent.objects.get(pk=gid,
                                         tenant_id=getattr(request.user, "tenant_id", None))
        except LocalAgent.DoesNotExist:
            return Response({"error": "Gateway introuvable"}, status=404)
        a.revoked_at = timezone.now()
        a.connected = False
        a.channel_name = ""
        a.save(update_fields=["revoked_at", "connected", "channel_name"])
        return Response(_serialize_gateway(a))


class GatewayReactivateView(APIView):
    """POST /api/v1/devices/edge-gateway/<id>/reactivate/

    Annule la révocation + génère un nouveau token d'activation.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, gid):
        try:
            a = LocalAgent.objects.get(pk=gid,
                                         tenant_id=getattr(request.user, "tenant_id", None))
        except LocalAgent.DoesNotExist:
            return Response({"error": "Gateway introuvable"}, status=404)
        a.revoked_at = None
        a.activated_at = None
        a.api_token = secrets.token_urlsafe(32)
        a.hmac_secret = secrets.token_urlsafe(32)
        a.activation_token = secrets.token_urlsafe(24)
        a.activation_expires_at = timezone.now() + timedelta(hours=ACTIVATION_TOKEN_TTL_HOURS)
        a.save()
        return Response({
            **_serialize_gateway(a, include_secrets=True),
            "activation_pairing_url": _build_pairing_url(request, a),
        })


# ═══════════════════════════════════════════════════════════════════
# Actions administrateur (push commande vers Gateway)
# ═══════════════════════════════════════════════════════════════════
class GatewayActionView(APIView):
    """Base — actions poussées via l'EventBus vers le canal WS de l'agent."""
    permission_classes = [IsAuthenticated]
    action_type: str = ""

    def _get(self, request, gid):
        try:
            a = LocalAgent.objects.get(pk=gid,
                                         tenant_id=getattr(request.user, "tenant_id", None))
        except LocalAgent.DoesNotExist:
            return None
        return a

    def _push(self, agent, payload):
        """Push l'action sur les 2 canaux temps réel simultanément :
        - WebSocket (Django Channels → agent WS client)
        - MQTT (broker → agent MQTT sub sur kshield/cmd/edge/<id>/#)

        L'agent recevra la commande via le premier canal joignable.
        L'exécution est idempotente côté agent (dispatcher dédup par action_id).
        """
        from .services.event_bus import EventBus
        EventBus.push_to_agent(agent.pk, payload)

        # Publie aussi via MQTT — non-bloquant, fail-safe.
        try:
            from .services.mqtt_publisher import publish_command
            mqtt_res = publish_command(
                gateway_id=str(agent.pk),
                action_type=self.action_type,
                payload=payload,
            )
            if not mqtt_res.get("ok"):
                logger.debug("MQTT publish partial fail: %s", mqtt_res.get("error"))
        except Exception as exc:
            # MQTT indisponible ne doit pas bloquer l'API — le WS a déjà
            # pris le relais et la queue pending_actions (heartbeat) le fera aussi.
            logger.debug("MQTT publish exception (ignoré): %s", exc)

    def post(self, request, gid):
        a = self._get(request, gid)
        if a is None:
            return Response({"error": "Gateway introuvable"}, status=404)
        if a.revoked_at:
            return Response({"error": "Gateway révoqué"}, status=403)
        payload = self._payload(request)
        self._push(a, payload)
        logger.info("Gateway %s : action %s poussée (WS+MQTT)", a.pk, self.action_type)
        return Response({"ok": True, "action": self.action_type})

    def _payload(self, request) -> dict:
        return {"action": self.action_type}


class GatewayRestartView(GatewayActionView):
    """POST /edge-gateway/<id>/restart/"""
    action_type = "restart"


class GatewayForceSyncView(GatewayActionView):
    """POST /edge-gateway/<id>/force-sync/"""
    action_type = "force_sync"


class GatewayScanNetworkView(GatewayActionView):
    """POST /edge-gateway/<id>/scan-network/"""
    action_type = "scan_network"

    def _payload(self, request):
        return {"action": self.action_type,
                 "protocols": (request.data or {}).get("protocols", ["arp", "mdns"])}


class GatewayUpdateView(GatewayActionView):
    """POST /edge-gateway/<id>/update/  → pousse un ordre d'upgrade avec URL du package."""
    action_type = "update"

    def _payload(self, request):
        data = request.data or {}
        package_id = data.get("package_id")
        package_url = None
        checksum = ""
        if package_id:
            try:
                p = EdgeGatewayPackage.objects.get(pk=package_id)
                if p.file:
                    package_url = request.build_absolute_uri(p.file.url)
                checksum = p.checksum_sha256
            except EdgeGatewayPackage.DoesNotExist:
                pass
        return {"action": self.action_type,
                 "package_id": package_id,
                 "package_url": package_url,
                 "checksum": checksum}


class GatewayLogsView(APIView):
    """GET /edge-gateway/<id>/logs/ — logs récents captés côté serveur.

    Compose : heartbeats DB + événements WS/HTTP du cache Redis.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, gid):
        from django.core.cache import cache
        try:
            a = LocalAgent.objects.get(pk=gid,
                                         tenant_id=getattr(request.user, "tenant_id", None))
        except LocalAgent.DoesNotExist:
            return Response({"error": "Gateway introuvable"}, status=404)

        # Historique côté serveur (poussés par l'agent via WS)
        logs = cache.get(f"gateway_logs:{a.pk}") or []
        return Response({
            "gateway_id": str(a.pk),
            "count": len(logs),
            "logs": logs[-200:],
        })


class GatewayDevicesView(APIView):
    """GET /edge-gateway/<id>/devices/ — équipements découverts par l'agent."""
    permission_classes = [IsAuthenticated]

    def get(self, request, gid):
        try:
            a = LocalAgent.objects.get(pk=gid,
                                         tenant_id=getattr(request.user, "tenant_id", None))
        except LocalAgent.DoesNotExist:
            return Response({"error": "Gateway introuvable"}, status=404)
        return Response({
            "gateway_id": str(a.pk),
            "count": len(a.devices_discovered or []),
            "devices": a.devices_discovered or [],
        })


# ═══════════════════════════════════════════════════════════════════
# GatewayTarget CRUD (Phase 3 — équipements vendors)
# ═══════════════════════════════════════════════════════════════════
class GatewayTargetsView(APIView):
    """GET / POST /api/v1/devices/edge-gateway/<gid>/targets/

    GET : liste des targets de la gateway.
    POST : crée un nouveau target (body = {vendor, ip, port, username,
      password, label, extra, enabled}).
    """
    permission_classes = [IsAuthenticated]

    def _get_gateway(self, request, gid):
        tenant = _resolve_tenant(request.user)
        if tenant is None:
            return None, Response({"error": "Aucun tenant"}, status=403)
        try:
            return LocalAgent.objects.get(pk=gid, tenant=tenant), None
        except LocalAgent.DoesNotExist:
            return None, Response({"error": "Gateway introuvable"}, status=404)

    def get(self, request, gid):
        gw, err = self._get_gateway(request, gid)
        if err is not None:
            return err
        from .models import GatewayTarget
        targets = GatewayTarget.objects.filter(gateway=gw).order_by("vendor", "label")
        return Response({
            "count": targets.count(),
            "targets": [_serialize_target(t) for t in targets],
        })

    def post(self, request, gid):
        gw, err = self._get_gateway(request, gid)
        if err is not None:
            return err
        from .models import GatewayTarget

        data = request.data or {}
        if not data.get("vendor") or not data.get("ip"):
            return Response({"error": "vendor et ip requis"}, status=400)

        try:
            t = GatewayTarget.objects.create(
                gateway=gw,
                vendor=(data.get("vendor") or "").strip()[:24],
                ip=data["ip"],
                port=int(data.get("port") or 0),
                label=(data.get("label") or "")[:120],
                username=(data.get("username") or "")[:120],
                password=data.get("password") or "",
                mac=(data.get("mac") or "")[:17],
                model=(data.get("model") or "")[:80],
                serial_number=(data.get("serial_number") or "")[:64],
                extra=data.get("extra") or {},
                enabled=bool(data.get("enabled", True)),
            )
        except Exception as exc:
            return Response({"error": str(exc)}, status=400)

        return Response(_serialize_target(t), status=201)


class GatewayTargetDetailView(APIView):
    """GET / PATCH / DELETE /api/v1/devices/edge-gateway/<gid>/targets/<tid>/"""
    permission_classes = [IsAuthenticated]

    def _get(self, request, gid, tid):
        tenant = _resolve_tenant(request.user)
        if tenant is None:
            return None, Response({"error": "Aucun tenant"}, status=403)
        from .models import GatewayTarget
        try:
            t = GatewayTarget.objects.get(pk=tid, gateway_id=gid, gateway__tenant=tenant)
            return t, None
        except GatewayTarget.DoesNotExist:
            return None, Response({"error": "Target introuvable"}, status=404)

    def get(self, request, gid, tid):
        t, err = self._get(request, gid, tid)
        if err is not None:
            return err
        return Response(_serialize_target(t, full=True))

    def patch(self, request, gid, tid):
        t, err = self._get(request, gid, tid)
        if err is not None:
            return err
        data = request.data or {}
        for field in ("label", "ip", "port", "username", "password",
                       "mac", "model", "serial_number", "extra", "enabled"):
            if field in data:
                setattr(t, field, data[field])
        t.save()
        return Response(_serialize_target(t, full=True))

    def delete(self, request, gid, tid):
        t, err = self._get(request, gid, tid)
        if err is not None:
            return err
        t.delete()
        return Response({"ok": True})


class FleetTargetsView(APIView):
    """GET /api/v1/devices/edge-gateway/fleet/targets/

    Vue agrégée : tous les targets de toutes les gateways du tenant.
    Filtres query params : ?vendor=hikvision, ?connected=true, ?search=IP.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        tenant = _resolve_tenant(request.user)
        if tenant is None:
            return Response({"count": 0, "targets": []})

        from .models import GatewayTarget
        qs = GatewayTarget.objects.filter(gateway__tenant=tenant).select_related(
            "gateway", "gateway__site"
        )

        vendor = (request.query_params.get("vendor") or "").strip()
        if vendor:
            qs = qs.filter(vendor=vendor)

        connected = request.query_params.get("connected")
        if connected == "true":
            qs = qs.filter(connected=True)
        elif connected == "false":
            qs = qs.filter(connected=False)

        search = (request.query_params.get("search") or "").strip()
        if search:
            from django.db.models import Q
            qs = qs.filter(
                Q(label__icontains=search) |
                Q(ip__icontains=search) |
                Q(serial_number__icontains=search) |
                Q(gateway__label__icontains=search)
            )

        # Pagination simple
        limit = int(request.query_params.get("limit") or 100)
        offset = int(request.query_params.get("offset") or 0)
        total = qs.count()
        qs = qs[offset:offset + limit]

        targets = []
        for t in qs:
            d = _serialize_target(t)
            d["gateway_id"]    = str(t.gateway_id)
            d["gateway_label"] = t.gateway.label
            d["gateway_site"]  = str(t.gateway.site) if t.gateway.site else ""
            targets.append(d)

        # Stats par vendor
        by_vendor = {}
        for t in GatewayTarget.objects.filter(gateway__tenant=tenant).values("vendor"):
            by_vendor[t["vendor"]] = by_vendor.get(t["vendor"], 0) + 1

        return Response({
            "count":     total,
            "returned":  len(targets),
            "offset":    offset,
            "limit":     limit,
            "by_vendor": by_vendor,
            "targets":   targets,
        })


class GatewayScanResultsView(APIView):
    """POST /api/v1/devices/edge-gateway/<gid>/scan-results/

    L'agent Go push le résultat d'un scan réseau LAN. On stocke le résultat
    dans LocalAgent.devices_discovered et on log une entrée dans le buffer
    d'événements pour l'UI supervision.

    Auth : HMAC agent (Bearer api_token).

    Body :
      {
        "devices": [
          {"ip":"...", "mac":"...", "vendor":"...", "model":"...",
           "protocol":"...", "sources":["arp","onvif"], "found_at":"..."}
        ],
        "duration_ms": 1234,
        "probes_run": ["arp","onvif","mdns"]
      }
    """
    permission_classes = []
    authentication_classes = [AgentHmacAuthentication]

    def post(self, request, gid):
        agent = getattr(request, "agent", None)
        if agent is None or str(agent.pk) != str(gid):
            return Response({"error": "Agent hors scope"}, status=403)
        if agent.revoked_at:
            return Response({"error": "Gateway révoquée"}, status=403)

        data = request.data or {}
        devices = data.get("devices") or []
        if not isinstance(devices, list):
            return Response({"error": "devices doit être une liste"}, status=400)

        # Persiste dans LocalAgent.devices_discovered (max 500)
        agent.devices_discovered = devices[:500]
        agent.save(update_fields=["devices_discovered"])

        # Log dans le buffer de supervision live
        _append_gateway_log(agent.pk, {
            "type":         "scan_result",
            "at":           timezone.now().isoformat(),
            "count":        len(devices),
            "duration_ms":  data.get("duration_ms", 0),
            "probes_run":   data.get("probes_run", []),
        })

        # Auto-match : si un device scanné correspond à un GatewayTarget
        # existant (même IP), on met à jour mac/model/firmware.
        _auto_enrich_targets(agent, devices)

        return Response({
            "ok": True,
            "processed": len(devices),
            "server_time": timezone.now().isoformat(),
        })


def _auto_enrich_targets(agent, devices: list):
    """Enrichit les targets existants avec les métadonnées trouvées au scan.

    Match par IP → recopie mac/model/firmware/serial si absent.
    """
    from .models import GatewayTarget
    ips = {}
    for d in devices:
        if isinstance(d, dict) and d.get("ip"):
            ips[d["ip"]] = d

    if not ips:
        return

    updates = 0
    for t in GatewayTarget.objects.filter(gateway=agent, ip__in=list(ips.keys())):
        d = ips.get(t.ip)
        if not d:
            continue
        changed = False
        if not t.mac and d.get("mac"):
            t.mac = d["mac"][:17]
            changed = True
        if not t.model and d.get("model"):
            t.model = d["model"][:80]
            changed = True
        if not t.serial_number and d.get("serial"):
            t.serial_number = str(d["serial"])[:64]
            changed = True
        if changed:
            t.save(update_fields=["mac", "model", "serial_number"])
            updates += 1
    if updates > 0:
        logger.info("scan_results: enriched %d targets de gateway %s",
                     updates, agent.pk)


class GatewayTargetActionView(APIView):
    """POST /api/v1/devices/edge-gateway/<gid>/targets/<tid>/<action>/

    Actions : door-unlock / test-connect
    Publie une commande MQTT ciblée vers l'agent qui délègue au driver.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, gid, tid, action):
        tenant = _resolve_tenant(request.user)
        if tenant is None:
            return Response({"error": "Aucun tenant"}, status=403)
        try:
            gw = LocalAgent.objects.get(pk=gid, tenant=tenant)
        except LocalAgent.DoesNotExist:
            return Response({"error": "Gateway introuvable"}, status=404)

        from .models import GatewayTarget
        try:
            t = GatewayTarget.objects.get(pk=tid, gateway=gw)
        except GatewayTarget.DoesNotExist:
            return Response({"error": "Target introuvable"}, status=404)

        action_key = action.strip().lower()
        if action_key not in ("door_unlock", "door-unlock",
                                "test_connect", "test-connect"):
            return Response({"error": f"Action inconnue: {action}"}, status=400)

        # Normalise (URL utilise -, dispatcher agent utilise _)
        mqtt_action = action_key.replace("-", "_")

        payload = {"target_id": str(t.pk), **(request.data or {})}
        try:
            from .services.mqtt_publisher import publish_command
            res = publish_command(
                gateway_id=str(gw.pk),
                action_type=mqtt_action,
                payload=payload,
            )
        except Exception as exc:
            return Response({"ok": False, "error": str(exc)}, status=500)

        return Response(res)


def _serialize_target(t, full: bool = False) -> dict:
    """Serialize un GatewayTarget pour JSON — password jamais exposé."""
    d = {
        "id":            str(t.pk),
        "label":         t.label,
        "vendor":        t.vendor,
        "ip":            t.ip,
        "port":          t.port,
        "connected":     t.connected,
        "last_seen_at":  t.last_seen_at.isoformat() if t.last_seen_at else None,
        "events_count":  t.events_count,
        "enabled":       t.enabled,
    }
    if full:
        d.update({
            "username":       t.username,
            "mac":            t.mac,
            "model":          t.model,
            "firmware":       t.firmware,
            "serial_number":  t.serial_number,
            "last_error":     t.last_error,
            "extra":          t.extra or {},
        })
    return d


# ═══════════════════════════════════════════════════════════════════
# Download dynamique — package personnalisé par gateway (Phase 1)
# ═══════════════════════════════════════════════════════════════════
class GatewayDownloadPackageView(APIView):
    """GET /api/v1/devices/edge-gateway/<gid>/download/?platform=<xxx>

    Génère à la volée un ZIP d'installation contenant :
      - config/kshield-agent.toml    : gateway_id + activation_token injectés
      - install-edge.sh / .ps1        : script installation OS-spécifique
      - docker-compose.yml            : uniquement pour platform=docker
      - README.txt                    : instructions plateforme
      - VERSION.json                  : manifest pour auto-update

    Chaque download regénère l'activation_token (sauf gateway déjà activée)
    afin d'éviter la réutilisation d'un token téléchargé par un tiers.

    Auth : IsAuthenticated + doit appartenir au tenant de la gateway.
    """
    permission_classes = [IsAuthenticated]

    # Plateformes supportées côté endpoint (whitelist stricte)
    ALLOWED_PLATFORMS = {
        "linux_deb", "linux_rpm", "linux_sh", "macos_pkg",
        "windows_exe", "windows_portable", "docker",
        "raspberry_pi", "mini_pc",
    }

    def get(self, request, gid):
        # 1. Validation platform
        platform = request.query_params.get("platform", "").strip()
        if platform not in self.ALLOWED_PLATFORMS:
            return Response(
                {"error": "Platform invalide",
                 "allowed": sorted(self.ALLOWED_PLATFORMS)},
                status=400,
            )

        # 2. Récupère la gateway (scope tenant strict)
        tenant = _resolve_tenant(request.user)
        if tenant is None:
            return Response({"error": "Aucun tenant disponible"}, status=403)

        try:
            agent = LocalAgent.objects.get(pk=gid, tenant=tenant)
        except LocalAgent.DoesNotExist:
            return Response({"error": "Gateway introuvable"}, status=404)

        # 3. Refuse le download si gateway révoquée
        if agent.revoked_at is not None:
            return Response(
                {"error": "Gateway révoquée — réactivez-la avant téléchargement"},
                status=403,
            )

        # 4. Génération du package
        try:
            from .services.package_generator import PackageGenerator
            gen = PackageGenerator(agent, platform)
            pkg = gen.generate()
        except Exception as exc:
            logger.exception("PackageGenerator failed for gateway %s", gid)
            return Response(
                {"error": "Erreur génération package", "detail": str(exc)},
                status=500,
            )

        # 5. Log l'accès
        logger.info(
            "Gateway package downloaded: gateway=%s platform=%s user=%s size=%d",
            gid, platform, request.user.pk, pkg.size_bytes,
        )

        # 6. Streaming HTTP response
        response = HttpResponse(pkg.content, content_type="application/zip")
        response["Content-Disposition"] = (
            f'attachment; filename="{pkg.filename}"'
        )
        response["Content-Length"] = pkg.size_bytes
        response["X-Kshield-Checksum-Sha256"] = pkg.checksum_sha256
        response["X-Kshield-Gateway-Id"] = str(agent.id)
        response["X-Kshield-Platform"] = platform
        # Cache-Control : pas de cache car token change à chaque call
        response["Cache-Control"] = "no-store, no-cache, must-revalidate"
        return response


# ═══════════════════════════════════════════════════════════════════
# Update check + Action result (Phase 2.3)
# ═══════════════════════════════════════════════════════════════════
class UpdateCheckView(APIView):
    """GET /api/v1/edge-gateway/updates/check/?version=<sem>&platform=<p>

    Retourne les infos de mise à jour disponible.
    Auth : HMAC agent (Bearer api_token).

    Réponse :
      {
        "has_update":        true/false,
        "latest_version":    "1.2.3",
        "current_version":   "1.0.0",
        "download_url":      "https://.../kshield-agent-linux-amd64",
        "checksum_sha256":   "...",
        "release_notes_url": "https://.../releases/1.2.3",
        "mandatory":         false
      }
    """
    permission_classes = []
    authentication_classes = [AgentHmacAuthentication]

    def get(self, request):
        a = getattr(request, "agent", None)
        if a is None or a.revoked_at:
            return Response({"error": "Non autorisé"}, status=403)

        current = request.query_params.get("version", "") or ""
        platform = request.query_params.get("platform", "") or ""

        # Cherche le dernier package publié pour cette plateforme
        latest = EdgeGatewayPackage.objects.filter(
            platform=platform, is_latest=True,
        ).order_by("-published_at").first()

        if not latest:
            return Response({
                "has_update":      False,
                "current_version": current,
                "message":         f"Aucun package publié pour platform={platform}",
            })

        has_update = _version_greater(latest.version, current)

        payload = {
            "has_update":       has_update,
            "current_version":  current,
            "latest_version":   latest.version,
        }
        if has_update:
            payload.update({
                "download_url":      request.build_absolute_uri(
                    f"/api/v1/devices/edge-gateway/packages/{latest.pk}/download/"
                ),
                "checksum_sha256":   latest.checksum_sha256 or "",
                "release_notes_url": request.build_absolute_uri(
                    f"/api/v1/devices/edge-gateway/packages/{latest.pk}/"
                ),
                "mandatory":         False,   # Phase 3 : marquable via admin
            })
        return Response(payload)


class ActionResultView(APIView):
    """POST /api/v1/edge-gateway/action-result/

    L'agent renvoie le résultat d'une action exécutée (restart/sync/scan/update).
    Utilisé par le dispatcher pour tracer les commandes.

    Body :
      {
        "action_id":  "uuid",
        "success":    true,
        "error":      "..." (si !success),
        "output":     { ... },
        "finished_at": "ISO8601"
      }
    """
    permission_classes = []
    authentication_classes = [AgentHmacAuthentication]

    def post(self, request):
        a = getattr(request, "agent", None)
        if a is None or a.revoked_at:
            return Response({"error": "Non autorisé"}, status=403)

        data = request.data or {}
        action_id = data.get("action_id") or ""
        success = bool(data.get("success"))

        _append_gateway_log(a.pk, {
            "type":         "action_result",
            "at":           timezone.now().isoformat(),
            "action_id":    action_id,
            "success":      success,
            "error":        data.get("error") or "",
            "output":       data.get("output") or {},
        })

        # Marquer la DeviceCommand comme completed/failed si elle existe
        try:
            from devices.models import DeviceCommand
            cmd = DeviceCommand.objects.filter(pk=action_id).first()
            if cmd:
                cmd.status = "completed" if success else "failed"
                cmd.completed_at = timezone.now()
                cmd.error_message = (data.get("error") or "")[:500]
                cmd.result_payload = data.get("output") or {}
                cmd.save(update_fields=[
                    "status", "completed_at", "error_message", "result_payload",
                ])
        except Exception as e:
            logger.debug("action_result: DeviceCommand not tracked: %s", e)

        return Response({"ok": True})


def _version_greater(latest: str, current: str) -> bool:
    """Compare deux versions semver-like sans dépendance externe.

    Considère "1.10" > "1.9" (comparaison par tuple d'ints).
    Fallback string compare si parse échoue (safer than crash).
    """
    def parse(v):
        v = (v or "").strip().lstrip("v")
        parts = v.split("-")[0].split(".")
        try:
            return tuple(int(p) for p in parts)
        except ValueError:
            return None

    lv, cv = parse(latest), parse(current)
    if lv is None or cv is None:
        return latest > current
    return lv > cv


# ═══════════════════════════════════════════════════════════════════
# Registration au premier boot (l'agent contacte le serveur)
# ═══════════════════════════════════════════════════════════════════
class GatewayActivateView(APIView):
    """POST /api/v1/devices/edge-gateway/activate/

    Endpoint public appelé par le Gateway au premier boot avec son
    activation_token. En retour : api_token permanent + hmac_secret + config.

    Body :
        {
          "activation_token": "<token>",
          "hostname": "gw-riviera-01",
          "os_info": "Ubuntu 22.04",
          "version": "1.2.0",
          "ip_local": "192.168.1.42"
        }

    Sécurité :
      * Token à usage unique — invalidé après activation
      * Expiration 24h par défaut
      * IP publique capturée automatiquement
      * Audit log complet
    """
    permission_classes = []
    authentication_classes = []

    @transaction.atomic
    def post(self, request):
        data = request.data or {}
        token = data.get("activation_token") or ""
        if not token:
            return Response({"error": "activation_token requis"}, status=400)

        try:
            a = LocalAgent.objects.select_for_update().get(activation_token=token)
        except LocalAgent.DoesNotExist:
            logger.warning("Tentative activation avec token invalide")
            return Response({"error": "Token invalide"}, status=401)

        # Vérifications
        if a.revoked_at:
            return Response({"error": "Gateway révoqué"}, status=403)
        if a.activated_at:
            return Response({"error": "Gateway déjà activé"}, status=409)
        if a.activation_expires_at and a.activation_expires_at < timezone.now():
            return Response({"error": "Token expiré"}, status=410)

        now = timezone.now()
        a.activated_at = now
        a.activation_token = None            # usage unique
        a.activation_expires_at = None

        # Support des 2 shapes de POST :
        # - Python legacy : {"os_info": "...", "version": "...", "ip_local": "..."}
        # - Go >= 1.0     : {"system_info": {"os": "...", "arch": "...", "hostname": "..."}}
        sys_info = data.get("system_info") or {}
        os_field = data.get("os_info") or ""
        if not os_field and sys_info:
            os_field = f"{sys_info.get('os', '')}/{sys_info.get('arch', '')} " \
                       f"{sys_info.get('hostname', '')}".strip()
        a.os_info = os_field[:120]

        version_field = data.get("version") or sys_info.get("agent_version", "")
        a.version = version_field[:32]
        a.ip_local = data.get("ip_local")
        a.ip_public = _client_ip(request)
        a.cloud_status = "ok"
        a.save()

        logger.info("Gateway %s activé (label=%s ip=%s)",
                     a.pk, a.label, a.ip_public)

        # ─── Credentials MQTT provisionnés dynamiquement ─────────────────
        # Le nom d'user MQTT est dérivé du gateway_id (déterministe, unique).
        # Le password est stocké chiffré dans a.hmac_secret pour l'instant —
        # une future version dédiera un champ propre mqtt_password crypto.
        from django.conf import settings as _settings
        mqtt_username = f"kshield-edge-{str(a.pk)[:8]}"
        # Note : pour la Phase 1, on retourne un password vide + username seul.
        # Phase 2+ : provisioning EMQX via API management HTTP.
        mqtt_password = ""

        return Response({
            # Champs partagés (nouveau + legacy)
            "success":       True,
            "gateway_id":    str(a.pk),
            "gateway_label": a.label,
            "label":         a.label,       # alias legacy
            "api_token":     a.api_token,
            "hmac_secret":   a.hmac_secret,
            "server_url":    _server_url(request),
            "tenant_id":     str(a.tenant_id) if a.tenant_id else "",
            "site_id":       str(a.site_id) if a.site_id else "",
            "activated_at":  now.isoformat(),
            "message":       "Gateway activée avec succès",
            # MQTT — nouveau (Go)
            "mqtt_host":     getattr(_settings, "MQTT_PUBLIC_HOST", None)
                                or _mqtt_public_host(request),
            "mqtt_port":     int(getattr(_settings, "MQTT_PORT", 1883)),
            "mqtt_use_tls":  bool(getattr(_settings, "MQTT_TLS", False)),
            "mqtt_username": mqtt_username,
            "mqtt_password": mqtt_password,
        })


def _mqtt_public_host(request):
    """Dérive un hostname public MQTT depuis Host header quand la var
    MQTT_PUBLIC_HOST n'est pas définie."""
    host = request.get_host().split(":")[0]
    # kaydanshield.com -> mqtt.kaydanshield.com (convention)
    if not host.startswith("mqtt."):
        return f"mqtt.{host}" if "." in host else host
    return host


class GatewayHeartbeatView(APIView):
    """POST /api/v1/devices/edge-gateway/heartbeat/

    L'agent push périodiquement son état runtime (autrement que via WS).
    Utilise l'authentification HMAC (Bearer token = api_token).
    """
    permission_classes = []
    authentication_classes = [AgentHmacAuthentication]

    def post(self, request):
        a = getattr(request, "agent", None)
        if a is None or a.revoked_at:
            return Response({"error": "Non autorisé"}, status=403)

        data = request.data or {}
        a.last_seen_at = timezone.now()
        a.ip_local = data.get("ip_local") or a.ip_local
        a.ip_public = _client_ip(request)
        a.uptime_seconds = data.get("uptime_seconds") or a.uptime_seconds
        a.events_pending = int(data.get("events_pending") or 0)
        a.mqtt_status = data.get("mqtt_status") or a.mqtt_status
        a.ws_status = data.get("ws_status") or a.ws_status
        a.cloud_status = "ok"
        if data.get("version"):
            a.version = data["version"][:32]
        if data.get("os_info"):
            a.os_info = data["os_info"][:120]
        if isinstance(data.get("devices_discovered"), list):
            a.devices_discovered = data["devices_discovered"][:500]
        a.save()

        # ─── Mise à jour des target statuses ────────────────────────
        target_statuses = data.get("target_statuses") or []
        if isinstance(target_statuses, list) and target_statuses:
            _apply_target_statuses(a, target_statuses)

        # ─── Récupère les pending actions (device commands en attente) ───
        pending_actions = _pending_actions_for_gateway(a)

        # Ajoute au buffer de logs pour supervision live
        _append_gateway_log(a.pk, {
            "type": "heartbeat",
            "at": a.last_seen_at.isoformat(),
            "ip_local": a.ip_local, "ip_public": a.ip_public,
            "uptime_seconds": a.uptime_seconds,
            "events_pending": a.events_pending,
            "targets_reported": len(target_statuses),
        })

        return Response({
            "ok": True,
            "server_time": timezone.now().isoformat(),
            "pending_actions": pending_actions,
        })


def _apply_target_statuses(agent, statuses: list):
    """Applique la liste des target statuses envoyés par l'agent à la DB."""
    from .models import GatewayTarget
    from django.utils import timezone as _tz

    now = _tz.now()
    for ts in statuses:
        if not isinstance(ts, dict):
            continue
        tid = ts.get("id")
        if not tid:
            continue
        try:
            t = GatewayTarget.objects.get(pk=tid, gateway=agent)
        except (GatewayTarget.DoesNotExist, ValueError):
            continue

        t.connected = bool(ts.get("connected"))
        t.events_count = int(ts.get("events_count") or 0)
        t.last_error = (ts.get("last_error") or "")[:1000]
        t.last_seen_at = now
        t.save(update_fields=["connected", "events_count",
                               "last_error", "last_seen_at"])


def _pending_actions_for_gateway(agent) -> list:
    """Retourne les DeviceCommand en attente pour cette gateway.

    Utilisé par le heartbeat pour permettre à l'agent de pull les actions
    même si MQTT/WS sont down (fallback HTTP polling).
    """
    try:
        from .models import DeviceCommand
        # Prend les commandes queued/dispatched liées à la gateway
        pending = DeviceCommand.objects.filter(
            gateway=agent,
            status__in=["queued", "dispatched"],
        )[:20]
        return [
            {
                "id":      str(c.pk),
                "type":    c.command_type,
                "payload": c.payload or {},
            }
            for c in pending
        ]
    except Exception:
        return []


def _client_ip(request) -> Optional[str]:
    xff = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def _server_url(request) -> str:
    scheme = "https" if request.is_secure() else "http"
    return f"{scheme}://{request.get_host()}"


def _append_gateway_log(gateway_id, entry: dict):
    from django.core.cache import cache
    key = f"gateway_logs:{gateway_id}"
    logs = cache.get(key) or []
    logs.append(entry)
    if len(logs) > 500:
        logs = logs[-500:]
    cache.set(key, logs, 3600)
