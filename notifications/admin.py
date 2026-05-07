from django.contrib import admin

from .models import Notification, NotificationPreference, NotificationTemplate, WebSocketSubscription


@admin.register(NotificationTemplate)
class NotificationTemplateAdmin(admin.ModelAdmin):
    list_display = ("code", "channel", "subject", "is_active", "tenant")
    list_filter = ("channel", "is_active")


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("recipient", "channel", "status", "sent_at", "read_at")
    list_filter = ("channel", "status")


admin.site.register([NotificationPreference, WebSocketSubscription])
