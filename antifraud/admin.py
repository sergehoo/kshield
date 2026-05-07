from django.contrib import admin

from .models import BLEStillnessSignal, FraudAlert, FraudInvestigation, FraudRule, FraudScoring


@admin.register(FraudRule)
class FraudRuleAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "severity", "is_active", "tenant")
    list_filter = ("severity", "is_active", "tenant")


@admin.register(FraudAlert)
class FraudAlertAdmin(admin.ModelAdmin):
    list_display = ("rule", "site", "severity", "status", "raised_at", "assigned_to")
    list_filter = ("status", "severity", "site")
    date_hierarchy = "raised_at"


admin.site.register([FraudInvestigation, FraudScoring, BLEStillnessSignal])
