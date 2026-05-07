from django.contrib import admin

from .models import (
    VisitLog, VisitPurpose, VisitRequest, Visitor, VisitorIDDocument,
    VisitorInvitation, VisitorPass, Watchlist,
)


@admin.register(Visitor)
class VisitorAdmin(admin.ModelAdmin):
    list_display = ("last_name", "first_name", "id_type", "id_number", "tenant", "created_at")
    list_filter = ("id_type", "tenant")
    search_fields = ("first_name", "last_name", "id_number", "phone")


@admin.register(VisitRequest)
class VisitRequestAdmin(admin.ModelAdmin):
    list_display = ("visitor", "site", "host_employee", "mode", "status", "scheduled_at")
    list_filter = ("status", "mode", "site")
    raw_id_fields = ("visitor", "host_employee")


admin.site.register([VisitPurpose, VisitorIDDocument, VisitorInvitation, VisitorPass, VisitLog, Watchlist])
