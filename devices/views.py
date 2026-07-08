import logging

from django.http import Http404, HttpResponse, StreamingHttpResponse
from django.utils import timezone
from django.views import View
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication

from accounts.hmac_auth import HMACAPIKeyAuthentication
from accounts.permissions import IsAuthenticatedOrAPIKey
from accounts.rbac import HasKshieldPermission

logger = logging.getLogger(__name__)

from .models import (
    Badge, BadgeAssignment, BadgeHelmetPairing, Camera, Device, DeviceHeartbeat,
    DeviceMaintenance, DeviceModel, FirmwareVersion, Helmet, OTAUpdate,
)
from .serializers import (
    BadgeHelmetPairingSerializer, BadgeSerializer, CameraSerializer,
    DeviceHeartbeatSerializer, DeviceMaintenanceSerializer, DeviceModelSerializer,
    DeviceSerializer, FirmwareVersionSerializer, HelmetSerializer,
    OTAUpdateSerializer,
)


@extend_schema_view(
    list=extend_schema(tags=["Equipements"], summary="Modèles d'équipement (catalogue)"),
    create=extend_schema(tags=["Equipements"], summary="Créer un modèle"),
    retrieve=extend_schema(tags=["Equipements"]),
    update=extend_schema(tags=["Equipements"]),
    partial_update=extend_schema(tags=["Equipements"]),
    destroy=extend_schema(tags=["Equipements"]),
)
class DeviceModelViewSet(viewsets.ModelViewSet):
    queryset = DeviceModel.objects.all(); serializer_class = DeviceModelSerializer
    search_fields = ("brand", "model"); filterset_fields = ("type", "is_active")
    permission_classes = [HasKshieldPermission]
    kshield_perms = {"read": "devices.view", "write": "devices.manage"}


@extend_schema_view(
    list=extend_schema(tags=["Equipements"], summary="Liste des équipements installés"),
    create=extend_schema(tags=["Equipements"], summary="Enregistrer un équipement"),
    retrieve=extend_schema(tags=["Equipements"], summary="Détail équipement"),
    update=extend_schema(tags=["Equipements"]),
    partial_update=extend_schema(tags=["Equipements"]),
    destroy=extend_schema(tags=["Equipements"]),
)
class DeviceViewSet(viewsets.ModelViewSet):
    """Lecteurs NFC/UHF, caméras, tablettes terrain — un par checkpoint."""
    queryset = Device.objects.select_related("tenant", "model", "site", "zone", "checkpoint").all()
    serializer_class = DeviceSerializer
    search_fields = ("serial_number",)
    filterset_fields = ("tenant", "site", "model", "status")
    permission_classes = [HasKshieldPermission]
    kshield_perms = {"read": "devices.view", "write": "devices.manage",
                      "heartbeat": "devices.view"}

    def get_queryset(self):
        from accounts.scoping import scope_queryset_by_company
        return scope_queryset_by_company(super().get_queryset(), self.request.user, "site__company")

    @action(detail=True, methods=["post"],
            authentication_classes=[HMACAPIKeyAuthentication, JWTAuthentication],
            permission_classes=[IsAuthenticatedOrAPIKey])
    def heartbeat(self, request, pk=None):
        """Heartbeat par ID device — accepte HMAC ou JWT.

        Pour push sans connaître l'ID interne (cas terminal IoT), préférer
        ``POST /api/v1/devices/heartbeat/`` (HeartbeatIngestView) qui identifie
        par ``serial_number``.
        """
        device = self.get_object()
        DeviceHeartbeat.objects.create(
            device=device,
            is_online=request.data.get("is_online", True),
            battery_level=request.data.get("battery_level"),
            signal_strength=request.data.get("signal_strength"),
            payload=request.data.get("payload", {}),
        )
        device.last_heartbeat_at = timezone.now()
        device.battery_level = request.data.get("battery_level", device.battery_level)
        device.save(update_fields=["last_heartbeat_at", "battery_level"])
        return Response({"status": "ok"})


@extend_schema_view(
    list=extend_schema(
        tags=["Badges"],
        summary="Liste des badges",
        description=(
            "Retourne tous les badges (visiteur QR, employé NFC, ouvrier UHF). "
            "Filtres: `category`, `status`, `holder_kind`. Recherche sur l'UID."
        ),
    ),
    create=extend_schema(tags=["Badges"], summary="Créer un badge brut",
        description="Préférer les workflows /api/v1/devices/badges/issue-* pour une émission métier complète."),
    retrieve=extend_schema(tags=["Badges"], summary="Détail badge"),
    update=extend_schema(tags=["Badges"]),
    partial_update=extend_schema(tags=["Badges"]),
    destroy=extend_schema(tags=["Badges"]),
)
class BadgeViewSet(viewsets.ModelViewSet):
    """Badges visiteurs (QR), employés (NFC) et ouvriers (UHF + casque)."""
    queryset = Badge.objects.all(); serializer_class = BadgeSerializer
    search_fields = ("uid",)
    filterset_fields = ("tenant", "type", "status", "holder_kind")
    permission_classes = [HasKshieldPermission]
    kshield_perms = {"read": "badges.view", "write": "badges.issue",
                      "revoke": "badges.issue"}

    @action(detail=True, methods=["post"])
    def revoke(self, request, pk=None):
        badge = self.get_object()
        badge.status = "revoked"
        badge.revoked_at = timezone.now()
        badge.revoked_reason = request.data.get("reason", "")
        badge.save(update_fields=["status", "revoked_at", "revoked_reason"])
        return Response({"status": badge.status})


class HelmetViewSet(viewsets.ModelViewSet):
    queryset = Helmet.objects.select_related("tenant", "current_worker").all()
    serializer_class = HelmetSerializer
    search_fields = ("serial_number", "uhf_tag_uid", "ble_beacon_uid")
    filterset_fields = ("tenant", "status")
    permission_classes = [HasKshieldPermission]
    kshield_perms = {"read": "badges.view", "write": "badges.issue"}


class BadgeHelmetPairingViewSet(viewsets.ModelViewSet):
    queryset = BadgeHelmetPairing.objects.select_related("worker", "badge", "helmet", "site").all()
    serializer_class = BadgeHelmetPairingSerializer
    filterset_fields = ("worker", "site", "pairing_date", "is_broken")
    permission_classes = [HasKshieldPermission]
    kshield_perms = {"read": "badges.view", "write": "badges.issue"}

    def get_queryset(self):
        from accounts.scoping import scope_queryset_by_company
        return scope_queryset_by_company(super().get_queryset(), self.request.user, "site__company")


class DeviceHeartbeatViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = DeviceHeartbeat.objects.select_related("device").all()
    serializer_class = DeviceHeartbeatSerializer
    filterset_fields = ("device", "is_online")
    permission_classes = [HasKshieldPermission]
    kshield_perms = {"read": "devices.view"}

    def get_queryset(self):
        from accounts.scoping import scope_queryset_by_company
        return scope_queryset_by_company(super().get_queryset(), self.request.user, "device__site__company")


@extend_schema_view(
    post=extend_schema(
        tags=["Equipements"],
        summary="Heartbeat device (HMAC)",
        description=(
            "Endpoint dédié pour les terminaux IoT — push leur heartbeat sans "
            "JWT, juste leur APIKey HMAC. Identifie par ``serial_number``."
        ),
    ),
)
class HeartbeatIngestView(APIView):
    """POST /api/v1/devices/heartbeat/ — push heartbeat depuis un terminal IoT.

    Auth : HMAC (terminal) ou JWT (back-office test).
    Body : ``{"serial_number": "...", "is_online": true, "battery_level": 87,
              "signal_strength": -65, "payload": {...}}``
    """
    authentication_classes = [HMACAPIKeyAuthentication, JWTAuthentication]
    permission_classes = [IsAuthenticatedOrAPIKey]

    def post(self, request):
        serial = (request.data.get("serial_number") or "").strip()
        if not serial:
            return Response({"error": "serial_number requis"},
                            status=status.HTTP_400_BAD_REQUEST)
        try:
            device = Device.objects.get(serial_number=serial)
        except Device.DoesNotExist:
            return Response({"error": f"Device {serial} inconnu"},
                            status=status.HTTP_404_NOT_FOUND)

        DeviceHeartbeat.objects.create(
            device=device,
            is_online=bool(request.data.get("is_online", True)),
            battery_level=request.data.get("battery_level"),
            signal_strength=request.data.get("signal_strength"),
            payload=request.data.get("payload", {}),
        )
        device.last_heartbeat_at = timezone.now()
        if request.data.get("battery_level") is not None:
            device.battery_level = request.data.get("battery_level")
        device.save(update_fields=["last_heartbeat_at", "battery_level"])
        return Response({"ok": True, "device_id": device.id,
                          "received_at": timezone.now().isoformat()})


class DeviceMaintenanceViewSet(viewsets.ModelViewSet):
    queryset = DeviceMaintenance.objects.all(); serializer_class = DeviceMaintenanceSerializer
    filterset_fields = ("device", "kind")
    permission_classes = [HasKshieldPermission]
    kshield_perms = {"read": "devices.view", "write": "devices.manage"}

    def get_queryset(self):
        from accounts.scoping import scope_queryset_by_company
        return scope_queryset_by_company(super().get_queryset(), self.request.user, "device__site__company")


class FirmwareVersionViewSet(viewsets.ModelViewSet):
    """Catalogue global de firmwares — pas de scoping (partagé tenant-wide)."""
    queryset = FirmwareVersion.objects.all(); serializer_class = FirmwareVersionSerializer
    filterset_fields = ("device_model", "is_published")
    permission_classes = [HasKshieldPermission]
    kshield_perms = {"read": "devices.view", "write": "devices.manage"}


class OTAUpdateViewSet(viewsets.ModelViewSet):
    queryset = OTAUpdate.objects.select_related("device", "firmware").all()
    serializer_class = OTAUpdateSerializer
    filterset_fields = ("device", "status")
    permission_classes = [HasKshieldPermission]
    kshield_perms = {"read": "devices.view", "write": "devices.manage"}

    def get_queryset(self):
        from accounts.scoping import scope_queryset_by_company
        return scope_queryset_by_company(super().get_queryset(), self.request.user, "device__site__company")


