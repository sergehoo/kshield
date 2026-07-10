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
        from .services.event_bus import EventBus
        EventBus.push_to_agent(agent.pk, payload)

    def post(self, request, gid):
        a = self._get(request, gid)
        if a is None:
            return Response({"error": "Gateway introuvable"}, status=404)
        if a.revoked_at:
            return Response({"error": "Gateway révoqué"}, status=403)
        payload = self._payload(request)
        self._push(a, payload)
        logger.info("Gateway %s : action %s poussée", a.pk, self.action_type)
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
        a.os_info = (data.get("os_info") or "")[:120]
        a.version = (data.get("version") or "")[:32]
        a.ip_local = data.get("ip_local")
        a.ip_public = _client_ip(request)
        a.cloud_status = "ok"
        a.save()

        logger.info("Gateway %s activé (label=%s ip=%s)",
                     a.pk, a.label, a.ip_public)

        return Response({
            "gateway_id": str(a.pk),
            "api_token": a.api_token,
            "hmac_secret": a.hmac_secret,
            "server_url": _server_url(request),
            "site_id": a.site_id,
            "label": a.label,
            "activated_at": now.isoformat(),
        })


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

        # Ajoute au buffer de logs pour supervision live
        _append_gateway_log(a.pk, {
            "type": "heartbeat",
            "at": a.last_seen_at.isoformat(),
            "ip_local": a.ip_local, "ip_public": a.ip_public,
            "uptime_seconds": a.uptime_seconds,
            "events_pending": a.events_pending,
        })

        return Response({"ok": True, "server_time": timezone.now().isoformat()})


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
