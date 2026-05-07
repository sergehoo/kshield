from django.contrib import admin

from .models import (
    Badge, BadgeHelmetPairing, Device, DeviceHeartbeat, DeviceMaintenance,
    DeviceModel, FirmwareVersion, Helmet, OTAUpdate,
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
