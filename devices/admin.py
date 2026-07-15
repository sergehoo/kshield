from django.contrib import admin

from .models import (
    Badge, BadgeHelmetPairing, Device, DeviceHeartbeat, DeviceMaintenance,
    DeviceModel, EdgeGatewayPackage, FirmwareVersion, GatewayTarget, Helmet,
    LocalAgent, OTAUpdate,
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
