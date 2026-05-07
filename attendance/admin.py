from django.contrib import admin

from .models import (
    AttendanceCorrection, AttendanceDay, BLEPresencePing, BLEPresenceWindow,
    LeaveRequest, OvertimeCalculation, OvertimeRule, Punch, Roster,
)


@admin.register(Punch)
class PunchAdmin(admin.ModelAdmin):
    list_display = ("timestamp", "site", "type", "status", "holder_kind", "delay_minutes")
    list_filter = ("type", "status", "holder_kind", "site")
    date_hierarchy = "timestamp"


@admin.register(AttendanceDay)
class AttendanceDayAdmin(admin.ModelAdmin):
    list_display = ("date", "site", "holder_kind", "holder_object_id", "status", "duration_minutes", "incidents_count")
    list_filter = ("status", "site", "date")


admin.site.register([
    BLEPresencePing, BLEPresenceWindow, LeaveRequest, Roster,
    OvertimeRule, OvertimeCalculation, AttendanceCorrection,
])
