from django.http import Http404, HttpResponse, StreamingHttpResponse
from django.utils import timezone
from django.views import View
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication

from accounts.hmac_auth import HMACAPIKeyAuthentication
from accounts.permissions import IsAuthenticatedOrAPIKey
from accounts.rbac import HasKshieldPermission

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
