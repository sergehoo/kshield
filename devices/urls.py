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
    ReaderDiscoverView,
    BadgeBulkEnrollView, HelmetBulkEnrollView, ScanInboxView,
    BleGatewayIngestView,
    FaceTerminalEventView, FacePushEmployeeView,
    DeviceConnectivityTestView,
    ZkSyncNowView, ZkSyncAllView, ZkPushUsersNowView,
    ZkEnrollSessionView, ZkImportUsersView, ZkPushEmployeeView,
    ZkAdmsWebhookView,
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
    # Auto-discovery lecteurs RFID UHF / NFC / BLE
    path("readers/discover/",                        ReaderDiscoverView.as_view(),      name="reader-discover"),
    # Enrôlement en masse — badges (NFC/UHF/QR) et casques (UHF+BLE)
    path("badges/bulk-enroll/",                      BadgeBulkEnrollView.as_view(),     name="badge-bulk-enroll"),
    path("helmets/bulk-enroll/",                     HelmetBulkEnrollView.as_view(),    name="helmet-bulk-enroll"),
    # Inbox éphémère pour scans live (cache Redis, TTL 10 min)
    path("scan/inbox/",                              ScanInboxView.as_view(),           name="scan-inbox"),
    # Ingestion BLE depuis gateway site ou app mobile (MOKO H7 Lite & co)
    path("ble-gateway/<str:gateway_serial>/ingest/", BleGatewayIngestView.as_view(),    name="ble-gateway-ingest"),
    # Terminal reconnaissance faciale — webhook event + push face employé
    path("face-terminal/<str:sn>/event/",            FaceTerminalEventView.as_view(),   name="face-terminal-event"),
    path("employees/<int:pk>/push-face/",            FacePushEmployeeView.as_view(),    name="employee-face-push"),
    # Test de connectivité d'un équipement (TCP + HTTP + LLRP + ZK)
    # NB : inclus sous /api/v1/devices/ — pas de double prefix.
    path("<int:pk>/test-connection/",                DeviceConnectivityTestView.as_view(), name="device-test-connection"),
    # ZKTeco — sync à la demande + push users + session d'enrôlement live
    path("zk-sync-all/",                             ZkSyncAllView.as_view(),            name="device-zk-sync-all"),
    path("employees/<int:pk>/push-to-zk/",           ZkPushEmployeeView.as_view(),       name="employee-zk-push"),
    # Webhook ADMS — le terminal POST ses events ici (mode push, alternative au pull)
    path("zk-adms/<str:sn>/cdata",                   ZkAdmsWebhookView.as_view(),        name="zk-adms-cdata"),
    path("zk-adms/cdata",                            ZkAdmsWebhookView.as_view(),        name="zk-adms-cdata-no-sn"),
    path("<int:pk>/zk-sync/",                        ZkSyncNowView.as_view(),            name="device-zk-sync"),
    path("<int:pk>/zk-push-users/",                  ZkPushUsersNowView.as_view(),       name="device-zk-push-users"),
    path("<int:pk>/enroll-session/",                 ZkEnrollSessionView.as_view(),      name="device-zk-enroll-session"),
    path("<int:pk>/zk-import-users/",                ZkImportUsersView.as_view(),        name="device-zk-import-users"),
] + router.urls
