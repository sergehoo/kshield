from django.contrib import admin

from .models import MobileBundle, MobileDevice, OfflineScanQueue, SyncSession


@admin.register(MobileDevice)
class MobileDeviceAdmin(admin.ModelAdmin):
    list_display = ("device_id", "name", "user", "site", "status", "last_sync_at")
    list_filter = ("os", "status", "site")
    search_fields = ("device_id", "name")


admin.site.register([OfflineScanQueue, SyncSession, MobileBundle])
