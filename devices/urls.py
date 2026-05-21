from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    BadgeHelmetPairingViewSet, BadgeIssueWorkflowAPIView,
    BadgeLookupAPIView, BadgeLostAPIView,
    BadgeReactivateAPIView, BadgeReleaseAPIView, BadgeRevokeAPIView,
    BadgeSuspendAPIView, BadgeViewSet,
    CameraOnvifDiscoverView, CameraRtspProbeMultipleView, CameraRtspProbeView,
    CameraStreamView, CameraViewSet,
    DeviceHeartbeatViewSet, DeviceMaintenanceViewSet, DeviceModelViewSet,
    DeviceViewSet, FirmwareVersionViewSet, HelmetViewSet,
    HeartbeatIngestView, OTAFirmwareMetadataView, OTAUpdateViewSet,
)

router = DefaultRouter()
router.register("models", DeviceModelViewSet)
router.register("devices", DeviceViewSet)
router.register("badges", BadgeViewSet)
router.register("helmets", HelmetViewSet)
router.register("pairings", BadgeHelmetPairingViewSet)
router.register("heartbeats", DeviceHeartbeatViewSet)
router.register("maintenances", DeviceMaintenanceViewSet)
router.register("firmwares", FirmwareVersionViewSet)
router.register("ota", OTAUpdateViewSet)
router.register("cameras", CameraViewSet)

urlpatterns = [
    path("badges/issue/",                 BadgeIssueWorkflowAPIView.as_view(), name="badge-issue"),
    path("badges/lookup/",                BadgeLookupAPIView.as_view(),        name="badge-lookup"),
    path("badges/<int:pk>/release/",      BadgeReleaseAPIView.as_view(),       name="badge-release"),
    path("badges/<int:pk>/suspend/",      BadgeSuspendAPIView.as_view(),       name="badge-suspend"),
    path("badges/<int:pk>/reactivate/",   BadgeReactivateAPIView.as_view(),    name="badge-reactivate"),
    path("badges/<int:pk>/revoke/",       BadgeRevokeAPIView.as_view(),        name="badge-revoke"),
    path("badges/<int:pk>/mark-lost/",    BadgeLostAPIView.as_view(),          name="badge-lost"),
    # IoT endpoints (HMAC + JWT)
    path("heartbeat/",                              HeartbeatIngestView.as_view(),     name="heartbeat-ingest"),
    path("ota/<int:firmware_id>/metadata/",         OTAFirmwareMetadataView.as_view(), name="ota-metadata"),
    # Caméras : streaming MJPEG (hors router DRF — multipart/x-mixed-replace)
    path("cameras/<int:pk>/stream.mjpg",            CameraStreamView.as_view(),        name="camera-stream"),
    path("cameras/discover/",                        CameraOnvifDiscoverView.as_view(), name="camera-onvif-discover"),
    path("cameras/probe-rtsp/",                      CameraRtspProbeView.as_view(),     name="camera-rtsp-probe"),
    path("cameras/probe-rtsp-bulk/",                 CameraRtspProbeMultipleView.as_view(), name="camera-rtsp-probe-bulk"),
] + router.urls
