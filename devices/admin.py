from django.contrib import admin

from .models import (
    Badge, BadgeHelmetPairing, Device, DeviceHeartbeat, DeviceMaintenance,
    DeviceModel, EdgeGatewayPackage, FirmwareVersion, GatewayTarget, Helmet,
    LocalAgent, OTAUpdate,
    # Phase 1 refonte événements
    EventType, DeviceEvent, EventAcknowledgement,
    # Phase 3 refonte badges
    BadgeAssignment, BadgeLifecycleEvent,
    # Phase 4 refonte sync
    EdgeSyncBatch, EdgeSyncItem, EdgeSyncConflict,
    # Phase 5 refonte discovery
    DeviceDiscovery, DeviceDiscoveryScan,
    # Phase 6 refonte agents
    LocalAgentType, LocalAgentHeartbeat, LocalAgentConfiguration, LocalAgentLog,
)


@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    list_display = ("serial_number", "model", "site", "status", "last_heartbeat_at", "battery_level")
    list_filter = ("status", "model__type", "site")
    search_fields = ("serial_number",)


@admin.register(Badge)
class BadgeAdmin(admin.ModelAdmin):
    list_display = ("uid", "type", "status", "holder_kind", "issued_at", "expires_at")
    list_filter = ("type", "status", "holder_kind")
    search_fields = ("uid",)


@admin.register(Helmet)
class HelmetAdmin(admin.ModelAdmin):
    list_display = ("serial_number", "uhf_tag_uid", "ble_beacon_uid", "status", "current_worker")
    search_fields = ("serial_number", "uhf_tag_uid", "ble_beacon_uid")


@admin.register(BadgeHelmetPairing)
class PairingAdmin(admin.ModelAdmin):
    list_display = ("worker", "badge", "helmet", "site", "pairing_date", "is_broken", "verifications_count")
    list_filter = ("is_broken", "site", "pairing_date")
    raw_id_fields = ("worker", "badge", "helmet")


admin.site.register([DeviceModel, DeviceHeartbeat, DeviceMaintenance, FirmwareVersion, OTAUpdate])


@admin.register(EdgeGatewayPackage)
class EdgeGatewayPackageAdmin(admin.ModelAdmin):
    """Upload des binaires d'installation Kaydan Edge Gateway par plateforme.

    Après upload d'un fichier dans `file`, le SHA256 et la taille sont
    recalculés automatiquement au save (voir EdgeGatewayPackage.save()).
    """
    list_display = ("name", "platform", "version", "is_latest", "size_bytes",
                     "published_at")
    list_filter = ("platform", "is_latest")
    search_fields = ("name", "version", "checksum_sha256")
    readonly_fields = ("size_bytes", "checksum_sha256")
    fieldsets = (
        (None, {"fields": ("platform", "name", "version", "is_latest")}),
        ("Fichier / Docker", {"fields": ("file", "docker_image",
                                            "docker_compose_snippet")}),
        ("Métadonnées", {"fields": ("min_os_version", "release_notes",
                                       "published_at")}),
        ("Intégrité (auto)", {"fields": ("size_bytes", "checksum_sha256")}),
    )


class GatewayTargetInline(admin.TabularInline):
    """Édition inline des targets vendors depuis LocalAgent."""
    model = GatewayTarget
    extra = 0
    fields = ("label", "vendor", "ip", "port", "username", "connected",
               "events_count", "enabled")
    readonly_fields = ("connected", "events_count", "last_seen_at")


@admin.register(LocalAgent)
class LocalAgentAdmin(admin.ModelAdmin):
    list_display = ("label", "tenant", "site", "connected", "activated_at",
                     "last_seen_at", "revoked_at")
    list_filter = ("connected", "tenant", "site")
    search_fields = ("label", "api_token")
    readonly_fields = ("api_token", "hmac_secret", "activation_token",
                        "activation_expires_at", "activated_at", "channel_name")
    inlines = [GatewayTargetInline]


@admin.register(GatewayTarget)
class GatewayTargetAdmin(admin.ModelAdmin):
    list_display = ("label", "vendor", "ip", "port", "gateway",
                     "connected", "events_count", "enabled", "last_seen_at")
    list_filter = ("vendor", "enabled", "connected")
    search_fields = ("label", "ip", "serial_number", "mac")
    readonly_fields = ("connected", "last_seen_at", "events_count", "last_error",
                        "firmware", "created_at", "updated_at")


# ═══════════════════════════════════════════════════════════════════
# Phase 1 refonte événements — nomenclature + traçabilité
# ═══════════════════════════════════════════════════════════════════
@admin.register(EventType)
class EventTypeAdmin(admin.ModelAdmin):
    list_display = ("code", "category", "label", "severity_default",
                     "result_default", "triggers_alert", "requires_ack",
                     "is_active", "is_system")
    list_filter = ("category", "severity_default", "triggers_alert",
                    "requires_ack", "is_active", "is_system")
    search_fields = ("code", "label", "description")
    readonly_fields = ("is_system", "created_at", "updated_at")
    fieldsets = (
        ("Identification", {
            "fields": ("code", "category", "label", "description"),
        }),
        ("Défauts (surchargeables au runtime)", {
            "fields": ("severity_default", "result_default", "icon", "color"),
        }),
        ("Comportement", {
            "fields": ("triggers_alert", "requires_ack", "is_active"),
        }),
        ("Système", {
            "fields": ("is_system", "created_at", "updated_at"),
            "classes": ("collapse",),
        }),
    )


