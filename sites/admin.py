from django.contrib import admin

from .models import Checkpoint, OpeningHours, Site, SitePolicy, Zone


@admin.register(Site)
class SiteAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "type", "status", "tenant", "company", "risk_level")
    list_filter = ("type", "status", "tenant", "company")
    search_fields = ("name", "code")


@admin.register(Zone)
class ZoneAdmin(admin.ModelAdmin):
    list_display = ("site", "name", "code", "parent", "is_restricted")
    list_filter = ("site", "is_restricted")


@admin.register(Checkpoint)
class CheckpointAdmin(admin.ModelAdmin):
    list_display = ("site", "name", "code", "type", "mode", "method", "is_active")
    list_filter = ("type", "mode", "method", "is_active")


@admin.register(OpeningHours)
class OpeningHoursAdmin(admin.ModelAdmin):
    list_display = ("site", "zone", "day_of_week", "open_time", "close_time", "is_closed")
    list_filter = ("day_of_week", "is_closed")


@admin.register(SitePolicy)
class SitePolicyAdmin(admin.ModelAdmin):
    list_display = ("site", "late_tolerance_minutes", "helmet_required", "badge_helmet_pairing_required")
