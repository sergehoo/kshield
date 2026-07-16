from django.urls import path
from rest_framework.routers import DefaultRouter

from .views_edge_gateway import (
    PackageListView, PackageInstallCommandView, PackageDownloadView,
    GatewayListCreateView, GatewayDetailView,
    GatewayRotateActivationView, GatewayRevokeView, GatewayReactivateView,
    GatewayRestartView, GatewayForceSyncView, GatewayScanNetworkView,
    GatewayUpdateView, GatewayLogsView, GatewayDevicesView,
    GatewayActivateView, GatewayHeartbeatView, GatewayPairingQrView,
    GatewayDownloadPackageView,
    UpdateCheckView, ActionResultView,
    GatewayTargetsView, GatewayTargetDetailView, GatewayTargetActionView,
    GatewayScanResultsView, FleetTargetsView,
)
from .views_events import (
    DeviceEventListView, DeviceEventLiveView, DeviceEventDetailView,
    DeviceEventActionView, EventTypeCatalogView, DeviceEventExportView,
)
from .views_badges import (
    BadgeAssignView, BadgeLifecycleActionView,
    BadgeHistoryView, BadgeCurrentAssignmentView,
)
from .views_sync import (
    AgentSyncStartView, AgentSyncItemsView, AgentSyncCompleteView,
    AgentSyncCancelView, AgentSyncStatusView,
    SyncBatchesListView, SyncConflictsListView, SyncConflictResolveView,
)
from .views_discovery import (
    AgentDiscoveryRegisterView, AgentScanCompleteView,
    DiscoveryListView, DiscoveryDetailView, DiscoveryActionView,
    DiscoveryScansListView,
)
from .views_agents import (
    AgentHeartbeatView, AgentLogsIngestView, AgentConfigPullView,
    AgentListView, AgentDetailView, AgentHeartbeatsListView,
    AgentLogsListView, AgentConfigsView, AgentConfigApplyView,
    AgentCommandView, AgentTypesListView,
)
from .views_enrollment import (
    EnrollmentStartView, EnrollmentStopView, EnrollmentConfirmView,
    EnrollmentSessionDetailView, EnrollmentIngestScanView,
    DeviceCommandCreateView, DeviceCommandDetailView, DeviceStatusView,
    AgentPullCommandsView, AgentEventView, AgentEventBatchView,
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
    # Auto-update + action result (Phase 2.3)
    path("edge-gateway/updates/check/",                         UpdateCheckView.as_view(),           name="edge-gateway-update-check"),
    path("edge-gateway/action-result/",                         ActionResultView.as_view(),          name="edge-gateway-action-result"),
    # Provisioning + supervision
    path("edge-gateway/",                                       GatewayListCreateView.as_view(),     name="edge-gateway-list"),
    path("edge-gateway/<int:gid>/",                             GatewayDetailView.as_view(),         name="edge-gateway-detail"),
    path("edge-gateway/<int:gid>/rotate-activation/",           GatewayRotateActivationView.as_view(), name="edge-gateway-rotate-activation"),
    path("edge-gateway/<int:gid>/pairing-qr.png",               GatewayPairingQrView.as_view(),      name="edge-gateway-qr"),
    path("edge-gateway/<int:gid>/revoke/",                      GatewayRevokeView.as_view(),         name="edge-gateway-revoke"),
    path("edge-gateway/<int:gid>/reactivate/",                  GatewayReactivateView.as_view(),     name="edge-gateway-reactivate"),
    # Actions
    path("edge-gateway/<int:gid>/restart/",                     GatewayRestartView.as_view(),        name="edge-gateway-restart"),
    path("edge-gateway/<int:gid>/force-sync/",                  GatewayForceSyncView.as_view(),      name="edge-gateway-force-sync"),
    path("edge-gateway/<int:gid>/scan-network/",                GatewayScanNetworkView.as_view(),    name="edge-gateway-scan"),
    path("edge-gateway/<int:gid>/update/",                      GatewayUpdateView.as_view(),         name="edge-gateway-update"),
    path("edge-gateway/<int:gid>/logs/",                        GatewayLogsView.as_view(),           name="edge-gateway-logs"),
    path("edge-gateway/<int:gid>/devices/",                     GatewayDevicesView.as_view(),        name="edge-gateway-devices"),
    # Download dynamique — génère un ZIP personnalisé par gateway/plateforme
    path("edge-gateway/<int:gid>/download/",                    GatewayDownloadPackageView.as_view(), name="edge-gateway-download"),
    # Résultats scan réseau depuis l'agent (auth HMAC)
    path("edge-gateway/<int:gid>/scan-results/",                GatewayScanResultsView.as_view(),    name="edge-gateway-scan-results"),
    # Fleet — vue agrégée de tous les targets du tenant
    path("edge-gateway/fleet/targets/",                         FleetTargetsView.as_view(),          name="edge-gateway-fleet-targets"),
    # Targets vendors (équipements pilotés par cette gateway)
    path("edge-gateway/<int:gid>/targets/",                     GatewayTargetsView.as_view(),        name="edge-gateway-targets"),
    path("edge-gateway/<int:gid>/targets/<int:tid>/",           GatewayTargetDetailView.as_view(),   name="edge-gateway-target-detail"),
    path("edge-gateway/<int:gid>/targets/<int:tid>/<str:action>/", GatewayTargetActionView.as_view(), name="edge-gateway-target-action"),

    # ═══ Agent local — Admin (provisioning + gestion) ═══
    path("local-agents/",                            LocalAgentListView.as_view(),        name="local-agent-list"),
    path("local-agents/<uuid:agent_id>/",            LocalAgentDetailView.as_view(),      name="local-agent-detail"),
    path("local-agents/<uuid:agent_id>/rotate-token/", LocalAgentRotateTokenView.as_view(), name="local-agent-rotate"),

    # ═══ Agent local (fallback HTTP polling) ═══
    path("agent/<uuid:agent_id>/commands/",          AgentPullCommandsView.as_view(),    name="agent-pull-commands"),
    path("agent/<uuid:agent_id>/events/",            AgentEventView.as_view(),           name="agent-events"),
    # Batch events (agent Go — pas d'agent_id dans path, HMAC identifie)
    path("agent/events/",                            AgentEventBatchView.as_view(),      name="agent-events-batch"),

    # Debug — dernières requêtes POST iclock/cdata (utile pour reverse-engineer un firmware inconnu)
    path("<int:pk>/iclock-debug/",                   DeviceIclockDebugView.as_view(),    name="device-iclock-debug"),
    # Debug global — dernières requêtes POST /pub/api (firmwares whitebox inconnus)
    path("pubapi-debug/",                            PubApiDebugView.as_view(),          name="pubapi-debug"),

    # ═══ Événements techniques (Phase 1 refonte — cahier des charges §1) ═══
    # Liste + filtres complets + pagination
    path("events/",                                    DeviceEventListView.as_view(),      name="events-list"),
    # Live view (avec URL WebSocket + stats 24h + limit initial)
    path("events/live/",                               DeviceEventLiveView.as_view(),      name="events-live"),
    # Nomenclature paramétrable
    path("events/types/",                              EventTypeCatalogView.as_view(),     name="events-types"),
    # Export CSV filtré (streamé)
    path("events/export.csv",                          DeviceEventExportView.as_view(),    name="events-export-csv"),
    # Détail événement + actions (acknowledge / resolve / comment)
    path("events/<uuid:event_id>/",                    DeviceEventDetailView.as_view(),    name="events-detail"),
    path("events/<uuid:event_id>/<str:action>/",       DeviceEventActionView.as_view(),    name="events-action"),

    # ═══ Cycle de vie badges (Phase 3 refonte — cahier §3.5) ═══
    path("badges/<uuid:badge_id>/assign/",             BadgeAssignView.as_view(),          name="badge-assign"),
    path("badges/<uuid:badge_id>/history/",            BadgeHistoryView.as_view(),         name="badge-history"),
    path("badges/<uuid:badge_id>/assignment/",         BadgeCurrentAssignmentView.as_view(), name="badge-current-assignment"),
    # Actions unitaires : unassign / suspend / resume / expire / report-lost /
    # report-stolen / disable / enable / revoke / destroy / archive
    path("badges/<uuid:badge_id>/<str:action>/",       BadgeLifecycleActionView.as_view(), name="badge-lifecycle-action"),

    # ═══ Edge Sync bidirectionnel (Phase 4 refonte — cahier §4.5) ═══
    # Agent (HMAC auth)
    path("edge/sync/batch/start/",                     AgentSyncStartView.as_view(),       name="edge-sync-start"),
    path("edge/sync/batch/<str:bid>/items/",           AgentSyncItemsView.as_view(),       name="edge-sync-items"),
    path("edge/sync/batch/<str:bid>/complete/",        AgentSyncCompleteView.as_view(),    name="edge-sync-complete"),
    path("edge/sync/batch/<str:bid>/cancel/",          AgentSyncCancelView.as_view(),      name="edge-sync-cancel"),
    path("edge/sync/batch/<str:bid>/status/",          AgentSyncStatusView.as_view(),      name="edge-sync-status"),
    # Admin (JWT auth)
    path("edge/gateways/<uuid:gid>/sync/batches/",     SyncBatchesListView.as_view(),      name="edge-sync-list-batches"),
    path("edge/sync/conflicts/",                       SyncConflictsListView.as_view(),    name="edge-sync-conflicts"),
    path("edge/sync/conflicts/<uuid:cid>/resolve/",    SyncConflictResolveView.as_view(),  name="edge-sync-resolve"),

    # ═══ Discovery équipements (Phase 5 refonte — cahier §2) ═══
    # Agent (HMAC)
    path("discovery/register/",                        AgentDiscoveryRegisterView.as_view(), name="discovery-register"),
    path("discovery/scan/<uuid:scan_id>/complete/",    AgentScanCompleteView.as_view(),      name="discovery-scan-complete"),
    # Admin (JWT)
    path("discovery/",                                 DiscoveryListView.as_view(),          name="discovery-list"),
    path("discovery/scans/",                           DiscoveryScansListView.as_view(),     name="discovery-scans-list"),
    path("discovery/<uuid:pk>/",                       DiscoveryDetailView.as_view(),        name="discovery-detail"),
    path("discovery/<uuid:pk>/<str:action>/",          DiscoveryActionView.as_view(),        name="discovery-action"),

    # ═══ Agents locaux (Phase 6 refonte — cahier §5) ═══
    # Agent (HMAC) — canal privilégié
    path("agents/heartbeat/",                          AgentHeartbeatView.as_view(),         name="agents-heartbeat"),
    path("agents/logs/",                               AgentLogsIngestView.as_view(),        name="agents-logs-ingest"),
    path("agents/config/",                             AgentConfigPullView.as_view(),        name="agents-config-pull"),
    # Admin (JWT)
    path("agents/types/",                              AgentTypesListView.as_view(),         name="agents-types"),
    path("agents/",                                    AgentListView.as_view(),              name="agents-list"),
    path("agents/<uuid:agent_id>/",                    AgentDetailView.as_view(),            name="agents-detail"),
    path("agents/<uuid:agent_id>/heartbeats/",         AgentHeartbeatsListView.as_view(),    name="agents-heartbeats"),
    path("agents/<uuid:agent_id>/logs/",               AgentLogsListView.as_view(),          name="agents-logs-list"),
    path("agents/<uuid:agent_id>/configs/",            AgentConfigsView.as_view(),           name="agents-configs"),
    path("agents/<uuid:agent_id>/configs/<int:version>/apply/",
                                                        AgentConfigApplyView.as_view(),      name="agents-configs-apply"),
    path("agents/<uuid:agent_id>/commands/<str:cmd>/", AgentCommandView.as_view(),           name="agents-command"),
] + router.urls