class EventAcknowledgementInline(admin.TabularInline):
    """Historique immutable des acks affiché dans DeviceEvent detail."""
    model = EventAcknowledgement
    extra = 0
    fields = ("action", "user", "notes", "evidence_url", "created_at")
    readonly_fields = ("action", "user", "notes", "evidence_url", "created_at")

    def has_add_permission(self, request, obj=None):
        return False   # acks créés uniquement via API

    def has_delete_permission(self, request, obj=None):
        return False   # immutable


@admin.register(DeviceEvent)
class DeviceEventAdmin(admin.ModelAdmin):
    list_display = ("occurred_at", "event_type", "site", "device", "gateway",
                     "severity", "result", "transmission_mode", "is_offline")
    list_filter = ("event_type__category", "severity", "result",
                    "transmission_mode", "is_offline", "is_synced")
    search_fields = ("badge_uid", "helmet_uid", "holder_ref", "message",
                      "event_type__code", "idempotency_key")
    readonly_fields = ("id", "received_at", "idempotency_key",
                        "sync_batch_id", "access_event")
    date_hierarchy = "occurred_at"
    inlines = [EventAcknowledgementInline]
    raw_id_fields = ("device", "gateway", "agent", "site", "zone",
                      "checkpoint", "access_event")


@admin.register(EventAcknowledgement)
class EventAcknowledgementAdmin(admin.ModelAdmin):
    list_display = ("created_at", "action", "user", "event")
    list_filter = ("action",)
    search_fields = ("event__event_type__code", "user__email", "notes")
    readonly_fields = ("event", "action", "user", "notes",
                        "evidence_url", "created_at")
    raw_id_fields = ("event", "user")


# ═══════════════════════════════════════════════════════════════════
# Phase 3 refonte badges — cycle de vie complet
# ═══════════════════════════════════════════════════════════════════
class BadgeLifecycleEventInline(admin.TabularInline):
    model = BadgeLifecycleEvent
    extra = 0
    fields = ("created_at", "from_status", "to_status", "reason", "performed_by")
    readonly_fields = ("created_at", "from_status", "to_status", "reason",
                        "performed_by")

    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(BadgeAssignment)
class BadgeAssignmentAdmin(admin.ModelAdmin):
    list_display = ("badge", "holder_kind", "holder_label", "site",
                     "access_level", "assigned_at", "expires_at",
                     "is_active_display")
    list_filter = ("holder_kind", "access_level", "closed_at", "site",
                    "is_permanent")
    search_fields = ("badge__uid", "holder_label", "reason")
    readonly_fields = ("id", "assigned_at", "closed_at",
                        "assigned_by", "validated_by", "closed_by")
    raw_id_fields = ("badge", "tenant", "site", "assigned_by",
                      "validated_by", "closed_by")
    filter_horizontal = ("zones",)
    date_hierarchy = "assigned_at"

    def is_active_display(self, obj):
        return "✓ Active" if obj.closed_at is None else f"Fermée ({obj.close_reason})"
    is_active_display.short_description = "État"


@admin.register(BadgeLifecycleEvent)
class BadgeLifecycleEventAdmin(admin.ModelAdmin):
    list_display = ("created_at", "badge", "from_status", "to_status",
                     "reason", "performed_by")
    list_filter = ("to_status", "from_status")
    search_fields = ("badge__uid", "reason")
    readonly_fields = ("id", "badge", "from_status", "to_status",
                        "reason", "performed_by", "metadata", "created_at")
    raw_id_fields = ("badge", "performed_by")


# ═══════════════════════════════════════════════════════════════════
# Phase 4 refonte Edge Sync
# ═══════════════════════════════════════════════════════════════════
class EdgeSyncItemInline(admin.TabularInline):
    model = EdgeSyncItem
    extra = 0
    fields = ("entity_type", "entity_key", "status", "payload_hash", "error")
    readonly_fields = ("entity_type", "entity_key", "status",
                        "payload_hash", "error", "received_at", "processed_at")

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(EdgeSyncBatch)
class EdgeSyncBatchAdmin(admin.ModelAdmin):
    list_display = ("batch_id_short", "gateway", "direction", "priority",
                     "status", "items_declared", "items_succeeded",
                     "items_failed", "items_conflicted",
                     "started_at", "duration_ms")
    list_filter = ("status", "direction", "priority")
    search_fields = ("batch_id", "gateway__label")
    readonly_fields = ("id", "batch_id", "started_at", "upload_finished_at",
                        "processed_at", "duration_ms",
                        "checksum_declared", "checksum_computed",
                        "items_uploaded", "items_processed",
                        "items_succeeded", "items_failed",
                        "items_conflicted")
    raw_id_fields = ("gateway", "tenant")
    date_hierarchy = "started_at"
    inlines = [EdgeSyncItemInline]

    def batch_id_short(self, obj):
        return obj.batch_id[:16] + ("…" if len(obj.batch_id) > 16 else "")
    batch_id_short.short_description = "Batch ID"


