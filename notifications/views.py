from django.utils import timezone
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Notification, NotificationPreference, NotificationTemplate, WebSocketSubscription
from .serializers import (
    NotificationPreferenceSerializer, NotificationSerializer,
    NotificationTemplateSerializer, WebSocketSubscriptionSerializer,
)


class NotificationTemplateViewSet(viewsets.ModelViewSet):
    queryset = NotificationTemplate.objects.all(); serializer_class = NotificationTemplateSerializer
    filterset_fields = ("tenant", "channel", "is_active")
    search_fields = ("code", "subject")


class NotificationPreferenceViewSet(viewsets.ModelViewSet):
    queryset = NotificationPreference.objects.all(); serializer_class = NotificationPreferenceSerializer
    filterset_fields = ("user", "channel", "template_code", "is_enabled")


class NotificationViewSet(viewsets.ModelViewSet):
    queryset = Notification.objects.all(); serializer_class = NotificationSerializer
    filterset_fields = ("tenant", "recipient", "channel", "status")

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.user.is_authenticated and not self.request.user.is_staff:
            qs = qs.filter(recipient=self.request.user)
        return qs

    @action(detail=True, methods=["post"], url_path="mark-read")
    def mark_read(self, request, pk=None):
        notif = self.get_object()
        notif.read_at = timezone.now()
        notif.status = "read"
        notif.save(update_fields=["read_at", "status"])
        return Response(NotificationSerializer(notif).data)


class WebSocketSubscriptionViewSet(viewsets.ModelViewSet):
    queryset = WebSocketSubscription.objects.all(); serializer_class = WebSocketSubscriptionSerializer
    filterset_fields = ("user", "topic")
