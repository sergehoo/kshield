from django.contrib import admin

from .models import AccessDecision, AccessEvent, AccessRule, DoorCommand, QRCodeToken


@admin.register(AccessEvent)
class AccessEventAdmin(admin.ModelAdmin):
    list_display = ("timestamp", "site", "badge_uid", "holder_kind", "decision", "method", "device")
    list_filter = ("decision", "method", "holder_kind", "site")
    search_fields = ("badge_uid", "helmet_uid")
    date_hierarchy = "timestamp"


@admin.register(AccessRule)
class AccessRuleAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "type", "severity", "site", "is_active")
    list_filter = ("type", "severity", "is_active", "site")
    search_fields = ("code", "name")


admin.site.register([AccessDecision, DoorCommand, QRCodeToken])