@admin.register(EdgeSyncConflict)
class EdgeSyncConflictAdmin(admin.ModelAdmin):
    list_display = ("entity_type", "entity_key", "resolution",
                     "edge_version", "cloud_version", "resolved_by",
                     "resolved_at", "created_at")
    list_filter = ("resolution", "entity_type")
    search_fields = ("entity_key", "resolution_notes")
    readonly_fields = ("id", "batch", "item", "tenant", "entity_type",
                        "entity_key", "edge_payload", "cloud_payload",
                        "edge_version", "cloud_version",
                        "edge_updated_at", "cloud_updated_at",
                        "created_at", "updated_at")
    raw_id_fields = ("batch", "item", "tenant", "resolved_by")


# ═══════════════════════════════════════════════════════════════════
# Phase 5 refonte Discovery
# ═══════════════════════════════════════════════════════════════════
@admin.register(DeviceDiscoveryScan)
class DeviceDiscoveryScanAdmin(admin.ModelAdmin):
    list_display = ("created_at", "gateway", "status", "devices_detected",
                     "devices_new", "duration_ms", "protocols_used")
    list_filter = ("status",)
    readonly_fields = ("id", "created_at", "updated_at", "duration_ms",
                        "devices_detected", "devices_new", "devices_updated")
    raw_id_fields = ("tenant", "gateway", "site")
    date_hierarchy = "created_at"


@admin.register(DeviceDiscovery)
class DeviceDiscoveryAdmin(admin.ModelAdmin):
    list_display = ("last_seen_at", "mac_address", "ip_address", "vendor",
                     "model", "device_type", "status", "compatibility",
                     "suggested_driver", "times_seen")
    list_filter = ("status", "compatibility", "detected_via",
                    "vendor", "device_type")
    search_fields = ("mac_address", "ip_address", "hostname",
                      "serial_number", "vendor", "model")
    readonly_fields = ("id", "first_seen_at", "last_seen_at", "times_seen",
                        "last_test_at", "last_test_success", "last_test_error",
                        "last_test_response", "adopted_at", "adopted_by",
                        "rejected_at", "adopted_device")
    raw_id_fields = ("tenant", "gateway", "site", "scan", "adopted_device")
    date_hierarchy = "last_seen_at"
    actions = ["mark_stale"]

    def mark_stale(self, request, queryset):
        count = queryset.update(status="stale")
        self.message_user(request, f"{count} découvertes marquées stale")
    mark_stale.short_description = "Marquer comme périmées (stale)"


# ═══════════════════════════════════════════════════════════════════
# Phase 6 refonte Agents locaux
# ═══════════════════════════════════════════════════════════════════
@admin.register(LocalAgentType)
class LocalAgentTypeAdmin(admin.ModelAdmin):
    list_display = ("code", "label", "module_name", "is_active", "is_system")
    list_filter = ("is_active", "is_system")
    search_fields = ("code", "label", "description")
    readonly_fields = ("is_system", "created_at", "updated_at")


@admin.register(LocalAgentHeartbeat)
class LocalAgentHeartbeatAdmin(admin.ModelAdmin):
    list_display = ("received_at", "agent", "state", "version",
                     "cpu_percent", "memory_percent", "storage_percent",
                     "events_pending", "errors_last_hour")
    list_filter = ("state", "version")
    search_fields = ("agent__label",)
    readonly_fields = ("id", "sent_at", "received_at", "state", "version",
                        "uptime_seconds", "cpu_percent", "memory_percent",
                        "memory_mb", "storage_percent", "storage_free_mb",
                        "network_latency_ms", "events_processed",
                        "events_pending", "devices_connected",
                        "devices_expected", "errors_last_hour",
                        "sync_last_success_at", "recent_errors", "metadata")
    raw_id_fields = ("agent", "tenant")
    date_hierarchy = "received_at"


@admin.register(LocalAgentConfiguration)
class LocalAgentConfigurationAdmin(admin.ModelAdmin):
    list_display = ("agent", "version", "is_current", "is_draft",
                     "applied_at", "created_at")
    list_filter = ("is_current", "is_draft")
    search_fields = ("agent__label", "checksum", "notes")
    readonly_fields = ("id", "version", "checksum", "applied_at",
                        "created_at", "updated_at")
    raw_id_fields = ("agent",)


@admin.register(LocalAgentLog)
class LocalAgentLogAdmin(admin.ModelAdmin):
    list_display = ("ts", "agent", "level", "source", "message_short")
    list_filter = ("level", "source")
    search_fields = ("agent__label", "message", "source")
    readonly_fields = ("id", "agent", "ts", "level", "message",
                        "context", "source", "created_at")
    raw_id_fields = ("agent",)
    date_hierarchy = "ts"

    def message_short(self, obj):
        return obj.message[:100] + ("…" if len(obj.message) > 100 else "")
    message_short.short_description = "Message"