@extend_schema_view(
    get=extend_schema(
        tags=["Equipements"],
        summary="Métadonnées firmware OTA (avec SHA-256)",
        description=(
            "Retourne les métadonnées d'un firmware (URL, taille, SHA-256) à "
            "consommer par un device IoT pour vérifier l'intégrité avant flash. "
            "Le SHA-256 est calculé serveur-side et constitue la *signature* "
            "qui doit matcher après download."
        ),
    ),
)
class OTAFirmwareMetadataView(APIView):
    """GET /api/v1/devices/ota/<firmware_id>/metadata/ — méta + hash SHA-256.

    Auth : HMAC (device) ou JWT (back-office). Le device récupère le file_url,
    le télécharge, puis vérifie ``hashlib.sha256(file_bytes).hexdigest() == sha256``.
    """
    authentication_classes = [HMACAPIKeyAuthentication, JWTAuthentication]
    permission_classes = [IsAuthenticatedOrAPIKey]

    def get(self, request, firmware_id):
        import hashlib
        from django.core.cache import cache

        try:
            fw = FirmwareVersion.objects.select_related("device_model").get(
                pk=firmware_id, is_published=True
            )
        except FirmwareVersion.DoesNotExist:
            return Response({"error": "Firmware introuvable ou non publié."},
                            status=status.HTTP_404_NOT_FOUND)
        if not fw.file or not fw.file.name:
            return Response({"error": "Aucun fichier attaché à ce firmware."},
                            status=status.HTTP_404_NOT_FOUND)

        # Cache SHA-256 30 jours pour éviter de relire le fichier à chaque hit
        cache_key = f"fw_sha256:{fw.pk}:{fw.file.name}"
        sha256 = cache.get(cache_key)
        size = None
        if not sha256:
            h = hashlib.sha256()
            try:
                with fw.file.open("rb") as fh:
                    size = 0
                    for chunk in iter(lambda: fh.read(64 * 1024), b""):
                        h.update(chunk)
                        size += len(chunk)
                sha256 = h.hexdigest()
                cache.set(cache_key, sha256, 60 * 60 * 24 * 30)
            except Exception:
                return Response({"error": "Fichier firmware illisible."},
                                status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response({
            "firmware_id": fw.pk,
            "device_model": f"{fw.device_model.brand} {fw.device_model.model}",
            "version": fw.version,
            "release_notes": fw.release_notes,
            "file_url": request.build_absolute_uri(fw.file.url),
            "size_bytes": size if size is not None else fw.file.size,
            "sha256": sha256,
            "algo": "sha256",
        })


# ===========================================================================
# Caméras IP — CRUD + streaming MJPEG + snapshot + test connexion
# ===========================================================================
@extend_schema_view(
    list=extend_schema(tags=["Cameras"], summary="Liste des caméras IP"),
    create=extend_schema(tags=["Cameras"], summary="Ajouter une caméra IP"),
    retrieve=extend_schema(tags=["Cameras"], summary="Détail caméra"),
    update=extend_schema(tags=["Cameras"]),
    partial_update=extend_schema(tags=["Cameras"]),
    destroy=extend_schema(tags=["Cameras"]),
)
class CameraViewSet(viewsets.ModelViewSet):
    """CRUD complet des caméras IP + actions stream / snapshot / test."""
    queryset = Camera.objects.select_related("site", "zone").all()
    serializer_class = CameraSerializer
    filterset_fields = ("site", "zone", "status", "is_active",
                          "enable_face_recognition")
    search_fields = ("name", "location_label", "rtsp_url")
    permission_classes = [HasKshieldPermission]
    kshield_perms = {"read": "devices.view", "write": "devices.manage",
                      "test": "devices.view", "snapshot": "devices.view"}

    def get_queryset(self):
        # Scoping filiale : on passe par site.company (cameras sont rattachées à un site)
        from accounts.scoping import scope_queryset_by_company
        return scope_queryset_by_company(super().get_queryset(), self.request.user, "site__company")

    @action(detail=True, methods=["post"])
    def test(self, request, pk=None):
        """POST /cameras/<pk>/test/ — essaie d'ouvrir le flux 8 sec, renvoie résultat."""
        cam = self.get_object()
        from .streaming import capture_snapshot
        jpeg, err = capture_snapshot(cam, timeout_sec=8.0)
        if err:
            cam.status = "error"
            cam.last_error = err
            cam.save(update_fields=["status", "last_error"])
            return Response({"ok": False, "error": err}, status=status.HTTP_200_OK)
        # OK : MAJ status + last_seen + last_snapshot
        from django.core.files.base import ContentFile
        cam.status = "online"
        cam.last_seen_at = timezone.now()
        cam.last_error = ""
        cam.last_snapshot.save(
            f"cam_{cam.pk}_{int(timezone.now().timestamp())}.jpg",
            ContentFile(jpeg), save=False,
        )
        cam.save(update_fields=["status", "last_seen_at", "last_error", "last_snapshot"])
        return Response({
            "ok": True,
            "status": "online",
            "snapshot_url": cam.last_snapshot.url if cam.last_snapshot else None,
            "size_bytes": len(jpeg),
        })

    @action(detail=True, methods=["get"])
    def snapshot(self, request, pk=None):
        """GET /cameras/<pk>/snapshot/ — capture une frame unique en JPEG."""
        cam = self.get_object()
        from .streaming import capture_snapshot
        jpeg, err = capture_snapshot(cam, timeout_sec=6.0)
        if err:
            return Response({"error": err}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        return HttpResponse(jpeg, content_type="image/jpeg")


class CameraRtspProbeView(APIView):
    """POST /api/v1/devices/cameras/probe-rtsp/ — devine l'URL RTSP depuis une IP.

    Body : {
        "host": "192.168.1.50",
        "user": "admin",
        "pass": "azerty123",
        "rtsp_port": 554,    // optionnel
        "onvif_port": 80,    // optionnel
        "channel": 1         // optionnel (NVR multi-canaux)
    }

    Réponse :
        OK    : {"ok": true, "rtsp_url": "rtsp://...", "brand": "hikvision"}
        Échec : {"ok": false, "error": "Le port RTSP 554 ne répond pas..."}
    """
    permission_classes = [HasKshieldPermission]
    kshield_perms = {"read": "devices.manage", "write": "devices.manage"}

    def post(self, request):
        host = (request.data.get("host") or "").strip()
        user = request.data.get("user") or ""
        passwd = request.data.get("pass") or request.data.get("password") or ""
        rtsp_port = int(request.data.get("rtsp_port") or 554)
        onvif_port = int(request.data.get("onvif_port") or 80)
        channel = int(request.data.get("channel") or 1)

        if not host:
            return Response({"ok": False, "error": "Paramètre 'host' requis."},
                              status=status.HTTP_400_BAD_REQUEST)

        try:
            from .rtsp_probe import probe_rtsp
            url, brand, err = probe_rtsp(
                host=host, user=user, password=passwd,
                rtsp_port=rtsp_port, onvif_port=onvif_port, channel=channel,
            )
        except Exception as exc:
            return Response({"ok": False, "error": f"Probe crash : {exc}"},
                              status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        if not url:
            return Response({"ok": False, "error": err or "Probe échoué"},
                              status=status.HTTP_200_OK)
        return Response({
            "ok": True,
            "rtsp_url": url,
            "brand": brand,
            "host": host,
        })


class CameraRtspProbeMultipleView(APIView):
    """POST /api/v1/devices/cameras/probe-rtsp-bulk/ — probe plusieurs IPs.

    Body : {"ips": ["192.168.1.50", "192.168.1.51", ...],
             "user": "admin", "pass": "..."}
    Utile quand le client a une liste d'IPs sans connaître la marque exacte.
    """
    permission_classes = [HasKshieldPermission]
    kshield_perms = {"read": "devices.manage", "write": "devices.manage"}

    def post(self, request):
        ips = request.data.get("ips") or []
        if isinstance(ips, str):
            ips = [s.strip() for s in ips.replace(",", "\n").splitlines() if s.strip()]
        if not ips:
            return Response({"error": "Liste 'ips' vide."},
                              status=status.HTTP_400_BAD_REQUEST)
        if len(ips) > 32:
            return Response({"error": "Maximum 32 IPs par requête."},
                              status=status.HTTP_400_BAD_REQUEST)

        from .rtsp_probe import probe_multiple_ips
        results = probe_multiple_ips(
            ips, user=request.data.get("user") or "",
            password=request.data.get("pass") or "",
        )
        ok_count = sum(1 for r in results if r["ok"])
        return Response({"results": results, "ok_count": ok_count,
                          "total": len(results)})


class ZkImportUsersView(APIView):
    """POST /api/v1/devices/<pk>/zk-import-users/ — dump tous les users actuels
    du terminal ZKTeco dans l'inbox d'enrôlement.

    Utile pour rapatrier en masse une base de cartes déjà programmée sur le K14
    (ex. à la mise en service Shield d'un site qui utilisait déjà ZKTeco seul).
    """
    permission_classes = [HasKshieldPermission]
    kshield_perms = {"read": "badges.manage", "write": "badges.manage"}

    def post(self, request, pk):
        from django.core.cache import cache
        from django.utils import timezone

        from .models import Device
        from .zk_client import is_zkteco_device, safe_zk_session

        try:
            device = Device.objects.select_related("model").get(pk=pk)
        except Device.DoesNotExist:
            return Response({"error": "device introuvable"},
                              status=status.HTTP_404_NOT_FOUND)
        if not is_zkteco_device(device) or not device.ip_address:
            return Response({"error": "device n'est pas un ZKTeco joignable"},
                              status=status.HTTP_400_BAD_REQUEST)

        pwd = 0
        if device.model and isinstance(device.model.spec, dict):
            pwd = int(device.model.spec.get("sdk_password", 0) or 0)

        with safe_zk_session(ip=device.ip_address, port=4370,
                                password=pwd, timeout=5) as zk:
            if zk is None:
                return Response({"error": "session ZK impossible"},
                                  status=status.HTTP_502_BAD_GATEWAY)
            try:
                users = zk.list_users()
            except Exception as exc:
                return Response({"error": f"get_users failed : {exc}"},
                                  status=status.HTTP_502_BAD_GATEWAY)

        inbox_key = "scan_inbox:reader:{}".format(device.pk)
        items = cache.get(inbox_key) or []
        added = 0
        skipped_no_card = 0
        existing_uids = {it.get("uid") for it in items}
        now_iso = timezone.now().isoformat()
        for u in users:
            card = int(getattr(u, "card", 0) or 0)
            if not card:
                skipped_no_card += 1
                continue
            uid_str = str(card)
            if uid_str in existing_uids:
                continue
            items.append({
                "uid": uid_str,
                "timestamp": now_iso,
                "source": "zkteco_existing_user",
                "device_id": device.pk,
                "raw": {
                    "user_id": str(u.user_id),
                    "name": u.name,
                    "card": card,
                },
            })
            existing_uids.add(uid_str)
            added += 1

        if len(items) > 500:
            items = items[-500:]
        cache.set(inbox_key, items, 600)

        return Response({
            "imported": added,
            "skipped_no_card": skipped_no_card,
            "total_users_on_terminal": len(users),
        })


class ZkEnrollSessionView(APIView):
    """Gère les sessions d'enrôlement live d'un terminal ZKTeco.

    POST /api/v1/devices/<pk>/enroll-session/  body={"action":"start|stop|status", "duration":300}
    """
    permission_classes = [HasKshieldPermission]
    kshield_perms = {"read": "badges.manage", "write": "badges.manage"}

    def post(self, request, pk):
        from .models import Device
        from .zk_client import is_zkteco_device
        from .zk_enrollment import EnrollmentSessionManager

        action = (request.data.get("action") or "").lower()
        if action not in ("start", "stop", "status"):
            return Response({"error": "action invalide (start|stop|status)"},
                              status=status.HTTP_400_BAD_REQUEST)

        try:
            device = Device.objects.select_related("model").get(pk=pk)
        except Device.DoesNotExist:
            return Response({"error": "device introuvable"},
                              status=status.HTTP_404_NOT_FOUND)

        if not is_zkteco_device(device):
            return Response({"error": "device n'est pas un terminal ZKTeco"},
                              status=status.HTTP_400_BAD_REQUEST)
        if not device.ip_address:
            return Response({"error": "device sans IP — impossible d'ouvrir la session"},
                              status=status.HTTP_400_BAD_REQUEST)

        if action == "start":
            duration = int(request.data.get("duration") or 300)
            duration = max(30, min(duration, 1800))  # 30s à 30 min
            result = EnrollmentSessionManager.start(device, duration=duration)
        elif action == "stop":
            result = EnrollmentSessionManager.stop(device.pk)
        else:
            result = EnrollmentSessionManager.status(device.pk)
        return Response(result)

    def get(self, request, pk):
        """Status raccourci en GET."""
        from .zk_enrollment import EnrollmentSessionManager
        return Response(EnrollmentSessionManager.status(int(pk)))


class ZkSyncNowView(APIView):
    """POST /api/v1/devices/<pk>/zk-sync/ — déclenche un pull pointages immédiat.

    Utilisé depuis l'UI ou pour debug. Bloque jusqu'à fin de sync (pas de Celery).
    """
    permission_classes = [HasKshieldPermission]
    kshield_perms = {"read": "devices.view", "write": "devices.manage"}

    def post(self, request, pk):
        from .tasks import sync_zkteco_attendances
        try:
            result = sync_zkteco_attendances(device_id=pk)
        except Exception as exc:
            return Response({"error": str(exc)},
                              status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        return Response(result)


class DeviceIdentifyByIpView(APIView):
    """POST /api/v1/devices/identify-by-ip/ — teste tous les protocoles connus
    sur une IP fournie et renvoie ce qu'on a trouvé.

    Body : ``{"ip": "10.20.1.66"}``
    Utile quand le scan CIDR échoue (LAN isolé du container Docker).
    L'admin renseigne juste l'IP visible depuis l'interface web du terminal.

    Teste :
      - TCP open : 22, 80, 443, 554, 4370, 5084, 8000, 8081, 8443, 37777
      - ZKAccess SDK (pyzk) sur 4370 → firmware/serial/counts
      - Hikvision ISAPI sur 80 → /ISAPI/System/deviceInfo
      - HTTP banner sur 80/443 → Server: header + <title>
      - LLRP handshake sur 5084
      - RTSP DESCRIBE sur 554 (caméra IP ONVIF)

    Réponse : {
      "ip": "...", "reachable": true/false,
      "probes": [{"name": "TCP 4370", "ok": true, "ms": 3}, ...],
      "identified": {"brand": "Hikvision", "model": "DS-K1T671M", ...} | null,
    }
    """
    permission_classes = [HasKshieldPermission]
    kshield_perms = {"read": "devices.view", "write": "devices.manage"}

    def post(self, request):
        import socket
        import time as _time

        ip = (request.data.get("ip") or "").strip()
        if not ip:
            return Response({"error": "ip requise"}, status=400)

        # Validation basique
        try:
            socket.inet_aton(ip)
        except OSError:
            try:
                ip = socket.gethostbyname(ip)
            except OSError as exc:
                return Response({
                    "ip": ip, "reachable": False,
                    "error": f"DNS/IP invalide : {exc}",
                }, status=200)

        start = _time.monotonic()
        # Timeout global : on doit répondre en < 15s pour ne pas atteindre le
        # timeout gunicorn (60s) ni Traefik (90s). Chaque probe TCP a un timeout
        # court (500ms) et on parallélise pour ne pas dépasser 1s au total.
        SCAN_PORTS = [
            (22, "SSH"), (80, "HTTP"), (443, "HTTPS"), (554, "RTSP"),
            (2000, "Onvif"), (4370, "ZKAccess"), (5084, "LLRP"),
            (8000, "Hikvision"), (8081, "ADMS"), (8443, "HTTPS-alt"),
            (9000, "MinIO-like"), (37777, "Dahua NetSDK"),
        ]
        PROBE_TIMEOUT = 0.6      # 600 ms max par port

        def _test_port(port_label):
            port, label = port_label
            t = _time.monotonic()
            ok = False
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.settimeout(PROBE_TIMEOUT)
                    ok = s.connect_ex((ip, port)) == 0
            except Exception:
                ok = False
            ms = int((_time.monotonic() - t) * 1000)
            return {"name": f"TCP {port} ({label})",
                    "ok": ok, "ms": ms, "port": port,
                    "label": label}

        from concurrent.futures import ThreadPoolExecutor
        probes = []
        open_ports = []
        with ThreadPoolExecutor(max_workers=12) as pool:
            for r in pool.map(_test_port, SCAN_PORTS, timeout=2.0):
                probes.append(r)
                if r["ok"]:
                    open_ports.append((r["port"], r["label"]))

        reachable = bool(open_ports)
        identified = None

        # ── Probe ZKAccess (4370) — 2s max ──
        if any(p == 4370 for p, _ in open_ports):
            try:
                from .zk_client import ZkClient, ZkConnectionError, ZkUnavailable
                try:
                    with ZkClient(ip, port=4370, timeout=2).open() as zk:
                        info = zk.info()
                    identified = {
                        "brand": "ZKTeco",
                        "model": info.get("name") or "K-series / SpeedFace",
                        "firmware": info.get("firmware"),
                        "serial": info.get("serial"),
                        "platform": info.get("platform"),
                        "protocol": "ZKAccess SDK",
                        "port": 4370,
                        "users_count": info.get("users_count"),
                        "fingerprints_count": info.get("fingerprints_count"),
                    }
                    probes.append({"name": "Dialogue ZKAccess SDK",
                                    "ok": True, "detail": info.get("name")})
                except (ZkUnavailable, ZkConnectionError) as exc:
                    probes.append({"name": "Dialogue ZKAccess SDK",
                                    "ok": False, "detail": str(exc)[:200]})
            except Exception:
                pass

        # ── Probe Hikvision ISAPI (80/443/8000) ──
        if identified is None and any(p in (80, 443, 8000, 8443) for p, _ in open_ports):
            try:
                import requests
                for port in (443, 80, 8000, 8443):
                    if port not in [p for p, _ in open_ports]:
                        continue
                    scheme = "https" if port in (443, 8443) else "http"
                    url = f"{scheme}://{ip}:{port}/ISAPI/System/deviceInfo"
                    try:
                        r = requests.get(url, timeout=1.5,
                                          verify=False, auth=None)
                        # Hikvision renvoie 401 sans auth mais headers reconnaissables
                        server = r.headers.get("Server", "")
                        auth_hdr = r.headers.get("WWW-Authenticate", "")
                        if ("app-webserver" in server.lower()
                                or "hikvision" in server.lower()
                                or "hikvision" in auth_hdr.lower()):
                            identified = {
                                "brand": "Hikvision",
                                "model": "DS-K1T ou compatible ISAPI",
                                "protocol": "ISAPI HTTP",
                                "port": port,
                                "server_header": server,
                                "requires_auth": r.status_code == 401,
                            }
                            probes.append({"name": f"Hikvision ISAPI ({port})",
                                            "ok": True, "detail": server})
                            break
                    except Exception:
                        continue
            except Exception:
                pass

        # ── Probe HTTP banner générique ──
        if identified is None:
            for port, _ in open_ports:
                if port not in (80, 443, 8000, 8081, 8443):
                    continue
                try:
                    import ssl as _ssl
                    import urllib.request
                    scheme = "https" if port in (443, 8443) else "http"
                    url = f"{scheme}://{ip}:{port}/"
                    ctx = _ssl.create_default_context()
                    ctx.check_hostname = False
                    ctx.verify_mode = _ssl.CERT_NONE
                    req = urllib.request.Request(
                        url, headers={"User-Agent": "KaydanShield-Identify/1.0"})
                    with urllib.request.urlopen(req, timeout=1.5, context=ctx) as r:
                        server = r.headers.get("Server", "")
                        body = r.read(4096).decode(errors="ignore").lower()
                    haystack = (server + " | " + body).lower()
                    for keyword, brand in (
                        ("hikvision",  "Hikvision"),
                        ("dahua",      "Dahua"),
                        ("dnvrs-webs", "Dahua"),
                        ("mongoose",   "Dahua"),
                        ("zkteco",     "ZKTeco"),
                        ("speedface",  "ZKTeco"),
                        ("anviz",      "Anviz"),
                        ("suprema",    "Suprema"),
                        ("impinj",     "Impinj"),
                        ("zebra",      "Zebra"),
                        ("axis",       "Axis"),
                    ):
                        if keyword in haystack:
                            identified = {
                                "brand": brand,
                                "protocol": f"HTTP ({port})",
                                "port": port,
                                "server_header": server,
                                "url": url,
                            }
                            probes.append({"name": f"HTTP banner ({port})",
                                            "ok": True, "detail": server})
                            break
                    if identified: break
                except Exception:
                    continue

        # ── Probe LLRP (5084) ──
        if identified is None and any(p == 5084 for p, _ in open_ports):
            try:
                with socket.socket() as s:
                    s.settimeout(2.0)
                    s.connect((ip, 5084))
                    raw = s.recv(10)
                if raw and len(raw) >= 2:
                    identified = {
                        "brand": "Générique",
                        "model": "Lecteur RFID UHF (LLRP)",
                        "protocol": "LLRP",
                        "port": 5084,
                    }
                    probes.append({"name": "Handshake LLRP",
                                    "ok": True, "detail": raw.hex()[:20]})
            except Exception:
                pass

        duration = int((_time.monotonic() - start) * 1000)
        return Response({
            "ip": ip,
            "reachable": reachable,
            "duration_ms": duration,
            "open_ports": [p for p, _ in open_ports],
            "probes": probes,
            "identified": identified,
        })


class FaceTerminalEventView(APIView):
    """Webhook générique pour events des terminaux face reco.

    URL : POST /api/v1/devices/face-terminal/<sn>/event/
    Body accepté (format standardisé, chaque marque peut en dériver) :
        {
          "user_id": "42",           // ID interne terminal (ou matricule employé)
          "timestamp": "2026-07-06T18:00:00Z",
          "similarity": 0.87,        // 0–1
          "method": "face" | "card" | "hybrid",
          "granted": true,
          "mask_detected": true,
          "temperature": 36.5,
          "photo_base64": "..."      // optionnel — snapshot
        }
    """
    permission_classes = [AllowAny]

    def post(self, request, sn=None):
        from datetime import datetime

        from django.utils import timezone

        from access_control.models import AccessEvent

        from .models import Device
        from .tasks import _fallback_site, _resolve_direction

        if not sn:
            return Response({"error": "sn requis"}, status=400)
        device = Device.objects.filter(serial_number=sn).first()
        if not device:
            return Response({"error": f"terminal inconnu : {sn}"}, status=404)

        data = request.data or {}
        user_id = str(data.get("user_id") or "")
        ts = data.get("timestamp")
        if isinstance(ts, str):
            try:
                ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except Exception:
                ts = timezone.now()
        else:
            ts = timezone.now()
        if hasattr(ts, "tzinfo") and ts.tzinfo is None:
            ts = timezone.make_aware(ts, timezone.get_current_timezone())

        # Lookup Employee par matricule/user_id
        from employees.models import Employee
        from django.contrib.contenttypes.models import ContentType
        emp = None
        if user_id:
            emp = Employee.objects.filter(
                tenant=device.tenant, matricule=user_id,
            ).first() or Employee.objects.filter(
                tenant=device.tenant, pk=user_id if user_id.isdigit() else 0,
            ).first()

        holder_kind = "unknown"; holder_ct = None; holder_oid = None
        if emp:
            holder_kind = "employee"
            holder_ct = ContentType.objects.get_for_model(Employee)
            holder_oid = emp.pk

        granted = bool(data.get("granted", True))
        decision = "granted" if granted else "denied"
        denial = "" if granted else (data.get("reason") or "Face non reconnue")

        class _Att: punch = 0
        direction = _resolve_direction(device=device, badge=None, att=_Att())

        AccessEvent.objects.create(
            tenant=device.tenant,
            timestamp=ts,
            site=device.site or _fallback_site(device),
            zone=getattr(device, "zone", None),
            checkpoint=getattr(device, "checkpoint", None),
            direction=direction,
            method="face" if data.get("method", "face") == "face" else "nfc",
            decision=decision,
            denial_reason=denial,
            device=device,
            badge_uid="",
            holder_kind=holder_kind,
            holder_content_type=holder_ct,
            holder_object_id=holder_oid,
            raw_payload={
                "source": "face_terminal_webhook",
                "terminal_user_id": user_id,
                "similarity": data.get("similarity"),
                "mask_detected": data.get("mask_detected"),
                "temperature": data.get("temperature"),
                "method": data.get("method"),
            },
        )
        device.last_heartbeat_at = timezone.now()
        device.save(update_fields=["last_heartbeat_at"])
        return Response({"ok": True, "matched_employee": emp.pk if emp else None})


class FacePushEmployeeView(APIView):
    """POST /api/v1/devices/employees/<pk>/push-face/ — provisionne la photo
    de l'employé sur TOUS les terminaux face du tenant.
    """
    permission_classes = [HasKshieldPermission]
    kshield_perms = {"read": "employees.view", "write": "employees.manage"}

    def post(self, request, pk):
        from employees.models import Employee

        from .face_terminal import (FaceRecord, FaceTerminalError, get_adapter,
                                      is_face_terminal)
        from .models import Device

        try:
            emp = Employee.objects.get(pk=pk)
        except Employee.DoesNotExist:
            return Response({"error": "employé introuvable"}, status=404)

        if not emp.photo:
            return Response(
                {"error": "employé sans photo — uploader d'abord via /employees/<id>/update/"},
                status=400,
            )

        try:
            with emp.photo.open("rb") as f:
                photo_bytes = f.read()
        except Exception as exc:
            return Response({"error": f"photo illisible : {exc}"}, status=400)

        targets = [d for d in Device.objects.filter(
            tenant=getattr(emp, "tenant", None) or None,
            status="active", ip_address__isnull=False,
        ) if is_face_terminal(d)]

        if not targets:
            return Response({"error": "aucun terminal face actif"}, status=400)

        record = FaceRecord(
            user_id=str(emp.pk),
            name=f"{emp.first_name} {emp.last_name}".strip()[:32],
            photo_bytes=photo_bytes,
        )
        results = []
        for d in targets:
            try:
                adapter = get_adapter(d)
                ok = adapter.push_face(record)
                results.append({"device": d.serial_number, "ok": bool(ok)})
            except FaceTerminalError as exc:
                results.append({"device": d.serial_number, "ok": False,
                                  "error": str(exc)[:200]})

        return Response({
            "employee": str(emp),
            "photo_size_bytes": len(photo_bytes),
            "devices_targeted": len(targets),
            "devices_succeeded": sum(1 for r in results if r["ok"]),
            "results": results,
        })


class BleGatewayIngestView(APIView):
    """Endpoint d'ingestion des pings BLE depuis une gateway (Aruba, Estimote,
    Kontakt.io, Minew) ou directement depuis l'app mobile contrôleur.

    Reçoit la liste des beacons détectés (MOKO H7 Lite typiquement) avec leur
    RSSI. Pour chaque ping :
      1. Lookup ``Helmet`` par ``ble_beacon_uid`` (MAC ou UUID)
      2. Crée un ``BLEPresencePing``
      3. Si le casque est actif et associé à un worker → met à jour
         ``helmet.last_seen_at``

    URL : POST /api/v1/devices/ble-gateway/<gateway_serial>/ingest/

    Body :
        {
          "beacons": [
            {
              "mac": "AA:BB:CC:11:22:33",     // ou "uuid": "...", "major": 1, "minor": 42
              "rssi": -67,
              "timestamp": "2026-06-16T15:30:00Z",  // optionnel
              "battery": 88                          // optionnel %
            },
            ...
          ],
          "site_id": 1                  // optionnel — sinon prend le site de la gateway
        }

    Réponse : {"ingested": N, "matched": M, "unknown": K}

    Auth : ouvert (les gateways ne signent pas). Sécurité par le fait que
    le gateway_serial doit matcher un Device enregistré.
    """
    permission_classes = [AllowAny]

    def post(self, request, gateway_serial=None):
        from datetime import datetime

        from django.utils import timezone

        from attendance.models import BLEPresencePing

        from .models import Device, Helmet

        # 1) Identifier la gateway
        if not gateway_serial:
            return Response({"error": "gateway_serial requis"}, status=400)
        gateway = Device.objects.filter(serial_number=gateway_serial).first()
        if not gateway:
            return Response(
                {"error": f"Gateway inconnue : {gateway_serial}"},
                status=404,
            )

        body = request.data or {}
        beacons = body.get("beacons") or []
        if not isinstance(beacons, list):
            return Response({"error": "beacons doit être une liste"}, status=400)

        site = gateway.site
        if body.get("site_id"):
            from sites.models import Site
            site = Site.objects.filter(pk=body["site_id"]).first() or site

        ingested = 0; matched = 0; unknown = 0
        unknown_uids = []

        for b in beacons[:1000]:    # cap soft
            # UID : on accepte MAC ou UUID
            uid = (b.get("mac") or b.get("uuid") or "").strip().upper()
            if not uid:
                continue

            rssi = b.get("rssi")
            try: rssi = int(rssi) if rssi is not None else None
            except (TypeError, ValueError): rssi = None

            ts = b.get("timestamp")
            if isinstance(ts, str):
                try:
                    ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                except Exception:
                    ts = timezone.now()
            elif ts is None:
                ts = timezone.now()
            if hasattr(ts, "tzinfo") and ts.tzinfo is None:
                ts = timezone.make_aware(ts, timezone.get_current_timezone())

            # Lookup Helmet
            helmet = (Helmet.objects
                      .filter(tenant=gateway.tenant, ble_beacon_uid=uid)
                      .first())
            if not helmet:
                unknown += 1
                if len(unknown_uids) < 10:
                    unknown_uids.append(uid)
                continue

            # Crée le ping
            try:
                BLEPresencePing.objects.create(
                    helmet=helmet,
                    zone=getattr(gateway, "zone", None),
                    timestamp=ts,
                    rssi=rssi,
                    is_immobile=bool(b.get("is_immobile", False)),
                    accelerometer_payload=b.get("accel") or {},
                )
                ingested += 1
                matched += 1
            except Exception:
                logger.exception("BLE ping create failed for %s", uid)

            # Met à jour last_seen + battery
            update_fields = ["last_seen_at"]
            helmet.last_seen_at = ts
            battery = b.get("battery")
            if battery is not None:
                try:
                    helmet.last_battery_level = int(battery)
                    update_fields.append("last_battery_level")
                except (TypeError, ValueError):
                    pass
            try:
                helmet.save(update_fields=update_fields)
            except Exception:
                logger.exception("Helmet save failed %s", helmet.pk)

        # Heartbeat gateway
        gateway.last_heartbeat_at = timezone.now()
        gateway.save(update_fields=["last_heartbeat_at"])

        return Response({
            "ingested": ingested,
            "matched": matched,
            "unknown": unknown,
            "unknown_uids_sample": unknown_uids,
        })


class IclockGetRequestView(APIView):
    """GET /iclock/getrequest?SN=<sn>&INFO=... — heartbeat + demandes de commandes.

    Le terminal ADMS appelle cet endpoint toutes les N secondes pour :
      - annoncer sa présence (SN + info firmware/IP/version)
      - récupérer d'éventuelles commandes en attente (ex. "reboot", "clear log")

    Shield renvoie ``OK\\n`` en text/plain (ou la commande à exécuter si dispo).
    Cet endpoint sert de heartbeat et met à jour ``device.last_heartbeat_at``.
    """
    permission_classes = [AllowAny]

    def get(self, request):
        from django.http import HttpResponse
        from django.utils import timezone

        from .models import Device

        sn = request.query_params.get("SN") or request.query_params.get("sn") or ""
        info = request.query_params.get("INFO") or ""

        if sn:
            device = Device.objects.filter(serial_number=sn).first()
            if device:
                device.last_heartbeat_at = timezone.now()
                update = ["last_heartbeat_at"]
                # Le champ INFO contient souvent version|user_count|log_count|...
                if info and info != device.firmware_version:
                    parts = info.split("|")
                    if parts and parts[0] != device.firmware_version:
                        device.firmware_version = parts[0][:40]
                        update.append("firmware_version")
                device.save(update_fields=update)
                logger.debug("iclock heartbeat from %s (%s)", sn, info[:40])

        # ADMS attend "OK\n" ou une commande à exécuter.
        # Pour l'instant on répond juste OK. Plus tard on pourra retourner
        # des commandes en attente (queue Redis).
        return HttpResponse("OK\n", content_type="text/plain")


class IclockDeviceCmdView(APIView):
    """POST /iclock/devicecmd?SN=<sn>&ID=<cmd_id> — ack d'une commande exécutée.

    Le terminal ADMS confirme ici qu'il a bien exécuté une commande précédemment
    reçue via /iclock/getrequest. Utilisé plus tard quand on implémentera
    l'envoi de commandes (reboot, sync users, etc.).
    """
    permission_classes = [AllowAny]

    def post(self, request):
        from django.http import HttpResponse
        return HttpResponse("OK\n", content_type="text/plain")

    def get(self, request):
        from django.http import HttpResponse
        return HttpResponse("OK\n", content_type="text/plain")


class PubApiCatchAllView(APIView):
    """POST /pub/api — Handler protocole AiFace / AI810 (firmware fp80v).

    Les terminaux AiFace whitebox chinois utilisent un protocole HTTP JSON
    custom au chemin `/pub/api`. Format des messages :

        REQUEST                                  RÉPONSE ATTENDUE
        ─────────────────────────                ─────────────────────────
        {"cmd":"reg", "sn":..., "devinfo":...}   {"ret":"reg", "result":true,
                                                  "cloudtime":"YYYY-MM-DD hh:mm:ss",
                                                  "nosenduser":false, ...}
        {"cmd":"sendlog", "sn":..., "log":[...]} {"ret":"sendlog", "result":true,
                                                  "count":N}
        {"cmd":"senduser", "sn":...,             {"ret":"senduser","result":true}
         "user":{...}}
        {"cmd":"sendface", "sn":...,             {"ret":"sendface","result":true}
         "user":..., "face":"base64..."}
        {"cmd":"sendfp", ...}                    {"ret":"sendfp","result":true}
        {"cmd":"sendpalm", ...}                  {"ret":"sendpalm","result":true}
        {"cmd":"sendcard", ...}                  {"ret":"sendcard","result":true}

    À chaque `reg` :
     - Mise à jour `device.last_heartbeat_at` et `firmware_version`
     - Le champ `usednewlog` indique combien de logs le terminal n'a pas encore
       poussé — s'il est > 0, on renvoie `nosenduser=false, needlog=true` pour
       forcer le push.

    Fait un fallback vers l'ancienne logique de log brut si `cmd` inconnu.
    """
    permission_classes = [AllowAny]

    def _log_and_cache(self, request, raw_body, client_ip):
        """Log Docker + cache Redis (utile pour reverse eng nouveaux protocoles)."""
        from django.core.cache import cache
        logger.info(
            "[pub/api %s] ip=%s ct=%s bytes=%d body=%r",
            request.method, client_ip, request.content_type,
            len(request.body or b""), raw_body[:400],
        )
        try:
            key = f"pubapi_hits:{client_ip}"
            entries = cache.get(key) or []
            entries.append({
                "at": timezone.now().isoformat(),
                "method": request.method,
                "path": request.path,
                "content_type": request.content_type,
                "query": dict(request.query_params.items()),
                "body_preview": raw_body[:1000],
                "user_agent": request.META.get("HTTP_USER_AGENT", "")[:200],
            })
            cache.set(key, entries[-20:], 3600)
            ips = set(cache.get("pubapi_client_ips") or [])
            ips.add(client_ip)
            cache.set("pubapi_client_ips", list(ips), 3600)
        except Exception:
            logger.exception("pub/api cache logging failed")

    def _handle(self, request):
        import json
        from django.http import HttpResponse, JsonResponse

        raw_body = (request.body or b"").decode(errors="ignore")
        client_ip = (
            request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip()
            or request.META.get("REMOTE_ADDR", "unknown")
        )
        self._log_and_cache(request, raw_body[:2000], client_ip)

        # GET → répond OK simple (ping / probe)
        if request.method == "GET":
            return HttpResponse("OK\n", content_type="text/plain")

        # Tente parsing JSON
        try:
            payload = json.loads(raw_body) if raw_body else {}
        except Exception:
            return HttpResponse("OK\n", content_type="text/plain")

        cmd = (payload.get("cmd") or "").lower()
        sn = payload.get("sn") or ""

        # ─── Dispatch selon cmd ───
        handler = {
            "reg":       self._cmd_reg,
            "sendlog":   self._cmd_sendlog,
            "senduser":  self._cmd_senduser,
            "sendface":  self._cmd_sendface,
            "sendfp":    self._cmd_generic_ack,
            "sendpalm":  self._cmd_generic_ack,
            "sendcard":  self._cmd_generic_ack,
            "sendpwd":   self._cmd_generic_ack,
        }.get(cmd, self._cmd_unknown)

        try:
            return handler(cmd, sn, payload)
        except Exception as exc:
            logger.exception("AiFace handler %s failed: %s", cmd, exc)
            return JsonResponse({"ret": cmd, "result": False, "reason": "server_error"})

    # ─────────────────────────────────────────────────────────
    # /pub/api command handlers
    # ─────────────────────────────────────────────────────────
    def _cmd_reg(self, cmd, sn, payload):
        """Handshake initial + heartbeat périodique.

        Met à jour Device.last_heartbeat_at et firmware. Répond avec
        cloudtime + nosenduser=false pour autoriser l'upload des logs.
        """
        from django.http import JsonResponse
        from .models import Device

        device = Device.objects.filter(serial_number=sn).first()
        if device:
            devinfo = payload.get("devinfo") or {}
            fw = devinfo.get("firmware") or ""
            update_fields = ["last_heartbeat_at"]
            device.last_heartbeat_at = timezone.now()
            if fw and fw != device.firmware_version:
                device.firmware_version = fw[:40]
                update_fields.append("firmware_version")
            device.save(update_fields=update_fields)

            # Compte de logs en attente sur le terminal
            new_log_count = devinfo.get("usednewlog") or 0
            if new_log_count > 0:
                logger.info(
                    "AiFace %s a %d log(s) non poussé(s) — on demande le push",
                    sn, new_log_count,
                )
        else:
            logger.warning(
                "AiFace reg reçu de SN inconnu '%s' — enregistre le Device", sn,
            )

        # Réponse dans le format attendu par le firmware.
        # On envoie TOUS les flags connus des variantes de firmware AiFace/AI810
        # pour maximiser les chances de trigger le push des logs.
        now_str = timezone.now().strftime("%Y-%m-%d %H:%M:%S")
        return JsonResponse({
            # Champs standard
            "ret": "reg",
            "result": True,
            "cloudtime": now_str,
            "cloud_time": now_str,   # alias
            "servertime": now_str,   # autre alias possible
            "code": 0,               # certains firmwares veulent code:0
            "message": "OK",

            # Flags de contrôle — le firmware push les logs si:
            "nosenduser": False,       # push users OK
            "nosendlog": False,        # push logs OK
            "nosendface": False,       # push faces OK
            "nosendfp": False,
            "nosendpalm": False,
            "nosendcard": False,
            "nosendpwd": False,
            "needlog": True,           # variante : demande explicite
            "sendlog": True,           # variante
            "getalllog": True,         # variante : envoie TOUS les logs, pas seulement les nouveaux
            "trans_flag": "1111111111",  # ZKTeco-style flags (11 chiffres)
            "realtime": 1,             # activer push realtime
            "encrypt": 0,              # pas de chiffrement
            "log_upload": 1,           # upload logs
        })

    def _cmd_sendlog(self, cmd, sn, payload):
        """Le terminal envoie une batch de logs (events de scan face).

        Format attendu du log[] :
            [
              {"enrollid":123, "time":"2026-07-08 12:15:32", "mode":8,
               "inout":0, "event":0, ...},
              ...
            ]

        mode : 8=face, 1=fingerprint, 4=card, 2=palm, 16=password
        inout: 0=in, 1=out
        event: 0=verify ok, 1=verify fail
        """
        from datetime import datetime
        from django.contrib.contenttypes.models import ContentType
        from django.http import JsonResponse

        from access_control.models import AccessEvent
        from .models import Device

        device = Device.objects.filter(serial_number=sn).first()
        if not device:
            logger.warning("AiFace sendlog reçu de SN inconnu '%s'", sn)
            return JsonResponse({"ret": "sendlog", "result": True, "count": 0})

        logs = payload.get("log") or payload.get("logs") or []
        if isinstance(logs, dict):
            logs = [logs]

        site = device.site
        if not site:
            logger.warning("AiFace %s: device sans site — events non enregistrés", sn)
            return JsonResponse({"ret": "sendlog", "result": True, "count": 0})

        created = 0
        for entry in logs:
            try:
                # Timestamp — format "YYYY-MM-DD HH:MM:SS"
                ts_str = entry.get("time") or entry.get("timestamp") or ""
                ts = None
                for fmt in ("%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
                    try:
                        ts = datetime.strptime(ts_str, fmt)
                        break
                    except ValueError:
                        continue
                if ts is None:
                    ts = timezone.now()
                else:
                    ts = timezone.make_aware(ts) if timezone.is_naive(ts) else ts

                mode = int(entry.get("mode", 0))
                method = {8: "face", 1: "fingerprint", 4: "nfc", 2: "palm",
                          16: "password"}.get(mode, "manual")
                # Notre model n'a pas "face" en choix → on utilise "nfc" pour face
                # (le vrai type est traçable via raw_payload)
                api_method = "nfc" if method in ("face", "fingerprint", "palm", "password") else method

                inout = int(entry.get("inout", 0))
                direction = "in" if inout == 0 else "out"

                event_code = int(entry.get("event", 0))
                decision = "granted" if event_code == 0 else "denied"

                enrollid = str(entry.get("enrollid") or entry.get("userid") or "")

                # Résolution du holder par matricule/enrollid
                holder_kind = "unknown"
                holder_ct = None
                holder_id = None
                if enrollid:
                    # Essaie employee.matricule puis worker.matricule
                    try:
                        from employees.models import Employee
                        emp = Employee.objects.filter(
                            tenant=device.tenant, matricule=enrollid,
                        ).first()
                        if emp:
                            holder_kind = "employee"
                            holder_ct = ContentType.objects.get_for_model(Employee)
                            holder_id = emp.id
                        else:
                            from ouvriers.models import Worker
                            w = Worker.objects.filter(
                                tenant=device.tenant, matricule=enrollid,
                            ).first()
                            if w:
                                holder_kind = "worker"
                                holder_ct = ContentType.objects.get_for_model(Worker)
                                holder_id = w.id
                    except Exception:
                        pass

                AccessEvent.objects.create(
                    tenant=device.tenant,
                    site=site,
                    device=device,
                    timestamp=ts,
                    badge_uid=enrollid,       # tag l'enrollid comme uid pour recherche
                    holder_kind=holder_kind,
                    holder_content_type=holder_ct,
                    holder_object_id=holder_id,
                    direction=direction,
                    method=api_method,
                    decision=decision,
                    denial_reason="" if decision == "granted" else "AIFACE_VERIFY_FAIL",
                )
                created += 1
            except Exception as exc:
                logger.warning("AiFace log entry skip: %s | %r", exc, entry)

        # Update heartbeat au passage
        device.last_heartbeat_at = timezone.now()
        device.save(update_fields=["last_heartbeat_at"])

        logger.info("AiFace %s: %d event(s) créés (batch de %d)", sn, created, len(logs))
        return JsonResponse({
            "ret": "sendlog",
            "result": True,
            "count": created,
            "cloudtime": timezone.now().strftime("%Y-%m-%d %H:%M:%S"),
        })

    def _cmd_senduser(self, cmd, sn, payload):
        """Le terminal envoie un user enrôlé localement (via écran tactile).

        Format : {"cmd":"senduser","sn":...,"user":{"enrollid":..,"name":"...","admin":0}}
        """
        from django.http import JsonResponse
        user = payload.get("user") or {}
        logger.info(
            "AiFace %s: senduser reçu enrollid=%s name=%s",
            sn, user.get("enrollid"), user.get("name"),
        )
        # TODO : créer/upsert Employee ou Worker selon convention matricule
        return JsonResponse({"ret": "senduser", "result": True})

    def _cmd_sendface(self, cmd, sn, payload):
        """Template face reçu depuis le terminal (base64).

        On stocke la ref pour push ultérieur ou association employé.
        """
        from django.http import JsonResponse
        from django.core.cache import cache

        enrollid = str(payload.get("enrollid") or payload.get("userid") or "")
        face_b64 = payload.get("face") or payload.get("faceimage") or ""
        if enrollid and face_b64:
            # Cache 24h — permettra le push vers d'autres terminaux
            cache.set(f"aiface_template:{sn}:{enrollid}", face_b64[:200000], 86400)
            logger.info(
                "AiFace %s: template face reçu pour enrollid=%s (%d bytes)",
                sn, enrollid, len(face_b64),
            )
        return JsonResponse({"ret": "sendface", "result": True})

    def _cmd_generic_ack(self, cmd, sn, payload):
        """Ack générique pour sendfp/sendpalm/sendcard/sendpwd — pas d'action métier
        pour l'instant, on accuse juste réception pour que le terminal continue."""
        from django.http import JsonResponse
        logger.debug("AiFace %s: %s reçu (ack générique)", sn, cmd)
        return JsonResponse({"ret": cmd, "result": True})

    def _cmd_unknown(self, cmd, sn, payload):
        """Commande AiFace inconnue — on ack pour éviter le retry, mais on log
        les clés pour analyse."""
        from django.http import JsonResponse
        keys = list(payload.keys())[:10]
        logger.warning("AiFace %s: cmd inconnu '%s' — keys=%s", sn, cmd, keys)
        return JsonResponse({"ret": cmd, "result": True})

    # ─────────────────────────────────────────────────────────
    # HTTP methods
    # ─────────────────────────────────────────────────────────
    def get(self, request, *args, **kwargs):
        return self._handle(request)

    def post(self, request, *args, **kwargs):
        return self._handle(request)

    def put(self, request, *args, **kwargs):
        return self._handle(request)


class PubApiDebugView(APIView):
    """GET /api/v1/devices/pubapi-debug/ — dump des derniers POST /pub/api par IP.

    Vue admin pour inspecter ce que des équipements inconnus envoient sur
    /pub/api (chemin utilisé par certains firmwares chinois whitebox).
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from django.core.cache import cache
        ips = cache.get("pubapi_client_ips") or []
        result = {}
        for ip in ips:
            entries = cache.get(f"pubapi_hits:{ip}") or []
            result[ip] = {
                "count": len(entries),
                "last": entries[-1] if entries else None,
                "entries": entries[-5:],  # 5 derniers pour compacité
            }
        return Response({
            "ips": list(ips),
            "detail_by_ip": result,
        })


class DeviceIclockDebugView(APIView):
    """GET /api/v1/devices/<id>/iclock-debug/ — dump des derniers POST bruts iclock/cdata.

    Sert à reverse-engineer le format d'un terminal push inconnu (ex. AiFace ai810)
    quand aucun AccessEvent n'est créé alors que le heartbeat fonctionne.

    Retourne les 20 derniers body preview (2KB max chacun) stockés en cache Redis
    depuis les hits ZkAdmsWebhookView.post().
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        from django.core.cache import cache
        from .models import Device
        try:
            device = Device.objects.get(pk=pk)
        except Device.DoesNotExist:
            return Response({"error": "Device introuvable"}, status=404)
        sn = device.serial_number or ""
        if not sn:
            return Response({
                "sn": None,
                "entries": [],
                "hint": "Ce device n'a pas de serial_number défini.",
            })
        entries = cache.get(f"iclock_last_post:{sn}") or []
        return Response({
            "sn": sn,
            "device_id": device.pk,
            "device_name": device.name,
            "last_heartbeat_at": device.last_heartbeat_at,
            "entries_count": len(entries),
            "entries": entries,
        })


class ZkAdmsWebhookView(APIView):
    """Endpoint ADMS / push HTTP des terminaux ZKTeco.

    Plusieurs terminaux ZKTeco supportent un mode "ADMS" (Auto Data Management
    Server) où ils POSTent chaque event de vérification (succès ET échec) à un
    serveur HTTP au lieu d'attendre un pull.

    URL côté terminal à configurer (menu → COMM → Cloud Server) :
        http://<shield_host>/api/v1/devices/zk-adms/<serial>/cdata
        ou simplement /iclock/cdata avec stamp= et SN= en query string.

    On accepte deux variantes du payload :

    A) JSON :
       {"sn": "CQUJ222460289", "user_id": "1", "card": 6238480,
        "timestamp": "2026-06-09 12:34:56", "status": 0,
        "punch": 0, "verify": "card"}

    B) Format ATTLOG raw (legacy ZKTeco) :
       Tab-separated lines: <user_id>\\t<timestamp>\\t<status>\\t<verify>...

    Auth : on autorise tous (les K14 ne signent pas) — la sécurité vient du
    fait que le `sn` doit matcher un Device.serial_number connu.
    """
    permission_classes = [AllowAny]   # webhook depuis le terminal lui-même

    def get(self, request, sn=None):
        """GET /iclock/cdata?SN=<sn>&options=all — test de disponibilité initial.

        Les terminaux ADMS envoient d'abord un GET pour vérifier que le serveur
        répond, puis basculent en POST pour les events. On retourne du texte
        au format attendu par ZKTeco : "GetOption\\nDelay=30\\n..." + OK.
        """
        from django.http import HttpResponse
        # Configuration renvoyée : delay heartbeat 30s, transaction 5s
        cfg = (
            "GetOption\n"
            "Delay=30\n"
            "TransTimes=00:00\n"
            "TransInterval=5\n"
            "TransFlag=1111111111\n"
            "TimeZone=0\n"
            "Realtime=1\n"
            "Encrypt=None\n"
        )
        return HttpResponse(cfg, content_type="text/plain")

    def post(self, request, sn=None):
        from datetime import datetime

        from django.contrib.contenttypes.models import ContentType
        from django.utils import timezone

        from access_control.models import AccessEvent

        from .models import Badge, Device
        from .tasks import _resolve_direction, _fallback_site

        # Détermine le SN du terminal : via URL ou query string ou body
        if not sn:
            sn = (request.query_params.get("SN") or request.query_params.get("sn")
                  or (request.data or {}).get("sn"))
        if not sn:
            return Response({"error": "sn requis"}, status=400)

        # ── Log DEBUG du body brut : indispensable pour reverse-engineer les
        # firmwares custom (AiFace ai810, etc.) qui utilisent des formats variés.
        # Chaque POST enregistré dans le cache Redis (TTL 1h) pour debug UI.
        try:
            raw_body = request.body.decode(errors="ignore")[:2000]
            table = request.query_params.get("table") or ""
            stamp = request.query_params.get("Stamp") or ""
            logger.info(
                "[iclock POST] SN=%s table=%s stamp=%s content-type=%s bytes=%d "
                "body_preview=%r",
                sn, table, stamp, request.content_type, len(request.body or b""),
                raw_body[:400],
            )
            # Stocke aussi dans le cache pour inspection UI/API
            from django.core.cache import cache
            key = f"iclock_last_post:{sn}"
            entries = cache.get(key) or []
            entries.append({
                "at": timezone.now().isoformat(),
                "table": table,
                "content_type": request.content_type,
                "body_preview": raw_body[:1000],
                "query": dict(request.query_params.items()),
            })
            cache.set(key, entries[-20:], 3600)   # garde 20 derniers, 1h
        except Exception:
            logger.exception("iclock body logging failed")

        device = Device.objects.filter(serial_number=sn).first()
        if not device:
            # Auto-provisioning : si un terminal push avec un SN inconnu,
            # on log un warning au lieu de renvoyer 404 (sinon le terminal
            # retry en boucle). L'admin peut ensuite enregistrer le device
            # manuellement avec ce SN.
            logger.warning(
                "iclock/cdata reçu de SN inconnu '%s' — enregistre le Device dans Shield",
                sn,
            )
            from django.http import HttpResponse
            return HttpResponse("OK\n", content_type="text/plain")

        # Parse les events (JSON ou ATTLOG raw)
        events_in = self._parse_payload(request)
        if not events_in:
            return Response({"received": 0, "ok": True})

        # Cache du mapping user_id → card côté Shield (Badge stocké par card)
        created = 0
        errors = []
        for ev in events_in:
            try:
                user_id = str(ev.get("user_id") or "")
                card = ev.get("card") or 0
                badge_uid_str = str(card) if card else user_id
                ts = ev.get("timestamp")
                if isinstance(ts, str):
                    try:
                        ts = datetime.fromisoformat(ts.replace(" ", "T"))
                    except Exception:
                        ts = timezone.now()
                if hasattr(ts, "tzinfo") and ts.tzinfo is None:
                    ts = timezone.make_aware(ts, timezone.get_current_timezone())

                badge = Badge.objects.filter(
                    tenant=device.tenant, uid=badge_uid_str,
                ).first()
                holder_kind = "unknown"
                holder_ct = None
                holder_oid = None
                if badge and badge.holder_object_id:
                    holder_kind = badge.holder_kind or "unknown"
                    holder_ct = badge.holder_content_type
                    holder_oid = badge.holder_object_id

                # Status ADMS : certains firmwares envoient status=5 pour
                # "rejected" et 0/1 pour granted in/out
                raw_status = ev.get("status")
                verify = (ev.get("verify") or "").lower()
                decision = "granted"
                denial = ""
                if not badge:
                    decision = "denied"
                    denial = f"Badge inconnu : {badge_uid_str}"
                elif raw_status in (5, "5"):
                    decision = "denied"
                    denial = "Vérification refusée par le terminal"
                elif verify in ("invalid", "fail", "rejected"):
                    decision = "denied"
                    denial = "Carte refusée"

                # Direction via checkpoint ou toggle
                class _Att:
                    punch = ev.get("punch") or 0
                direction = _resolve_direction(device=device, badge=badge,
                                                  att=_Att())

                AccessEvent.objects.create(
                    tenant=device.tenant,
                    timestamp=ts,
                    site=device.site or _fallback_site(device),
                    zone=getattr(device, "zone", None),
                    checkpoint=getattr(device, "checkpoint", None),
                    direction=direction,
                    method="nfc",
                    decision=decision,
                    denial_reason=denial,
                    device=device,
                    badge_uid=badge_uid_str,
                    holder_kind=holder_kind,
                    holder_content_type=holder_ct,
                    holder_object_id=holder_oid,
                    raw_payload={
                        "source": "zkteco_adms",
                        "zk_user_id": user_id,
                        "zk_card": card,
                        "zk_status": raw_status,
                        "zk_verify": verify,
                        "zk_punch": ev.get("punch"),
                    },
                )
                created += 1
            except Exception as exc:
                errors.append(str(exc)[:200])

        # Heartbeat OK
        device.last_heartbeat_at = timezone.now()
        device.save(update_fields=["last_heartbeat_at"])

        # Le K14 attend une réponse simple "OK" en text/plain pour confirmer
        # l'ingestion. On retourne ça si le content-type d'origine était texte.
        if "text" in (request.content_type or "").lower():
            from django.http import HttpResponse
            return HttpResponse("OK\n", content_type="text/plain")
        return Response({"received": len(events_in), "created": created,
                          "errors": errors})

    def _parse_payload(self, request):
        """Extrait une liste d'events depuis le body, JSON ou ATTLOG raw."""
        # JSON
        if isinstance(request.data, dict):
            if "events" in request.data:
                return request.data["events"]
            # Single event
            if "user_id" in request.data or "card" in request.data:
                return [request.data]
        if isinstance(request.data, list):
            return request.data

        # ATTLOG raw (text/plain, lignes tab-separated)
        raw = request.body.decode(errors="ignore") if request.body else ""
        if not raw or "\t" not in raw:
            return []
        events = []
        for line in raw.splitlines():
            parts = line.split("\t")
            if len(parts) < 2:
                continue
            try:
                events.append({
                    "user_id": parts[0].strip(),
                    "timestamp": parts[1].strip(),
                    "status": int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else None,
                    "verify": parts[3].strip() if len(parts) > 3 else "",
                    "punch": int(parts[4]) if len(parts) > 4 and parts[4].lstrip("-").isdigit() else 0,
                })
            except Exception:
                continue
        return events


class ZkPushEmployeeView(APIView):
    """POST /api/v1/devices/employees/<pk>/push-to-zk/ — pousse un employé vers
    TOUS les terminaux ZKTeco actifs de son tenant.

    Récupère le badge actif de l'employé, dérive (uid ZK, card) et set_user sur
    chaque K14 du même tenant. Réponse : per-device status.

    Body optionnel : {"device_ids": [...]} pour cibler des K14 spécifiques.
    """
    permission_classes = [HasKshieldPermission]
    kshield_perms = {"read": "employees.view", "write": "employees.manage"}

    def post(self, request, pk):
        from django.contrib.contenttypes.models import ContentType

        from employees.models import Employee

        from .models import Badge, Device
        from .zk_client import ZkConnectionError, is_zkteco_device, safe_zk_session

        try:
            emp = Employee.objects.get(pk=pk)
        except Employee.DoesNotExist:
            return Response({"error": "employé introuvable"},
                              status=status.HTTP_404_NOT_FOUND)

        # Badge actif lié à cet employé (peut être attribué via Workflow 2A)
        emp_ct = ContentType.objects.get_for_model(Employee)
        badge = Badge.objects.filter(
            tenant=emp.tenant if hasattr(emp, "tenant") else None,
            holder_content_type=emp_ct,
            holder_object_id=emp.pk,
            status__in=("active", "assigned"),
        ).first()
        if not badge:
            # Fallback : sans tenant filter (en mono-tenant pas grave)
            badge = Badge.objects.filter(
                holder_content_type=emp_ct,
                holder_object_id=emp.pk,
                status__in=("active", "assigned"),
            ).first()
        if not badge:
            return Response({
                "error": "Cet employé n'a aucun badge actif. Attribue-lui d'abord "
                         "un badge via le Workflow 2A puis réessaye."
            }, status=status.HTTP_400_BAD_REQUEST)

        # Cible : tous les K14 actifs du tenant + IP renseignée
        target_devices = (
            Device.objects.select_related("model")
            .filter(status="active", ip_address__isnull=False)
        )
        if hasattr(badge, "tenant_id") and badge.tenant_id:
            target_devices = target_devices.filter(tenant_id=badge.tenant_id)
        device_ids = request.data.get("device_ids") if isinstance(
            request.data, dict) else None
        if device_ids:
            target_devices = target_devices.filter(pk__in=device_ids)
        # Garde seulement les vrais ZKTeco
        target_devices = [d for d in target_devices if is_zkteco_device(d)]

        if not target_devices:
            return Response({
                "error": "Aucun terminal ZKTeco actif éligible (vérifier brand "
                         "et IP des devices)."
            }, status=status.HTTP_400_BAD_REQUEST)

        # Dérive uid + card pour le push
        try:
            card_int = int(badge.uid, 16) if not badge.uid.isdigit() else int(badge.uid)
        except Exception:
            card_int = abs(hash(badge.uid)) % 9_999_999
        try:
            uid_int = card_int % 65500 + 1
        except Exception:
            uid_int = abs(hash(badge.uid)) % 65500 + 1
        name = (f"{emp.first_name} {emp.last_name}".strip()
                or emp.matricule or badge.uid)

        results = []
        for device in target_devices:
            pwd = 0
            if device.model and isinstance(device.model.spec, dict):
                pwd = int(device.model.spec.get("sdk_password", 0) or 0)
            with safe_zk_session(ip=device.ip_address, port=4370,
                                   password=pwd, timeout=4) as zk:
                if zk is None:
                    results.append({
                        "device_id": device.pk,
                        "device": device.serial_number,
                        "ok": False, "error": "session impossible",
                    })
                    continue
                try:
                    zk.set_user(
                        uid=uid_int, name=name[:24],
                        card=card_int, user_id=str(badge.uid)[:9],
                    )
                    results.append({
                        "device_id": device.pk,
                        "device": device.serial_number,
                        "ok": True, "uid": uid_int, "card": card_int,
                    })
                except ZkConnectionError as exc:
                    results.append({
                        "device_id": device.pk,
                        "device": device.serial_number,
                        "ok": False, "error": str(exc)[:200],
                    })

        success_count = sum(1 for r in results if r["ok"])
        return Response({
            "employee": str(emp),
            "badge_uid": badge.uid,
            "devices_targeted": len(target_devices),
            "devices_succeeded": success_count,
            "results": results,
        })


class ZkSyncAllView(APIView):
    """POST /api/v1/devices/zk-sync-all/ — sync immédiat de TOUS les terminaux ZKTeco.

    Idéal pour rafraîchir la page realtime à la demande (sans attendre le worker).
    """
    permission_classes = [HasKshieldPermission]
    kshield_perms = {"read": "devices.view", "write": "devices.manage"}

    def post(self, request):
        from .tasks import sync_zkteco_attendances
        try:
            result = sync_zkteco_attendances()   # pas de device_id = tous
        except Exception as exc:
            return Response({"error": str(exc)},
                              status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        return Response(result)


class ZkPushUsersNowView(APIView):
    """POST /api/v1/devices/<pk>/zk-push-users/ — push users immédiat."""
    permission_classes = [HasKshieldPermission]
    kshield_perms = {"read": "devices.view", "write": "devices.manage"}

    def post(self, request, pk):
        from .tasks import push_zkteco_users
        try:
            result = push_zkteco_users(device_id=pk)
        except Exception as exc:
            return Response({"error": str(exc)},
                              status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        return Response(result)


class DeviceConnectivityTestView(APIView):
    """POST /api/v1/devices/<pk>/test-connection/ — vérifie qu'un équipement répond.

    Pour un lecteur réseau, on enchaîne :
      1. Résolution DNS / présence de l'IP
      2. TCP connect sur les ports caractéristiques selon le type
         (5084 LLRP pour UHF, 80/443 HTTP, 8080, etc.)
      3. HTTP probe sur le premier port HTTP ouvert (récupère server header)
      4. LLRP handshake léger (lecture des 4 premiers bytes) sur 5084

    Réponse :
      {
        "device":   {"id": 5, "serial_number": "UHF-...", "ip": "192.168.1.50"},
        "reachable": true,
        "duration_ms": 123,
        "checks": [
          {"name": "DNS",     "ok": true,  "detail": "192.168.1.50"},
          {"name": "TCP 5084 (LLRP)", "ok": true, "ms": 12},
          {"name": "TCP 80 (HTTP)",   "ok": true, "ms": 8},
          {"name": "HTTP GET /",      "ok": true, "ms": 154, "status": 200, "server": "Impinj/1.0"},
          {"name": "LLRP handshake",  "ok": true, "ms": 25,  "msg_type": "GET_READER_CAPABILITIES_RESPONSE"}
        ]
      }
    """
    permission_classes = [HasKshieldPermission]
    kshield_perms = {"read": "devices.view", "write": "devices.manage"}

    def post(self, request, pk):
        import socket
        import time as _time
        from .models import Device

        try:
            device = Device.objects.select_related("model").get(pk=pk)
        except Device.DoesNotExist:
            return Response({"error": "device introuvable"},
                              status=status.HTTP_404_NOT_FOUND)

        ip = device.ip_address
        if not ip:
            return Response({
                "device": {"id": device.pk, "serial_number": device.serial_number},
                "reachable": False,
                "error": "Aucune IP renseignée pour cet équipement. "
                         "Modifier le device et renseigner ip_address.",
            }, status=status.HTTP_200_OK)

        from .zk_client import is_zkteco_device
        is_zk = is_zkteco_device(device)

        device_type = (device.model.type if device.model else "") or ""
        # Ports à tester selon le type
        if is_zk:
            # Terminal ZKTeco — port 4370 (SDK ZKAccess) + 80 (web) + 8081 (ADMS)
            ports = [(4370, "ZKAccess SDK"), (80, "HTTP"), (8081, "ADMS"), (4380, "ZK-HTTP")]
            try_llrp = False
        elif device_type.startswith("reader_uhf") or device_type == "portique":
            ports = [(5084, "LLRP"), (80, "HTTP"), (443, "HTTPS"), (22, "SSH")]
            try_llrp = True
        elif device_type.startswith("reader_nfc"):
            ports = [(80, "HTTP"), (443, "HTTPS"), (8000, "HTTP-alt"), (4370, "ZKAccess SDK")]
            try_llrp = False
        elif device_type == "beacon_ble":
            ports = [(80, "HTTP"), (443, "HTTPS"), (8080, "HTTP-alt"), (1883, "MQTT")]
            try_llrp = False
        elif device_type == "camera":
            ports = [(80, "HTTP"), (554, "RTSP"), (443, "HTTPS")]
            try_llrp = False
        else:
            # Lecteur générique
            ports = [(80, "HTTP"), (443, "HTTPS"), (5084, "LLRP"), (8080, "HTTP-alt"), (4370, "ZKAccess SDK")]
            try_llrp = (5084 in [p for p, _ in ports])

        start = _time.monotonic()
        checks = []

        # 1) DNS / IP résolu
        try:
            socket.inet_aton(ip)  # valid IPv4 ?
            checks.append({"name": "DNS / IP", "ok": True, "detail": ip})
        except OSError:
            try:
                resolved = socket.gethostbyname(ip)
                checks.append({"name": "DNS", "ok": True, "detail": resolved})
                ip = resolved
            except OSError as exc:
                checks.append({"name": "DNS", "ok": False, "detail": str(exc)})
                duration = int((_time.monotonic() - start) * 1000)
                return Response({
                    "device": {"id": device.pk, "serial_number": device.serial_number,
                                 "ip": device.ip_address},
                    "reachable": False, "checks": checks,
                    "duration_ms": duration,
                })

        # 2) TCP connect par port
        open_ports = []
        for port, label in ports:
            t = _time.monotonic()
            ok = False
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.settimeout(2.0)
                    ok = s.connect_ex((ip, port)) == 0
            except Exception:
                ok = False
            ms = int((_time.monotonic() - t) * 1000)
            checks.append({
                "name": f"TCP {port} ({label})",
                "ok": ok, "ms": ms, "port": port,
            })
            if ok:
                open_ports.append((port, label))

        # ── Warning si tous les ports semblent ouverts en < 10 ms depuis un
        # VPS et que l'IP est RFC1918 (probablement un rebond hébergeur) ──
        import ipaddress as _ipaddr
        try:
            _addr = _ipaddr.ip_address(ip)
            _is_private = _addr.is_private
        except Exception:
            _is_private = False
        if _is_private:
            fast_opens = [c for c in checks
                           if c.get("ok") and c.get("ms", 999) < 20]
            if fast_opens:
                checks.append({
                    "name": "⚠️  Alerte routage",
                    "ok": False,
                    "detail": (
                        f"L'IP {ip} est RFC1918 (privée) mais répond en < 20 ms "
                        f"depuis Shield. Le VPS où tourne Shield est probablement "
                        f"sur un réseau privé de l'hébergeur qui rebond sur autre "
                        f"chose. Utilise le MODE PUSH (le terminal envoie ses events "
                        f"à Shield) au lieu de compter sur ce scan."
                    ),
                })

        # 3) HTTP probe sur premier port HTTP ouvert — vérifie la vraie identité
        http_port = next((p for p, l in open_ports
                           if l in ("HTTP", "HTTPS", "HTTP-alt")), None)
        if http_port:
            scheme = "https" if http_port in (443, 8443) else "http"
            url = f"{scheme}://{ip}:{http_port}/"
            t = _time.monotonic()
            try:
                import ssl
                import urllib.request
                req = urllib.request.Request(
                    url, headers={"User-Agent": "KaydanShield-PingTest/1.0"},
                )
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                with urllib.request.urlopen(req, timeout=3.0, context=ctx) as resp:
                    code = resp.status
                    server = resp.headers.get("Server", "")
                ms = int((_time.monotonic() - t) * 1000)
                checks.append({
                    "name": f"HTTP GET {url}",
                    "ok": 200 <= code < 500, "ms": ms,
                    "status": code, "server": server,
                })
            except Exception as exc:
                ms = int((_time.monotonic() - t) * 1000)
                checks.append({
                    "name": f"HTTP GET {url}",
                    "ok": False, "ms": ms, "detail": str(exc)[:200],
                })

        # 4a) Check ZKAccess SDK approfondi : ouvre une vraie session pyzk,
        # récupère firmware + serial + count users. Beaucoup plus parlant
        # qu'un simple "port ouvert".
        if any(p == 4370 for p, _ in open_ports):
            t = _time.monotonic()
            try:
                from .zk_client import ZkClient, ZkConnectionError, ZkUnavailable
                pwd = 0
                if device.model and isinstance(device.model.spec, dict):
                    pwd = device.model.spec.get("sdk_password", 0) or 0
                try:
                    with ZkClient(ip, port=4370, password=int(pwd), timeout=4).open() as zk:
                        info = zk.info()
                except (ZkUnavailable, ZkConnectionError) as exc:
                    raise RuntimeError(str(exc))
                ms = int((_time.monotonic() - t) * 1000)
                detail = (
                    f"{info.get('name') or '?'} / {info.get('firmware') or '?'} / "
                    f"SN {info.get('serial') or '?'} · "
                    f"{info.get('users_count') or 0} user(s), "
                    f"{info.get('fingerprints_count') or 0} empreinte(s)"
                )
                checks.append({
                    "name": "Dialogue ZKAccess SDK", "ok": True, "ms": ms,
                    "detail": detail,
                    "zk_info": info,
                })
                # Met à jour firmware si on l'a appris
                if info.get("firmware") and info["firmware"] != device.firmware_version:
                    device.firmware_version = info["firmware"][:40]
                    device.save(update_fields=["firmware_version"])
            except Exception as exc:
                ms = int((_time.monotonic() - t) * 1000)
                checks.append({
                    "name": "Dialogue ZKAccess SDK", "ok": False, "ms": ms,
                    "detail": str(exc)[:200],
                })

        # 4b) Handshake LLRP léger : ouvre TCP/5084, lit 10 bytes, parse l'header
        if try_llrp and any(p == 5084 for p, _ in open_ports):
            t = _time.monotonic()
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.settimeout(3.0)
                    s.connect((ip, 5084))
                    # Le lecteur envoie spontanément un READER_EVENT_NOTIFICATION
                    # à la connexion. On lit l'entête : version + msg_type + length
                    raw = s.recv(10)
                if len(raw) >= 6:
                    # bits 0-2 version, 3-15 type, 16-47 length
                    b0, b1 = raw[0], raw[1]
                    msg_type = ((b0 & 0x03) << 8) | b1
                    msg_types = {
                        63: "READER_EVENT_NOTIFICATION",
                         1: "GET_READER_CAPABILITIES",
                        11: "GET_READER_CONFIG_RESPONSE",
                    }
                    name = msg_types.get(msg_type, f"msg_type={msg_type}")
                    ms = int((_time.monotonic() - t) * 1000)
                    checks.append({
                        "name": "Handshake LLRP", "ok": True, "ms": ms,
                        "detail": name, "bytes_read": len(raw),
                    })
                else:
                    ms = int((_time.monotonic() - t) * 1000)
                    checks.append({
                        "name": "Handshake LLRP", "ok": False, "ms": ms,
                        "detail": f"Réponse incomplète ({len(raw)} octets)",
                    })
            except Exception as exc:
                ms = int((_time.monotonic() - t) * 1000)
                checks.append({
                    "name": "Handshake LLRP", "ok": False, "ms": ms,
                    "detail": str(exc)[:200],
                })

        # Synthèse : reachable si au moins 1 port s'ouvre OU si HTTP a répondu
        reachable = bool(open_ports) or any(
            c.get("ok") and c["name"].startswith("HTTP GET") for c in checks
        )

        # ── Message contextuel pour les terminaux push-mode ──
        # Si le device est configuré en push (ADMS/ZKAccess), le fait qu'il soit
        # injoignable en SORTANT n'est pas grave — il PUSH vers Shield.
        # On regarde s'il a un heartbeat récent = preuve qu'il communique.
        recently_seen = False
        push_mode = False
        if device.last_heartbeat_at:
            from datetime import timedelta
            from django.utils import timezone as _tz
            recently_seen = (_tz.now() - device.last_heartbeat_at) < timedelta(minutes=10)
        device_type = device_type or ""
        push_mode = device_type == "face_terminal" or (
            device.model
            and isinstance(device.model.spec, dict)
            and "push" in str(device.model.spec.get("protocol", "")).lower()
        )

        if not reachable and push_mode and recently_seen:
            # Faux négatif attendu — le terminal push, on ne peut pas le pinger.
            checks.append({
                "name": "Mode PUSH détecté", "ok": True,
                "detail": (
                    f"Ce terminal est configuré en mode PUSH (envoie ses events "
                    f"vers Shield). Le test ping/TCP échoue parce que Shield ne "
                    f"peut pas atteindre son LAN local — c'est NORMAL. "
                    f"Dernier heartbeat reçu il y a "
                    f"{int((_tz.now() - device.last_heartbeat_at).total_seconds())}s : "
                    f"le terminal communique correctement."
                ),
            })
            reachable = True   # on considère qu'il est actif

        # Met à jour last_heartbeat_at si reachable
        if reachable:
            from django.utils import timezone
            device.last_heartbeat_at = timezone.now()
            device.save(update_fields=["last_heartbeat_at"])

        duration_ms = int((_time.monotonic() - start) * 1000)
        return Response({
            "device": {
                "id": device.pk,
                "serial_number": device.serial_number,
                "ip": device.ip_address,
                "type": device_type,
            },
            "reachable": reachable,
            "duration_ms": duration_ms,
            "checks": checks,
            "summary": (
                f"{len(open_ports)} port(s) ouvert(s) : "
                + ", ".join(f"{p}" for p, _ in open_ports)
                if open_ports else
                "Aucun port ne répond — vérifier IP, alimentation, firewall."
            ),
        })


class ScanInboxView(APIView):
    """Inbox éphémère de scans bruts pour l'enrôlement live.

    Les scans sont stockés dans le cache Django (TTL 10 min) — pas de table SQL.
    Permet à un lecteur RFID/NFC IP de pousser ses lectures, et à l'UI admin de
    les afficher en temps réel.

    GET  /api/v1/devices/scan/inbox/?reader_id=<id>&since=<iso8601>
        → {"scans": [{"uid": "AABBCC01", "timestamp": "…"}, ...], "now": "…"}

    POST /api/v1/devices/scan/inbox/   (utilisé par les lecteurs IP en webhook)
        Body : {"reader_id": <id_ou_serial>, "uid": "AABBCC01", "rssi": -45}
        → {"ok": true}

    DELETE /api/v1/devices/scan/inbox/?reader_id=<id>
        → vide la file (bouton "Vider" UI)
    """
    permission_classes = [HasKshieldPermission]
    kshield_perms = {"read": "badges.manage", "write": "badges.manage"}

    CACHE_KEY = "scan_inbox:reader:{}"      # liste de dicts {uid, timestamp, rssi}
    CACHE_TTL = 600                          # 10 minutes
    MAX_ITEMS = 500

    def _cache_key(self, reader_id) -> str:
        return self.CACHE_KEY.format(reader_id)

    def get(self, request):
        from datetime import datetime, timezone
        from django.core.cache import cache

        from .models import Device
        from .zk_client import is_zkteco_device, safe_zk_session

        reader_id = request.query_params.get("reader_id")
        if not reader_id:
            return Response({"error": "reader_id requis"},
                              status=status.HTTP_400_BAD_REQUEST)
        since = request.query_params.get("since") or ""

        # ── Si le lecteur est un terminal ZKTeco, on PULL en live ──
        # Cap à 1 pull toutes les 3s par device pour ne pas saturer le terminal.
        device = None
        try:
            device = Device.objects.select_related("model").get(pk=reader_id)
        except (Device.DoesNotExist, ValueError):
            pass

        if device and is_zkteco_device(device) and device.ip_address:
            throttle_key = f"zk_pull_lock:{device.pk}"
            if not cache.get(throttle_key):
                cache.set(throttle_key, 1, 3)   # lock 3s
                self._pull_zk_into_inbox(device)

        # Lecture des items dans l'inbox
        items = cache.get(self._cache_key(reader_id)) or []

        # Filtre par `since` si fourni
        if since:
            try:
                cutoff = datetime.fromisoformat(since.replace("Z", "+00:00"))
                items = [
                    it for it in items
                    if datetime.fromisoformat(it["timestamp"]) > cutoff
                ]
            except Exception:
                pass

        now_iso = datetime.now(timezone.utc).isoformat()
        return Response({"scans": items, "now": now_iso, "count": len(items)})

    def _pull_zk_into_inbox(self, device):
        """Pull les nouveaux pointages d'un terminal ZKTeco et les met dans l'inbox.

        Pour chaque pointage, on remplace ``user_id`` (interne au terminal, ex. "1")
        par le ``card`` correspondant (numéro de carte RFID, ex. "6238480") qui
        est ce que l'enrôlement attend comme UID de badge. Le mapping user_id →
        card est cache 60s pour éviter de re-fetcher get_users à chaque pull.

        Watermark stocké en cache pour ne pas retourner deux fois le même UID.
        """
        from datetime import datetime, timezone
        from django.core.cache import cache

        from .zk_client import safe_zk_session

        watermark_key = f"zk_inbox_watermark:{device.pk}"
        mapping_key = f"zk_user_to_card:{device.pk}"
        last_seen_iso = cache.get(watermark_key)
        last_seen = None
        if last_seen_iso:
            try:
                last_seen = datetime.fromisoformat(last_seen_iso)
            except Exception:
                last_seen = None

        pwd = 0
        if device.model and isinstance(device.model.spec, dict):
            pwd = int(device.model.spec.get("sdk_password", 0) or 0)

        with safe_zk_session(
            ip=device.ip_address, port=4370, password=pwd, timeout=3,
        ) as zk:
            if zk is None:
                return

            # Mapping user_id → card (cache 60s)
            user_to_card = cache.get(mapping_key)
            if user_to_card is None:
                user_to_card = {}
                try:
                    for u in zk.list_users():
                        card = int(getattr(u, "card", 0) or 0)
                        if card:
                            user_to_card[str(u.user_id)] = card
                except Exception:
                    pass
                cache.set(mapping_key, user_to_card, 60)

            try:
                atts = zk.pull_attendances(since=last_seen)
            except Exception:
                return
            if not atts:
                return

            inbox_key = self._cache_key(device.pk)
            items = cache.get(inbox_key) or []
            existing_uids = {it.get("uid") for it in items}
            max_ts = last_seen
            from django.utils import timezone as djtz
            for a in atts:
                ts = a.timestamp
                if ts.tzinfo is None:
                    ts_aware = djtz.make_aware(ts, djtz.get_current_timezone())
                else:
                    ts_aware = ts
                # Remplace user_id par le numéro de carte si dispo
                user_id_str = str(a.user_id)
                card = user_to_card.get(user_id_str)
                uid_to_push = str(card) if card else user_id_str
                # Dedup soft : ne pas re-pousser un uid déjà présent
                if uid_to_push in existing_uids:
                    if max_ts is None or ts > max_ts:
                        max_ts = ts
                    continue
                items.append({
                    "uid": uid_to_push,
                    "timestamp": ts_aware.isoformat(),
                    "source": "zkteco",
                    "device_id": device.pk,
                    "raw": {
                        "user_id": user_id_str,
                        "card": card,
                        "status": getattr(a, "status", None),
                        "punch":  getattr(a, "punch", None),
                    },
                })
                existing_uids.add(uid_to_push)
                if max_ts is None or ts > max_ts:
                    max_ts = ts

            # Cap à 500 items dans l'inbox
            if len(items) > self.MAX_ITEMS:
                items = items[-self.MAX_ITEMS:]
            cache.set(inbox_key, items, self.CACHE_TTL)
            if max_ts is not None:
                cache.set(watermark_key, max_ts.isoformat(), 7 * 86400)

    def post(self, request):
        from datetime import datetime, timezone
        from django.core.cache import cache

        from .models import Device
        reader_ref = request.data.get("reader_id") or request.data.get("reader")
        uid = (request.data.get("uid") or "").strip().upper()
        rssi = request.data.get("rssi")
        if not (reader_ref and uid):
            return Response({"error": "reader_id et uid requis"},
                              status=status.HTTP_400_BAD_REQUEST)

        # reader_ref peut être un PK ou un serial_number → on tente les deux
        device = None
        try:
            device = Device.objects.filter(pk=reader_ref).first()
        except Exception:
            device = None
        if not device:
            device = Device.objects.filter(serial_number=reader_ref).first()
        if not device:
            return Response({"error": f"lecteur introuvable : {reader_ref}"},
                              status=status.HTTP_404_NOT_FOUND)

        key = self._cache_key(device.pk)
        items = cache.get(key) or []
        items.append({
            "uid": uid,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "rssi": rssi,
        })
        # Cap mémoire
        if len(items) > self.MAX_ITEMS:
            items = items[-self.MAX_ITEMS:]
        cache.set(key, items, self.CACHE_TTL)
        return Response({"ok": True, "queued": len(items)})

    def delete(self, request):
        from django.core.cache import cache
        reader_id = request.query_params.get("reader_id")
        if not reader_id:
            return Response({"error": "reader_id requis"},
                              status=status.HTTP_400_BAD_REQUEST)
        cache.delete(self._cache_key(reader_id))
        return Response({"ok": True})


class BadgeBulkEnrollView(APIView):
    """POST /api/v1/devices/badges/bulk-enroll/ — enrôle plusieurs badges en pool.

    Body :
        {
          "type":       "nfc" | "uhf" | "uhf_xerafy" | "qr",
          "category":   "employee_rfid" | "worker_rfid" | "visitor_qr",
          "valid_from": "2026-06-01" (optionnel),
          "valid_until":"2027-06-01" (optionnel),
          "uids":       ["AABBCC01", "AABBCC02", ...]
        }

    Comportement :
      - Status forcé à "available" → en pool, pas encore attribué
      - Doublons silencieusement ignorés (uid unique en base)
      - holder_kind/holder_object_id laissés vides
      - Réponse : {"created": N, "skipped": M, "errors": [...]}
    """
    permission_classes = [HasKshieldPermission]
    kshield_perms = {"read": "badges.manage", "write": "badges.manage"}

    def post(self, request):
        from .models import Badge

        btype     = (request.data.get("type") or "nfc").lower()
        category  = (request.data.get("category") or "employee_rfid").lower()
        uids_raw  = request.data.get("uids") or []
        valid_from  = request.data.get("valid_from") or None
        valid_until = request.data.get("valid_until") or None

        if btype not in dict(Badge.TYPE_CHOICES):
            return Response({"error": f"type invalide : {btype}"},
                              status=status.HTTP_400_BAD_REQUEST)
        if category not in dict(Badge.CATEGORY_CHOICES):
            return Response({"error": f"category invalide : {category}"},
                              status=status.HTTP_400_BAD_REQUEST)
        if not isinstance(uids_raw, list) or not uids_raw:
            return Response({"error": "uids : liste non vide attendue"},
                              status=status.HTTP_400_BAD_REQUEST)

        # Normalise : uppercase, trim, retire les doublons en gardant l'ordre
        seen = set(); uids = []
        for u in uids_raw:
            s = str(u or "").strip().upper()
            if not s or s in seen:
                continue
            if len(s) > 64:
                continue
            seen.add(s); uids.append(s)
        if not uids:
            return Response({"error": "aucun UID valide après normalisation"},
                              status=status.HTTP_400_BAD_REQUEST)

        # Détecte les déjà-existants en une seule requête
        from core.services import get_kaydan_tenant
        tenant = get_kaydan_tenant()
        existing = set(
            Badge.objects.filter(tenant=tenant, uid__in=uids)
            .values_list("uid", flat=True)
        )

        to_create = []
        for uid in uids:
            if uid in existing:
                continue
            to_create.append(Badge(
                tenant=tenant,
                uid=uid,
                type=btype,
                category=category,
                status="available",
                valid_from=valid_from or None,
                valid_until=valid_until or None,
            ))

        created_count = 0
        if to_create:
            Badge.objects.bulk_create(to_create, batch_size=200, ignore_conflicts=True)
            created_count = len(to_create)

        return Response({
            "created": created_count,
            "skipped": len(existing) + (len(uids_raw) - len(uids)),
            "skipped_existing": sorted(existing),
            "total_input": len(uids_raw),
            "total_unique": len(uids),
            "type": btype,
            "category": category,
        })


class HelmetBulkEnrollView(APIView):
    """POST /api/v1/devices/helmets/bulk-enroll/ — enrôle des casques (UHF+BLE).

    Body :
        {
          "rows": [
            {"serial": "HLM-001", "uhf": "AABBCC01", "ble": "DEADBEEF01"},
            {"serial": "HLM-002", "uhf": "AABBCC02", "ble": "DEADBEEF02"},
            ...
          ],
          "size": "M" (optionnel, taille par défaut pour tous les casques)
        }

    Réponse : {"created": N, "skipped": M, "errors": [...]}
    """
    permission_classes = [HasKshieldPermission]
    kshield_perms = {"read": "badges.manage", "write": "badges.manage"}

    def post(self, request):
        from .models import Helmet

        rows = request.data.get("rows") or []
        size = request.data.get("size") or ""
        if not isinstance(rows, list) or not rows:
            return Response({"error": "rows : liste non vide attendue"},
                              status=status.HTTP_400_BAD_REQUEST)

        from core.services import get_kaydan_tenant
        tenant = get_kaydan_tenant()

        # Validation + normalisation
        clean_rows = []
        errors = []
        seen_serials = set(); seen_uhf = set(); seen_ble = set()
        for i, row in enumerate(rows, 1):
            serial = str(row.get("serial") or "").strip()
            uhf    = str(row.get("uhf") or "").strip().upper()
            ble    = str(row.get("ble") or "").strip().upper()
            if not (serial and uhf and ble):
                errors.append({"row": i, "error": "serial / uhf / ble requis"})
                continue
            if serial in seen_serials or uhf in seen_uhf or ble in seen_ble:
                errors.append({"row": i, "error": "doublon dans la requête"})
                continue
            seen_serials.add(serial); seen_uhf.add(uhf); seen_ble.add(ble)
            clean_rows.append({"serial": serial, "uhf": uhf, "ble": ble})

        if not clean_rows:
            return Response({
                "created": 0, "skipped": 0,
                "errors": errors or [{"error": "aucune ligne valide"}],
            }, status=status.HTTP_400_BAD_REQUEST)

        # Détecte les conflits existants en base (en une seule requête)
        from django.db.models import Q
        existing_qs = Helmet.objects.filter(
            Q(serial_number__in=[r["serial"] for r in clean_rows])
            | Q(uhf_tag_uid__in=[r["uhf"] for r in clean_rows])
            | Q(ble_beacon_uid__in=[r["ble"] for r in clean_rows])
        ).values("serial_number", "uhf_tag_uid", "ble_beacon_uid")
        ex_serials = {e["serial_number"] for e in existing_qs}
        ex_uhf     = {e["uhf_tag_uid"]   for e in existing_qs}
        ex_ble     = {e["ble_beacon_uid"]for e in existing_qs}

        to_create = []
        skipped = 0
        for r in clean_rows:
            if (r["serial"] in ex_serials or r["uhf"] in ex_uhf
                    or r["ble"] in ex_ble):
                skipped += 1
                errors.append({
                    "serial": r["serial"],
                    "error": "déjà enrôlé (serial / uhf / ble existant)",
                })
                continue
            to_create.append(Helmet(
                tenant=tenant,
                serial_number=r["serial"],
                uhf_tag_uid=r["uhf"],
                ble_beacon_uid=r["ble"],
                status="active",
                size=size,
            ))

        created_count = 0
        if to_create:
            # ignore_conflicts au cas où un autre process insère en parallèle
            Helmet.objects.bulk_create(to_create, batch_size=200, ignore_conflicts=True)
            created_count = len(to_create)

        return Response({
            "created": created_count,
            "skipped": skipped,
            "errors": errors,
            "total_input": len(rows),
        })


class ReaderDiscoverView(APIView):
    """POST /api/v1/devices/readers/discover/ — auto-discovery de lecteurs RFID/NFC/BLE.

    Body : ``{"kind": "uhf|nfc|ble", "cidr": "192.168.1.0/24", "timeout": 5, "mdns": true}``

    - ``kind`` requis : technologie ciblée.
    - ``cidr`` optionnel : plage à scanner en TCP (≤ /20). Sans CIDR, seul mDNS.
    - ``timeout`` : durée totale, 3-15s (default 5).
    - ``mdns`` : active / désactive la découverte mDNS (default True).

    Réponses :
      200 : ``{"readers": [...], "count": N, "kind": "uhf"}``
      400 : CIDR invalide ou kind invalide.
      503 : zeroconf non installé ET pas de CIDR fourni.
    """
    permission_classes = [HasKshieldPermission]
    kshield_perms = {"read": "devices.manage", "write": "devices.manage"}

    def post(self, request):
        kind = (request.data.get("kind") or "").lower()
        if kind not in ("uhf", "nfc", "ble", "zk", "face"):
            return Response(
                {"error": "kind invalide",
                 "detail": "Attendu : uhf, nfc, ble, zk ou face"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        cidr = request.data.get("cidr") or None
        timeout = int(request.data.get("timeout") or 5)
        timeout = max(3, min(timeout, 15))
        mdns = bool(request.data.get("mdns", True))

        try:
            from .reader_discovery import (
                ReaderDiscoveryError, ReaderDiscoveryUnavailable,
                discover_readers,
            )
            results = discover_readers(
                kind=kind, cidr=cidr, timeout=timeout, mdns=mdns,
            )
        except ReaderDiscoveryUnavailable as exc:
            return Response(
                {"error": "mDNS library missing", "detail": str(exc)},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except ReaderDiscoveryError as exc:
            return Response(
                {"error": "discovery error", "detail": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as exc:
            return Response(
                {"error": "discovery failed", "detail": str(exc)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response({
            "readers": results,
            "count": len(results),
            "kind": kind,
        })


class CameraOnvifDiscoverView(APIView):
    """POST /api/v1/devices/cameras/discover/ — scan ONVIF du LAN.

    Body optionnel : {"timeout": 5, "user": "admin", "pass": "..."}
    Réponse : liste de caméras trouvées avec leur RTSP URL si crédentiels OK.
    """
    permission_classes = [HasKshieldPermission]
    kshield_perms = {"read": "devices.manage", "write": "devices.manage"}

    def post(self, request):
        timeout = int(request.data.get("timeout") or 5)
        user = request.data.get("user") or ""
        passwd = request.data.get("pass") or ""
        creds = {"user": user, "pass": passwd} if user and passwd else None
        try:
            from .onvif_discovery import discover_cameras, OnvifUnavailable
            results = discover_cameras(
                timeout=min(timeout, 15),
                fetch_streams=creds is not None,
                credentials=creds,
            )
        except OnvifUnavailable as exc:
            return Response({
                "error": "ONVIF discovery library missing",
                "detail": str(exc),
            }, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        except Exception as exc:
            return Response({"error": "discovery failed", "detail": str(exc)},
                              status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        return Response({"cameras": results, "count": len(results)})


class CameraStreamView(View):
    """GET /api/v1/devices/cameras/<pk>/stream.mjpg — flux MJPEG temps réel.

    Auth : session admin OU JWT (vérifié manuellement, on est en dehors de DRF
    car le ResponseRenderer DRF ne sait pas streamer du multipart).
    """

    def get(self, request, pk):
        import logging
        log = logging.getLogger(__name__)
        try:
            # ── Auth : session OU JWT ───────────────────────────────
            if not (request.user and request.user.is_authenticated):
                try:
                    jwt_auth = JWTAuthentication()
                    auth = jwt_auth.authenticate(request)
                    if not auth:
                        return HttpResponse("unauth", status=401, content_type="text/plain")
                    request.user = auth[0]
                except Exception as exc:
                    log.warning("CameraStreamView JWT auth fail: %s", exc)
                    return HttpResponse("unauth", status=401, content_type="text/plain")

            # ── RBAC : devices.view (toléré si pas de perms du tout) ─
            try:
                from accounts.rbac import user_has_permission
                if not (request.user.is_superuser
                        or user_has_permission(request.user, "devices.view")):
                    return HttpResponse("forbidden", status=403, content_type="text/plain")
            except Exception as exc:
                log.warning("CameraStreamView RBAC check fail: %s", exc, exc_info=True)
                # On laisse passer si RBAC casse — l'auth a déjà été validée

            # ── Camera existe ? ────────────────────────────────────
            try:
                cam = Camera.objects.filter(pk=pk, is_active=True).first()
            except Exception as exc:
                log.exception("CameraStreamView DB error pk=%s: %s", pk, exc)
                return HttpResponse(f"db error: {exc}", status=500, content_type="text/plain")
            if not cam:
                return HttpResponse("camera not found or disabled",
                                     status=404, content_type="text/plain")

            # ── Wrap le générateur pour catcher toute erreur en amont ─
            from .streaming import stream_camera

            def _safe_generator():
                try:
                    yield from stream_camera(cam)
                except Exception as exc:
                    log.exception("CameraStreamView generator crash pk=%s: %s", pk, exc)
                    # Le client recevra la fin de stream — pas de 500 mid-stream

            resp = StreamingHttpResponse(
                _safe_generator(),
                content_type="multipart/x-mixed-replace; boundary=frame",
            )
            resp["Cache-Control"] = "no-cache, no-store, must-revalidate, private"
            resp["X-Accel-Buffering"] = "no"
            return resp

        except Exception as exc:
            # Filet de sécurité ultime — log + 500 explicite
            log.exception("CameraStreamView top-level crash pk=%s: %s", pk, exc)
            return HttpResponse(f"stream error: {exc}", status=500,
                                  content_type="text/plain")


# ===========================================================================
# Badge endpoints — PDF / Thumbnail / Workflow / Lifecycle / Lookup
# ===========================================================================
class BadgePDFDownloadView(View):
    """GET /badges/<pk>/pdf/ — sert le PDF du badge (régénère si absent)."""

    def get(self, request, pk):
        try:
            badge = Badge.objects.get(pk=pk)
        except Badge.DoesNotExist:
            raise Http404("Badge introuvable")

        from .services import BadgePDFService
        pdf_bytes = BadgePDFService.generate(badge)
        BadgePDFService.generate_and_save(badge)

        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        filename = f"badge_{badge.category}_{badge.uid}.pdf"
        response["Content-Disposition"] = f'inline; filename="{filename}"'
        return response


class BadgeThumbnailView(View):
    """GET /badges/<pk>/thumbnail/ — sert l'image PNG du badge."""

    def get(self, request, pk):
        try:
            badge = Badge.objects.get(pk=pk)
        except Badge.DoesNotExist:
            raise Http404("Badge introuvable")

        from django.core.files.base import ContentFile
        from .services import BadgeThumbnailService

        if not badge.thumbnail or not badge.thumbnail.name:
            try:
                png_bytes = BadgeThumbnailService.generate(badge)
                badge.thumbnail.save(
                    f"badge_{badge.category}_{badge.uid}.png",
                    ContentFile(png_bytes), save=True,
                )
            except Exception as e:
                import logging
                logging.getLogger(__name__).exception("thumbnail failed")
                return HttpResponse(f"Erreur: {e}", status=500)

        with badge.thumbnail.open("rb") as f:
            data = f.read()
        response = HttpResponse(data, content_type="image/png")
        response["Cache-Control"] = "private, max-age=3600"
        return response


class BadgeIssueWorkflowAPIView(APIView):
    """POST /api/v1/devices/badges/issue/ — Body: {workflow, ...}"""
    permission_classes = [AllowAny]

    def post(self, request):
        from .services import BadgeWorkflowService
        wf = (request.data or {}).get("workflow")

        try:
            if wf == "visitor_qr_pool":
                count = int(request.data.get("count", 10))
                badges = BadgeWorkflowService.create_visitor_qr_pool(count=count)
                return Response({
                    "created": [{"id": b.id, "uid": b.uid} for b in badges],
                    "total": len(badges),
                }, status=status.HTTP_201_CREATED)

            if wf == "employee":
                from employees.models import Employee
                emp = Employee.objects.get(pk=request.data["employee_id"])
                helmet = None
                if request.data.get("helmet_id"):
                    helmet = Helmet.objects.get(pk=request.data["helmet_id"])
                badge = BadgeWorkflowService.issue_employee_badge(emp, helmet=helmet)
                return Response({"id": badge.id, "uid": badge.uid,
                                 "category": badge.category}, status=201)

            if wf == "assign_pool":
                # Attribue un badge existant du pool à un employé ou ouvrier
                from employees.models import Employee
                from ouvriers.models import Worker
                badge_id = request.data.get("badge_id")
                if not badge_id:
                    return Response({"error": "badge_id requis"}, status=400)
                badge = Badge.objects.get(pk=badge_id)

                emp_id = request.data.get("employee_id")
                worker_id = request.data.get("worker_id")
                if emp_id:
                    holder = Employee.objects.get(pk=emp_id)
                elif worker_id:
                    holder = Worker.objects.get(pk=worker_id)
                else:
                    return Response({"error": "employee_id OU worker_id requis"}, status=400)

                helmet = None
                if request.data.get("helmet_id"):
                    helmet = Helmet.objects.get(pk=request.data["helmet_id"])

                badge = BadgeWorkflowService.assign_pool_badge(
                    badge, holder, helmet=helmet,
                )
                return Response({
                    "id": badge.id, "uid": badge.uid,
                    "category": badge.category, "status": badge.status,
                    "holder": str(holder),
                }, status=200)

            if wf == "worker":
                from ouvriers.models import Worker
                w = Worker.objects.get(pk=request.data["worker_id"])
                helmet = Helmet.objects.get(pk=request.data["helmet_id"])
                badge = BadgeWorkflowService.issue_worker_badge(w, helmet=helmet)
                return Response({"id": badge.id, "uid": badge.uid,
                                 "category": badge.category}, status=201)

            return Response({"error": "workflow inconnu"}, status=400)
        except (ValueError, Helmet.DoesNotExist) as e:
            return Response({"error": str(e)}, status=400)
        except Exception as e:
            import logging
            logging.getLogger(__name__).exception("badge workflow failed")
            return Response({"error": str(e)}, status=500)


class _BadgeLifecycleMixin:
    """Mixin qui charge le badge et invoque la méthode `service_method` du service."""
    permission_classes = [AllowAny]
    service_method: str = ""

    def post(self, request, pk):
        from .services import BadgeWorkflowService
        try:
            badge = Badge.objects.get(pk=pk)
        except Badge.DoesNotExist:
            return Response({"error": "badge introuvable"}, status=404)

        reason = (request.data or {}).get("reason", "")
        user = request.user if request.user.is_authenticated else None
        try:
            method = getattr(BadgeWorkflowService, self.service_method)
            if self.service_method == "reactivate":
                method(badge, by_user=user)
            else:
                method(badge, reason=reason, by_user=user)
        except ValueError as e:
            return Response({"error": str(e)}, status=400)
        return Response({
            "ok": True, "id": badge.id, "uid": badge.uid,
            "status": badge.status, "status_label": badge.get_status_display(),
        })


class BadgeSuspendAPIView(_BadgeLifecycleMixin, APIView):
    service_method = "suspend"


class BadgeReactivateAPIView(_BadgeLifecycleMixin, APIView):
    service_method = "reactivate"


class BadgeRevokeAPIView(_BadgeLifecycleMixin, APIView):
    service_method = "revoke"


class BadgeLostAPIView(_BadgeLifecycleMixin, APIView):
    service_method = "mark_lost"


class BadgeReleaseAPIView(APIView):
    """POST /api/v1/devices/badges/<pk>/release/ — restitue / libère."""
    permission_classes = [AllowAny]

    def post(self, request, pk):
        from .services import BadgeWorkflowService
        try:
            badge = Badge.objects.get(pk=pk)
        except Badge.DoesNotExist:
            return Response({"error": "badge introuvable"}, status=404)
        user = request.user if request.user.is_authenticated else None
        BadgeWorkflowService.release(badge, by_user=user)
        return Response({"ok": True, "status": badge.status,
                         "status_label": badge.get_status_display()})


class BadgeLookupAPIView(APIView):
    """GET /api/v1/devices/badges/lookup/?q=<uid_ou_qr>"""
    permission_classes = [AllowAny]

    def get(self, request):
        q = (request.query_params.get("q") or "").strip()
        if not q:
            return Response({"error": "paramètre 'q' requis"}, status=400)

        badge = (Badge.objects.filter(uid=q).select_related("paired_helmet").first()
                 or Badge.objects.filter(qr_payload=q).select_related("paired_helmet").first())

        if not badge and "BADGE:" in q:
            try:
                badge_uid = q.split("BADGE:", 1)[1].split("|", 1)[0]
                badge = Badge.objects.filter(uid=badge_uid).select_related("paired_helmet").first()
            except (IndexError, ValueError):
                # Format de QR badge invalide — fall through au not found 404 ci-dessous
                pass

        if not badge:
            return Response({"found": False, "query": q}, status=404)

        holder_label = ""
        if badge.holder:
            holder_label = str(badge.holder)
        elif badge.qr_payload and badge.qr_payload.startswith("VISIT-"):
            holder_label = f"Visite {badge.qr_payload[6:]}"

        return Response({
            "found": True, "id": badge.id, "uid": badge.uid,
            "category": badge.category,
            "category_label": badge.get_category_display(),
            "type": badge.type, "status": badge.status,
            "status_label": badge.get_status_display(),
            "holder_label": holder_label,
            "holder_kind": badge.holder_kind,
            "valid_from": badge.valid_from.isoformat() if badge.valid_from else None,
            "valid_until": badge.valid_until.isoformat() if badge.valid_until else None,
            "is_currently_valid": badge.is_currently_valid,
            "can_be_used": badge.can_be_used,
            "paired_helmet": (badge.paired_helmet.serial_number
                              if badge.paired_helmet else None),
            "last_scan_at": (badge.last_scan_at.isoformat()
                             if badge.last_scan_at else None),
            "scan_count": badge.scan_count,
            "pdf_url": f"/badges/{badge.id}/pdf/",
            "detail_url": f"/badges/{badge.id}/",
        })
