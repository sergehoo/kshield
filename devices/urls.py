from django.urls import path
from rest_framework.routers import DefaultRouter

from .views_edge_gateway import (
    PackageListView, PackageInstallCommandView, PackageDownloadView,
    GatewayListCreateView, GatewayDetailView,
    GatewayRotateActivationView, GatewayRevokeView, GatewayReactivateView,
    GatewayRestartView, GatewayForceSyncView, GatewayScanNetworkView,
    GatewayUpdateView, GatewayLogsView, GatewayDevicesView,
    GatewayActivateView, GatewayHeartbeatView, GatewayPairingQrView,
)
from .views_enrollment import (
    EnrollmentStartView, EnrollmentStopView, EnrollmentConfirmView,
    EnrollmentSessionDetailView, EnrollmentIngestScanView,
    DeviceCommandCreateView, DeviceCommandDetailView, DeviceStatusView,
    AgentPullCommandsView, AgentEventView,
    LocalAgentListView, LocalAgentDetailView, LocalAgentRotateTokenView,
    SystemAlertsView, SystemAlertAcknowledgeView, RealtimeStatsView,
    DriversListView, DriverTestView,
    DeviceTwinView, DeviceTwinRefreshView,
    MultiProtocolDiscoveryView,
    MaintenanceTicketListView, MaintenanceTicketDetailView,
    NetworkTopologyView,
    PluginCatalogView, PluginUploadView,
)
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
    FaceTerminalEventView, FacePushEmployeeView, DeviceIdentifyByIpView,
    DeviceConnectivityTestView,
    ZkSyncNowView, ZkSyncAllView, ZkPushUsersNowView,
    ZkEnrollSessionView, ZkImportUsersView, ZkPushEmployeeView,
    ZkAdmsWebhookView, DeviceIclockDebugView, PubApiDebugView,
    NetworkScanStartView, NetworkScanStatusView,
    NetworkScanCancelView, NetworkScanAdoptView,
    DevicePingView, DeviceSyncView, DeviceRestartView,
    DeviceResetConfigView, DeviceUpdateFirmwareView,
    DeviceLogsView, DeviceExportView,
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
    # Identifier un équipement par son IP (test tous protocoles)
    path("identify-by-ip/",                          DeviceIdentifyByIpView.as_view(),  name="device-identify-by-ip"),
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

    # ═══ Actions techniques par équipement ═══
    path("<int:pk>/ping/",             DevicePingView.as_view(),          name="device-ping"),
    path("<int:pk>/sync/",             DeviceSyncView.as_view(),          name="device-sync"),
    path("<int:pk>/restart/",          DeviceRestartView.as_view(),       name="device-restart"),
    path("<int:pk>/reset-config/",     DeviceResetConfigView.as_view(),   name="device-reset-config"),
    path("<int:pk>/update-firmware/",  DeviceUpdateFirmwareView.as_view(), name="device-update-firmware"),
    path("<int:pk>/logs/",             DeviceLogsView.as_view(),          name="device-logs"),
    path("<int:pk>/export/",           DeviceExportView.as_view(),        name="device-export"),
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
    # ═══ Scan réseau — découverte automatique d'équipements ═══
    path("scan/start/",           NetworkScanStartView.as_view(),  name="device-scan-start"),
    path("scan/<str:scan_id>/",   NetworkScanStatusView.as_view(), name="device-scan-status"),
    path("scan/<str:scan_id>/cancel/", NetworkScanCancelView.as_view(), name="device-scan-cancel"),
    path("scan/<str:scan_id>/adopt/",  NetworkScanAdoptView.as_view(),  name="device-scan-adopt"),

    # ═══ Commandes device (queue) ═══
    path("<int:pk>/commands/",                       DeviceCommandCreateView.as_view(),  name="device-command-create"),
    path("<int:pk>/status/",                         DeviceStatusView.as_view(),         name="device-status"),
    path("commands/<uuid:command_id>/",              DeviceCommandDetailView.as_view(),  name="device-command-detail"),

    # ═══ Alertes système agrégées + stats temps réel ═══
    path("alerts/system/",                           SystemAlertsView.as_view(),          name="system-alerts"),
    path("alerts/<uuid:alert_id>/acknowledge/",      SystemAlertAcknowledgeView.as_view(), name="system-alert-ack"),
    path("stats/realtime/",                          RealtimeStatsView.as_view(),         name="stats-realtime"),

    # ═══ Driver Framework ═══
    path("drivers/",                                 DriversListView.as_view(),           name="drivers-list"),
    path("<int:pk>/driver-test/",                    DriverTestView.as_view(),            name="driver-test"),

    # ═══ Digital Twin ═══
    path("<int:pk>/twin/",                           DeviceTwinView.as_view(),            name="device-twin"),
    path("<int:pk>/twin/refresh/",                   DeviceTwinRefreshView.as_view(),     name="device-twin-refresh"),

    # ═══ Auto Discovery multi-protocole ═══
    path("discovery/scan/",                          MultiProtocolDiscoveryView.as_view(), name="discovery-multi-scan"),

    # ═══ Maintenance prédictive ═══
    path("maintenance/tickets/",                     MaintenanceTicketListView.as_view(),   name="maintenance-tickets"),
    path("maintenance/tickets/<uuid:ticket_id>/",    MaintenanceTicketDetailView.as_view(), name="maintenance-ticket-detail"),

    # ═══ Topologie réseau ═══
    path("topology/",                                NetworkTopologyView.as_view(),         name="network-topology"),

    # ═══ Plugin Marketplace ═══
    path("marketplace/plugins/",                     PluginCatalogView.as_view(),           name="marketplace-plugins"),
    path("marketplace/plugins/upload/",              PluginUploadView.as_view(),            name="marketplace-plugin-upload"),

    # ═══ Edge Gateway — packages + gateways + registration ═══
    # Catalogue packages
    path("edge-gateway/packages/",                              PackageListView.as_view(),           name="edge-gateway-packages"),
    path("edge-gateway/packages/<int:pkg_id>/install-command/", PackageInstallCommandView.as_view(), name="edge-gateway-install-command"),
    path("edge-gateway/packages/<int:pkg_id>/download/",        PackageDownloadView.as_view(),       name="edge-gateway-download"),
    # Registration public
    path("edge-gateway/activate/",                              GatewayActivateView.as_view(),       name="edge-gateway-activate"),
    path("edge-gateway/heartbeat/",                             GatewayHeartbeatView.as_view(),      name="edge-gateway-heartbeat"),
    # Provisioning + supervision
    path("edge-gateway/",                                       GatewayListCreateView.as_view(),     name="edge-gateway-list"),
    path("edge-gateway/<uuid:gid>/",                            GatewayDetailView.as_view(),         name="edge-gateway-detail"),
    path("edge-gateway/<uuid:gid>/rotate-activation/",          GatewayRotateActivationView.as_view(), name="edge-gateway-rotate-activation"),
    path("edge-gateway/<uuid:gid>/pairing-qr.png",              GatewayPairingQrView.as_view(),      name="edge-gateway-qr"),
    path("edge-gateway/<uuid:gid>/revoke/",                     GatewayRevokeView.as_view(),         name="edge-gateway-revoke"),
    path("edge-gateway/<uuid:gid>/reactivate/",                 GatewayReactivateView.as_view(),     name="edge-gateway-reactivate"),
    # Actions
    path("edge-gateway/<uuid:gid>/restart/",                    GatewayRestartView.as_view(),        name="edge-gateway-restart"),
    path("edge-gateway/<uuid:gid>/force-sync/",                 GatewayForceSyncView.as_view(),      name="edge-gateway-force-sync"),
    path("edge-gateway/<uuid:gid>/scan-network/",               GatewayScanNetworkView.as_view(),    name="edge-gateway-scan"),
    path("edge-gateway/<uuid:gid>/update/",                     GatewayUpdateView.as_view(),         name="edge-gateway-update"),
    path("edge-gateway/<uuid:gid>/logs/",                       GatewayLogsView.as_view(),           name="edge-gateway-logs"),
    path("edge-gateway/<uuid:gid>/devices/",                    GatewayDevicesView.as_view(),        name="edge-gateway-devices"),

    # ═══ Agent local — Admin (provisioning + gestion) ═══
    path("local-agents/",                            LocalAgentListView.as_view(),        name="local-agent-list"),
    path("local-agents/<uuid:agent_id>/",            LocalAgentDetailView.as_view(),      name="local-agent-detail"),
    path("local-agents/<uuid:agent_id>/rotate-token/", LocalAgentRotateTokenView.as_view(), name="local-agent-rotate"),

    # ═══ Agent local (fallback HTTP polling) ═══
    path("agent/<uuid:agent_id>/commands/",          AgentPullCommandsView.as_view(),    name="agent-pull-commands"),
    path("agent/<uuid:agent_id>/events/",            AgentEventView.as_view(),           name="agent-events"),

    # Debug — dernières requêtes POST iclock/cdata (utile pour reverse-engineer un firmware inconnu)
    path("<int:pk>/iclock-debug/",                   DeviceIclockDebugView.as_view(),    name="device-iclock-debug"),
    # Debug global — dernières requêtes POST /pub/api (firmwares whitebox inconnus)
    path("pubapi-debug/",                            PubApiDebugView.as_view(),          name="pubapi-debug"),
] + router.urls
