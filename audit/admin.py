from django.contrib import admin

from .models import AuditLog, ConformityRegister, DataExportRequest, LegalRetentionPolicy


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("timestamp", "user", "action", "target_model", "target_id", "ip")
    list_filter = ("action", "target_model")
    search_fields = ("target_id", "user__email")
    date_hierarchy = "timestamp"


admin.site.register([DataExportRequest, LegalRetentionPolicy, ConformityRegister])
